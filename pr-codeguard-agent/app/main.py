import asyncio
import logging
import os
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import webhook, results, tasks, config_routes, reports, knowledge, discovery, alerts, scan_strategy, chat, system_hooks, tf_plan_webhook, events_webhook, query, scan, auth, audit, settings as settings_route, health, email as email_route
from app.services.storage import StorageService, UserRecord
from app.config import settings

logger = logging.getLogger(__name__)

storage = StorageService()
knowledge_base: "KnowledgeBase | None" = None


async def init_default_admin():
    """Initialize default admin user if not exists."""
    try:
        from app.services.auth_service import hash_password
        s = StorageService()
        existing = await s.get_user_by_username("admin")
        if not existing:
            import uuid
            record = UserRecord(
                id=uuid.uuid4().hex[:12],
                username="admin",
                password_hash=hash_password("admin123"),
                role="admin",
            )
            await s.save_user(record)
            logger.info("Default admin user created (admin/admin123)")
    except Exception as e:
        logger.warning("Failed to init default admin user: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and knowledge base on startup."""
    await storage.init_db()

    # Initialize default admin user
    await init_default_admin()

    # Initialize knowledge base if enabled
    global knowledge_base
    if settings.knowledge_enabled:
        from app.knowledge.knowledge_base import KnowledgeBase
        kb = KnowledgeBase(
            db_path=settings.knowledge_db_path,
            chroma_dir=settings.chroma_persist_dir,
        )
        kb.init()
        knowledge_base = kb
        app.state.knowledge_base = kb
        app.state.kb = kb  # short alias

    # Initialize discovery service (auto-register webhooks on startup)
    if settings.gitlab_api_token and settings.auto_discovery_enabled:
        from app.services.discovery_service import DiscoveryService
        discovery_svc = DiscoveryService()
        discovery_svc.set_agent_url(settings.host, settings.port)
        app.state.discovery_service = discovery_svc

        try:
            loop = asyncio.get_event_loop()
            projects = await loop.run_in_executor(None, discovery_svc.scan_all)
            logger.info(
                "Auto-discovery: found %d projects from GitLab",
                len(projects),
            )

            stats = await loop.run_in_executor(None, discovery_svc.ensure_webhooks)
            logger.info("Auto-discovery webhooks: %s", stats)
        except Exception as e:
            logger.warning("Auto-discovery failed (non-fatal): %s", e)
    else:
        logger.info(
            "Auto-discovery disabled (token=%s, enabled=%s)",
            bool(settings.gitlab_api_token),
            settings.auto_discovery_enabled,
        )
        # Provide a minimal placeholder so API doesn't 503
        from app.services.discovery_service import DiscoveryService
        app.state.discovery_service = DiscoveryService()

    # Initialize alert service
    if settings.alert_enabled:
        from app.services.alert_service import AlertService
        alert_svc = AlertService()
        app.state.alert_service = alert_svc
        if not alert_svc.is_configured:
            logger.info("Alert service initialized (no channels configured)")
        else:
            logger.info("Alert service initialized with %d channel(s)", len(alert_svc._channels))

    # Initialize scan strategy manager
    from app.services.scan_strategy import ScanStrategyManager
    strategy_mgr = ScanStrategyManager(db_path=settings.knowledge_db_path)
    app.state.scan_strategy_manager = strategy_mgr
    logger.info("Scan strategy manager initialized")

    # Initialize webhook health checker (with periodic background task)
    from app.services.webhook_health import WebhookHealthChecker
    health_checker = WebhookHealthChecker()
    app.state.webhook_health_checker = health_checker

    async def _periodic_webhook_health_check():
        """Check webhook health every 30 minutes."""
        discovery_svc = getattr(app.state, "discovery_service", None)
        if not discovery_svc:
            logger.info("Webhook health: no discovery service, skipping periodic check")
            return

        while True:
            try:
                await asyncio.sleep(1800)  # 30 minutes
                projects = discovery_svc.list_discovered()
                if projects and health_checker:
                    loop = asyncio.get_event_loop()
                    results = await loop.run_in_executor(
                        None, health_checker.check_all, projects
                    )
                    healthy = sum(1 for r in results if r.healthy)
                    auto_fixed = sum(1 for r in results if r.auto_fixed)
                    if auto_fixed > 0:
                        logger.info(
                            "Periodic webhook health: %d/%d healthy, %d auto-fixed",
                            healthy, len(results), auto_fixed,
                        )
                    else:
                        logger.debug(
                            "Periodic webhook health: %d/%d healthy",
                            healthy, len(results),
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Periodic webhook health check error: %s", e)

    # Check Trivy health on startup
    from app.engine.trivy_scanner import find_trivy
    trivy_path = find_trivy()
    if trivy_path:
        logger.info("Trivy binary found: %s", trivy_path)
        trivy_cache = os.path.abspath(settings.trivy_cache_dir)
        db_file = os.path.join(trivy_cache, "db", "trivy.db")
        if os.path.isfile(db_file):
            logger.info("Trivy DB found: %s (%d KB)", db_file, os.path.getsize(db_file) // 1024)
        else:
            logger.warning("Trivy DB not found at %s", db_file)
    else:
        logger.warning("Trivy binary not found - scans will be skipped")

    # Start background task
    health_task = asyncio.create_task(_periodic_webhook_health_check())

    # ------------------------------------------------------------------
    # Periodic project sync (detect new/deleted projects every 5 minutes)
    # ------------------------------------------------------------------

    async def _periodic_project_sync():
        """Sync project list from GitLab every 5 minutes."""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                svc = getattr(app.state, "discovery_service", None)
                if svc:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, svc.sync_with_gitlab)
                    if result["added"] > 0 or result["removed"] > 0:
                        logger.info(
                            "Periodic project sync: +%d/-%d (total=%d)",
                            result["added"], result["removed"], result["total_after"],
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Periodic project sync error: %s", e, exc_info=True)

    sync_task = asyncio.create_task(_periodic_project_sync())

    # Start email scheduler if SMTP is configured
    email_scheduler = None
    if settings.alert_smtp_host and settings.alert_email_to:
        from app.services.email_scheduler import EmailScheduler
        email_scheduler = EmailScheduler()
        await email_scheduler.start()
        app.state.email_scheduler = email_scheduler
        logger.info("Email scheduler started (SMTP: %s)", settings.alert_smtp_host)
    else:
        logger.info(
            "Email scheduler disabled (SMTP host=%s, email_to=%s)",
            bool(settings.alert_smtp_host),
            bool(settings.alert_email_to),
        )

    # ------------------------------------------------------------------
    # Periodic auto-scan (every day at configured time)
    # ------------------------------------------------------------------
    auto_scan_task = None
    if settings.auto_scan_enabled:
        auto_scan_time = settings.auto_scan_time  # e.g. "02:00"

        async def _periodic_auto_scan():
            while True:
                now = datetime.now(datetime.UTC)
                hour, minute = auto_scan_time.split(":")
                target = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
                if now >= target:
                    target = target + timedelta(days=1)

                sleep_seconds = (target - now).total_seconds()
                logger.info(
                    "Next auto scan scheduled at %s (in %.0f seconds)",
                    target.isoformat(), sleep_seconds,
                )
                await asyncio.sleep(sleep_seconds)

                try:
                    from app.services.discovery_service import DiscoveryService
                    from app.services.orchestrator import Orchestrator
                    from app.services.storage import StorageService
                    from app.models.task import ScanTask
                    from app.utils.helpers import generate_task_id
                    from datetime import datetime as _dt

                    discovery = DiscoveryService()
                    projects = discovery.list_discovered()
                    if not projects:
                        discovery.scan_all()
                        projects = discovery.list_discovered()

                    if not projects:
                        logger.info("Auto scan: no projects discovered, skipping")
                        continue

                    storage = StorageService()
                    orchestrator = Orchestrator()
                    scanned = 0
                    for proj in projects:
                        repo_url = proj.get("http_url_to_repo", "") if isinstance(proj, dict) else getattr(proj, "http_url_to_repo", "")
                        default_branch = proj.get("default_branch", "main") if isinstance(proj, dict) else getattr(proj, "default_branch", "main")
                        if not repo_url:
                            continue
                        try:
                            task = ScanTask(
                                id=generate_task_id(),
                                repo_url=repo_url,
                                mr_id=0,
                                mr_title="Scheduled scan",
                                source_branch=default_branch,
                                status="pending",
                                created_at=_dt.utcnow(),
                            )
                            await storage.save_task(task)
                            result = await orchestrator.run_scan(
                                task=task, source_branch=default_branch,
                                target_branch=default_branch,
                                ai_enabled=False, tf_change_detection=False,
                            )
                            await storage.save_task(result)
                            scanned += 1
                        except Exception as e:
                            logger.error("Auto scan failed for %s: %s", repo_url, e)

                    logger.info("Auto scan complete: %d projects scanned", scanned)
                except Exception as e:
                    logger.error("Auto scan task failed: %s", e)

        auto_scan_task = asyncio.create_task(_periodic_auto_scan())
        logger.info("Auto scan enabled, scheduled at %s daily", auto_scan_time)
    else:
        logger.info("Auto scan disabled")

    yield

    # Cleanup
    health_task.cancel()
    sync_task.cancel()
    if email_scheduler:
        await email_scheduler.stop()
    if auto_scan_task:
        auto_scan_task.cancel()


app = FastAPI(
    title="PR-CodeGuard Agent",
    description="Automated code review agent for Merge Requests",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook.router)
app.include_router(results.router)
app.include_router(tasks.router)
app.include_router(config_routes.router)
app.include_router(reports.router)
app.include_router(knowledge.router)
app.include_router(discovery.router)
app.include_router(alerts.router)
app.include_router(scan_strategy.router)
app.include_router(chat.router)
app.include_router(system_hooks.router)
app.include_router(tf_plan_webhook.router)
app.include_router(events_webhook.router)
app.include_router(query.router)
app.include_router(scan.router)
app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(settings_route.router)
app.include_router(health.router)
app.include_router(email_route.router)


@app.get("/health")
async def health():
    """Health check endpoint with Trivy status."""
    from app.engine.trivy_scanner import find_trivy
    trivy_path = find_trivy()
    trivy_info = {
        "available": trivy_path is not None,
        "path": trivy_path or "",
    }
    if trivy_path:
        trivy_cache = os.path.abspath(settings.trivy_cache_dir)
        db_file = os.path.join(trivy_cache, "db", "trivy.db")
        trivy_info["db_ok"] = os.path.isfile(db_file)
        trivy_info["cache_dir"] = trivy_cache

    return {
        "status": "ok",
        "trivy": trivy_info,
    }


# ---------------------------------------------------------------------------
# Serve frontend static files (optional)
# If frontend/dist exists, serve it at / and provide SPA fallback.
# ---------------------------------------------------------------------------
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(_frontend_dir):
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dir, "assets")), name="frontend_assets")

    # SPA catch-all: return index.html for all non-API routes
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Do not intercept API routes
        if full_path.startswith("api/") or full_path == "health":
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        index_path = os.path.join(_frontend_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path, media_type="text/html")
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    logger.info("Frontend static files mounted from %s", _frontend_dir)
else:
    logger.info("Frontend dist not found at %s, dashboard UI unavailable", _frontend_dir)

# Serve query.html directly (Phase 2 Q&A frontend)
_query_html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "query.html")
if os.path.isfile(_query_html):
    from fastapi.responses import FileResponse

    @app.get("/query")
    async def serve_query_page():
        return FileResponse(_query_html, media_type="text/html")
    logger.info("Query page mounted from %s", _query_html)
