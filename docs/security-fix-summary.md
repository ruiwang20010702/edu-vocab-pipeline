# 安全与性能风险修复总结

两份风险分析报告（`fix.md` 性能风险 10 项 + `fix2.md` 安全风险 10 项）共计 **20 项问题**，已**全部修复**。全量测试 709 个全部通过。

---

## fix.md — 性能风险（10/10 已修复）

### 高风险

| # | 问题 | 修复方式 | 涉及文件 |
|---|------|---------|---------|
| 1 | 大事务长时间持锁 | 生产流水线拆分为 4 个独立步骤，每步独立 session + commit | `routers/batch.py` |
| 2 | AI 调用无熔断 | 新建 `CircuitBreaker` 三态状态机（CLOSED→OPEN→HALF_OPEN），生成器和 L2 质检各自独立实例 | `circuit_breaker.py`（新建）、`generators/base.py`、`qc/layer2/ai_base.py`、`config.py` +2 配置项 |
| 3 | 导出全表加载 OOM | 分批生成器（batch_size=500）+ StreamingResponse 流式输出，内存从 O(N) 降至 O(500) | `export_service.py`、`routers/export.py` |
| 4 | 同步/异步桥接开销 | 提取公共 `async_bridge.run_async_in_sync()`，无 running loop 时直接 `asyncio.run()` 零开销 | `async_bridge.py`（新建）、`qc/layer2/runner.py` |

### 中风险

| # | 问题 | 修复方式 | 涉及文件 |
|---|------|---------|---------|
| 5 | 无缓存层 | 新建线程安全 `TTLCache`，Stats 查询缓存 10 秒 | `cache.py`（新建）、`stats_service.py` |
| 6 | 连接池偏小 | 显式配置 pool_size=20 / max_overflow=10 / pool_pre_ping / pool_recycle=1800 | `db.py` |
| 7 | 日志同步写 | QueueHandler + QueueListener 异步日志，请求线程只做 queue.put() | `main.py` |
| 8 | 重试无抖动 | L2 质检重试加 `random.uniform(0, 1)` 随机抖动，分散 thundering herd | `qc/layer2/ai_base.py` |

### 低风险

| # | 问题 | 修复方式 |
|---|------|---------|
| 9 | 临时对象 GC | 导出已改用分批生成器，每批处理完释放 |
| 10 | HTTP 客户端重建 | 模块级单例 + 双检锁，按事件循环缓存，应用关闭时优雅释放 |

---

## fix2.md — 安全风险（10/10 已修复）

### 高风险

| # | 问题 | 修复方式 | 涉及文件（行数） |
|---|------|---------|----------------|
| 高1 | AI API Key 明文存库 | L2 runner 改从 `settings.ai_api_key`（环境变量）读取，不再从 DB 读 `prompt.ai_api_key`；Prompt API schema 三处删除 `ai_api_key` 字段；service 层不再写入该字段。ORM 列保留避免数据库迁移 | `runner.py:54-63`、`schemas/prompt.py`（整文件重写，46→45 行）、`prompt_service.py:129,141` |
| 高2 | Nginx 无 TLS | `nginx.conf` 重写为 HTTPS 模板：80 端口 301 重定向 → 443 ssl http2 + TLS 1.2/1.3 + 安全套件 + HSTS。新建 `nginx-dev.conf` 保留纯 HTTP 开发配置 | `deploy/nginx.conf`（35→59 行）、`deploy/nginx-dev.conf`（新建 35 行） |
| 高3 | XSS HTML 过滤可绕过 | 在 `security.py` 新增统一 `reject_html_input()` 函数：正则加 `re.DOTALL`（覆盖换行绕过）+ 新增 `javascript:`/`data:` URI 检测。`review.py` 删除局部实现改用公共函数；`words.py` 从"剥离 HTML"改为"拒绝 HTML"策略，同时补上 `content_cn` 过滤 | `security.py:12-31`（新增 ~20 行）、`review.py:1-25`（删 ~15 行）、`words.py:182-186`（改 5 行） |
| 高4 | SSRF DNS Rebinding | 新增 `allowed_ai_hosts` 白名单配置。`validate_ai_url()` 优先检查 hostname 是否在白名单中，命中则跳过 DNS 解析（消除 TOCTOU 窗口）。生产环境强制白名单非空 | `config.py:32`（+1 行）、`config.py:99-100`（+2 行）、`security.py:50-52`（+3 行） |

### 中风险

| # | 问题 | 修复方式 | 涉及文件（行数） |
|---|------|---------|----------------|
| 中1 | JWT 存 localStorage | JWT 迁移到 httpOnly Cookie（`SameSite=Lax`）。`/verify` 通过 `Set-Cookie` 下发 token，JSON body 仅返回 user_name/user_role；新增 `/logout` 清除 cookie；`deps.py` Cookie 优先 + Authorization header 兼容；前端删除 `getToken()` 改用 `credentials:'include'`；config 新增 5 个 cookie 配置字段 + 生产环境 `cookie_secure` 校验 | `routers/auth.py`、`deps.py`、`schemas/auth.py`、`config.py`、`frontend/src/lib/api.ts`、`frontend/src/App.tsx`、`frontend/src/types.ts` |
| 中2 | 导出无限速 | `/download` 和 `/excel` 添加 `@limiter.limit("5/minute")` | `routers/export.py:55,70`（+2 行装饰器 + 函数签名加 `request: Request`） |
| 中3 | 健康检查无限速 | `/health` 添加 `@auth.limiter.limit("30/minute")` | `main.py:127`（+1 行装饰器 + 函数签名加 `request: Request`） |
| 中4 | 邮箱白名单可缺失 | `validate_production_config()` 的守卫条件从 `!= "production"` 改为 `not in ("production", "staging")`，staging 也纳入安全校验。`validate_email_domain()` 白名单为空时发出 warning（仅首次） | `config.py:67`（改 1 行）、`auth_service.py:25-37`（+13 行） |

### 低风险

| # | 问题 | 修复方式 | 涉及文件（行数） |
|---|------|---------|----------------|
| 低1 | 字段长度无限制 | 新增 5 个长度常量（word=100, pos=20, definition=500, source=200, ipa=200）+ `_truncate_field()` 辅助函数。`_parse_csv_text()` 和 `_parse_excel()` 中：超长 word 跳过，其余字段截断 + warning | `import_service.py:9-16,27-31`（+15 行常量和辅助函数）、CSV 解析（+5 行）、Excel 解析（+16 行） |
| 低2 | SMTP 密码泄日志 | `exc_info=True` 改为仅记录 `type(e).__name__`，不打完整 traceback | `routers/auth.py:52-53`（改 2 行） |

---

## 新增测试

| 测试文件 | 测试数 | 覆盖内容 |
|---------|--------|---------|
| `tests/unit/test_security_html.py` | 14 | `reject_html_input()` 全场景：标签/不闭合标签/换行绕过/事件处理器/实体编码/javascript:/data: URI |
| `tests/unit/test_import_field_length.py` | 7 | 字段截断/超长 word 跳过/正常数据不受影响 |
| `tests/integration/test_auth_api.py`（新增 3 个） | 3 | httpOnly cookie 标志验证 / cookie 认证端点访问 / logout 清除 cookie |

（fix.md 轮次另新增 `test_circuit_breaker.py` 9 个 + `test_ttl_cache.py` 8 个测试）

---

## 后续修复：AI Gateway 兼容性 & 熔断器健壮性（2026-03-17）

| # | 问题 | 修复方式 | 涉及文件 |
|---|------|---------|---------|
| 1 | sync_prompts 不更新 model | 更新分支增加 `existing.model = _model_for_dimension(dimension)` | `prompt_service.py` |
| 2 | 熔断器阈值过低（5），并发场景误触发 | 阈值 5→15（允许 5 个并发任务各失败 3 次才熔断） | `config.py` |
| 3 | .env 示例缺少 `\|efficiency` 后缀 | 模型名统一加 `\|efficiency` | `.env.example`、`.env.production.example` |

---

## 验证结果

```
PYTHONPATH=backend .venv/bin/pytest tests/ -x -q --tb=short
709 passed in 3.14s
```

---

## 对运维的回复（2026-03-17 代码审计核实）

以下是对 `fix.md`（性能）和 `fix2.md`（安全）两份风险分析报告中所有问题的逐项代码核实结果。

### fix.md — 性能风险 10 项：全部已实现 ✅

| # | 问题 | 状态 | 核实证据 |
|---|------|------|---------|
| 1 | 大事务长时间持锁 | ✅ | `routers/batch.py:234-317` — `_run_production_bg()` 拆为 4 步，每步独立 session + commit |
| 2 | AI 调用无熔断 | ✅ | `circuit_breaker.py:7-64` CircuitBreaker 三态类；`generators/base.py:15,22-25` 和 `ai_base.py:13,54-57` 均已接入 |
| 3 | 导出全表加载 OOM | ✅ | `export_service.py:55-147` `_iter_approved_batches()` 分批生成器（500条/批）；`routers/export.py:62,79` StreamingResponse |
| 4 | 同步/异步桥接开销 | ✅ | `async_bridge.py:7-19` `run_async_in_sync()` 函数，无 running loop 时零开销 |
| 5 | 无缓存层 | ✅ | `cache.py:11-46` TTLCache 类（线程安全）；`stats_service.py:16` `stats_cache = TTLCache(default_ttl=10.0)` |
| 6 | 连接池偏小 | ✅ | `db.py:22-26` pool_size=20, max_overflow=10, pool_pre_ping=True, pool_recycle=1800 |
| 7 | 日志同步写 | ✅ | `main.py:5,23-31` QueueHandler + QueueListener，后台线程异步消费 |
| 8 | 重试无抖动 | ✅ | `ai_base.py:117` 和 `generators/base.py:545,624` 均已加 `random.uniform(0, 1)` |
| 9 | 临时对象 GC | ✅ | 导出服务已用分批生成器，每批处理完释放，内存 O(500) |
| 10 | HTTP 客户端重建 | ✅ | `generators/base.py:322-391` 模块级单例 + 双检锁 + 事件循环缓存 + `close_http_clients()` 优雅关闭 |

### fix2.md — 安全风险 10 项：全部已实现 ✅

| # | 问题 | 状态 | 核实证据 |
|---|------|------|---------|
| 高1 | API Key 明文存库 | ✅ | `runner.py:60` 已从 `settings.ai_api_key`（环境变量）读取；`schemas/prompt.py` 响应模型已删除该字段；ORM 列保留是设计决策（避免数据库迁移），运行时不再从 DB 读取 Key |
| 高2 | Nginx 无 TLS | ✅ | `deploy/nginx.conf:5-7` HTTP 80 → 301 重定向；`:12` listen 443 ssl http2；`:20-24` TLSv1.2/1.3 + 安全套件；`:31` HSTS |
| 高3 | XSS HTML 过滤可绕过 | ✅ | `security.py:13` 正则含 `re.DOTALL`（覆盖换行绕过）；`:19` `reject_html_input()` 公共函数；`review.py:192-193` 已调用 |
| 高4 | SSRF DNS Rebinding | ✅ | `config.py:32` `allowed_ai_hosts` 白名单；`security.py:50-52` 白名单优先检查（消除 TOCTOU 窗口） |
| 中1 | JWT 存 localStorage | ✅ | `routers/auth.py:62-75` `_set_token_cookie()` httpOnly Cookie；`api.ts:30` `credentials:'include'` |
| 中2 | 导出无限速 | ✅ | `routers/export.py:55,70` `@limiter.limit("5/minute")` |
| 中3 | 健康检查无限速 | ✅ | `main.py:127` `@auth.limiter.limit("30/minute")` |
| 中4 | 邮箱白名单可缺失 | ✅ | `config.py:74` staging 环境纳入校验；`auth_service.py:28-40` 白名单为空时 warning |
| 低1 | 字段长度无限制 | ✅ | `import_service.py:12-16` 5 个长度常量；`:27-32` `_truncate_field()` 函数 |
| 低2 | SMTP 密码泄日志 | ✅ | `routers/auth.py:54` 仅记录 `type(e).__name__`，不打完整 traceback |

### 结论

> **两份风险分析报告共 20 项问题，已全部在代码中落地实现。**
> 709 个测试全部通过，前端编译无错。
>
> 部署注意事项：
> 1. **TLS 证书**：`nginx.conf` 中引用了 `/etc/nginx/ssl/cert.pem` 和 `key.pem`，部署前需确保证书文件到位
> 2. **环境变量**：`VOCAB_QC_AI_API_KEY` 必须通过环境变量设置，不再从数据库读取
> 3. **白名单**：生产环境 `VOCAB_QC_ALLOWED_AI_HOSTS` 和 `VOCAB_QC_ALLOWED_EMAIL_DOMAINS` 必须非空
> 4. **Cookie**：生产环境 `VOCAB_QC_COOKIE_SECURE=true`（需 HTTPS）
