# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

教育词汇数据产品的生产系统——将人教版中小学英语教材词表整合为标准化词库，为每个词生成音标、释义、语块、例句、助记五个维度的学习内容。最终用户是中小学生。

**产品质量红线**：学生拿到的每一条数据都必须是对的。系统设计为 fail-safe——未审核通过的内容不会出现在最终产出中。

## 当前状态

质检后端已实现，159 个测试全部通过。下一步：接入真实数据 + 数据导入功能。

```
VocabularyDataCleaning1.0/
├── CLAUDE.md / README.md / roadmap.md
├── pyproject.toml               ← 项目配置，入口 vocab = vocab_qc.cli.main:app
├── alembic.ini + alembic/       ← 数据库迁移
├── standards/standards.yaml     ← 质量标准（机器可读）
│
├── vocab_qc/
│   ├── core/
│   │   ├── config.py            ← Pydantic Settings，环境变量前缀 VOCAB_QC_
│   │   ├── db.py                ← 数据库连接（sync + async）
│   │   ├── models/              ← ORM 模型（14 张表）
│   │   │   ├── data_layer.py    ← Word, Phonetic, Meaning, Source
│   │   │   ├── content_layer.py ← ContentItem（含 qc_status/retry_count）
│   │   │   ├── quality_layer.py ← QcRun, QcRuleResult, RetryCounter, ReviewItem, AuditLogV2
│   │   │   ├── package_layer.py ← Package, PackageMeaning
│   │   │   └── enums.py         ← QcStatus, ReviewReason 等枚举
│   │   ├── qc/
│   │   │   ├── base.py          ← RuleResult, ItemCheckResult, RuleChecker 协议
│   │   │   ├── registry.py      ← 装饰器注册中心
│   │   │   ├── runner.py        ← Layer 1 运行器
│   │   │   ├── layer1/          ← 22 条算法规则（M3-M6, P1-P2, S1-S4, C1-C2 + C4-C5, E6-E8, N1-N5）
│   │   │   └── layer2/          ← AI 语义校验（13 per-rule + 3 unified 检查器）
│   │   ├── services/
│   │   │   ├── qc_service.py    ← 质检编排
│   │   │   ├── review_service.py← 审核流程（approve/regenerate/manual_edit + 3 次重试）
│   │   │   ├── export_service.py← 导出门禁（仅 approved 放行）
│   │   │   ├── generation_service.py
│   │   │   └── audit_service.py
│   │   └── generators/          ← 内容生成器（chunk/sentence/mnemonic）
│   ├── api/                     ← FastAPI 路由
│   └── cli/                     ← Typer CLI 命令
│
├── tests/                       ← 159 个测试
│   ├── conftest.py              ← SQLite 内存数据库 + 样例数据 fixture
│   ├── unit/                    ← 模型 + 规则 + AI 基础
│   └── integration/             ← 质检流水线 + 审核流程 + API + E2E
│
└── docs/
    └── 单词2.0--内容生产与质检工作流程.md
```

## 开发命令

```bash
# 测试
.venv/bin/pytest tests/ -v --tb=short

# 启动 API
uvicorn vocab_qc.api.main:app --reload

# CLI
vocab qc run --layer 1
vocab review list
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
