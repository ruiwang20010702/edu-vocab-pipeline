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
│   └── routers/    ← 11 个 router: auth, admin, stats, words, import_, qc, review, batch, export, prompt, callback
├── core/           ← 业务层
│   ├── config.py   ← Pydantic Settings，所有配置项前缀 VOCAB_QC_（如 VOCAB_QC_DATABASE_URL_SYNC）
│   ├── db.py       ← SQLAlchemy Engine + SyncSessionLocal（SQLite/PostgreSQL 双模式）
│   ├── models/     ← ORM 模型，按层组织（data_layer / content_layer / quality_layer / batch_layer / package_layer / user / prompt）
│   ├── services/   ← 业务服务（auth / user / generation / production / review / qc / export / stats / prompt / audit / batch / import / word）
│   ├── generators/ ← 内容生成器（chunk / sentence / mnemonic×4 / syllable），base.py 含 AI 调用 + 熔断器
│   └── qc/         ← 质检引擎：Layer 1（25 条算法规则）+ Layer 2（AI语义校验），装饰器注册机制
└── cli/            ← Typer CLI（qc_commands + review_commands + cleanup/create-admin）
```

**关键设计模式**：

- **AI Gateway 适配**：`generators/base.py` 同时支持直连 OpenAI 格式 API 和 51talk AI Gateway（异步提交+轮询）模式，通过 `settings.ai_gateway_mode` 切换
- **熔断器**：`circuit_breaker.py` 保护 AI 调用，连续失败超阈值自动熔断
- **规则注册中心**：`qc/registry.py` 用装饰器自动注册 Layer 1/2 规则，`dimension_matches()` 处理 mnemonic 维度通配
- **Prompt 三级 fallback**：DB → 文件（docs/prompts/generation/）→ 硬编码

### 前端（React 19 + TypeScript + Tailwind CSS v4）

单页应用，7 个页面：数据看板、词表导入、生产监控、质检审核、总表管理、Prompt管理、用户管理（admin-only）。`lib/api.ts` 封装 fetch + JWT 自动注入，`lib/auth.ts` 管理认证状态。Vite 开发服务器代理 `/api/*` 到后端。

总表（MasterTable）已支持：维度子集"重新生产"（含 `dry_run` 预览 + 仅补缺字段项 + 强制覆盖）、"一键补全缺失字段"全量回填按钮（含 `unique_missing` 去重计数预览）。Excel 导出包含审核人列（按义项聚合 ReviewItem.reviewer）。

Excel 导出为**异步后台任务**：`POST /api/export/excel/async` 建任务立即返回 → 后台线程串行构建落盘 → 前端每 2s 轮询 `GET /api/export/jobs/{id}` → 完成后下载 `/jobs/{id}/download`。避免同步导出大数据量（3.8w 义项 ~159s）撞网关 120s 超时被掐断。任务态存 `export_jobs` 表，含并发去重、僵尸超时（>20min 判 failed）、24h TTL 文件清理。旧同步端点 `/api/export/excel` 保留向后兼容。

### 数据库（PostgreSQL 16 / 测试用 SQLite 内存）

ORM 模型分布在 `core/models/` 下，共 20 张表。测试通过 `conftest.py` 使用 SQLite 内存数据库 + 事务回滚隔离。Alembic 管理 24 个迁移版本。

## 关键业务规则

1. **释义合并**：释义文本完全一致 → 合并来源；释义文本不同 → 保留为独立义项
2. **内容按义项挂载**：语块、例句、助记均按义项生成（防止多义词张冠李戴），音节按单词生成
3. **质量门禁**：Layer 1 算法规则 → Layer 2 AI 语义校验 → 人工审核（最多 3 次重新生成）→ 导出门禁（全部 approved 才放行）
4. **词包按词关联**：Package 通过 PackageWord（word_id）关联单词，导入/生产/统计均按词维度操作
5. **生产中锁**：Package 状态为 processing 时，其关联词不会被批次领取（防止生产与审核并发冲突）
6. **生产编排**：`production_service.py` 按 Package 维度编排 生成→质检→入队审核 全流程，支持并发 AI 调用（`ai_max_concurrency` 控制）
7. **Prompt 版本指纹**：每条 ContentItem 持久化 `generated_with_prompt_id` + `generated_with_prompt_hash`。重新生产时双指纹与当前 active prompt 完全一致 → 视为最新版自动跳过（取代 24h 窗口启发式）
8. **仅补缺字段项**：`only_missing_extra_field=True` 忽略指纹去重，只命中 content 非空但缺主 extra 键（如 `extension_words` / `exam_sentence`）的项；总表"一键补全缺失字段"用此模式增量回灌
9. **维度子集生产**：`/api/batch/produce` 支持 `dimensions` 数组（仅指定维度重生）+ `dry_run` 预览 + `force_overwrite` 强制覆盖。批次模式 `is_regen_mode = dimensions is not None`
10. **POS 权威标签**：23 个带点标签（`n. / v. / mod. / int. / det. / ...`，2026-05-26 学科同步）。导出层不再做 `art.→det.` 强制映射，保留原始标签

## 配置体系

所有配置通过环境变量注入，前缀 `VOCAB_QC_`。关键配置：

- `DATABASE_URL_SYNC`：数据库连接串（默认 `postgresql://localhost:5432/vocab_qc`）
- `AI_API_KEY` / `AI_API_BASE_URL` / `AI_MODEL`：AI 服务配置
- `AI_GATEWAY_MODE` / `AI_GATEWAY_ASYNC`：51talk AI Gateway 模式开关
- `JWT_SECRET_KEY`：生产环境必须替换默认值（≥32 字节）
- `ALLOWED_EMAIL_DOMAINS`：邮箱域名白名单
- `ENV`：`development` / `staging` / `production`，生产环境强制校验安全配置（`config.py:validate_production_config`）

## 测试体系

71 个测试文件，分为 `tests/unit/` 和 `tests/integration/` 两层。`conftest.py` 使用 SQLite 内存数据库 + 事务回滚隔离（`session` 级 engine，`function` 级 session）。`sample_word` fixture 创建含多义项、多内容项的测试单词。

Ruff 配置：line-length=120, target-version=py311, select=[E,F,I,N,W]。

## AI 调用链路

```
Generator.generate()
  → ai_gateway_mode=True?
    → Yes: 异步提交到 51talk AI Gateway → PollingPool 轮询结果
    → No:  直连 OpenAI 格式 API（httpx POST）
  → CircuitBreaker 保护（连续 15 次失败 → 熔断 30s）
  → 失败自动重试（最多 3 次）
  → 响应 JSON 解析 → ContentItem 入库
```

Task Queue 模式（`ai_use_task_queue=True`）：批量提交（batch_size=20, stagger=0.5s）+ 多 worker 轮询（pool_size=50, scan_interval=2s）。

## 安全加固

- JWT 4h 过期 + Cookie httpOnly + 邮箱域名白名单 + slowapi 60/min 全局限速
- Admin 禁止降级自身角色/停用自身 + Prompt API 限 admin-only
- 文件上传 magic bytes 校验 + HTML 过滤 + SSRF 防护 + defusedxml 防 XXE
- Prompt injection 防护（`sanitize_prompt_input`）+ 熔断器 + AI 单任务超时
- 生产环境禁用 Swagger/ReDoc，强制安全头（CSP / HSTS / X-Frame-Options）
- Docker 网络隔离（internal + external），后端不直接暴露端口

## 钉钉问答机器人（`dingtalk_bot/`，独立子服务）

`dingtalk_bot/` 是一个**与主项目同仓、但运行与部署完全独立**的钉钉问答机器人，面向审核员团队回答"操作怎么做"和"业务规则"问题（只读、不碰业务数据库）。技术形态：钉钉企业内部应用 + Stream 模式（WebSocket 外拨，免公网回调）+ 51talk AI Gateway 同步问答。完整说明见 `dingtalk_bot/README.md` 与 `docs/钉钉机器人MVP方案.md`。

**与盖娅/主部署的边界（重要，勿混淆）**：

- 盖娅构建用的是 `gaea/Dockerfile`，它**只 COPY `backend/` + 前端 + `docs/prompts/`，不包含 `dingtalk_bot/`**。因此 push 代码 + 走盖娅部署主项目，**部署的仍只是 vocab-pipeline 主应用，机器人不会被构建/部署，也不影响主应用**。
- 机器人与主应用**不能共用一个容器/部署**：入口不同（主应用 `gunicorn ... main:app` 开 :80；机器人 `python stream_client.py` 长连 WebSocket、不开端口），环境不同（机器人需 `DINGTALK_APP_KEY/SECRET`）。
- 要上线机器人需**单独的部署单元**：用 `dingtalk_bot/Dockerfile` 单独构建（盖娅另建一个应用指向它，或放任意能外拨连钉钉的机器常驻）。
- 机器人复用主项目的 51talk AI Gateway 凭证，但用独立 `biz_type=vocab_qc_bot` 以便单独统计 AI 成本。
- 机器人有自己的依赖与测试（`dingtalk_bot/requirements.txt`、`dingtalk_bot/tests/`、`dingtalk_bot/.venv`），与主项目的 pytest/依赖互不干扰。
