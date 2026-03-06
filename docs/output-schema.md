# 输出数据结构 — 完整示例

> 本文档承接 PRD 第十五章，提供完整的输入/输出对比和多场景 JSON 示例。
> 字段说明表和分端展示规则请参见 PRD 15.1-15.2 节。

---

## 1. 前后对比：一个词从原始输入到最终出库

以多义词 **empathy** 为例，展示原始词表输入和最终出库数据的完整对比。

### 原始输入（教材词表 Excel 中的一行）

| 列 | 值 |
|----|----|
| 单词 | empathy |
| 词性 | n. |
| 中文释义 | 共情；同理心 |
| 教材来源 | 人教版九年级英语全一册 |

**仅此而已。** 没有音标、没有音节、没有语块、没有例句、没有助记。系统需要把这一行变成下面的完整数据。

### 最终出库（通过所有质检的完整数据）

```json
{
  "id": 2201,
  "word": "empathy",
  "syllables": "em·pa·thy",
  "ipa": "/ˈem·pə·θi/",
  "meanings": [
    {
      "pos": "n.",
      "def": "共情；同理心",
      "sources": ["人教版九年级英语全一册"],
      "chunk": "show empathy for",
      "sentence": "A good friend always shows empathy for others.",
      "sentence_cn": "好朋友总是对他人表现出同理心。"
    }
  ],
  "mnemonics": [
    {
      "type": "词根词缀",
      "formula": "em(进入) + path(感受) + y(名词后缀)",
      "rhyme": "进入别人的感受，就是同理心",
      "teacher_script": "同学们看这个词：empathy。我们把它拆开来——em 是一个前缀，表示"进入"……（约500字，完整六步话术）"
    },
    {
      "type": "词中词",
      "formula": "em·path·y → path(路径) ≈ 走进别人的路",
      "rhyme": "走别人走过的路，感同身受",
      "teacher_script": "……（约500字）"
    },
    {
      "type": "音义联想",
      "formula": "empathy ≈ "爱慕·怕·他" → 因为爱慕所以怕他受伤",
      "rhyme": "爱慕他所以怕他痛，就是共情",
      "teacher_script": "……（约500字）"
    },
    {
      "type": "考试应用",
      "formula": "empathy = em(进入) + path(感情) + y → 常考搭配：show empathy for / feel empathy with",
      "rhyme": "中考阅读理解常见：show empathy for others 表示对他人有同理心",
      "teacher_script": "……（约500字）"
    }
  ]
}
```

### 对比：输入 vs 出库新增了什么

| 维度 | 原始输入 | 出库数据 | 新增来源 |
|------|---------|---------|---------|
| 拼写 word | empathy | empathy | 原样保留 |
| 词性 pos | n. | n. | 原样保留 |
| 释义 def | 共情；同理心 | 共情；同理心 | 原样保留（来自权威词典） |
| 来源 sources | 人教版九年级全一册 | ["人教版九年级英语全一册"] | 结构化，如果多册出现则合并 |
| 音标 ipa | **无** | /ˈem·pə·θi/ | 系统生成（IPA GA 美式） |
| 音节 syllables | **无** | em·pa·thy | 系统生成（居中点分隔） |
| 语块 chunk | **无** | show empathy for | AI 生成（2-5 词高频搭配） |
| 例句 sentence | **无** | A good friend always shows empathy for others. | AI 生成（5-20 词，匹配学段） |
| 例句翻译 sentence_cn | **无** | 好朋友总是对他人表现出同理心。 | AI 生成 |
| 助记 mnemonics | **无** | 4 组助记（词根词缀 / 词中词 / 音义联想 / 考试应用） | AI 生成（全部 4 种类型） |
| 每组含 formula | **无** | em(进入) + path(感受) + y(名词后缀) | AI 生成（含中文标注） |
| 每组含 rhyme | **无** | 进入别人的感受，就是同理心 | AI 生成（≤15 字） |
| 每组含 teacher_script | **无** | （约 500 字，见上方完整示例） | AI 生成（六步话术） |

**结论：原始输入只有 4 个字段（单词、词性、释义、来源），出库数据新增了音标、音节、语块、例句、例句翻译、4 组助记共 9 个维度的内容。**

---

## 2. 多义词完整示例

```json
{
  "id": 1203,
  "word": "kind",
  "syllables": "kind",
  "ipa": "/kaɪnd/",
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
  "mnemonics": [
    {
      "type": "词根词缀",
      "formula": "kind → kin(亲属) + d",
      "rhyme": "对亲人(kin)般友好，就是kind",
      "teacher_script": "……（约500字）"
    },
    {
      "type": "词中词",
      "formula": "kind = king(国王) - g + d",
      "rhyme": "国王(king)换一个字母就变友好(kind)",
      "teacher_script": "同学们，kind 这个词你们都认识……（约500字，完整六步话术）"
    },
    {
      "type": "音义联想",
      "formula": "kind ≈ "开恩的" → 开恩 = 友好",
      "rhyme": "开恩的人就是友好的人",
      "teacher_script": "……（约500字）"
    },
    {
      "type": "考试应用",
      "formula": "kind → 常考搭配：be kind to sb. / a kind of / all kinds of",
      "rhyme": "be kind to 对…友好；a kind of 一种——两个意思都是高频考点",
      "teacher_script": "……（约500字）"
    }
  ]
}
```

---

## 3. 极短基础词示例（助记留空）

```json
{
  "id": 1001,
  "word": "a",
  "syllables": "a",
  "ipa": "/eɪ/",
  "meanings": [
    {
      "pos": "art.",
      "def": "一个",
      "sources": ["人教版三年级英语上册(PEP)"],
      "chunk": "a book",
      "sentence": "I have a cat at home.",
      "sentence_cn": "我家里有一只猫。"
    }
  ],
  "mnemonics": []
}
```

> 按 PRD 3.5 "宁缺毋滥"原则，极短基础词（a, an, as, but 等）无合理拆解逻辑时，mnemonics 为空数组。
