# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

S9 词汇数据生产系统——将人教版中小学英语教材词表整合为标准化词库，为每个词生成音标、释义、语块、例句、助记五个维度的学习内容。最终用户是中小学生。

**产品质量红线**：学生拿到的每一条数据都必须是对的。系统设计为 fail-safe——未审核通过的内容不会出现在最终产出中。

## 开发命令

```bash
# 测试（venv 解释器路径可能需要重建，优先用 PYTHONPATH 方式）
PYTHONPATH=backend python3 -m pytest tests/ -v --tb=short

# 运行单个测试文件
PYTHONPATH=backend python3 -m pytest tests/unit/test_generators.py -v

# 运行匹配关键字的测试
PYTHONPATH=backend python3 -m pytest tests/ -k "test_chunk" -v

# 启动后端 API
PYTHONPATH=backend uvicorn vocab_qc.api.main:app --reload

# 启动前端开发服务器（Vite dev server，代理 API 到 localhost:8000）
cd frontend && npm run dev

# CLI 工具
PYTHONPATH=backend python3 -m vocab_qc.cli.main qc run --layer 1
PYTHONPATH=backend python3 -m vocab_qc.cli.main review list

# Alembic 数据库迁移
PYTHONPATH=backend alembic upgrade head

# Docker 一键部署（需设置 DB_PASSWORD 环境变量）
DB_PASSWORD=xxx docker compose up -d

# Lint
ruff check backend/
```

## 架构概览

### 后端（FastAPI + SQLAlchemy + PostgreSQL）

**分层结构**：

```
vocab_qc/
├── api/            ← HTTP 层：FastAPI routers + Pydantic schemas + 依赖注入
│   ├── main.py     ← 应用入口（lifespan: prompt同步 + 词素KB预热 + httpx关闭）
│   ├── deps.py     ← DI：get_db(Session), get_current_user(JWT Cookie/Bearer), require_role()
│   └── routers/    ← 10 个 router: auth, admin, stats, words, import_, qc, review, batch, export, prompt
├── core/           ← 业务层
│   ├── config.py   ← Pydantic Settings，所有配置项前缀 VOCAB_QC_（如 VOCAB_QC_DATABASE_URL_SYNC）
│   ├── db.py       ← SQLAlchemy Engine + SyncSessionLocal（SQLite/PostgreSQL 双模式）
│   ├── models/     ← ORM 模型，按层组织（data_layer / content_layer / quality_layer / batch_layer / package_layer / user / prompt）
│   ├── services/   ← 业务服务（auth / user / generation / production / review / qc / export / stats / prompt / audit）
│   ├── generators/ ← 内容生成器（chunk / sentence / mnemonic×4 / syllable），base.py 含 AI 调用 + 熔断器
│   └── qc/         ← 质检引擎：Layer 1（22条算法规则）+ Layer 2（AI语义校验），装饰器注册机制
└── cli/            ← Typer CLI（qc_commands + review_commands + cleanup/create-admin）
```

**关键设计模式**：

- **AI Gateway 适配**：`generators/base.py` 同时支持直连 OpenAI 格式 API 和 51talk AI Gateway（异步提交+轮询）模式，通过 `settings.ai_gateway_mode` 切换
- **熔断器**：`circuit_breaker.py` 保护 AI 调用，连续失败超阈值自动熔断
- **规则注册中心**：`qc/registry.py` 用装饰器自动注册 Layer 1/2 规则，`dimension_matches()` 处理 mnemonic 维度通配
- **Prompt 三级 fallback**：DB → 文件（docs/prompts/generation/）→ 硬编码

### 前端（React 19 + TypeScript + Tailwind CSS v4）

单页应用，7 个页面：数据看板、词表导入、生产监控、质检审核、总表管理、Prompt管理、用户管理（admin-only）。`lib/api.ts` 封装 fetch + JWT 自动注入，`lib/auth.ts` 管理认证状态。Vite 开发服务器代理 `/api/*` 到后端。

### 数据库（PostgreSQL 16 / 测试用 SQLite 内存）

ORM 模型分布在 `core/models/` 下，约 17 张表。测试通过 `conftest.py` 使用 SQLite 内存数据库 + 事务回滚隔离。Alembic 管理 15 个迁移版本。

## 关键业务规则

1. **释义合并**：释义文本完全一致 → 合并来源；释义文本不同 → 保留为独立义项
2. **内容按义项挂载**：语块、例句、助记均按义项生成（防止多义词张冠李戴），音节按单词生成
3. **质量门禁**：Layer 1 算法规则 → Layer 2 AI 语义校验 → 人工审核（最多 3 次重新生成）→ 导出门禁（全部 approved 才放行）
4. **词包按词关联**：Package 通过 PackageWord（word_id）关联单词，导入/生产/统计均按词维度操作
5. **生产中锁**：Package 状态为 processing 时，其关联词不会被批次领取（防止生产与审核并发冲突）
6. **生产编排**：`production_service.py` 按 Package 维度编排 生成→质检→入队审核 全流程，支持并发 AI 调用（`ai_max_concurrency` 控制）

## 配置体系

所有配置通过环境变量注入，前缀 `VOCAB_QC_`。关键配置：

- `DATABASE_URL_SYNC`：数据库连接串（默认 `postgresql://localhost:5432/vocab_qc`）
- `AI_API_KEY` / `AI_API_BASE_URL` / `AI_MODEL`：AI 服务配置
- `AI_GATEWAY_MODE` / `AI_GATEWAY_ASYNC`：51talk AI Gateway 模式开关
- `JWT_SECRET_KEY`：生产环境必须替换默认值（≥32 字节）
- `ALLOWED_EMAIL_DOMAINS`：邮箱域名白名单
- `ENV`：`development` / `staging` / `production`，生产环境强制校验安全配置（`config.py:validate_production_config`）

## 安全加固

- JWT 4h 过期 + Cookie httpOnly + 邮箱域名白名单 + slowapi 60/min 全局限速
- Admin 禁止降级自身角色/停用自身 + Prompt API 限 admin-only
- 文件上传 magic bytes 校验 + HTML 过滤 + SSRF 防护 + defusedxml 防 XXE
- Prompt injection 防护（`sanitize_prompt_input`）+ 熔断器 + AI 单任务超时
- 生产环境禁用 Swagger/ReDoc，强制安全头（CSP / HSTS / X-Frame-Options）
- Docker 网络隔离（internal + external），后端不直接暴露端口
