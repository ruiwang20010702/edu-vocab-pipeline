# VocabularyDataCleaning -- 教育词汇数据生产系统

将人教版中小学英语教材词表整合为标准化词库，为每个词生成音标、释义、语块、例句、助记五个维度的学习内容。最终用户是中小学生，系统的核心设计目标：**学生拿到的每一条数据都必须是对的**。

> 当前状态：质检后端已实现（Layer 1 算法规则 22 条 + Layer 2 AI 语义校验 16 个检查器 + 人工审核流程 + 导出门禁），159 个测试全部通过。下一步：接入真实数据 + 补全 standards.yaml 正反例。

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
| 助记 | 拼写/发音记忆技巧 | 高效记词 |

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
- **助记**（mnemonic）：词级——面向整个单词的拼写/发音，与义项无关

以 `kind` 为例（2 个义项 → 2 条语块 + 2 条例句 + 1 条助记）：

```
kind
├── 义项 1：adj. 友好的
│   ├── chunk: "be kind to sb."
│   ├── sentence: "The teacher is always kind to every student."
│   └── sentence_cn: "老师对每位同学总是很友好。"
├── 义项 2：n. 种类
│   ├── chunk: "a kind of"
│   ├── sentence: "There are many kinds of animals in the zoo."
│   └── sentence_cn: "动物园里有很多种动物。"
└── mnemonic（词级）: "kind 和 king 只差一个字母，国王(king)对人友好(kind)"
```

### 词包模型

一个中央内容池，多个选择视图。同一条语块在多个词包间只生成一次、审核一次。

---

## 3. 质量体系

### 四道质量门禁

```
Gate 1（数据完整性）→ Gate 2（内容规则校验）→ Gate 3（AI 语义校验）→ Gate Export（全部 approved 才放行）
```

### 人工审核机制

- 人工审核环节有 **3 次重新生成**未通过部分的机会
- 3 次重新生成后仍未通过 → 需人工手动修改
- 审核结果持久化在数据库中，重跑流水线不丢失审核记录

---

## 4. 设计原则

- **标准前置**：生产和审核看同一份标准，标准用机器可读格式维护
- **事实与生成分离**：数据层（词/音标/释义）与内容层（语块/例句/助记）物理隔离
- **单一职责**：每个维度独立生成器，每个检查器只检查一件事
- **原子操作**：修一个词不影响其他词
- **质量门禁**：fail-safe，未审核不放行
- **审计可追溯**：每次操作可追溯完整生命周期

---

## 5. 输出数据结构

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

## 6. 角色与协作

| 角色 | 职责 |
|------|------|
| **学科产品** | 定标准、出 Prompt、做终审 |
| **AI产品经理** | 选模型、跑生产、做质检 |
| **业务产品** | 搞数据、做入库 |
| **前端团队** | 消费词库 |

---

## 7. 数据规模

| 指标 | 数值 |
|------|------|
| 教材词表 | 12 份 |
| 原始词条 | 3310 条 |
| 去重后独立单词 | 2557 个 |
| 义项总数 | 2819 个 |

---

## 8. 技术栈

Python 3.12 + FastAPI + SQLAlchemy 2.0 + Typer (CLI) + Alembic (迁移)

### 快速开始

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# CLI 命令
vocab qc run --layer 1              # Layer 1 质检
vocab qc run --layer 1 --dim chunk  # 仅质检语块
vocab qc summary                    # 质检统计
vocab review list                   # 审核队列
vocab review approve <id>           # 通过
vocab review regenerate <id>        # 重新生成（最多 3 次）
vocab review edit <id> "new content" # 人工修改
```

### API 端点

```
POST /api/qc/run            # 触发质检
GET  /api/qc/runs/{id}      # 运行详情
GET  /api/qc/summary        # 统计
GET  /api/reviews            # 审核队列
POST /api/reviews/{id}/approve     # 通过
POST /api/reviews/{id}/regenerate  # 重新生成
POST /api/reviews/{id}/edit        # 人工修改
GET  /api/export/word/{id}   # 导出单词
GET  /api/export/readiness   # 导出就绪状态
GET  /health                 # 健康检查
```

---

## 相关文档

- `roadmap.md` — 产品方法论与设计决策手册
- `docs/单词2.0--内容生产与质检工作流程.md` — 内容生产与质检 SOP
