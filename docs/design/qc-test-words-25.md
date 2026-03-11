# 质检模型评估 — 25 词精选

## 选词原则

每类 5 词，选择标准：
1. **最大化维度覆盖**：优先选有词根词缀/词中词/音义联想的词，让助记维度有足够样本
2. **最大化区分力**：选最容易让模型"翻车"的词（多义、多词性、前缀词）
3. **音节复杂度梯度**：每类至少包含单音节和多音节词

---

## 1. 常规词（5 词）

| 词 | 词性 | 释义 | 音节 | 词根 | 词中词 | 音义 | 选择理由 |
|----|------|------|------|------|--------|------|---------|
| **focus** | v./n. | 集中；焦点 | fo·cus | ✅ | ✅ | ✅ | 双词性 + 三种助记全有 + focus on 考点 |
| **believe** | v. | 相信；认为 | be·lieve | ✅ | ✅ | ✅ | 三种助记全有 + believe in 辨析 |
| **manage** | v. | 管理；设法完成 | man·age | ✅ | ✅ | ✅ | 三种助记全有(man+age) + manage to do 考点 |
| **protect** | v. | 保护；防护 | pro·tect | ✅ | ❌ | ❌ | 前缀 pro- 测音节切分 + protect...from 考点 |
| **process** | n./v. | 过程/处理 | pro·cess | ✅ | ❌ | ❌ | 双词性+重音切换 + 前缀 pro- 测音节 |

> 覆盖：3 词三种助记全有，2 词测前缀音节；2 词双词性

---

## 2. 不规则变形（5 词）

| 词 | 词性 | 释义 | 音节 | 词根 | 词中词 | 音义 | 选择理由 |
|----|------|------|------|------|--------|------|---------|
| **occur** | v. | 发生；出现 | oc·cur | ✅ | ❌ | ❌ | 双写 r + It occurs to sb that 考点 |
| **analyze** | v. | 分析 | an·a·lyze | ✅ | ❌ | ❌ | 多音节切分 + analyze→analysis 变形 |
| **lie** | v. | 躺；说谎 | lie | ❌ | ❌ | ❌ | 单音节 + 两套变形(lay-lain/lied-lied)最易错 |
| **leaf** | n. | 叶子 | leaf | ❌ | ❌ | ❌ | 单音节 + 不规则复数 leaves |
| **curriculum** | n. | 课程 | cur·ric·u·lum | ✅ | ❌ | ❌ | 最长词测音节 + 拉丁复数 curricula |

> 覆盖：3 词有词根，2 词单音节测 SA1；lie 是义项匹配+变形双重难点

---

## 3. 多义/熟词生义（5 词）

| 词 | 词性 | 释义 | 音节 | 词根 | 词中词 | 音义 | 选择理由 |
|----|------|------|------|------|--------|------|---------|
| **fine** | adj./n. | 好的/罚款 | fine | ❌ | ❌ | ❌ | 最经典多义词 + 单音节 + 助记应 false |
| **leave** | v. | 离开；留下 | leave | ❌ | ❌ | ❌ | 离开/留下/假期 + leaves 跨词性 |
| **address** | n./v. | 地址/解决 | ad·dress | ✅ | ❌ | ❌ | 熟词生义核心词 + 有前缀 |
| **interest** | n. | 兴趣；利息 | in·ter·est | ✅ | ❌ | ❌ | 三义(兴趣/利益/利息) + be interested in 考点 |
| **sound** | n./adj. | 声音/合理的 | sound | ❌ | ❌ | ❌ | 名/动/形三词性切换 + 单音节 |

> 覆盖：5 词全是义项匹配杀手；3 词单音节；fine/leave/sound 助记应输出 false

---

## 4. 易混淆（5 词）

| 词 | 词性 | 释义 | 音节 | 词根 | 词中词 | 音义 | 选择理由 |
|----|------|------|------|------|--------|------|---------|
| **affect** | v. | 影响 | af·fect | ✅ | ❌ | ❌ | affect/effect 最经典混淆 |
| **principle** | n. | 原则 | prin·ci·ple | ✅ | ❌ | ❌ | principle/principal 拼写混淆 |
| **consistent** | adj. | 一致的 | con·sis·tent | ✅ | ❌ | ❌ | consistent with 考点 + 前缀 con- 测音节 |
| **sensitive** | adj. | 敏感的 | sen·si·tive | ✅ | ❌ | ❌ | sensitive/sensible 语义混淆 |
| **adopt** | v. | 采纳；收养 | a·dopt | ✅ | ❌ | ❌ | adopt/adapt 最小对混淆 |

> 覆盖：5 词全有词根；5 种不同混淆类型（形近/义近/搭配/拼写/最小对）

---

## 5. 高阶抽象（5 词）

| 词 | 词性 | 释义 | 音节 | 词根 | 词中词 | 音义 | 选择理由 |
|----|------|------|------|------|--------|------|---------|
| **abstract** | adj./n./v. | 抽象的/摘要/提取 | ab·stract | ✅ | ❌ | ❌ | 三词性 + 前缀 ab- + 词汇天花板测试 |
| **perspective** | n. | 观点；视角 | per·spec·tive | ✅ | ❌ | ❌ | per+spect+ive 标准词根词缀 |
| **consequence** | n. | 后果；结果 | con·se·quence | ✅ | ❌ | ❌ | as a consequence 考点 + qu 原子单位测音节 |
| **fundamental** | adj. | 基础的；根本的 | fun·da·men·tal | ✅ | ❌ | ❌ | 四音节最长 + fund 词根 |
| **interpret** | v. | 解释；口译 | in·ter·pret | ✅ | ❌ | ❌ | 前缀 in- + interpret as 考点 |

> 覆盖：5 词全有词根；4 词有前缀测音节切分；abstract 三词性

---

## 汇总统计

| 维度 | 适用词数 | 正例 | 反例 | 案例数 |
|------|---------|------|------|--------|
| 例句 | 25 | 25 | 25 | 50 |
| 语块 | 25 | 25 | 25 | 50 |
| 音节 | 25 | 25 | 25 | 50 |
| 助记-词根词缀 | 20 | 20 | 20 | 40 |
| 助记-词中词 | 3~5 | ~4 | ~4 | ~8 |
| 助记-音义联想 | 3~5 | ~4 | ~4 | ~8 |
| 助记-考试应用 | ~15 | 15 | 15 | 30 |
| **合计** | | **~118** | **~118** | **~236** |

评估表行数：236 × 3 模型 = **708 行**

### 考试应用适用词（约 15 词）

focus(on), believe(in), manage(to do), protect(from), occur(It occurs to sb),
interest(be interested in), affect(vs effect), principle(vs principal),
consistent(with), sensitive(to), adopt(vs adapt),
abstract(多义), consequence(as a consequence), interpret(as), leave(for/leave sb doing)

### 不适用助记的词（应输出 false 的词，也是重要测试点）

fine, leave, sound, lie, leaf — 这些词在词中词/音义联想维度应判定为 false，
测试模型能否正确拒绝不合适的强行拆解。
