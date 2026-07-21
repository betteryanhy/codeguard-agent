# PR-CodeGuard 前端精简重构设计

## 背景

当前前端基于 Vue 3 + Element Plus，包含 7 个独立页面（Dashboard、Repositories、Tasks、TaskDetail、Strategy、Assistant、Reports、Alerts），通过侧边栏导航。用户反馈：

1. 打开后不知道如何开始使用，缺少清晰引导
2. 功能与日常需求不对齐，大量页面不常用
3. 页面视觉上显得沉重

## 目标

将前端精简为 3-Tab 结构，聚焦核心高频操作，降低认知负担，提升日常使用效率。

## 整体架构

### 布局

去掉侧边栏左侧导航，改为顶部 Tab 栏 + 内容区的两段式布局。

```
┌──────────────────────────────────────────────────┐
│ 🔒 CodeGuard    [仪表盘] [分支风险] [问答]   🟢  │  ← Tab 栏 + 状态
├──────────────────────────────────────────────────┤
│                                                  │
│                 当前 Tab 内容区                     │  ← 主要内容
│                                                  │
├──────────────────────────────────────────────────┤
│ v0.1.0                                           │  ← 简约 footer
└──────────────────────────────────────────────────┘
```

### 路由设计

使用 Vue Router Hash 模式，3 条路由：

| 路径 | 名称 | 组件 | Tab 标题 |
|------|------|------|---------|
| `/` | - | 重定向到 `/dashboard` | - |
| `/dashboard` | Dashboard | Dashboard.vue | 仪表盘 |
| `/risk` | Risk | Risk.vue (新建) | 分支风险 |
| `/assistant` | Assistant | Assistant.vue (现有) | 问答 |

### 文件变动

#### 删除（不再需要）
- `src/views/Repositories.vue`
- `src/views/Tasks.vue`
- `src/views/TaskDetail.vue`
- `src/views/Reports.vue`
- `src/views/Alerts.vue`
- `src/views/Knowledge.vue`
- `src/views/Chat.vue`

#### 保留并修改
- `src/views/Dashboard.vue` → 重写为仪表盘 Tab
- `src/views/Strategy.vue` → 保留但入口隐藏（仪表盘右上角设置按钮）
- `src/views/Assistant.vue` → 保持为问答 Tab

#### 布局相关
- `src/layout/MainLayout.vue` → 改为 3-Tab 布局
- `src/router/index.js` → 简化为 3 条路由

#### 新建
- `src/views/Risk.vue` → 分支风险 Tab

## Tab 一：仪表盘

### 布局

上下两部分排列。

#### 上半部分：双列布局

左侧 - **项目风险卡片网格**（2 列或 3 列弹性网格）：
- 每个项目一张卡片
- 显示：项目名称、风险状态灯（🟢 安全 / 🟡 中危 / 🔴 高危）、高危发现数、最后扫描时间
- 卡片点击跳转到 `/#/risk` 并自动展开该项目

右侧 - **开发者活跃度列表**：
- 顶部时间筛选器：日 / 周 / 月 / 总计
- 开发者卡片列表，按提交数降序排列
- 每张卡片：姓名、提交数、MR 数、+/- 行变更
- 数据来源：`GET /api/v1/query/trends?days=N`

#### 下半部分：统计数字行

4 个关键数字横排展示：
- 监控项目数
- 高危发现总数
- 本周提交数
- 活跃开发者数

### 数据来源

| 数据 | API | 备注 |
|------|-----|------|
| 项目列表 | `GET /api/v1/discovery/projects` | 含项目名称 |
| 项目风险 | 扫描任务结果聚合 | - |
| 开发者活动 | `GET /api/v1/query/trends?days=7` | 日/周/月/总计 |
| 高危发现数 | 统计所有项目 critical 级别发现 | - |

## Tab 二：分支风险

### 布局

列表样式，每行一个项目，可展开显示分支。

#### 未展开状态

```
📁 项目名                    🟡 中危 · 3 个发现    ▸
📁 另一个项目                🟢 安全  · 0 个发现    ▸
```

#### 展开状态

```
📁 backend-api               🟡 中危 · 3 个发现    ▾
  ├── main (默认)            🟡 中危  2🔴 3🟡 1🔵
  │   扫描时间: 2026-07-21 09:15
  │   ┌─────────────────────────────────────────┐
  │   │ 🔴 Critical  SQL注入漏洞                │
  │   │    app/auth/login.py:42                 │
  │   │    Trivy · CVE-2026-1234               │
  │   ├─────────────────────────────────────────┤
  │   │ 🔴 Critical  硬编码密钥泄露             │
  │   │    config/secrets.py:15                 │
  │   │    Semgrep · rule:hardcoded-secret      │
  │   ├─────────────────────────────────────────┤
  │   │ 🟡 Major  不安全的日志配置              │
  │   │    app/logging.py:88                    │
  │   │    Best Practice · rule:log-config      │
  │   └─────────────────────────────────────────┘
  ├── develop                 🟢 安全  0 发现
  └── feature/payment         🔴 高危  1🔴 1🟡
```

#### 交互行为

1. 点击项目行 → 展开/收起该项目的分支列表
2. 点击分支行 → 展开/收起该分支的发现详情面板
3. 发现详情面板内联显示，不跳转页面
4. 发现包含：严重等级徽标、描述、文件路径、引擎类型、CVE/规则ID
5. 面板顶部显示最近一次扫描时间

#### 搜索筛选

- 顶部搜索框：按项目名模糊搜索
- 复选框："仅显示有风险的项目"

## Tab 三：问答

保留现有 `Assistant.vue`，功能不变。

## API 数据需求

分支风险 Tab 需要聚合扫描结果数据。当前可用的 API：

| API | 用途 |
|-----|------|
| `GET /api/v1/discovery/projects` | 获取所有项目列表 |
| `GET /api/v1/tasks/?skip=0&limit=100` | 获取扫描任务（可按项目筛选） |
| `GET /api/v1/results/{taskId}` | 获取某个任务的详细扫描结果 |

前端将在 Risk.vue 中聚合这些数据：调用 `listProjects()` 获取项目 → 对每个项目调用 `listTasks(0, 5)` 过滤最近任务 → 对最新任务调用 `getResult()` 获取发现。

## 实施步骤

1. 修改 `MainLayout.vue`：去掉侧边栏，改为顶部 Tab 栏
2. 修改 `router/index.js`：简化为 3 条路由
3. 重写 `Dashboard.vue`：双列布局 + 统计行
4. 新建 `Risk.vue`：项目 + 分支 + 内联详情
5. 清理不需要的页面组件文件
6. 重新构建前端：`npm run build`

## 不包含的范围

- 不替换 UI 框架（Element Plus 保持）
- 不修改后端 API
- 不删除数据库中的历史数据
- 不修改现有的 Assistant 问答功能
