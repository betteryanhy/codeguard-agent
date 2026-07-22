# 手动扫描功能测试计划

## 测试范围

手动扫描功能：`POST /api/v1/scan/repo` 和 `POST /api/v1/scan/all` 的端到端测试。

---

## 测试用例

### TC1: 单项目扫描成功

| 项目 | 内容 |
|------|------|
| **前置** | 项目已发现（discovery 有数据），repo_url 有效 |
| **步骤** | 1. 在仪表盘页点击项目卡片上的「扫描」按钮<br>2. 观察按钮显示 loading<br>3. 等待扫描完成 |
| **预期** | 扫描完成后提示"扫描完成: N 个发现"，页面自动刷新，项目风险状态更新 |

### TC2: 扫描超时

| 项目 | 内容 |
|------|------|
| **前置** | Trivy 扫描需要较长时间（首次扫描下载 DB） |
| **步骤** | 1. 点击「扫描」按钮<br>2. 等待超过 30s |
| **预期** | **修复前**：30s 后报 timeout 错误<br>**修复后**：5 分钟内扫描不超时，正常返回结果 |

### TC3: 扫描按钮状态

| 项目 | 内容 |
|------|------|
| **前置** | 2+ 个项目均可扫描 |
| **步骤** | 1. 点击项目 A 的「扫描」按钮<br>2. 观察项目 A 按钮状态<br>3. 观察项目 B 按钮状态 |
| **预期** | 项目 A 按钮显示 loading 并禁用；项目 B 按钮正常可点击；多个项目可同时并行扫描 |

### TC4: 分支风险页扫描

| 项目 | 内容 |
|------|------|
| **前置** | 分支风险页有项目列表 |
| **步骤** | 1. 切换到「分支风险」Tab<br>2. 点击某个项目行的「扫描」按钮 |
| **预期** | 扫描正常执行，完成后页面刷新，发现数和风险等级更新 |

### TC5: 空状态引导

| 项目 | 内容 |
|------|------|
| **前置** | 有已发现项目，但所有项目都无扫描数据 |
| **步骤** | 1. 打开仪表盘页<br>2. 观察项目卡片区上方 |
| **预期** | 显示"暂无扫描数据，点击项目卡片上的「扫描」按钮开始首次扫描"引导文本 |

### TC6: 全量扫描 API

| 项目 | 内容 |
|------|------|
| **前置** | 多个已发现项目 |
| **步骤** | 1. 调用 `POST /api/v1/scan/all`<br>2. 等待返回 |
| **预期** | 返回 `{ "results": [...], "total": N }`，每个项目有 findings_count 和 status |

### TC7: 定时扫描触发

| 项目 | 内容 |
|------|------|
| **前置** | `auto_scan_enabled=true`，`auto_scan_time=02:00` |
| **步骤** | 1. 查看 agent 启动日志<br>2. 确认定时任务已注册 |
| **预期** | 日志输出 "Auto scan enabled, scheduled at 02:00 daily" |

---

## API 测试用例

### TC8: 无效 repo_url

```bash
curl -X POST http://localhost:8082/api/v1/scan/repo \
  -H "Content-Type: application/json" \
  -d '{"repo_url": ""}'
```
预期：400 响应 `{"detail": "repo_url is required"}`

### TC9: 扫描结果完整性

```bash
curl -X POST http://localhost:8082/api/v1/scan/repo \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "http://localhost/root/test-python-app.git"}'
```
预期：返回 `task_id`, `status`, `findings_count`, `by_severity`, `findings[]` 等字段
