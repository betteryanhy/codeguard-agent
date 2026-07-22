"""Chat API - conversational agent interface for users."""

import json
import logging
import asyncio
import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.scan_strategy import ScanStrategyManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# ── System Prompt ────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """你是 PR-CodeGuard Agent 的专业助手，回答 GitLab 项目安全扫描相关的问题。

规则：
- 用中文回答，**直接给答案，不加"根据数据"、"基于信息"等前缀**
- **不要输出建议性文字**（如"建议到 Dashboard 查看"、"请联系管理员"、"可能原因"等）
- 如果工具没有返回有效数据，直接说"暂无数据"即可，不要解释原因
- **当 search_knowledge 工具返回结果时，必须如实报告找到的内容**，特别是标记为 critical/high 安全风险的结果必须明确提及
- 如果搜索结果中包含 RDS、database、数据库相关的删除/修改风险，请明确指出这是高危操作
- 给出具体数字，不要模糊表述
- 回答不超过 3 句话，除非需要列举数据
- **注意区分开发者姓名**，如"tester"和"IAC Tester"是不同的人，不要混淆
- **结合对话历史理解用户意图**。例如用户先问"有几个项目"，再问"分别是什么功能"，应回答项目各自的功能描述，而不是 MR 合并功能
- **当项目描述为空时，根据项目名称推断用途**（如 vuln-app 可能是安全测试项目、iac-terraform 是基础设施即代码项目等）

可用的数据和功能：
1. 项目列表（ID、名称、可见性）
2. 日报数据（MR 数量、提交、开发者、风险）
3. 趋势数据（按周/月的风险和活动）
4. 扫描策略（全局默认 + 仓库级覆盖）
5. 知识库搜索（MR 和代码的语义搜索，可搜漏洞/安全风险）
6. 告警状态（通道和阈值）
7. **开发者统计**（各开发者的提交次数、代码行数、涉及项目）
8. **开发者提交明细**（指定开发者的所有提交记录）
9. **已合并功能**（已合并的 MR 及其功能描述）
10. **安全扫描结果**（通过知识库搜索漏洞和安全风险）
11. **扫描任务查询**（最近扫描任务、扫描发现、各仓库扫描状态）
12. **风险记录查询**（按仓库/严重度查询扫描发现的风险项）

当前时间：{current_time}
"""


class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict] = []
    tool_results: dict[str, str] = {}  # Added for debugging


# ── Context Builder ──────────────────────────────────────────────


def _build_context(app_state=None) -> str:
    """Build a compact context snapshot from available data."""
    from app.main import knowledge_base
    parts = []

    # Project discovery (with descriptions)
    if app_state:
        try:
            discovery_svc = getattr(app_state, "discovery_service", None)
            if discovery_svc:
                projects = discovery_svc.list_discovered()
                if projects:
                    parts.append(f"已发现 GitLab 项目数：{len(projects)}")
                    for p in projects[:10]:
                        desc = p.get('description', '') or ''
                        name = p.get('name_with_namespace', '')
                        url = p.get('http_url_to_repo', '')
                        if desc:
                            parts.append(f"- {name}: {desc[:100]}")
                        else:
                            parts.append(f"- {name}")
        except Exception:
            pass

    # Knowledge summary
    if knowledge_base:
        try:
            recent_mrs = knowledge_base.get_mr_records("", limit=3)
            if recent_mrs:
                parts.append("最近 MR 记录：")
                for r in recent_mrs:
                    parts.append(f"- !{r.mr_id} {r.mr_title} ({r.author or 'unknown'})")
        except Exception:
            pass

    # Strategy summary
    try:
        mgr = ScanStrategyManager()
        strategies = mgr.list_strategies()
        if strategies:
            parts.append(f"已配置策略数：{len(strategies)}")
            for s in strategies:
                if s.is_default():
                    parts.append(f"- 默认策略: {s.scan_level} (ai={s.ai_enabled})")
    except Exception:
        pass

    # Recent scan task overview (via HTTP call to own API - non-blocking)
    try:
        import httpx
        with httpx.Client(timeout=5) as client:
            stats_resp = client.get("http://127.0.0.1:8082/api/v1/tasks/stats")
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                parts.append(f"扫描统计：共{stats.get('total',0)}个任务，今日{stats.get('today_scans',0)}次扫描")
            tasks_resp = client.get("http://127.0.0.1:8082/api/v1/tasks/", params={"skip": 0, "limit": 10})
            if tasks_resp.status_code == 200:
                tasks = tasks_resp.json()
                if isinstance(tasks, list):
                    with_findings = [t for t in tasks if t.get("total_findings", 0) > 0]
                    if with_findings:
                        parts.append(f"有发现的任务：{len(with_findings)}个")
                        for t in with_findings[:5]:
                            repo = t.get("repo_url", "").split("/")[-1].replace(".git", "")
                            parts.append(f"  - {repo}: {t['total_findings']}个发现")
    except Exception:
        pass

    return "\n".join(parts) if parts else "(暂无上下文数据)"


# ── Intent detection ─────────────────────────────────────────────


def _conversation_was_about_projects(history: list[ChatMessage]) -> bool:
    """Check if recent conversation history was about GitLab projects."""
    for msg in history[-3:]:  # Check last 3 messages
        content = (msg.content or "").lower()
        if any(kw in content for kw in ["项目", "project", "仓库", "repo", "gitlab 上有"]):
            return True
    return False


def _detect_tool_intent(message: str, history: list[ChatMessage] | None = None) -> list[dict]:
    """Detect if the user wants to execute specific tools based on keywords."""
    tools = []
    msg_lower = message.lower()
    history = history or []

    # Report / daily report (including time-based queries)
    if any(kw in msg_lower for kw in [
        "日报", "daily", "今天的报告", "报告", "报表",
        "昨天", "今天", "本周", "上周", "昨日", "今日",
    ]):
        tools.append({"tool": "get_daily_report", "params": {}})

    # Trends
    if any(kw in msg_lower for kw in ["趋势", "trend", "走势", "变化"]):
        tools.append({"tool": "get_trends", "params": {"period": "weekly", "count": 8}})

    # Knowledge search (also used for security findings / vulnerabilities)
    if any(kw in msg_lower for kw in [
        "搜索", "查找", "查询", "search", "find", "知识库",
        "扫描结果", "扫描发现", "漏洞", "安全风险", "安全隐患",
        "风险", "危险", "安全问题", "有什么 mr", "有什么问题",
        "mr !", "mr #", "看下", "看看", "检查",
    ]):
        tools.append({"tool": "search_knowledge", "params": {"query": message}})

    # Scan strategy
    if any(kw in msg_lower for kw in ["策略", "strategy", "配置", "引擎", "扫描等级"]):
        tools.append({"tool": "get_default_strategy", "params": {}})

    # Alert status
    if any(kw in msg_lower for kw in ["告警", "alert", "通知", "报警"]):
        tools.append({"tool": "get_alert_status", "params": {}})

    # List discovered projects
    if any(kw in msg_lower for kw in ["项目", "project", "仓库", "repo", "gitlab", "发现", "已发现"]):
        tools.append({"tool": "list_discovered_projects", "params": {}})

    # Developer stats / comparison / ranking
    if any(kw in msg_lower for kw in [
        "开发者", "开发人员", "提交次数", "代码量", "对比",
        "developer", "committer", "contributor",
        "谁提交", "哪个开发", "最多", "最少", "谁最", "谁多", "谁少",
    ]):
        tools.append({"tool": "get_developer_stats", "params": {}})

    # Developer commits - detailed commits by a specific person
    known_developers = sorted(["henry yan", "yanhaoyu", "demo user", "tester", "iac tester"], key=len, reverse=True)

    # If question has multiple names separated by 和/、/vs, don't match specific author
    has_multiple_names = False
    msg_has_separator = any(sep in msg_lower for sep in [" 和 ", "、", " vs ", "对比"])
    if msg_has_separator:
        name_count = sum(1 for name in known_developers if name in msg_lower)
        has_multiple_names = name_count >= 2

    found_author = None
    if not has_multiple_names:
        for name in known_developers:
            if name in msg_lower:
                found_author = name
                break

    if found_author or any(kw in msg_lower for kw in ["提交了", "做了什么", "commit", "提交"]):
        params = {}
        if found_author and not has_multiple_names:
            params["author"] = found_author
        tools.append({"tool": "get_developer_stats", "params": params})

    # Merged features - what features were shipped / recent project changes
    # If conversation was about projects, "功能" means project functions, not MR features
    was_about_projects = _conversation_was_about_projects(history)
    if not was_about_projects and any(kw in msg_lower for kw in [
        "功能", "feature", "上线", "合并", "merge",
        "发布了", "更新了", "变更", "最近", "改动", "修改", "变化",
    ]):
        tools.append({"tool": "get_merged_features", "params": {}})

    # Project-specific MR queries
    if any(kw in msg_lower for kw in ["有什么 mr", "有什么合并", "最近 mr", "mr 列表", "合并请求", "项目的 mr"]):
        tools.append({"tool": "get_merged_features", "params": {}})

    # Scan tasks / recently scanned / security findings from scans
    if any(kw in msg_lower for kw in [
        "扫描了吗", "扫描了", "扫描结果", "最近扫描",
        "扫描到", "扫到什么", "扫描发现", "扫到了",
        "扫描问题", "有什么风险", "风险记录",
    ]):
        tools.append({"tool": "get_recent_scans", "params": {}})

    # IaC / infrastructure related queries
    if any(kw in msg_lower for kw in [
        "iac", "基础设施", "terraform", "infrastructure",
        "最近提了哪些代码", "最近提交", "最近代码",
        "合并代码", "哪天合并", "那天合并", "何时合并",
    ]):
        # Check if asking about recent commits
        if any(kw in msg_lower for kw in ["代码", "提交", "commit", "合并", "提了"]):
            tools.append({"tool": "get_gitlab_mr_history", "params": {"query": message}})
        else:
            tools.append({"tool": "get_gitlab_mr_history", "params": {"query": message}})

    return tools


async def _execute_tool(tool_call: dict, app_state=None, request=None) -> str:
    """Execute a detected tool and return its result as text (async safe)."""
    tool = tool_call.get("tool", "")
    params = tool_call.get("params", {})

    try:
        if tool == "get_daily_report":
            from app.api.reports import daily_report
            result = await daily_report(date_str="", repo_url="")
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool == "get_trends":
            # Use HTTP call (avoids import/db path issues with direct function call)
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        "http://127.0.0.1:8082/api/v1/reports/trends",
                        params={"period": params.get("period", "weekly"), "count": params.get("count", 8)},
                    )
                    result = resp.json()
            except Exception:
                from app.api.reports import trends
                result = await trends(
                    period=params.get("period", "weekly"),
                    count=params.get("count", 8),
                )
            # Format a compact summary for the LLM
            data = result.get("data", [])
            lines = [f"趋势周期数: {len(data)}"]
            for w in data:
                if w.get("commit_count", 0) > 0 or w.get("mr_count", 0) > 0:
                    lines.append(
                        f"{w['period']}: MR={w['mr_count']} 提交={w['commit_count']} "
                        f"开发者={w['developer_count']} 风险={w['risk_count']}"
                    )
            if data:
                last = data[-1]
                lines.insert(0, f"最近一周({last['period']}): MR={last.get('mr_count',0)} 提交={last.get('commit_count',0)} 开发者={last.get('developer_count',0)} 新增={last.get('additions',0)}行 删除={last.get('deletions',0)}行")
            return "\n".join(lines)

        elif tool == "search_knowledge":
            from app.main import knowledge_base
            if not knowledge_base:
                return "知识库未初始化"
            raw_query = params.get("query", "")
            # Build multiple query variants for better semantic matching
            query_variants = [raw_query]
            # Extract MR number and create focused queries
            import re
            mr_match = re.search(r'mr\s*[!#]?\s*(\d+)', raw_query, re.IGNORECASE)
            if mr_match:
                mr_num = mr_match.group(1)
                query_variants.append(f"MR {mr_num} RDS 数据库 删除 风险")
                query_variants.append(f"MR {mr_num} production-database 删除")
            # Also try RDS/database specific queries
            if any(kw in raw_query.lower() for kw in ['风险', '安全', 'danger', 'risk', '删除', 'delete']):
                if 'rds' not in raw_query.lower() and '数据库' not in raw_query.lower():
                    query_variants.append(f"{raw_query} RDS 数据库 删除")
            results = []
            seen_ids = set()
            for qv in query_variants:
                try:
                    mr_results = knowledge_base.search_mr(qv, n_results=5)
                    if mr_results:
                        for r in mr_results:
                            if r.get("id") not in seen_ids:
                                seen_ids.add(r.get("id"))
                                results.append(r)
                except Exception:
                    pass
                try:
                    code_results = knowledge_base.search_code(qv, n_results=5)
                    if code_results:
                        for r in code_results:
                            if r.get("id") not in seen_ids:
                                seen_ids.add(r.get("id"))
                                results.append(r)
                except Exception:
                    pass
            if not results:
                return json.dumps({"total": 0, "results": []}, ensure_ascii=False)
            # Sort by distance (lower = more relevant), keep top results
            results.sort(key=lambda r: r.get("distance", 1.0))
            # Format results as readable text instead of raw JSON
            top = results[:8]
            lines = [f"搜索到 {len(top)} 条相关结果：", ""]
            for i, r in enumerate(top, 1):
                doc = r.get("document", "") or ""
                meta = r.get("metadata", {}) or {}
                rid = r.get("id", "")
                score = r.get("score", r.get("distance", 0))
                severity = meta.get("severity", "")
                cat = meta.get("type", meta.get("category", ""))
                # Build a compact summary line
                tags = []
                if severity:
                    tags.append(severity)
                if cat:
                    tags.append(cat)
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                lines.append(f"{i}. [{rid}]{tag_str}")
                lines.append(f"   内容: {doc[:200]}")
                if severity in ("critical", "high"):
                    lines.append(f"   ⚠ 严重风险！{doc[:100]}")
                lines.append("")
            return "\n".join(lines)

        elif tool == "get_default_strategy":
            mgr = ScanStrategyManager()
            return json.dumps(mgr.get_strategy("__default__").to_dict(), ensure_ascii=False)

        elif tool == "get_alert_status":
            from app.api.alerts import alert_status
            result = await alert_status(request)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool == "list_discovered_projects":
            if not app_state:
                return "暂无数据"
            discovery_svc = getattr(app_state, "discovery_service", None)
            if not discovery_svc:
                return "暂无数据"
            projects = discovery_svc.list_discovered()
            if not projects:
                # On-demand rescan if cache is empty
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, discovery_svc.scan_all)
                except Exception:
                    pass
                projects = discovery_svc.list_discovered()
            summary = {
                "total": len(projects),
                "projects": [
                    {
                        "id": p.get("project_id"),
                        "name": p.get("name_with_namespace", ""),
                        "url": p.get("http_url_to_repo", ""),
                        "visibility": p.get("visibility", ""),
                        "default_branch": p.get("default_branch", ""),
                        "description": p.get("description", ""),
                        "registered": p.get("registered", False),
                    }
                    for p in projects
                ],
            }
            return json.dumps(summary, ensure_ascii=False, default=str)

        elif tool == "get_developer_stats":
            from app.services.developer_service import DeveloperService
            dev_svc = DeveloperService()
            author = params.get("author", "")
            if author:
                commits = dev_svc.get_developer_commits(author, limit=20)
                return json.dumps({
                    "type": "developer_commits",
                    "author": author,
                    "total_commits": len(commits),
                    "commits": commits,
                }, ensure_ascii=False, default=str)
            else:
                stats = dev_svc.get_developer_stats()
                return json.dumps({
                    "type": "developer_stats",
                    "developers": stats,
                }, ensure_ascii=False, default=str)

        elif tool == "get_merged_features":
            from app.services.developer_service import DeveloperService
            svc = DeveloperService()
            features = svc.get_merged_features(limit=20)
            return json.dumps({
                "type": "merged_features",
                "total": len(features),
                "features": features,
            }, ensure_ascii=False, default=str)

        elif tool == "get_recent_scans":
            """Query recent scan tasks and their findings."""
            from app.services.storage import StorageService
            store = StorageService()
            # Get last 10 completed tasks with findings
            all_tasks = await store.list_tasks(limit=50, offset=0)
            completed_tasks = [t for t in all_tasks if t.status == "completed" and len(t.findings or []) > 0]
            completed_tasks = completed_tasks[:10]

            if not completed_tasks:
                # Still report task counts
                all_count = len(all_tasks)
                comp_count = sum(1 for t in all_tasks if t.status == "completed")
                fail_count = sum(1 for t in all_tasks if t.status == "failed")
                return json.dumps({
                    "type": "scan_summary",
                    "total_tasks": all_count,
                    "completed": comp_count,
                    "failed": fail_count,
                    "with_findings": len(completed_tasks),
                    "latest_scans": [
                        {
                            "repo": t.repo_url.split("/")[-1].replace(".git", ""),
                            "status": t.status,
                            "findings_count": len(t.findings or []),
                            "created": str(t.created_at)[:19] if t.created_at else "",
                        }
                        for t in all_tasks[:5]
                    ],
                    "message": "暂无扫描发现的风险项" if not completed_tasks else ""
                }, ensure_ascii=False, default=str)

            result = {
                "type": "scan_results",
                "total_scan_tasks": len(all_tasks),
                "recent_scans_with_findings": [],
            }
            for t in completed_tasks:
                repo_name = t.repo_url.split("/")[-1].replace(".git", "")
                by_severity = {"critical": 0, "major": 0, "minor": 0, "info": 0}
                findings_detail = []
                for f in (t.findings or []):
                    sev = (f.severity or "info").lower()
                    if sev in by_severity:
                        by_severity[sev] += 1
                    findings_detail.append({
                        "severity": f.severity,
                        "engine": f.engine,
                        "message": f.message[:120],
                        "file": f.file_path,
                        "rule": f.rule_id,
                    })
                result["recent_scans_with_findings"].append({
                    "repo": repo_name,
                    "task_id": t.id,
                    "created": str(t.created_at)[:19] if t.created_at else "",
                    "total_findings": len(t.findings or []),
                    "by_severity": by_severity,
                    "findings": findings_detail[:10],  # Top 10 findings per task
                })

            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool == "get_gitlab_mr_history":
            """Query GitLab API for recent MRs or commits in a project."""
            query = params.get("query", "")
            query_lower = query.lower()

            import httpx
            from app.config import settings
            gitlab_url = settings.gitlab_url.rstrip("/")
            admin_token = settings.gitlab_admin_token or settings.gitlab_api_token

            # Determine which project(s) to query
            project_ids = []
            project_names = []

            # Map common names to project paths
            name_to_path = {
                "iac": "root/iac-terraform",
                "terraform": "root/iac-terraform",
                "iac-terraform": "root/iac-terraform",
                "基础设施": "root/iac-terraform",
                "infrastructure": "root/iac-terraform",
                "iac-infrastructure": "root/iac-infrastructure",
                "python": "root/test-python-app",
                "vuln": "root/vuln-app",
                "litellm": "root/litellm-config",
                "dev/litellm": "dev/litellm",
            }

            matched_projects = []
            for keyword, path in name_to_path.items():
                if keyword in query_lower:
                    matched_projects.append(path)

            if not matched_projects:
                # Default to iac-terraform
                matched_projects = ["root/iac-terraform"]

            results = []
            async with httpx.AsyncClient(timeout=15, verify=False) as client:
                for proj_path in matched_projects[:2]:  # Max 2 projects
                    # Get project ID by path
                    proj_resp = await client.get(
                        f"{gitlab_url}/api/v4/projects/{proj_path.replace('/', '%2F')}",
                        headers={"PRIVATE-TOKEN": admin_token},
                    )
                    if proj_resp.status_code != 200:
                        results.append({"project": proj_path, "error": f"HTTP {proj_resp.status_code}"})
                        continue

                    proj_data = proj_resp.json()
                    pid = proj_data.get("id")
                    proj_name = proj_data.get("path_with_namespace", proj_path)

                    # Get recent MRs
                    mrs_resp = await client.get(
                        f"{gitlab_url}/api/v4/projects/{pid}/merge_requests",
                        params={"state": "all", "per_page": 10, "order_by": "updated_at"},
                        headers={"PRIVATE-TOKEN": admin_token},
                    )

                    mrs = []
                    if mrs_resp.status_code == 200:
                        for mr in mrs_resp.json():
                            mrs.append({
                                "iid": mr.get("iid"),
                                "title": mr.get("title"),
                                "state": mr.get("state"),
                                "merged_at": mr.get("merged_at", ""),
                                "created_at": mr.get("created_at", ""),
                                "source_branch": mr.get("source_branch"),
                                "target_branch": mr.get("target_branch"),
                                "author": mr.get("author", {}).get("name", ""),
                            })

                    # Get recent commits
                    commits_resp = await client.get(
                        f"{gitlab_url}/api/v4/projects/{pid}/repository/commits",
                        params={"per_page": 10, "ref_name": "main"},
                        headers={"PRIVATE-TOKEN": admin_token},
                    )

                    commits = []
                    if commits_resp.status_code == 200:
                        for c in commits_resp.json():
                            commits.append({
                                "id": c.get("id", "")[:8],
                                "title": c.get("title", ""),
                                "author": c.get("author_name", ""),
                                "created_at": c.get("created_at", ""),
                                "message": c.get("message", "")[:100].strip(),
                            })

                    results.append({
                        "project": proj_name,
                        "project_id": pid,
                        "mrs": mrs,
                        "commits": commits,
                    })

            return json.dumps({
                "type": "gitlab_mr_history",
                "results": results,
            }, ensure_ascii=False)

        else:
            return f"未知工具: {tool}"
    except Exception as e:
        logger.warning("Tool %s execution failed: %s", tool, e)
        return f"执行 {tool} 时出错: {str(e)}"


# ── Chat Endpoint ───────────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def chat(req: Request, body: ChatRequest):
    """Chat with the PR-CodeGuard Agent.

    The agent will:
    1. Detect user intent from the message
    2. Execute relevant tools (reports, search, etc.)
    3. Use LLM to generate a natural language response
    """
    if not settings.ai_api_key:
        return ChatResponse(
            reply="AI 聊天功能未配置。请先在 `.env` 中设置 `AI_API_KEY`。",
        )

    # Prepare messages (includes tool execution)
    messages, tool_calls, tool_results = await _prepare_messages(req, body)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.ai_api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": settings.ai_max_tokens,
                },
            )
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"]

        return ChatResponse(reply=reply, tool_calls=tool_calls, tool_results=tool_results)

    except httpx.TimeoutException:
        return ChatResponse(reply="AI 服务响应超时，请稍后重试。", tool_calls=tool_calls, tool_results=tool_results)
    except Exception as e:
        logger.error("Chat API error: %s", e)
        return ChatResponse(
            reply=f"AI 服务请求失败：{str(e)[:200]}",
            tool_calls=tool_calls,
            tool_results=tool_results,
        )


# ── Helper: prepare LLM messages ──────────────────────────────


async def _prepare_messages(req: Request, body: ChatRequest) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Build the messages list for LLM chat completion.

    Returns (messages, tool_calls, tool_results).
    Runs intent detection and tool execution as side effects.
    """
    app_state = req.app.state

    # Context
    context = _build_context(app_state)

    # Tool intents
    tool_calls = _detect_tool_intent(body.message, history=body.history)
    tool_results = {}
    for tc in tool_calls:
        result_text = await _execute_tool(tc, app_state=app_state, request=req)
        tool_results[tc["tool"]] = result_text

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT.format(
            current_time=datetime.utcnow().isoformat()
        )},
    ]

    if context:
        messages.append({
            "role": "system",
            "content": f"当前上下文信息：\n{context}",
        })

    if tool_results:
        tool_summary = "\n".join(
            f"[{k}]: {v[:4000]}"
            for k, v in tool_results.items()
        )
        messages.append({
            "role": "system",
            "content": f"工具执行结果：\n{tool_summary}",
        })

    for msg in body.history[-10:]:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": body.message})

    return messages, tool_calls, tool_results


# ── Streaming Chat Endpoint (SSE) ─────────────────────────────


@router.post("/stream")
async def chat_stream(req: Request, body: ChatRequest):
    """Stream chat response via Server-Sent Events.

    Events:
      data: {"type": "start", "tool_calls": [...]}
      data: {"type": "token", "content": "..."}
      data: {"type": "end"}
    """
    if not settings.ai_api_key:
        return ChatResponse(reply="AI 聊天功能未配置")

    async def event_stream():
        try:
            messages, tool_calls, _tool_results = await _prepare_messages(req, body)

            # Send start event with tool calls
            yield f"data: {json.dumps({'type': 'start', 'tool_calls': tool_calls}, ensure_ascii=False)}\n\n"

            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ai_api_base}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.ai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.ai_model,
                        "messages": messages,
                        "temperature": 0.3,
                        "max_tokens": settings.ai_max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        yield f"data: {json.dumps({'type': 'error', 'content': f'AI 服务错误: {error_text[:200]!r}'}, ensure_ascii=False)}\n\n"
                        yield "data: {\"type\": \"end\"}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(chunk)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"
                        except json.JSONDecodeError:
                            continue

            yield "data: {\"type\": \"end\"}\n\n"

        except Exception as e:
            logger.error("Chat stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': f'服务错误: {str(e)[:200]}'}, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"end\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
