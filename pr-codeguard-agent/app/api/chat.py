"""Chat API - conversational agent interface for users."""

import json
import logging
import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.scan_strategy import ScanStrategyManager
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# ── System Prompt ────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """你是 PR-CodeGuard Agent 的智能助手，负责回答用户关于代码仓库、扫描结果、日常报告等问题。

你可以使用以下知识来回答问题：
1. **知识库搜索** - 搜索已记录的 MR 信息、代码变更和扫描发现
2. **日报数据** - 查看每日开发产量、MR 合并、开发者统计
3. **趋势数据** - 按周/月聚合的代码活动和安全风险趋势
4. **扫描策略** - 各仓库的扫描配置、引擎开关、风险阈值
5. **仓库发现** - 已发现的 GitLab 项目和 Webhook 状态
6. **告警状态** - 已配置的告警通道和系统运行状态

回答时请注意：
- 使用中文回答
- 基于已知数据回答，不要编造
- 如果用户要求执行操作（如扫描、发邮件等），先确认后再执行
- 给出具体的数字和统计结果
- 可以建议用户使用 Dashboard 上的对应功能查看更多细节

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


# ── Context Builder ──────────────────────────────────────────────


def _build_context() -> str:
    """Build a compact context snapshot from available data."""
    from app.main import knowledge_base
    parts = []

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

    return "\n".join(parts) if parts else "(暂无上下文数据)"


# ── Intent detection ─────────────────────────────────────────────


def _detect_tool_intent(message: str) -> list[dict]:
    """Detect if the user wants to execute specific tools based on keywords."""
    tools = []
    msg_lower = message.lower()

    # Report / daily report
    if any(kw in msg_lower for kw in ["日报", "daily", "今天的报告", "报告", "报表"]):
        tools.append({"tool": "get_daily_report", "params": {}})

    # Trends
    if any(kw in msg_lower for kw in ["趋势", "trend", "走势", "变化"]):
        tools.append({"tool": "get_trends", "params": {"period": "weekly", "count": 8}})

    # Knowledge search
    if any(kw in msg_lower for kw in ["搜索", "查找", "查询", "search", "find", "知识库"]):
        tools.append({"tool": "search_knowledge", "params": {"query": message}})

    # Scan strategy
    if any(kw in msg_lower for kw in ["策略", "strategy", "配置", "引擎", "扫描等级"]):
        tools.append({"tool": "get_default_strategy", "params": {}})

    # Alert status
    if any(kw in msg_lower for kw in ["告警", "alert", "通知", "报警"]):
        tools.append({"tool": "get_alert_status", "params": {}})

    return tools


def _execute_tool(tool_call: dict) -> str:
    """Execute a detected tool and return its result as text."""
    tool = tool_call.get("tool", "")
    params = tool_call.get("params", {})

    try:
        if tool == "get_daily_report":
            from app.api.reports import daily_report
            import asyncio
            result = asyncio.run(daily_report())
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool == "get_trends":
            from app.api.reports import trends
            import asyncio
            result = asyncio.run(trends(
                period=params.get("period", "weekly"),
                count=params.get("count", 8),
            ))
            return json.dumps(result, ensure_ascii=False, default=str)

        elif tool == "search_knowledge":
            from app.main import knowledge_base
            if not knowledge_base:
                return "知识库未初始化"
            results = knowledge_base.search(params.get("query", ""), n_results=5)
            if isinstance(results, list):
                return json.dumps(results, ensure_ascii=False, default=str)
            return str(results)

        elif tool == "get_default_strategy":
            mgr = ScanStrategyManager()
            return json.dumps(mgr.get_strategy("__default__").to_dict(), ensure_ascii=False)

        elif tool == "get_alert_status":
            from app.api.alerts import alert_status
            import asyncio
            result = asyncio.run(alert_status())
            return json.dumps(result, ensure_ascii=False, default=str)

        else:
            return f"未知工具: {tool}"
    except Exception as e:
        logger.warning("Tool %s execution failed: %s", tool, e)
        return f"执行 {tool} 时出错: {str(e)}"


# ── Chat Endpoint ───────────────────────────────────────────────


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
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

    # Step 1: Build context from knowledge base + tools
    context = _build_context()

    # Step 2: Detect and execute tool intents
    tool_calls = _detect_tool_intent(request.message)
    tool_results = {}
    for tc in tool_calls:
        result_text = _execute_tool(tc)
        tool_results[tc["tool"]] = result_text

    # Step 3: Call LLM for the final answer
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT.format(
            current_time=datetime.utcnow().isoformat()
        )},
    ]

    # Add context as system message
    if context:
        messages.append({
            "role": "system",
            "content": f"当前上下文信息：\n{context}",
        })

    # Add tool results as system message
    if tool_results:
        tool_summary = "\n".join(
            f"[{k}]: {v[:500]}"
            for k, v in tool_results.items()
        )
        messages.append({
            "role": "system",
            "content": f"工具执行结果：\n{tool_summary}",
        })

    # Add conversation history
    for msg in request.history[-10:]:  # Keep last 10 messages
        messages.append({"role": msg.role, "content": msg.content})

    # Add current user message
    messages.append({"role": "user", "content": request.message})

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

        return ChatResponse(reply=reply, tool_calls=tool_calls)

    except httpx.TimeoutException:
        return ChatResponse(reply="AI 服务响应超时，请稍后重试。", tool_calls=tool_calls)
    except Exception as e:
        logger.error("Chat API error: %s", e)
        return ChatResponse(
            reply=f"AI 服务请求失败：{str(e)[:200]}",
            tool_calls=tool_calls,
        )
