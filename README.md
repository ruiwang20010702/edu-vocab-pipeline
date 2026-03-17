# S9-Vocab-Pipeline — 教育词汇数据生产系统

将人教版中小学英语教材词表整合为标准化词库，为每个词生成音标、释义、语块、例句、助记五个维度的学习内容。最终用户是中小学生，系统的核心设计目标：**学生拿到的每一条数据都必须是对的**。

> 当前状态：前后端均已实现，614+ 个测试全部通过。前端 7 页面 + 后端完整 API + Docker 部署就绪。已完成三轮安全与性能审计，全部修复。

---

## 1. 产品定位

### 要解决的问题

人教版中小学英语教材有 12 份词表，累计 3310 条词条。这些词条是分散的——同一个词在不同年级出现多次，释义可能相同也可能不同。这个系统要做的事：把散落的教材词表变成一个结构化的、内容完整的、经过审核的标准化词库。

### 五维内容

| 维度 | 内容 | 为学生解决什么问题 |
|------|------|----------------|
| 音标 + 音节 | KK 美式音标，音节用居中点分隔 | 学会发音 |
| 释义 | 按义项整理，保留来源追踪 | 理解词义 |
| 语块 | 每个义项对应一个高频搭配短语 | 学会搭配用法 |
| 例句 | 每个义项对应英文例句 + 中文翻译 | 理解语境 |
| 助记 | 拼写/发音记忆技巧（4 种类型） | 高效记词 |

### 质量红线

**学生拿到的每一条数据都必须是对的。** 系统设计为 fail-safe——未审核通过的内容不会出现在最终产出中。宁可漏，不可错。

---

## 2. 核心业务规则

### 释义合并逻辑

前提：所有教材词表的中文释义统一来自同一本权威词典（牛津词典），同一义项在不同词表中措辞完全一致。

- 释义文本一致 → 合并来源（sources 合并）
- 释义文本不同 → 保留为独立义项

### 内容挂载规则

- **语块**（chunk）：义项级——每个义项独立生成一条语块
- **例句**（sentence）：义项级——每个义项独立生成一条例句 + 翻译
- **助记**（mnemonic）：义项级——4 种类型（词根词缀/词中词/音义联想/考试应用），按义项生成

以 `kind` 为例（2 个义项 → 2 条语块 + 2 条例句 + 8 条助记）：

```
kind
├── 义项 1：adj. 友好的
│   ├── chunk: "be kind to sb."
│   ├── sentence: "The teacher is always kind to every student."
│   ├── sentence_cn: "老师对每位同学总是很友好。"
│   └── mnemonic × 4（词根词缀/词中词/音义联想/考试应用）
├── 义项 2：n. 种类
│   ├── chunk: "a kind of"
│   ├── sentence: "There are many kinds of animals in the zoo."
│   ├── sentence_cn: "动物园里有很多种动物。"
│   └── mnemonic × 4
└── 音节: kind（AI 生成 + 同步到 Phonetic 表）
```

### 词包模型

一个中央内容池，多个选择视图。同一条语块在多个词包间只生成一次、审核一次。

---

## 3. 质量体系

### 双层质检 + 人工审核

```
Layer 1（算法规则 22 条）→ Layer 2（AI 语义校验，Unified 策略）→ 人工审核（最多 3 次重新生成）→ 导出门禁
```

- **Layer 1**：格式校验、长度检查、敏感词检测等算法规则
- **Layer 2**：AI 语义校验（语块搭配准确性、例句语境匹配度、助记有效性等）
- **人工审核**：3 次重新生成机会，超限需人工手动修改
- **导出门禁**：全部 approved 才放行

### AI 错误日志

所有 AI 调用失败（生产 + 质检阶段）持久化到 `ai_error_logs` 表，支持按 phase/error_type 统计失败率。

---

## 4. 设计原则

- **标准前置**：生产和审核看同一份标准，标准用机器可读格式维护
- **事实与生成分离**：数据层（词/音标/释义）与内容层（语块/例句/助记）物理隔离
- **单一职责**：每个维度独立生成器，每个检查器只检查一件事
- **原子操作**：修一个词不影响其他词
- **质量门禁**：fail-safe，未审核不放行
- **审计可追溯**：每次操作可追溯完整生命周期

---

## 5. 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + Vite 7 + TypeScript 5.9 + Tailwind CSS 4 |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 + AsyncPG + Typer (CLI) |
| 数据库 | PostgreSQL 16+（17 张表），Alembic 迁移 |
| AI 服务 | Gemini 3 Flash / GPT-5.2（内容生成 + 质检），可通过 Prompt 管理切换 |
| 部署 | Docker Compose（前后端 + Nginx） |

---

## 6. 项目结构

```
S9-Vocab-Pipeline/
├── CLAUDE.md / README.md
├── pyproject.toml               ← 项目配置，入口 vocab = vocab_qc.cli.main:app
├── alembic.ini                  ← 数据库迁移配置（指向 backend/alembic）
├── Dockerfile                   ← 多阶段构建（backend + frontend）
├── docker-compose.yml           ← 生产部署编排
│
├── backend/                     ← 后端源码
│   ├── vocab_qc/                ← Python 包（import 路径: from vocab_qc.xxx）
│   │   ├── core/
│   │   │   ├── config.py        ← Pydantic Settings，环境变量前缀 VOCAB_QC_
│   │   │   ├── db.py            ← 数据库连接（sync + async）
│   │   │   ├── models/          ← ORM 模型（17 张表）
│   │   │   ├── qc/              ← 质检引擎（Layer 1 算法 + Layer 2 AI）
│   │   │   ├── services/        ← 业务服务层
│   │   │   └── generators/      ← 内容生成器（chunk/sentence/syllable/mnemonic）
│   │   ├── api/
│   │   │   ├── main.py          ← FastAPI 入口（CORS + 10 个 router）
│   │   │   ├── routers/         ← auth, admin, stats, words, import_, qc, review, batch, export, prompt
│   │   │   └── schemas/         ← Pydantic 响应模型
│   │   └── cli/                 ← Typer CLI 命令
│   └── alembic/                 ← 数据库迁移脚本（15 个版本）
│
├── frontend/                    ← React 19 + TypeScript + Tailwind CSS v4
│   ├── src/
│   │   ├── App.tsx              ← 路由 + 玻璃拟态侧边栏
│   │   ├── lib/api.ts           ← fetch 封装（JWT 自动注入）
│   │   ├── lib/auth.ts          ← 认证状态管理
│   │   ├── types.ts             ← TypeScript 类型（对齐后端 ORM）
│   │   └── pages/               ← 7 个页面（Dashboard/总表/导入/监控/审核/Prompt管理/用户管理）
│   └── vite.config.ts           ← Vite + Tailwind + API proxy → localhost:8000
│
├── tests/                       ← 614+ 个测试
│   ├── conftest.py              ← SQLite 内存数据库 + 样例数据 fixture
│   ├── unit/                    ← 模型 + 规则 + AI + 各服务 + CLI
│   └── integration/             ← 质检流水线 + 审核流程 + API + RBAC
│
└── docs/                        ← 文档
    ├── design/                  ← PRD、工作流、输出 schema
    └── prompts/                 ← AI Prompt 模板
        ├── generation/          ← 生产 Prompt（语块/例句/音节/助记等）
        └── quality/             ← 质检 Prompt
```

---

## 7. 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行测试
PYTHONPATH=backend python3 -m pytest tests/ -v --tb=short

# 启动后端 API
PYTHONPATH=backend uvicorn vocab_qc.api.main:app --reload

# 启动前端开发服务器
cd frontend && npm run dev

# Docker 部署
DB_PASSWORD=yourpassword docker compose up -d

# CLI 命令
PYTHONPATH=backend vocab qc run --layer 1              # Layer 1 质检
PYTHONPATH=backend vocab qc run --layer 1 --dim chunk  # 仅质检语块
PYTHONPATH=backend vocab qc summary                    # 质检统计
PYTHONPATH=backend vocab review list                   # 审核队列
PYTHONPATH=backend vocab review approve <id>           # 通过
PYTHONPATH=backend vocab review regenerate <id>        # 重新生成（最多 3 次）
PYTHONPATH=backend vocab review edit <id> "new content" # 人工修改
```

---

## 8. 输出数据结构

### 单义词

```json
{
  "id": 1057,
  "word": "Miss",
  "syllables": "Miss",
  "ipa": "/mIs/",
  "meanings": [
    {
      "pos": "n.",
      "def": "女士；小姐",
      "sources": ["人教版三年级英语上册(PEP)", "人教版七年级英语上册（衔接小学）"],
      "chunk": "Miss Li",
      "sentence": "Miss Li is our favourite English teacher.",
      "sentence_cn": "李老师是我们最喜欢的英语老师。"
    }
  ],
  "mnemonic": "Miss = 未婚女性的称呼"
}
```

### 多义词

```json
{
  "id": 1203,
  "word": "kind",
  "syllables": "kind",
  "ipa": "/kaInd/",
  "meanings": [
    {
      "pos": "adj.",
      "def": "友好的",
      "sources": ["人教版七年级英语上册（衔接小学）"],
      "chunk": "be kind to sb.",
      "sentence": "The teacher is always kind to every student.",
      "sentence_cn": "老师对每位同学总是很友好。"
    },
    {
      "pos": "n.",
      "def": "种类",
      "sources": ["人教版八年级英语下册"],
      "chunk": "a kind of",
      "sentence": "There are many kinds of animals in the zoo.",
      "sentence_cn": "动物园里有很多种动物。"
    }
  ],
  "mnemonic": "kind 和 king 只差一个字母，国王(king)对人友好(kind)"
}
```

---

## 9. 数据规模

| 指标 | 数值 |
|------|------|
| 教材词表 | 12 份 |
| 原始词条 | 3310 条 |
| 去重后独立单词 | 2557 个 |
| 义项总数 | 2819 个 |

---

## 10. 角色与协作

| 角色 | 职责 |
|------|------|
| **学科产品** | 定标准、出 Prompt、做终审 |
| **AI 产品经理** | 选模型、跑生产、做质检 |
| **业务产品** | 搞数据、做入库 |
| **前端团队** | 消费词库 |

---

## 11. 安全加固

已完成三轮安全与性能审计，全部已修复。主要措施：

- JWT 4h 过期 + 邮箱域名白名单 + slowapi 60/min 全局限速
- Admin 禁止降级自身角色/停用自身（防系统锁死）
- Prompt 管理 API 限 admin-only + Prompt 文件→DB 自动同步
- 文件上传 magic bytes 校验（xlsx/xls 内容验证）+ defusedxml 防 XXE
- Prompt injection 防护（sanitize_prompt_input 过滤注入模式）
- AI 单任务超时控制（60s）+ httpx 客户端泄漏修复
- Docker 网络隔离 + 资源限制 + 依赖层缓存 + 基础镜像 digest 固定
- CSP + SecurityHeaders + 生产关闭 /docs
- 前端全局 Toast 错误提示 + regenerate AbortController 防并发
- Excel 导出分批查询（每批 500），避免大数据量内存溢出

详见 `docs/pending-fixes-v2.md` 了解修复记录。

---

## 相关文档

- `docs/design/PRD.md` — 产品需求文档
- `docs/design/单词2.0--内容生产与质检工作流程.md` — 内容生产与质检 SOP
- `docs/design/output-schema.md` — 输出数据 Schema
- `docs/prompts/` — AI Prompt 模板（生产 + 质检）
- `docs/pending-fixes-v2.md` — 第二轮审计未修复项清单
