# PR-CodeGuard Agent

智能代码审查 Agent，集成安全扫描、知识库、语义搜索和日报功能。连接 GitLab 后，自动监听 Merge Request 事件，执行多引擎安全扫描，记录代码变更到知识库，并以 Review Comment 形式反馈结果。

## 核心功能

### 1. 多引擎安全扫描
提交 MR 后自动触发扫描管线，涵盖四个维度：

| 引擎 | 检测项 | 工具 |
|------|--------|------|
| 密钥检测 | 硬编码密码、Token、私钥泄露 | Gitleaks |
| SAST | SQL 注入、凭证硬编码等代码缺陷 | Semgrep |
| IaC 合规 | Terraform 安全反模式（公开 S3、未加密等） | Checkov |
| 最佳实践 | 自定义规则集 | 规则引擎 |

### 2. AI Agent 架构
LLM 驱动的智能决策系统：
- **Planner** — 根据事件类型（MR 开启/更新/合并、用户提问）自动生成执行计划
- **Executor** — 调用工具集（扫描器、知识库读写、评论器）执行计划
- **Tools** — 工具抽象层，现有工具：代码扫描、差异分析、知识库读写、GitLab 评论、基线构建

### 3. 知识库系统
双重存储架构，保存项目变更历史：
- **SQLite 结构化存储** — 项目基线、模块、接口、MR 记录、提交记录、文件变更详情
- **Chroma 向量存储** — 代码语义向量，支持自然语言搜索

### 4. 语义搜索
支持通过自然语言检索知识库，快速定位历史变更：
```
GET /api/v1/knowledge/search?q=KMS+encryption+database+security
```
返回相关 MR 和代码片段，附带相关性评分。

### 5. 日报与报告
聚合 MR 合并、代码提交、开发者和安全问题数据：
```
GET /api/v1/reports/daily?date=2026-07-17
```
返回当日新增代码行数、合并 MR、开发者贡献统计。

### 6. IaC 专项检测
针对 Terraform 代码的专项安全检测，覆盖：
- S3 Bucket 公开访问
- KMS 加密缺失
- 安全组过度开放
- 日志记录禁用
- 网络 ACL 配置缺陷

## 架构

```
GitLab Webhook → Agent Brain (LLM 决策)
                    ├── Planner
                    ├── Executor
                    │       ├── Scanner Tool (Gitleaks + Semgrep + Checkov + Best Practices)
                    │       ├── Knowledge Writer Tool
                    │       ├── Knowledge Reader Tool
                    │       ├── Diff Analyzer Tool
                    │       ├── Baseline Builder Tool
                    │       └── GitLab Commenter Tool
                    │
                    ├── Knowledge Base
                    │       ├── SQLite (结构化: MR / 提交 / 文件变更)
                    │       └── Chroma (向量: 代码语义搜索)
                    │
                    └── APIs
                            ├── Webhook Receiver
                            ├── Knowledge Search API
                            ├── Reports API
                            └── Health / Results / Config
```

## 快速开始

### 前提条件
- Python 3.10+
- GitLab 实例（Self-hosted 或 SaaS）
- （可选）扫描工具：Gitleaks、Semgrep、Checkov

### 安装

```bash
cd pr-codeguard-agent
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件：

```env
GITLAB_URL=http://your-gitlab:80
GITLAB_API_TOKEN=your-token
WEBHOOK_SECRET=your-webhook-secret
PORT=8082
AI_ENABLED=true
AI_API_KEY=your-deepseek-api-key
```

### 启动

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8082
```

### 配置 GitLab Webhook

在 GitLab 项目中配置 Webhook：
- **URL**: `http://your-agent:8082/api/v1/webhook/gitlab`
- **Secret Token**: 与 `WEBHOOK_SECRET` 一致
- **Trigger**: Merge Request events

## API 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /api/v1/webhook/gitlab | GitLab Webhook 接收 |
| GET | /api/v1/results/{task_id} | 获取扫描结果 |
| GET | /api/v1/results/{task_id}/summary | 获取结果摘要 |
| POST | /api/v1/config/repositories | 注册仓库 |
| POST | /api/v1/config/repositories/{id}/disable | 停用监控 |
| POST | /api/v1/config/repositories/{id}/enable | 启用监控 |
| GET | /api/v1/reports/daily | 日报数据 |
| GET | /api/v1/knowledge/search | 语义搜索知识库 |
| GET | /api/v1/knowledge/mrs | MR 知识记录列表 |
| POST | /api/v1/discovery/scan | 触发仓库自动发现扫描 |
| POST | /api/v1/discovery/register-webhooks | 为已发现仓库注册 Webhook |
| GET | /api/v1/discovery/projects | 列出已发现的仓库 |
| POST | /api/v1/discovery/projects/{id}/register | 为单个仓库注册 Webhook |
| GET | /api/v1/alerts/status | 告警系统状态 |
| POST | /api/v1/alerts/test | 发送测试告警 |
| POST | /api/v1/alerts/send-report | 发送日报邮件（可选 ?date_str=YYYY-MM-DD） |

## 测试

```bash
pytest tests/ -v
```

## 配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| GITLAB_URL | http://gitlab:80 | GitLab 地址 |
| GITLAB_API_TOKEN | - | GitLab API Token |
| WEBHOOK_SECRET | - | Webhook 密钥 |
| PORT | 8080 | 监听端口 |
| AI_ENABLED | false | 启用 AI 分析 |
| AI_API_KEY | - | DeepSeek API Key |
| AI_MODEL | deepseek-v4-flash | AI 模型 |
| KNOWLEDGE_ENABLED | true | 启用知识库 |
| ENGINES_IAC_ENABLED | true | 启用 IaC 扫描 |
| ENGINES_SAST_ENABLED | true | 启用 SAST 扫描 |
| ENGINES_SECRETS_ENABLED | true | 启用密钥检测 |
| AUTO_DISCOVERY_ENABLED | true | 启动时自动发现仓库并注册 Webhook |
| ALERT_ENABLED | true | 启用即时告警 |
| ALERT_SEVERITY_THRESHOLD | critical | 告警触发阈值（info/minor/major/critical/blocker） |
| ALERT_DINGTALK_WEBHOOK | - | 钉钉机器人 Webhook 地址 |
| ALERT_DINGTALK_SECRET | - | 钉钉机器人签名密钥 |
| ALERT_SLACK_WEBHOOK | - | Slack Incoming Webhook 地址 |
| ALERT_SMTP_HOST | - | SMTP 服务器地址（启用邮件告警） |
| ALERT_SMTP_PORT | 587 | SMTP 端口 |
| ALERT_SMTP_USER | - | SMTP 用户名 |
| ALERT_SMTP_PASSWORD | - | SMTP 密码 |
| ALERT_EMAIL_FROM | - | 发件人地址 |
| ALERT_EMAIL_TO | - | 收件人地址（逗号分隔） |
