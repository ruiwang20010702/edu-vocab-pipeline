# 第二轮审计 — 未修复项清单

> 已修复 10 项（S-H1/H2/H3, F-H1/H2/H3, F-M1, P-M2/M3, 009 migration），545 测试全绿。
> 以下为尚未动的项目，按优先级排列。

---

## 第二优先级（上线后一周内）

| # | 编号 | 问题 | 文件 | 修复方案 | 预计工时 | 备注 |
|---|------|------|------|---------|---------|------|
| 1 | P-H1 | `asyncio.run()` 每次创建新事件循环 | `production_service.py` L354 | 改为复用已有 loop 或 `loop.run_until_complete()` | 15min | 当前已有 try/except 分支 + ThreadPoolExecutor 兜底，不会阻塞主线程；但频繁创建/销毁 loop 有微量开销 |
| 2 | P-H2 | httpx.AsyncClient 在 `asyncio.run()` 场景下可能泄漏 | `generators/base.py` L39-56 | 在 `_generate_all()` 结束前显式 `await client.aclose()` | 15min | 当前 `_get_async_http_client()` 按 loop 缓存 + lifespan 关闭，正常 FastAPI 路径无泄漏；仅 CLI 同步调用路径有风险 |
| 3 | PM-H3 | Prompt 文件修改后 DB 不自动同步 | `prompt_service.py` | 新增 `sync_prompts()` 功能：Prompt 模型加 `source`/`file_hash` 字段，启动时自动对比文件 hash 与 DB，文件变更自动更新 DB，用户手动编辑过的不覆盖；新增管理 API（preview + sync） | 1h | 当前 `seed_defaults()` 仅在 DB 为空时导入，后续文件修改不生效 |

## 第三优先级（持续优化）

### 安全

| # | 编号 | 问题 | 文件 | 修复建议 | 备注 |
|---|------|------|------|---------|------|
| 3 | S-M2 | Prompt Injection 风险（word/meaning 拼入 prompt） | `generators/base.py` | 对 word/meaning 做 sanitize（去掉特殊指令字符） | 内部系统风险低，输入来自管理员导入的教材词表 |
| 4 | S-M3 | 后台生产任务无单任务超时控制 | `batch.py` | 给 `_run_production_bg` 加 `asyncio.wait_for` 单步超时 | 已有 5 分钟总超时；单步超时可防个别 AI 调用卡死 |
| 5 | S-M4 | openpyxl 未用 defusedxml | `import_service.py` | `pip install defusedxml`，openpyxl 自动使用 | 防止 XXE 攻击；内部系统上传者均为管理员 |
| 6 | S-L1 | localStorage 存 JWT Token | 前端 `lib/auth.ts` | 改为 HttpOnly cookie + CSRF token | 内部系统可接受，长期改善 |
| 7 | S-L2 | Dockerfile 未固定基础镜像 digest | `Dockerfile` | `python:3.12-slim@sha256:xxx` | 防止供应链攻击，CI 环境建议锁定 |
| 8 | S-L3 | 验证码 6 位纯数字 | `auth_service.py` | 当前 5 次尝试限制已足够 | 无需修改 |

### 性能

| # | 编号 | 问题 | 文件 | 修复建议 | 备注 |
|---|------|------|------|---------|------|
| 9 | P-M1 | Excel 导出全量加载内存 | `export_service.py` | 用 openpyxl `write_only` 模式流式写入 | 当前数据量小（百级单词），千级以上需优化 |

### 前端

| # | 编号 | 问题 | 文件 | 修复建议 | 备注 |
|---|------|------|------|---------|------|
| 10 | F-M2 | regenerate 后重复拉取 WordDetail | `WordReviewModal.tsx` | 用局部 state 更新代替全量 refetch | 优化性改动，不影响正确性 |
| 11 | F-M3 | AdminPage 编辑状态未做乐观更新 | `AdminPage.tsx` | 编辑成功后直接更新本地 state | 当前已用 `setUsers(prev => prev.map(...))` 做了局部更新，基本满足 |

---

## 风险评估

- **P-H1/P-H2**：仅影响 CLI 同步调用路径和极端并发场景，FastAPI 正常路径无问题
- **S-M2~M4**：内部系统，输入源可控（管理员上传教材词表），风险等级低
- **P-M1**：当前数据量（数百单词）不会触发内存问题，千级以上需处理
- **F-M2/F-M3**：体验优化，不影响功能正确性
