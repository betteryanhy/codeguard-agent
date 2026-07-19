<div align="center">

# 🔒 CodeGuard Agent

**AI 驱动的代码审查 Agent — 让 GitLab Merge Request 自动获得智能安全审查**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/betteryanhy/codeguard-agent?style=social)](https://github.com/betteryanhy/codeguard-agent)

</div>

## 📦 项目结构

```
codeguard-agent/
├── pr-codeguard-agent/    # Agent 核心源码
│   ├── app/               # 应用代码
│   ├── tests/             # 测试
│   └── requirements.txt   # Python 依赖
└── .gitignore
```

## 🚀 快速开始

```bash
cd pr-codeguard-agent
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 配置 GitLab 连接信息
python -m uvicorn app.main:app --host 0.0.0.0 --port 8082
```

更多信息请查看 [pr-codeguard-agent/README.md](pr-codeguard-agent/README.md)。

## ⚡ 核心特性

- **多引擎安全扫描** — Gitleaks、Semgrep、Checkov 协同工作
- **AI Agent 决策** — LLM 驱动的智能扫描规划
- **知识库系统** — SQLite + Chroma 双重存储，支持语义搜索
- **按仓库自定义策略** — 每个仓库独立配置扫描等级
- **即时告警** — 钉钉 / Slack / 邮件通知
- **日报与趋势** — 开发者产出和代码质量趋势分析

## 📄 许可证

MIT License
