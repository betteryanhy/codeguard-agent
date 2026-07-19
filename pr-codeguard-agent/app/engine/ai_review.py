"""AI-powered review engine that enhances raw findings with human-readable explanations."""

import json
import logging
from typing import Any

import httpx

from app.config import settings
from app.engine.base import AnalysisEngine
from app.models.finding import Finding

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """你是一个代码审查助手，负责把扫描工具的原始结果翻译成人话。

对每条问题，给出简短的中文解释（一句话说明什么问题 + 一句话如何修复），格式如下：
{解释}|{修复建议}

要求：
- 解释要简明扼要，让不懂安全的开发者也看得懂
- 修复建议要具体可操作
- 每条不超过 80 字
- 整体风格专业但不啰嗦"""


class AIReviewEngine(AnalysisEngine):
    """AI engine that enriches findings with natural language explanations."""

    @property
    def name(self) -> str:
        return "ai_review"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        """Not used — AIReviewEngine runs enrich() instead."""
        return []

    def enrich(self, findings: list[Finding]) -> list[Finding]:
        """Enrich existing findings with AI-generated explanations."""
        if not settings.ai_api_key:
            logger.warning("AI review disabled: no API key configured")
            return findings

        if not findings:
            return findings

        # Batch process findings to minimize API calls
        enriched = []
        batch = []
        batch_size = 10

        for f in findings:
            batch.append(f)
            if len(batch) >= batch_size:
                self._enrich_batch(batch, enriched)
                batch = []

        if batch:
            self._enrich_batch(batch, enriched)

        return enriched or findings

    def _enrich_batch(self, batch: list[Finding], enriched: list[Finding]) -> None:
        """Send a batch of findings to DeepSeek API for explanation."""
        try:
            results = self._call_deepseek(batch)
            for finding, result in zip(batch, results):
                finding.ai_explanation = result.get("explanation", "")
                if result.get("recommendation"):
                    finding.recommendation = result["recommendation"]
                enriched.append(finding)
        except Exception as e:
            logger.error(f"AI enrichment batch failed: {e}")
            # Fallback: pass through without enrichment
            enriched.extend(batch)

    def _call_deepseek(self, findings: list[Finding]) -> list[dict[str, str]]:
        """Call DeepSeek API to explain findings."""
        messages = self._build_messages(findings)

        try:
            with httpx.Client(timeout=settings.ai_request_timeout) as client:
                resp = client.post(
                    f"{settings.ai_api_base.rstrip('/')}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.ai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.ai_model,
                        "messages": messages,
                        "max_tokens": settings.ai_max_tokens,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.error("DeepSeek API request timed out")
            return [{"explanation": "", "recommendation": ""} for _ in findings]
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API error: {e.response.status_code} {e.response.text}")
            return [{"explanation": "", "recommendation": ""} for _ in findings]
        except Exception as e:
            logger.error(f"DeepSeek API request failed: {e}")
            return [{"explanation": "", "recommendation": ""} for _ in findings]

        try:
            content = data["choices"][0]["message"]["content"]
            return self._parse_response(content, findings)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse DeepSeek response: {e}")
            return [{"explanation": "", "recommendation": ""} for _ in findings]

    def _build_messages(self, findings: list[Finding]) -> list[dict[str, Any]]:
        """Build the messages payload for the DeepSeek API."""
        items = []
        for i, f in enumerate(findings):
            items.append({
                "index": i,
                "engine": f.engine,
                "severity": f.severity,
                "file": f.file_path,
                "line": f.line,
                "message": f.message,
                "code": f.code_snippet[:200] if f.code_snippet else "",
                "rule_id": f.rule_id,
            })

        user_prompt = (
            "请为以下代码扫描发现的问题提供简短的中文解释和修复建议。"
            f"共 {len(items)} 条问题，每条返回格式为：index|解释|修复建议\n\n"
            + json.dumps(items, ensure_ascii=False, indent=2)
        )

        return [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_response(
        self, content: str, findings: list[Finding]
    ) -> list[dict[str, str]]:
        """Parse the AI response into structured explanations."""
        results = [{"explanation": "", "recommendation": ""} for _ in findings]

        for line in content.strip().split("\n"):
            line = line.strip()
            if "|" not in line:
                continue

            parts = line.split("|", 2)
            if len(parts) < 3:
                continue

            try:
                idx = int(parts[0].strip())
                if 0 <= idx < len(results):
                    results[idx] = {
                        "explanation": parts[1].strip(),
                        "recommendation": parts[2].strip(),
                    }
            except (ValueError, IndexError):
                continue

        return results
