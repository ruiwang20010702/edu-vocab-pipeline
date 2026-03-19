# Gaea 生产环境配置

> **配置文件名**: `s9-vocab-pipeline-env`
> **挂载路径**: `/app/.env`
> **域名**: https://s9-vocab-pipeline.51suyang.cn

---

## 一、Gaea 自定义环境变量（数据库，单独管理）

| 变量名 | 变量值 | 说明 |
|--------|--------|------|
| `VOCAB_QC_DATABASE_URL_SYNC` | `postgresql://s9_vocab_write:ty9dwjzaI2d02p2RQ9@s9-training.rwlb.rds.aliyuncs.com:5432/s9_vocab_production` | 应用读写账号（无 DDL 权限） |
| `VOCAB_QC_DATABASE_URL_MIGRATE` | `postgresql://s9training_admin:5bBJ#2DCAi1cU3#TRF@s9-training.rwlb.rds.aliyuncs.com:5432/s9_vocab_production` | 迁移专用账号（仅 alembic 建表用） |

---

## 二、Gaea 配置文件（挂载到 /app/.env）

```env
# ═══ 基础环境 ═══
# 运行环境标识，production 会启用安全校验（强制 HTTPS Cookie、禁用 Swagger 等）
VOCAB_QC_ENV=production
# 关闭 SQL 日志（生产环境禁止开启，影响性能）
VOCAB_QC_DB_ECHO=false

# ═══ AI 服务（51talk AI Gateway） ═══
# Gateway API Key（51talk AI Gateway 分配的客户端密钥）
VOCAB_QC_AI_API_KEY=01225b1e-e498-46bf-8038-daeac9d07d90
# Gateway 接口地址
VOCAB_QC_AI_API_BASE_URL=https://aigateway.51talk.com/v1
# 模型标识（格式: 模型名|路由策略，efficiency=低成本路由）
VOCAB_QC_AI_MODEL=gemini-3-flash-preview|efficiency
# 启用 Gateway 模式（api_key 放 body，响应包裹在 res 字段）
VOCAB_QC_AI_GATEWAY_MODE=true
# Gateway 后端 provider（VERTEX=Google Vertex AI）
VOCAB_QC_AI_GATEWAY_PROVIDER=VERTEX
# Gateway 业务标识，用于计费和审计
VOCAB_QC_AI_GATEWAY_BIZ_TYPE=vocab_qc
# 启用异步模式（提交任务→轮询结果，避免长连接超时）
VOCAB_QC_AI_GATEWAY_ASYNC=true
# 异步轮询间隔（秒）
VOCAB_QC_AI_GATEWAY_POLL_INTERVAL=3.0
# 单任务最大轮询等待时间（秒），超时则标记失败
VOCAB_QC_AI_GATEWAY_POLL_MAX_WAIT=300
# 并发 AI 调用数上限（控制对 Gateway 的压力）
VOCAB_QC_AI_MAX_CONCURRENCY=20
# 并发请求启动间隔（秒），避免瞬间打满 Gateway
VOCAB_QC_AI_REQUEST_STAGGER=0.2
# 单次 AI 调用失败后的最大重试次数
VOCAB_QC_AI_MAX_RETRIES=3
# 单任务总超时（秒），需 ≥ POLL_MAX_WAIT
VOCAB_QC_AI_TASK_TIMEOUT=360
# 熔断器：连续失败多少次后触发熔断，暂停 AI 调用
VOCAB_QC_AI_CIRCUIT_BREAKER_THRESHOLD=15
# 熔断恢复冷却时间（秒）
VOCAB_QC_AI_CIRCUIT_BREAKER_RECOVERY=30
# AI 接口域名白名单（SSRF 防护，仅允许访问这些域名）
VOCAB_QC_ALLOWED_AI_HOSTS=["aigateway.51talk.com"]
# 禁止访问内网 AI 地址（防 SSRF）
VOCAB_QC_ALLOW_PRIVATE_AI_URL=false

# ═══ JWT 认证 ═══
# JWT 签名密钥（HS256 要求 ≥32 字节，此为随机生成的安全密钥）
VOCAB_QC_JWT_SECRET_KEY=ezhkgFKjAeKOhswl9CjnYId_wxHY0oc_jCAyPKwtv6gktYcaUC4wtvc6Bv5xrI_a
# JWT 签名算法
VOCAB_QC_JWT_ALGORITHM=HS256
# Token 过期时间（小时），过期后需重新登录
VOCAB_QC_JWT_EXPIRE_HOURS=4

# ═══ Cookie ═══
# 存储 JWT Token 的 Cookie 名称
VOCAB_QC_COOKIE_NAME=access_token
# 强制 HTTPS 传输 Cookie（生产环境必须为 true）
VOCAB_QC_COOKIE_SECURE=true
# Cookie SameSite 策略（lax=同站请求携带，防 CSRF）
VOCAB_QC_COOKIE_SAMESITE=lax
# Cookie 绑定域名
VOCAB_QC_COOKIE_DOMAIN=s9-vocab-pipeline.51suyang.cn
# Cookie 作用路径
VOCAB_QC_COOKIE_PATH=/

# ═══ SMTP 邮箱验证码 ═══
# SMTP 服务器地址（阿里企业邮箱）
VOCAB_QC_SMTP_HOST=smtp.qiye.aliyun.com
# SMTP 端口（465=SSL）
VOCAB_QC_SMTP_PORT=465
# 发件账号
VOCAB_QC_SMTP_USER=wangrui003@51talk.com
# 发件账号授权码
VOCAB_QC_SMTP_PASSWORD=WHorHCnJuRA3ICGO
# 发件人显示邮箱
VOCAB_QC_SMTP_FROM_EMAIL=wangrui003@51talk.com

# ═══ 认证与安全 ═══
# 允许登录的邮箱域名白名单（仅 51talk 员工可登录）
VOCAB_QC_ALLOWED_EMAIL_DOMAINS=["51talk.com"]
# 邮箱验证码有效期（分钟）
VOCAB_QC_VERIFICATION_CODE_EXPIRE_MINUTES=10
# CORS 允许的前端来源地址
VOCAB_QC_CORS_ORIGINS=["https://s9-vocab-pipeline.51suyang.cn"]

# ═══ 生产调优 ═══
# 大批量生产时每批处理的词数（避免单批过大导致超时）
VOCAB_QC_PRODUCTION_BATCH_SIZE=50
# Package processing 状态超时（小时），超时自动解锁
VOCAB_QC_PACKAGE_PROCESSING_TIMEOUT_HOURS=6
# 单条内容最大重新生成次数
VOCAB_QC_MAX_REGENERATE_RETRIES=3
# 文件上传大小限制（MB）
VOCAB_QC_MAX_UPLOAD_SIZE_MB=10
```

---

## 三、数据库账号说明

| 账号 | 用途 | 权限 |
|------|------|------|
| `s9_vocab_write` | 应用运行时读写 | SELECT / INSERT / UPDATE / DELETE |
| `s9training_admin` | Alembic 迁移建表 | DDL（CREATE / ALTER / DROP） |

- 数据库地址（内网）：`s9-training.rwlb.rds.aliyuncs.com:5432`
- 数据库地址（公网）：`s9-training-pub.rwlb.rds.aliyuncs.com:5432`
- 数据库名：`s9_vocab_production`
- ⚠️ `s9_vocab_write` 密码第 9 位是大写 `I`（不是小写 `l`）

---

## 四、与开发环境的差异

| 配置项 | 开发环境 | 生产环境 | 说明 |
|--------|---------|---------|------|
| ENV | development | production | 启用安全校验 |
| DATABASE_URL_SYNC | localhost | 阿里云 RDS 内网 | 读写账号分离 |
| ALLOWED_EMAIL_DOMAINS | [] (不限制) | ["51talk.com"] | 仅公司邮箱可登录 |
| CORS_ORIGINS | localhost | 正式域名 | 防跨域攻击 |
| COOKIE_SECURE | false | true | 强制 HTTPS |
| ALLOW_PRIVATE_AI_URL | true | false | 防 SSRF |
| JWT_SECRET_KEY | 开发密钥 | 随机生成64字符 | 生产必须替换 |

---

## 五、注意事项

1. 配置文件挂载到 `/app/.env`（Dockerfile WORKDIR 为 `/app`，pydantic-settings 从工作目录读取 `.env`）
2. 此文件不要提交到代码仓库（已在 .gitignore 中排除 .env）
3. SMTP 密码如需更换，到阿里企业邮箱后台重新生成授权码
4. 建表已通过本地 ORM 完成（2026-03-19），alembic 版本已 stamp 到 014，后续新迁移会自动增量执行
