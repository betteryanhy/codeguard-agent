# CodeGuard Agent 三阶段迭代开发计划

> **目标：** 在第一阶段安全扫描 + IaC Terraform Plan 集成基础上，逐步实现信息追溯问答和每日邮件服务，最终打造一个自发现、自分类、智能审查的代码安全 Agent。

**架构：** 以现有 FastAPI + Trivy + 知识库 (SQLite/Chroma) 为基础，采用模块化扩展方式。每个阶段新增独立模块，不破坏现有功能。

**技术栈：** Python 3.11+, FastAPI, Trivy, Semgrep, Terraform, ChromaDB, SQLite, aiosmtplib

---

## 阶段一：安全功能增强（开发周期：2周）

### 范围
- 完善 Trivy 扫描（恢复 secret 扫描器）
- 引入 Semgrep SAST 扫描
- 实现 IaC Terraform Plan 集成（差异化核心竞争力）
- 实现项目自动发现与分类
- AI 智能评论摘要（如有 API Key）

### 阶段一任务分解

---

#### 任务 1.1：修复 Trivy Secret 扫描器

**问题分析：** Trivy v0.72 的 secret 扫描器在处理 app.py、config.json 等文件时存在 semaphore acquire 超时 BUG，目前被禁用。

**修复方案：** 升级 Trivy 版本 + 使用 --skip-files 排除问题文件 + 增加超时控制

**涉及文件：**
- 修改: `app/engine/trivy_scanner.py`
- 修改: `pr-codeguard-agent/.env`
- 修改: `app/services/orchestrator.py`

**关键改动：**
1. 将 Trivy 升级到 v0.58+（实际当前版本确认是否是 v0.72+）
2. 在 secret 扫描器中增加文件排除白名单
3. secret 扫描器独立超时控制（当前 300s，secret 需要更长）

```python
# app/engine/trivy_scanner.py 中需要修改的位置:
# _build_command 方法增加 --skip-files 参数
# _scanner_timeout_map 增加 secret 的超时配置
```

**验证方式：**
- 创建包含硬编码密钥的测试文件
- 运行 `trivy filesystem --scanners secret` 验证能正常检出
- 运行验收测试脚本 `_test_trivy_scanner.py`

---

#### 任务 1.2：引入 Semgrep SAST 引擎

**新文件：**
- 创建: `app/engine/sast_semgrep.py` — Semgrep 封装引擎
- 创建: `tests/engine/test_sast_semgrep.py` — 单元测试
- 创建: `tools/semgrep/rules/` — 自定义规则目录

**修改文件：**
- 修改: `app/services/orchestrator.py` — 注册新引擎
- 修改: `pr-codeguard-agent/.env` — 新增 Semgrep 配置
- 修改: `app/config.py` — 新增 Semgrep 配置项

**Semgrep 规则覆盖：**
| 规则类别 | 检测内容 | 示例 |
|---------|---------|------|
| SQL注入 | 字符串拼接 SQL | `f"SELECT * FROM users WHERE id = {user_input}"` |
| 路径遍历 | 未验证的文件路径 | `open(request.GET['file'])` |
| 硬编码密钥 | 代码中的明文密码 | `PASSWORD = "123456"` |
| 危险函数 | eval/exec/os.system | `eval(user_input)` |
| 调试泄露 | print/console.log 遗留 | `print(f"DEBUG: {password}")` |

```python
# app/engine/sast_semgrep.py (核心结构)
"""
Semgrep SAST engine for code pattern analysis.

Integrates Semgrep CLI (>=1.0.0) for static analysis.
Covers: SQL injection, path traversal, hardcoded secrets, dangerous functions.
"""
import json
import subprocess
import logging
from app.engine.base import AnalysisEngine
from app.models.finding import Finding

logger = logging.getLogger(__name__)

# Semgrep severity mapping
SEVERITY_MAP = {
    "ERROR": "critical",
    "WARNING": "major",
    "INFO": "minor",
}

class SemgrepScanner(AnalysisEngine):
    @property
    def name(self) -> str:
        return "sast_semgrep"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        findings = []
        semgrep_path = self._find_semgrep()
        if not semgrep_path:
            logger.warning("Semgrep not found, skipping")
            return findings

        cmd = [
            semgrep_path, "scan",
            "--json",
            "--no-rewrite-rule-ids",
            "--quiet",
            "--config", "auto",  # Uses Semgrep Registry
            "--severity", "ERROR,WARNING",
            "--max-target-bytes", "500000",
        ]

        if diff_files:
            # Only scan changed files
            changed_paths = [os.path.join(repo_path, f) for f in diff_files]
            cmd.extend(changed_paths)
        else:
            cmd.append(repo_path)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=300, cwd=repo_path,
            )
            findings = self._parse_results(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Semgrep scan timed out")
        except Exception as e:
            logger.error(f"Semgrep scan failed: {e}")

        return findings

    def _parse_results(self, stdout: str) -> list[Finding]:
        findings = []
        try:
            data = json.loads(stdout)
            for result in data.get("results", []):
                path = result.get("path", "")
                findings.append(Finding(
                    engine="sast_semgrep",
                    severity=SEVERITY_MAP.get(result.get("extra", {}).get("severity", ""), "major"),
                    file_path=path,
                    line=result.get("start", {}).get("line"),
                    message=result.get("extra", {}).get("message", ""),
                    code_snippet=result.get("extra", {}).get("lines", ""),
                    recommendation=result.get("extra", {}).get("fix", ""),
                    rule_id=result.get("check_id", ""),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Semgrep parse error: {e}")
        return findings
```

---

#### 任务 1.3：IaC Terraform Plan 集成（核心差异化功能）

**新文件：**
- 创建: `app/services/tf_plan_webhook.py` — Terraform Plan webhook 接收端点
- 创建: `app/engine/tf_plan_analyzer.py` — Plan JSON 解析与评估引擎
- 创建: `tests/services/test_tf_plan_analyzer.py`
- 创建: `docs/tf-plan-integration-guide.md`

**修改文件：**
- 修改: `app/main.py` — 注册新路由
- 修改: `app/config.py` — TF Plan 配置项

**架构流程：**
```
GitLab CI Job
  │  terraform plan -out=plan.tfplan
  │  terraform show -json plan.tfplan > plan.json
  │  curl -X POST http://agent:8082/api/v1/webhook/tf-plan \
  │    -H "X-Project-Id: $CI_PROJECT_ID" \
  │    -H "X-MR-IID: $CI_MERGE_REQUEST_IID" \
  │    -d @plan.json
  ▼
Agent TF Plan Webhook
  │
  ├── 解析 plan.json → resource_changes[]
  ├── 提取：增/删/改的资源类型、名称、属性
  ├── 对比知识库规则（"RDS 删除需审批"）
  ├── 评分：BLOCKER / CRITICAL / MAJOR / MINOR
  └── 输出 → MR 评论 + 库记录
```

**Terraform Plan 分析规则（内置 + 知识库可扩展）：**

```python
# 关键资源操作风险等级
RISK_MATRIX = {
    ("delete", "aws_rds_cluster"): "critical",
    ("delete", "aws_rds_instance"): "critical",
    ("delete", "aws_s3_bucket"): "critical",
    ("delete", "aws_security_group"): "major",
    ("delete", "aws_vpc"): "critical",
    ("delete", "aws_ec2_instance"): "major",
    ("create", "aws_security_group_rule"): "major",  # 入站规则需审查
    ("update", "aws_security_group_rule"): "major",   # 规则变更需审查
}
```

```python
# app/engine/tf_plan_analyzer.py 核心逻辑
class TfPlanAnalyzer:
    """Analyze Terraform plan JSON for risk assessment."""

    RISK_MATRIX = {
        ("delete", "aws_rds_cluster"): "critical",
        ("delete", "aws_rds_instance"): "critical",
        ("delete", "aws_s3_bucket"): "critical",
        ("delete", "aws_security_group"): "major",
        ("delete", "aws_vpc"): "critical",
        ("delete", "aws_ec2_instance"): "major",
        ("create", "aws_security_group_rule"): "major",
        ("update", "aws_security_group_rule"): "major",
        ("delete", "aws_kms_key"): "critical",
        ("delete", "aws_kms_alias"): "critical",
        ("delete", "aws_dynamodb_table"): "major",
    }

    def analyze(self, plan_json: dict, project_id: str = "") -> list[Finding]:
        """Analyze a Terraform plan JSON document."""
        findings = []
        changes = plan_json.get("resource_changes", [])

        for change in changes:
            action = self._get_action(change)
            resource_type = change.get("type", "")
            resource_name = change.get("name", "")
            address = change.get("address", "")

            # Check static risk matrix
            risk = self.RISK_MATRIX.get((action, resource_type))
            if risk:
                findings.append(Finding(
                    engine="tf_plan",
                    severity=risk,
                    file_path=address,
                    line=None,
                    message=f"[Terraform Plan] {action.upper()} {resource_type}.{resource_name}",
                    recommendation=self._get_recommendation(action, resource_type),
                    rule_id=f"tf_{action}_{resource_type}",
                ))

            # Check knowledge base for project-specific rules
            kb_findings = self._check_knowledge_base(action, resource_type, resource_name, project_id)
            findings.extend(kb_findings)

        return findings
```

---

#### 任务 1.4：项目自动发现与分类增强

**修改文件：**
- 修改: `app/services/discovery_service.py` — 增加项目类型判断
- 修改: `app/knowledge/knowledge_base.py` — 增加项目元数据存储

**分类逻辑：**
```python
def classify_project(project: dict) -> dict:
    """Classify project by its file structure."""
    files = project.get("files", [])
    types = set()

    for f in files:
        if f.endswith(".tf") or f.endswith(".tfvars"):
            types.add("iac_terraform")
        if f == "Dockerfile" or f.endswith(".dockerfile"):
            types.add("container")
        if f in ("go.mod", "go.sum"):
            types.add("go")
        if f in ("package.json", "package-lock.json", "yarn.lock"):
            types.add("node")
        if f in ("requirements.txt", "Pipfile", "setup.py"):
            types.add("python")
        if f in ("pom.xml", "build.gradle"):
            types.add("java")
        if f.endswith(".yaml") or f.endswith(".yml"):
            # Check if it's K8s manifest
            types.add("k8s_manifest")

    return {
        "project_id": project["id"],
        "path": project["path_with_namespace"],
        "types": list(types),
        "primary_type": _determine_primary(types),
    }

def _determine_primary(types: set) -> str:
    priority = ["iac_terraform", "k8s_manifest", "go", "java", "node", "python", "container"]
    for t in priority:
        if t in types:
            return t
    return "unknown"
```

---

### 阶段一测试计划

| 测试 | 类型 | 内容 |
|------|------|------|
| `tests/engine/test_sast_semgrep.py` | 单元测试 | Semgrep 结果解析、规则匹配 |
| `tests/engine/test_tf_plan_analyzer.py` | 单元测试 | Plan JSON 解析、风险评分 |
| `tests/services/test_discovery.py` | 单元测试 | 项目分类逻辑 |
| `_test_trivy_scanner.py` | 验证测试 | Trivy 各扫描器回归测试 |
| 端到端测试 | 集成测试 | 创建 MR → 扫描 → MR 评论全流程 |

---

## 阶段二：信息问答系统（开发周期：1.5周）

### 范围
- GitLab System Hooks 监听（push、branch、MR 事件）
- 事件 → 知识库流水线
- 自然语言查询 API（关键词 + 向量语义检索）
- 开发者活动查询
- 简易前端查询界面

### 阶段二任务分解

---

#### 任务 2.1：GitLab System Hooks 监听

**新文件：**
- 创建: `app/api/system_hooks.py` — System hook 接收端点
- 创建: `app/services/event_processor.py` — 事件分类与入库

**修改文件：**
- 修改: `app/main.py` — 注册 hooks 路由

**支持的事件类型：**
| 事件 | 触发时机 | 记录内容 |
|------|---------|---------|
| `push` | 代码推送 | 分支、提交信息、文件列表、作者 |
| `tag_push` | 打标签 | 标签名、target |
| `repository_update` | 仓库更新 | 更新类型 |
| `merge_request` | MR 事件 | 源/目标分支、标题、操作类型 |
| `branch_create` | 新建分支 | 分支名、创建者 |
| `branch_delete` | 删除分支 | 分支名、删除者 |

```python
# app/api/system_hooks.py
from fastapi import APIRouter, Request
from app.services.event_processor import EventProcessor

router = APIRouter(prefix="/api/v1/hooks", tags=["system_hooks"])
processor = EventProcessor()

@router.post("/gitlab-system")
async def handle_system_hook(request: Request):
    """Receive GitLab System Hook events."""
    body = await request.json()
    event = body.get("event_type", body.get("object_kind", "unknown"))
    await processor.process(event, body)
    return {"status": "accepted", "event": event}
```

```python
# app/services/event_processor.py
class EventProcessor:
    """Process GitLab system events and store in knowledge base."""

    def __init__(self):
        self.kb = KnowledgeBase()

    async def process(self, event_type: str, payload: dict):
        handler_map = {
            "push": self._handle_push,
            "tag_push": self._handle_tag_push,
            "merge_request": self._handle_merge_request,
            "repository_update": self._handle_repo_update,
            "branch_create": self._handle_branch_create,
            "branch_delete": self._handle_branch_delete,
        }
        handler = handler_map.get(event_type)
        if handler:
            await handler(payload)

    async def _handle_push(self, payload: dict):
        """Store push event into knowledge base."""
        project_path = payload.get("project", {}).get("path_with_namespace", "")
        ref = payload.get("ref", "")  # refs/heads/main
        branch = ref.replace("refs/heads/", "")
        before = payload.get("before", "")
        after = payload.get("after", "")
        user = payload.get("user_name", "")
        user_email = payload.get("user_email", "")
        commits = payload.get("commits", [])

        # Record each commit
        for commit in commits:
            commit_id = commit.get("id", "")[:12]
            message = commit.get("message", "").split("\n")[0]
            files_added = commit.get("added", [])
            files_modified = commit.get("modified", [])
            files_removed = commit.get("removed", [])

            await self.kb.add_commit_record(CommitRecord(
                commit_id=commit_id,
                project_path=project_path,
                branch=branch,
                author=user,
                author_email=user_email,
                message=message,
                files_added=files_added,
                files_modified=files_modified,
                files_removed=files_removed,
                timestamp=datetime.utcnow(),
            ))
```

---

#### 任务 2.2：自然语言查询 API

**新文件：**
- 创建: `app/api/query.py` — 查询接口
- 创建: `app/services/query_engine.py` — 查询引擎（关键词 + 向量）

**修改文件：**
- 修改: `app/main.py` — 注册查询路由

**查询能力：**
```
用户问: "user_service.go 这个文件最近谁改过？"
→ 关键词解析 + 向量检索
→ 返回: "张三在 3天前的 MR !47 (fix: 修复用户服务空指针) 中修改过"

用户问: "payment 模块上周有什么变更？"
→ 向量检索 payment 相关记录
→ 返回: 3次commit, 2个MR, 涉及5个文件
```

```python
# app/services/query_engine.py
class QueryEngine:
    """Unified query engine combining keyword matching and vector search."""

    def __init__(self):
        self.kb = KnowledgeBase()

    async def query(self, question: str) -> dict:
        """Answer a natural language question about code activity."""
        # 1. Try vector search first (semantic)
        vector_results = self.kb.search_mr(question, n_results=5)

        # 2. Try keyword extraction
        keywords = self._extract_keywords(question)
        keyword_results = self._keyword_search(keywords)

        # 3. Merge results
        merged = self._merge_results(vector_results, keyword_results)

        return {
            "question": question,
            "answer": self._format_answer(merged, question),
            "source_count": len(merged),
            "sources": merged[:5],
        }

    def _extract_keywords(self, question: str) -> list[str]:
        """Extract meaningful keywords from a natural language question."""
        # Remove stop words, extract file names, module names
        words = question.lower().split()
        stop_words = {"的", "了", "在", "是", "谁", "什么", "最近", "上周", "这个",
                      "有", "过", "吗", "吧", "啊", "呢", "the", "a", "an", "is",
                      "was", "were", "has", "have", "been"}
        keywords = [w.strip("？?，,。.!！") for w in words if w not in stop_words and len(w) > 1]

        # Detect file paths (words containing .py, .go, .js, etc.)
        file_keywords = [k for k in keywords if "." in k]
        return file_keywords or keywords
```

---

#### 任务 2.3：简易查询前端页面

**新文件：**
- 创建: `app/static/query.html` — 查询页面

**修改文件：**
- 修改: `app/main.py` — 挂载静态文件

```html
<!-- app/static/query.html (简版) -->
<!DOCTYPE html>
<html>
<head>
  <title>CodeGuard Q&A</title>
  <style>
    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }
    textarea { width: 100%; padding: 12px; font-size: 16px; border: 1px solid #ddd; border-radius: 6px; }
    button { padding: 10px 24px; background: #1a73e8; color: white; border: none; border-radius: 6px; cursor: pointer; }
    .result { margin-top: 20px; padding: 16px; background: #f5f5f5; border-radius: 6px; white-space: pre-wrap; }
    .sources { margin-top: 12px; font-size: 14px; color: #666; }
  </style>
</head>
<body>
  <h2>🔍 CodeGuard 知识查询</h2>
  <textarea id="question" rows="3" placeholder="例如: payment 模块最近谁改过？"></textarea>
  <br><br>
  <button onclick="ask()">查询</button>
  <div id="result" class="result" style="display:none"></div>

  <script>
    async function ask() {
      const q = document.getElementById('question').value;
      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question: q})
      });
      const data = await res.json();
      const div = document.getElementById('result');
      div.style.display = 'block';
      div.innerHTML = `<strong>💡 回答：</strong><br>${data.answer}<br>
        <div class="sources">来源: ${data.source_count} 条记录</div>`;
    }
  </script>
</body>
</html>
```

---

### 阶段二测试计划

| 测试 | 类型 | 内容 |
|------|------|------|
| `tests/services/test_event_processor.py` | 单元测试 | 事件解析、入库逻辑 |
| `tests/services/test_query_engine.py` | 单元测试 | 关键词提取、向量检索 |
| `tests/api/test_query_api.py` | 集成测试 | API 端点功能 |

---

## 阶段三：每日邮件服务（开发周期：1周）

### 范围
- 每日数据聚合（扫描结果、开发者活动、仓库动态）
- 邮件模板引擎（Markdown → HTML）
- 定时发送调度
- 发送状态跟踪 + 失败重试

### 阶段三任务分解

---

#### 任务 3.1：日报数据聚合服务

**新文件：**
- 创建: `app/services/daily_digest.py` — 日报数据生成器

**修改文件：**
- 修改: `app/api/alerts.py` — 整合日报 API

```python
# app/services/daily_digest.py
class DailyDigest:
    """Generate daily digest data for email reports."""

    def __init__(self):
        self.gitlab = GitLabClient()
        self.kb = KnowledgeBase()

    async def generate(self, date: datetime.date | None = None) -> dict:
        """Generate daily digest data."""
        date = date or datetime.utcnow().date()

        # 1. Scan results summary
        scan_summary = await self._get_scan_summary(date)

        # 2. Developer activity
        dev_activity = await self._get_developer_activity(date)

        # 3. Project updates
        project_updates = await self._get_project_updates(date)

        # 4. Top findings (new critical/high issues)
        top_findings = await self._get_top_findings(date)

        return {
            "date": date.isoformat(),
            "scan_summary": scan_summary,
            "developer_activity": dev_activity,
            "project_updates": project_updates,
            "top_findings": top_findings,
        }

    async def _get_scan_summary(self, date: datetime.date) -> dict:
        """Get scan results for the day."""
        # Query today's scan tasks from memory/storage
        # Group by severity
        return {
            "total_scans": 12,
            "total_findings": 45,
            "by_severity": {"critical": 2, "major": 15, "minor": 28},
            "new_cves": 8,
            "regressions": 1,
        }

    async def _get_developer_activity(self, date: datetime.date) -> list[dict]:
        """Get developer commit/MR activity for the day."""
        # Query knowledge base for today's commits
        return [
            {"name": "张三", "commits": 5, "mrs": 2, "files_changed": 12, "additions": 350, "deletions": 120},
            {"name": "李四", "commits": 3, "mrs": 1, "files_changed": 8, "additions": 180, "deletions": 45},
        ]
```

---

#### 任务 3.2：邮件模板引擎

**新文件：**
- 创建: `app/services/email_templates.py` — 邮件模板系统
- 创建: `app/static/templates/daily_report.html` — 日报 HTML 模板

```python
# app/services/email_templates.py
class EmailTemplates:
    """HTML email template renderer."""

    DAILY_REPORT_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1a73e8; color: white; padding: 24px; border-radius: 8px 8px 0 0;">
            <h1 style="margin:0; font-size: 20px;">📋 CodeGuard 每日报告</h1>
            <p style="margin:4px 0 0; opacity: 0.9;">{date}</p>
        </div>
        <div style="padding: 24px; background: #fafafa; border: 1px solid #e0e0e0;">

            <!-- Severity Summary -->
            <h2>扫描概览</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 12px; text-align: center; background: #fff; border: 1px solid #e0e0e0;">
                        <div style="font-size: 28px; font-weight: bold; color: #d32f2f;">{critical_count}</div>
                        <div style="font-size: 12px; color: #666;">CRITICAL</div>
                    </td>
                    <td style="padding: 12px; text-align: center; background: #fff; border: 1px solid #e0e0e0;">
                        <div style="font-size: 28px; font-weight: bold; color: #f57c00;">{major_count}</div>
                        <div style="font-size: 12px; color: #666;">MAJOR</div>
                    </td>
                    <td style="padding: 12px; text-align: center; background: #fff; border: 1px solid #e0e0e0;">
                        <div style="font-size: 28px; font-weight: bold; color: #1976d2;">{minor_count}</div>
                        <div style="font-size: 12px; color: #666;">MINOR</div>
                    </td>
                    <td style="padding: 12px; text-align: center; background: #fff; border: 1px solid #e0e0e0;">
                        <div style="font-size: 28px; font-weight: bold; color: #388e3c;">{scans_count}</div>
                        <div style="font-size: 12px; color: #666;">扫描次数</div>
                    </td>
                </tr>
            </table>

            <!-- Developer Activity -->
            <h2 style="margin-top: 24px;">开发者活跃度</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background: #e8eaf6;">
                    <th style="text-align: left; padding: 8px; font-size: 13px;">开发者</th>
                    <th style="text-align: center; padding: 8px; font-size: 13px;">提交</th>
                    <th style="text-align: center; padding: 8px; font-size: 13px;">MR</th>
                    <th style="text-align: center; padding: 8px; font-size: 13px;">+/- 行</th>
                </tr>
                {developer_rows}
            </table>

            <!-- Top Findings -->
            <h2 style="margin-top: 24px;">高危发现</h2>
            {top_findings_list}

            <p style="margin-top: 24px; font-size: 12px; color: #999;">
                由 PR-CodeGuard Agent 自动生成 · 查看详情: {dashboard_url}
            </p>
        </div>
    </body>
    </html>
    """
```

---

#### 任务 3.3：定时邮件发送

**新文件：**
- 创建: `app/services/email_scheduler.py` — 定时调度器

**修改文件：**
- 修改: `app/main.py` — 注册定时任务
- 修改: `pr-codeguard-agent/.env` — 邮件配置

```python
# app/services/email_scheduler.py
import asyncio
import logging
from datetime import datetime, time
from app.services.daily_digest import DailyDigest
from app.services.email_templates import EmailTemplates
from app.services.alert_service import AlertService

logger = logging.getLogger(__name__)

class EmailScheduler:
    """Scheduled daily email sender."""

    def __init__(self):
        self.digest = DailyDigest()
        self.templates = EmailTemplates()
        self.alert = AlertService()
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the daily scheduler."""
        self._task = asyncio.create_task(self._run_daily())
        logger.info("Email scheduler started")

    async def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_daily(self):
        """Run daily at configured time (default 09:00)."""
        while True:
            now = datetime.utcnow()
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=target.day + 1)

            seconds = (target - now).total_seconds()
            logger.info(f"Next daily email at {target.isoformat()} (in {seconds:.0f}s)")
            await asyncio.sleep(seconds)

            try:
                await self.send_daily_report()
            except Exception as e:
                logger.error(f"Daily email failed: {e}")

    async def send_daily_report(self, date: datetime.date | None = None):
        """Generate and send daily report."""
        data = await self.digest.generate(date)
        html = self.templates.render_daily(data)
        subject = f"CodeGuard 每日报告 - {data['date']}"

        recipients = settings.alert_email_to or []
        for recipient in recipients:
            try:
                self.alert._send_email_sync(recipient, subject, html)
                logger.info(f"Daily email sent to {recipient}")
            except Exception as e:
                logger.error(f"Failed to send to {recipient}: {e}")
```

---

### 阶段三测试计划

| 测试 | 类型 | 内容 |
|------|------|------|
| `tests/services/test_daily_digest.py` | 单元测试 | 数据聚合逻辑 |
| `tests/services/test_email_templates.py` | 单元测试 | 模板渲染 |
| `tests/services/test_email_scheduler.py` | 集成测试 | 调度逻辑 |

---

## 依赖关系与衔接策略

```
阶段一 ──────────────────────────────→ 阶段二 ──────────→ 阶段三
  │                                       │                 │
  ├── Trivy 增强 ← 独立，无依赖            │                 │
  ├── Semgrep 引擎 ← 独立，无依赖           │                 │
  ├── TF Plan 集成 ← 独立，无依赖           │                 │
  ├── 自动发现分类 ───→ 阶段二使用分类结果    │                 │
  │                                       │                 │
  │                          ├── System Hooks ← 依赖 GitLab   │
  │                          ├── Event Processor → 写入知识库  │
  │                          ├── Query Engine ← 依赖知识库     │
  │                          │                               │
  │                          │             ├── Daily Digest ← 依赖知识库 + GitLab
  │                          │             ├── Email Templates ← 独立
  │                          │             ├── Email Scheduler ← 依赖 Digest + Alert
```

**衔接策略：**
1. 每个阶段结束时运行完整回归测试，确保不破坏已有功能
2. 阶段产出的模块（如自动发现分类）以独立 PR 合并
3. 阶段间预留 1 天缓冲期用于集成测试和问题修复
4. 阶段二依赖阶段一的自动发现功能（项目分类），其他模块可并行开发

---

## 全局约束

1. 所有新增代码必须遵循现有架构风格（FastAPI router + service/engine 分层）
2. 所有模块必须可独立测试，不依赖外部服务（GitLab API 调用需 mock）
3. 扫描结果统一使用 `Finding` 模型，不新增重复的数据模型
4. 配置文件统一在 `.env` 管理，不硬编码任何敏感信息
5. 知识库操作统一通过 `KnowledgeBase` 入口，不直接操作 SQLite/Chroma
