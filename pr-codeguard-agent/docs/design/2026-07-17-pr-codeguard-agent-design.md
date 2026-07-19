# PR-CodeGuard Agent 架构设计

## 概述

将 PR-CodeGuard 从"固定管线的扫描程序"升级为"具备记忆和决策能力的代码审查 Agent"。
核心变化：
- 引入向量知识库（Chroma）记录代码语义和历史变更
- 引入 LLM 驱动的"大脑"决策事件处理流程
- 将扫描、理解、存储、输出抽象为独立工具

## 架构总览

```
外部触发 (GitLab Webhook / 用户提问)
        │
        ▼
┌─────────────────────────────────┐
│        Agent 大脑 (LLM 驱动)      │
│  ① 理解上下文 → ② 制定计划       │
│  ③ 执行工具 → ④ 综合输出         │
└──┬──┬──┬──┬──┬─────────────────┘
   │  │  │  │  │
   ▼  ▼  ▼  ▼  ▼
 扫描 语义 知识 评论 基线
 工具 分析 库  输出  构建
        │          │
        ▼          ▼
    ┌──────┐  ┌──────────┐
    │Chroma│  │ SQLite   │
    │向量库 │  │ 结构化数据│
    └──────┘  └──────────┘
```

## 存储层设计

### SQLite 结构化表

```sql
CREATE TABLE project_baseline (
    id INTEGER PRIMARY KEY,
    repo_url TEXT NOT NULL,
    default_branch TEXT,
    total_files INTEGER,
    total_modules INTEGER,
    tech_stack TEXT,
    summary TEXT,
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE modules (
    id INTEGER PRIMARY KEY,
    baseline_id INTEGER REFERENCES project_baseline(id),
    name TEXT NOT NULL,
    description TEXT,
    relative_path TEXT,
    created_at DATETIME
);

CREATE TABLE interfaces (
    id INTEGER PRIMARY KEY,
    module_id INTEGER REFERENCES modules(id),
    name TEXT NOT NULL,
    type TEXT,
    signature TEXT,
    description TEXT,
    file_path TEXT,
    line_number INTEGER,
    created_at DATETIME
);

CREATE TABLE mr_records (
    id INTEGER PRIMARY KEY,
    repo_url TEXT NOT NULL,
    mr_id INTEGER NOT NULL,
    mr_title TEXT,
    mr_description TEXT,
    source_branch TEXT,
    target_branch TEXT,
    author TEXT,
    merged_by TEXT,
    merged_at DATETIME,
    summary TEXT,
    risks TEXT,
    interfaces_changed TEXT,
    chroma_ids TEXT,
    created_at DATETIME
);
```

### Chroma 向量集合

- `code_chunks` — 代码片段语义向量（嵌入文件摘要、函数说明）
- `mr_semantics` — MR 变更语义向量（变更意图、影响范围）

## Agent 大脑

事件驱动流程：

1. 事件分类（MR 事件 / 用户提问 / 定时任务）
2. LLM 分析上下文，输出 JSON 格式的"行动计划"
3. 按顺序执行工具调用，每个工具返回结果
4. LLM 汇总工具结果，生成最终输出（评论/回答）

### 工具定义

| 工具 | 说明 |
|------|------|
| get_diff | 从 GitLab 获取 MR diff |
| run_scanners | 运行现有扫描引擎 |
| semantic_analyze | LLM 理解变更语义 |
| check_knowledge | 搜索知识库 |
| write_knowledge | 写入 Chroma + SQLite |
| build_baseline | 全库基线构建 |
| write_comment | 写 MR 评论 |
| answer_question | 回答用户问题 |

## 文件组织

```
app/
├── agent/          ← 新增：大脑层
│   ├── __init__.py
│   ├── brain.py    ← LLM 决策循环入口
│   ├── planner.py  ← 计划生成
│   └── executor.py ← 工具执行器
├── tools/          ← 新增：工具层
│   ├── __init__.py
│   ├── base.py
│   ├── scanner.py
│   ├── diff_analyzer.py
│   ├── knowledge_writer.py
│   ├── knowledge_reader.py
│   ├── baseline_builder.py
│   └── gitlab_commenter.py
├── knowledge/      ← 新增：知识库层
│   ├── __init__.py
│   ├── chroma_store.py
│   ├── sqlite_store.py
│   └── schemas.py
├── engine/         ← 现有，不变
├── services/       ← 现有，不变
└── config.py       ← 现有 + 新增配置
```

## 实施路线

### 阶段一：知识库基础 + 基线构建
1. Chroma + SQLite 基础设施搭建
2. 全库基线构建器（遍历项目 → LLM 理解 → 入库）
3. Agent 大脑雏形（代替当前固定管线）
4. MR 语义记录

### 阶段二：MR 深度审查
1. 语义增强的扫描结果
2. 知识增强的评论（引用历史记录）
3. 智能排序和分类

### 阶段三：问答接口
1. POST /api/v1/ask 自然语言问答
2. 多轮对话上下文
3. 可视化的变更历史时间线
