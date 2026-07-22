# PR-CodeGuard 功能总结

## 概述

PR-CodeGuard 是一个自动化的 Merge Request 代码审查 Agent，集成 GitLab Webhook，在 MR 创建/更新时自动执行多引擎扫描，并将审查结果以评论形式发布到 MR 中，帮助审批人快速评估风险。

---

## 核心功能

### 1. 多引擎扫描

| 引擎 | 扫描内容 | 检测类型 |
|------|---------|---------|
| **Trivy (SCA)** | 依赖漏洞扫描 | `vuln` — CVE 漏洞、`secret` — 敏感信息泄露、`misconfig` — IaC 配置错误、`license` — 许可证合规 |
| **Secrets Scanner** | 硬编码密钥检测 | Base64 高熵字符串、API Token、密码、私钥等 |
| **SAST Scanner (Semgrep)** | 静态代码分析 | SQL 注入、XSS、命令注入、路径遍历等常见漏洞模式 |
| **IaC Scanner** | 基础设施即代码检查 | Terraform/K8s 配置最佳实践、安全基线违规 |
| **Best Practice Scanner** | 代码规范检查 | 代码风格、常见错误模式 |

### 2. MR 自动审查

- **Webhook 触发**：GitLab MR `open`/`reopen`/`update` 事件自动触发扫描
- **差异化扫描**：仅扫描 MR 中变更的文件，提高效率
- **评论发布**：扫描完成后自动在 MR 中发布审查报告评论
- **评论更新**：新推送时清理旧评论并发布新评论

### 3. 审查报告内容

MR 评论包含以下章节：

```
## PR-CodeGuard 审查报告

### 风险评价
- 严重度统计表（Blocker / Critical / Major / Minor / Info）
- 整体风险评级与建议

### 组件风险总览
- 按组件（Package）分组的漏洞统计
- 最高严重度、建议修复版本

### 变更概览
- 新增/删除/修改的文件列表
- 代码行数变更统计（+/-）

### 风险详情
- 按严重度分组的详细发现列表
- 每条发现包含：文件位置、引擎类型、问题描述、修复建议、代码片段
- AI 智能解释（可选，需配置 AI API）

### 基础设施架构影响分析（IaC 项目专用）
- 新增/删除/修改的 Terraform 资源清单
- 架构影响评估（基础设施状态、依赖关系、安全合规）
- AWS/K8s 资源类型提醒
- 变更文件明细
```

### 4. 基础设施架构影响分析（IaC 增强）

针对 Terraform 项目的 MR，自动解析 diff 识别资源变更：

- **资源识别**：分析 `resource`、`data`、`module`、`variable`、`output` 等块
- **变更分类**：识别新增、删除、修改的资源
- **影响评估**：说明对基础设施状态、依赖关系、安全合规的潜在影响
- **平台提醒**：根据资源类型（AWS/K8s）给出针对性建议

### 5. 前端仪表盘

- **分支风险看板**：按项目/分支展示扫描结果，支持去重展示
- **任务列表**：查看所有扫描任务状态和结果
- **策略配置**：按项目配置扫描策略（启用/禁用特定引擎、设置严重度阈值）
- **安全设置**：用户认证、审计日志
- **报表导出**：扫描结果统计与趋势

### 6. 自动发现与注册

- **项目自动发现**：自动扫描 GitLab 中的项目并分类（Python/Go/Node/IaC 等）
- **Webhook 自动注册**：为新发现的项目自动注册 MR 事件 Webhook
- **周期同步**：定期同步项目列表，检测新增/删除项目

### 7. 定时扫描与邮件报告

- **每日定时扫描**：在指定时间对所有项目执行全量扫描
- **邮件报告**：通过 SMTP 发送日报，包含扫描摘要、组件漏洞、开发者活动

### 8. 知识库与查询（Beta）

- **事件记录**：监听 GitLab System Hook，记录 Push/MR/Tag 事件
- **向量检索**：支持自然语言查询历史事件和扫描结果
- **查询页面**：简易前端查询界面

---

## 架构

```
┌─────────────┐     ┌─────────────────────────────────────────────┐
│   GitLab    │────▶│              PR-CodeGuard Agent             │
│             │     │                                             │
│  MR Events  │     │  Webhook → Orchestrator → Scan Engines     │
│  Push Events│     │       ↓                                    │
│  System Hook│     │  CommentBuilder → GitLab MR Comment         │
│             │     │       ↓                                    │
│             │     │  StorageService (SQLite)                    │
│             │     │       ↓                                    │
│             │     │  KnowledgeBase (Chroma + SQLite)            │
│             │     │       ↓                                    │
│             │     │  Frontend (Vue 3 + Element Plus)            │
└─────────────┘     └─────────────────────────────────────────────┘
```

### 技术栈

| 层 | 技术 |
|----|------|
| 框架 | Python 3.11+ / FastAPI |
| 扫描引擎 | Trivy (Go), Semgrep (OCaml/ Python), 自研 Python 引擎 |
| 前端 | Vue 3 + Element Plus + ECharts |
| 存储 | SQLite + ChromaDB (向量) |
| AI | 兼容 OpenAI API (DeepSeek / OpenAI) |
| 部署 | Docker / Uvicorn |

---

## 快速开始

```bash
# 1. 复制配置
cp pr-codeguard-agent/.env.example pr-codeguard-agent/.env
# 编辑 .env 填入 GitLab 地址和 Token

# 2. 安装依赖
cd pr-codeguard-agent
pip install -r requirements.txt

# 3. 启动
uvicorn app.main:app --host 0.0.0.0 --port 8082

# 4. 在 GitLab 中为项目配置 Webhook
# URL: http://your-agent:8082/api/v1/webhook/gitlab
# Secret: 与 WEBHOOK_SECRET 一致
# 勾选: Merge Request events
```

---

## 配置说明

核心环境变量（详见 `.env.example`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GITLAB_URL` | GitLab 地址 | `http://gitlab:80` |
| `GITLAB_API_TOKEN` | API Token（需 Repoter+ 权限） | — |
| `HOST` / `PORT` | Agent 监听地址 | `0.0.0.0:8082` |
| `ENGINES_*` | 各引擎开关 | `true` |
| `TRIVY_*` | Trivy 扫描配置 | — |
| `AI_ENABLED` / `AI_API_KEY` | AI 评论增强（可选） | `false` |
| `ALERT_*` | 邮件/钉钉/ Slack 通知（可选） | — |

---

## 项目结构

```
pr-codeguard/
├── pr-codeguard-agent/         # Agent 主项目
│   ├── app/
│   │   ├── api/                # FastAPI 路由
│   │   ├── engine/             # 扫描引擎
│   │   ├── models/             # 数据模型
│   │   ├── services/           # 业务逻辑
│   │   ├── tools/              # 工具函数
│   │   └── main.py             # 入口
│   ├── frontend/               # Vue 3 前端
│   ├── tests/                  # 测试
│   └── requirements.txt
├── docker-compose.yml          # GitLab CE（测试用）
└── .gitignore
```
