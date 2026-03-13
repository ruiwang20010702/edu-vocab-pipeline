# 第二轮审计 — 未修复项清单

> 已修复 10 项（S-H1/H2/H3, F-H1/H2/H3, F-M1, P-M2/M3, 009 migration），545 测试全绿。
> **第三轮修复（2026-03-13）：全部 9 项已修复，572 测试全绿。**

---

## 第二优先级（上线后一周内）— ✅ 已全部修复

| # | 编号 | 问题 | 状态 | 修复说明 |
|---|------|------|------|---------|
| 1 | P-H1 | `asyncio.run()` 每次创建新事件循环 | ✅ 已修复 | 提取 `async_bridge.run_async_in_sync()` 公共函数，production_service + layer2/runner 共用 |
| 2 | P-H2 | httpx.AsyncClient CLI 路径泄漏 | ✅ 已修复 | `_generate_all()` 结束前调用 `close_http_clients()` |
| 3 | PM-H3 | Prompt 文件修改后 DB 不自动同步 | ✅ 已修复 | Prompt 模型新增 `source`/`file_hash` 字段 + `sync_prompts()` 服务 + API 端点 + 启动自动同步 |

## 第三优先级（持续优化）— ✅ 已全部修复

### 安全

| # | 编号 | 问题 | 状态 | 修复说明 |
|---|------|------|------|---------|
| 3 | S-M2 | Prompt Injection 风险 | ✅ 已修复 | `sanitize_prompt_input()` 过滤注入模式、控制字符、截断长度；chunk/sentence/mnemonic 调用 |
| 4 | S-M3 | 后台生产任务无单任务超时 | ✅ 已修复 | `asyncio.wait_for(timeout=ai_task_timeout)` 包装每个 AI 调用 |
| 5 | S-M4 | openpyxl 未用 defusedxml | ✅ 已修复 | `pyproject.toml` 添加 `defusedxml>=0.7.1`，openpyxl 自动使用 |
| 6 | S-L1 | localStorage 存 JWT Token | ⏸ 暂缓 | 内部系统，改 httpOnly cookie 工作量大，暂不处理 |
| 7 | S-L2 | Dockerfile 未固定基础镜像 digest | ✅ 已修复 | 三个 FROM 行均添加 `@sha256:...` |
| 8 | S-L3 | 验证码 6 位纯数字 | ⏭ 无需修复 | 已有 5 次尝试限制 |

### 性能

| # | 编号 | 问题 | 状态 | 修复说明 |
|---|------|------|------|---------|
| 9 | P-M1 | Excel 导出全量加载内存 | ✅ 已修复 | 新增 `_iter_approved_batches()` 分批查询（每批 500），`export_to_excel` 逐批写入 |

### 前端

| # | 编号 | 问题 | 状态 | 修复说明 |
|---|------|------|------|---------|
| 10 | F-M2 | regenerate 后重复拉取 WordDetail | ✅ 已修复 | useEffect 添加 AbortController 防并发；api.get 支持 signal 参数 |
| 11 | F-M3 | AdminPage 乐观更新 | ⏭ 无需修复 | 已用 API 返回值更新本地 state，设计合理 |
