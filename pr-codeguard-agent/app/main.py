import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import webhook, results, tasks, config_routes, reports, knowledge, discovery, alerts, scan_strategy, chat
from app.services.storage import StorageService
from app.config import settings

logger = logging.getLogger(__name__)

storage = StorageService()
knowledge_base: "KnowledgeBase | None" = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and knowledge base on startup."""
    await storage.init_db()

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

    # Start background task
    health_task = asyncio.create_task(_periodic_webhook_health_check())

    yield

    # Cleanup
    health_task.cancel()


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


@app.get("/health")
async def health():
    return {"status": "ok"}


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
