安全漏洞修复回复报告

针对 fix3.md 提出的 10 项安全漏洞（4 高 / 4 中 / 2 低），逐项核实代码后确认：7 项在此前迭代中已修复（报告未反映最新代码），实际仅剩 3 项需要处理，现已全部修复完毕。

---

高风险（4项）

**H1 — AI API Key 明文存库**

报告描述：prompt.py:30 的 ai_api_key 字段使用 String(200) 明文存储，存在数据库泄露风险。

状态：✅ 已修复

经全量代码搜索确认，ai_api_key 是一个死字段——PromptCreateRequest、PromptUpdateRequest、PromptResponse 三个 Pydantic schema 均不含此字段，prompt_service 的 create/update 不处理此字段，所有 AI 调用均从 settings.ai_api_key 环境变量获取密钥。该字段从未被任何代码路径读写过。

已修复内容：直接从 ORM 模型中删除该字段（比加密更安全——不存在的字段不可能泄露）。models/prompt.py 删除 ai_api_key 字段定义，新建迁移 014_remove_prompt_ai_api_key.py 执行 drop_column。

---

**H2 — Nginx 无 TLS**

报告描述：nginx.conf 仍只有 listen 80，无 TLS 配置。

状态：⏭️ 忽略

报告自身已标注"可忽略"。TLS 由 SLB 终结，Nginx 只负责内网转发，listen 80 是正确的架构选择，不构成漏洞。

---

**H3 — XSS 正则绕过**

报告描述：_HTML_TAG_RE 缺少 re.DOTALL，多行标签如 `<img\nsrc=x\nonerror=alert(1)>` 可绕过；words.py 的 re.sub 同样无 DOTALL。

状态：✅ 早已修复（报告与代码不符）

security.py:13 实际代码为 `_HTML_TAG_RE = re.compile(r"<\s*/?[a-zA-Z][^>]*?>?", re.DOTALL)`，re.DOTALL 已存在，换行符会被 `.` 匹配，多行标签会被拦截。同时 words.py 的内容修改端点已接入 reject_html_input，做 4 层检测（HTML 标签、事件处理器、HTML 实体、危险 URI），XSS 攻击面已封闭。

---

**H4 — SSRF DNS Rebinding（TOCTOU）**

报告描述：security.py 先用 gethostbyname 验证 IP，httpx 发请求时再次解析 DNS，两次解析之间存在时间窗口，攻击者可通过 DNS Rebinding 让第一次解析返回公网 IP 通过检查、第二次解析返回内网 IP 实现 SSRF。

状态：✅ 已修复

已修复内容分两步。第一步改造 security.py：validate_ai_url 的返回类型从 None 改为 str|None，白名单主机仍返回 None（直接使用原始 URL），非白名单主机解析 DNS 后检查 IP 安全性，通过则返回解析后的 IP 字符串；同时抽取 _check_ip_safety() 辅助函数封装 IP 安全检查逻辑。第二步改造 base.py：_do_request（同步）和 _call_ai_async（异步）两个方法中，当 validate_ai_url 返回了 resolved IP 时，将请求 URL 中的 hostname 替换为该 IP，同时设置 Host header 为原始 hostname（保证服务端虚拟主机路由正常）。这样 httpx 直接连接已验证的 IP 地址，消除了二次 DNS 解析的 TOCTOU 窗口。

---

中风险（4项）

**M1 — JWT 存 localStorage**

报告描述：auth.ts:10 仍使用 localStorage.getItem/setItem 存储 JWT，存在 XSS 窃取风险。

状态：✅ 早已修复（报告与代码不符）

报告混淆了"用户展示信息"和"认证令牌"。auth.ts 中 localStorage 只存储 `{ user_name, user_role }` 两个展示用字段（AuthUser 类型定义仅含 user_name: string 和 user_role: string），JWT 令牌通过后端 set_cookie(httponly=True) 设置在 httpOnly Cookie 中，JavaScript 无法访问。攻击链不成立。

---

**M2 — 导出端点无限速**

报告描述：export.py 的下载端点均无 @limiter.limit()。

状态：✅ 已修复

export.py 中 /download 和 /excel 已有 @limiter.limit("5/minute")，但 /word/{word_id} 和 /readiness 两个端点遗漏了限速。

已修复内容：export_word 加 @limiter.limit("30/minute") + 函数签名加 request: Request；export_readiness 加 @limiter.limit("30/minute") + 函数签名加 request: Request。至此 export router 全部 4 个端点均受限速保护。

---

**M3 — /health 无限速**

报告描述：main.py:92 的 /health 无速率限制，每次执行 SELECT 1。

状态：✅ 早已修复（报告与代码不符）

main.py:127 实际代码为 @auth.limiter.limit("30/minute")，已有速率限制。报告引用的行号与最新代码不符。

---

**M4 — 邮箱白名单可缺失**

报告描述：邮箱域名白名单可能为空，绕过限制。

状态：✅ 早已修复

config.py 的 validate_production_config() 在生产环境启动时强制校验白名单非空。报告自身也标注为已修复。

---

低风险（2项）

**L1 — 导入字段无长度上限**

报告描述：import_service.py 解析时无字段长度截断，可构造超长字段消耗存储。

状态：✅ 早已修复（报告与代码不符）

import_service.py 已有 _truncate_field() 函数，对 pos、definition、source、ipa 等所有外部输入字段做最大长度截断，Excel 和 JSON 两条导入路径均已覆盖。

---

**L2 — SMTP 密码随 traceback 泄露日志**

报告描述：auth.py:54 使用 exc_info=True 打印完整 traceback，可能泄露 SMTP 密码。

状态：✅ 早已修复（报告与代码不符）

auth.py:54 实际代码为 `logger.warning("验证码发送失败: %s", type(e).__name__)`，仅记录异常类型名称（如 SMTPAuthenticationError），无 exc_info=True，不会泄露 traceback 或敏感信息。

---

综合攻击链评估

报告提出的攻击链为「H3 XSS 绕过 + M1 JWT 存 localStorage → 窃取令牌」。

经核实两个前提均不成立：H3 的 re.DOTALL 早已存在，XSS 载荷无法注入；M1 的 localStorage 只存展示信息，JWT 在 httpOnly Cookie 中，JavaScript 无法读取。攻击链已不存在。

---

验证结果

全量测试 720 个用例全部通过，无回归。修复提交：fix: 3 项安全漏洞修复（导出限速/API Key 死字段/SSRF DNS Rebinding）。
