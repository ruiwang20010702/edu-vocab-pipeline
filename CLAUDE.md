# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

教育词汇数据产品的生产系统——将人教版中小学英语教材词表整合为标准化词库，为每个词生成音标、释义、语块、例句、助记五个维度的学习内容。最终用户是中小学生。

**产品质量红线**：学生拿到的每一条数据都必须是对的。系统设计为 fail-safe——未审核通过的内容不会出现在最终产出中。

## 当前状态

前后端均已实现，506 个测试全部通过。前端 6 页面 + 后端完整 API。

```
VocabularyDataCleaning1.0/
├── CLAUDE.md / README.md
├── pyproject.toml               ← 项目配置，入口 vocab = vocab_qc.cli.main:app
├── alembic.ini                  ← 数据库迁移配置（指向 backend/alembic）
│
├── backend/                     ← 后端源码
│   ├── vocab_qc/                ← Python 包（import 路径: from vocab_qc.xxx）
│   │   ├── core/
│   │   │   ├── config.py        ← Pydantic Settings，环境变量前缀 VOCAB_QC_
│   │   │   ├── db.py            ← 数据库连接（sync + async）
│   │   │   ├── models/          ← ORM 模型（14 张表）
│   │   │   ├── qc/              ← 质检引擎（Layer 1 算法 + Layer 2 AI）
│   │   │   ├── services/        ← 业务服务层
│   │   │   └── generators/      ← 内容生成器（chunk/sentence/mnemonic）
│   │   ├── api/
│   │   │   ├── main.py          ← FastAPI 入口（CORS + 10 个 router）
│   │   │   ├── routers/         ← auth, admin, stats, words, import_, qc, review, batch, export, prompt
│   │   │   └── schemas/         ← Pydantic 响应模型
│   │   └── cli/                 ← Typer CLI 命令
│   └── alembic/                 ← 数据库迁移脚本
│
├── frontend/                    ← React 19 + TypeScript + Tailwind CSS v4
│   ├── src/
│   │   ├── App.tsx              ← 路由 + 玻璃拟态侧边栏
│   │   ├── lib/api.ts           ← fetch 封装（JWT 自动注入）
│   │   ├── lib/auth.ts          ← 认证状态管理
│   │   ├── types.ts             ← TypeScript 类型（对齐后端 ORM）
│   │   └── pages/               ← 6 个页面
│   └── vite.config.ts           ← Vite + Tailwind + API proxy → localhost:8000
│
├── tests/                       ← 506 个测试
│   ├── conftest.py              ← SQLite 内存数据库 + 样例数据 fixture
│   ├── unit/                    ← 模型 + 规则 + AI + 各服务 + CLI
│   └── integration/             ← 质检流水线 + 审核流程 + API + RBAC
│
└── docs/                        ← 文档
    ├── design/                  ← PRD、工作流、输出 schema
    └── prompts/                 ← AI Prompt 模板
        ├── generation/          ← 生产 Prompt（语块/例句/助记等）
        └── quality/             ← 质检 Prompt
```

## 开发命令

```bash
# 测试
.venv/bin/pytest tests/ -v --tb=short

# 启动后端 API
PYTHONPATH=backend uvicorn vocab_qc.api.main:app --reload

# 启动前端开发服务器
cd frontend && npm run dev

# CLI
PYTHONPATH=backend vocab qc run --layer 1
PYTHONPATH=backend vocab review list
```

## 关键业务规则

1. **释义合并**：释义文本完全一致 → 合并来源；释义文本不同 → 保留为独立义项
2. **内容按义项挂载**：语块和例句按义项生成（防止多义词张冠李戴），助记按单词生成（面向拼写/发音，与义项无关）
3. **质量门禁**：未审核通过的内容不会出现在最终产出中
4. **人工审核拥有重试权**：人工审核环节有 3 次重新生成未通过部分的机会，3 次后需人工手动修改

## 设计原则

- **标准前置**：生产和审核看同一份标准
- **事实与生成分离**：数据层（词/音标/释义）与内容层（语块/例句/助记）物理隔离
- **单一职责**：每个维度独立生成、独立校验
- **质量门禁**：fail-safe，未审核不放行
- **审计可追溯**：每次操作可追溯
