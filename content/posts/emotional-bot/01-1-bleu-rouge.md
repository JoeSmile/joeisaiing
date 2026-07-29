---
title: "BLEU 与 ROUGE：别漏词、别漏关键点"
date: 2026-07-12T10:00:00+08:00
slug: "bleu-rouge"
url: "/bleu-rouge.html"
categories:
  - "学习笔记"
tags:
  - "BLEU"
  - "ROUGE"
  - "评估指标"
  - "大模型应用"
draft: false
---

评估文本生成时，两个最常被问到的自动指标：**BLEU** 查「用词像不像标准答案」，**ROUGE** 查「关键信息有没有漏掉」。

<!--more-->

## BLEU

> **感悟**：BLEU 别漏词——从文档中查到的原文是否匹配。

### 1. 怎么读、怎么叫？

**BLEU** 直译常是「双语评估替补」。实际工作中几乎没人说中文全称，直接读 **「布鲁」**，或说「BLEU 值 / BLEU 分数」。

### 2. 到底是什么？

**一句话**：BLEU 是机器翻译 / 文本生成质量评估指标，通过统计 **AI 输出** 与 **标准参考答案** 之间 **n-gram（连续 n 个词）的重叠度** 打分。

直观例子：

- 参考答案：`The cat is on the mat`
- 学生 A：`The cat is on the mat` → BLEU = 1.0
- 学生 B：`The cat sits on the mat` → BLEU ≈ 0.8
- 学生 C：`A dog under the table` → BLEU ≈ 0

**核心逻辑**：不关心语义是否「理解」，只关心「用词和参考答案有多像」。

### 3. 计算逻辑（三步）

1. **统计 n-gram 命中**（1-gram ~ 4-gram）
2. **加权平均**（通常取 n=1~4 的几何平均）
3. **惩罚过短输出**（过短会打折）

最终输出 0~1 分数，越高越好。

### 4. 代码实战

场景：合同摘要生成器，准备人工标准摘要后批量算 BLEU。

```python
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction

reference = [
    ["本", "合同", "约定", "甲方", "向", "乙方", "采购", "铝锭", "500", "吨"]
]
candidate = ["甲方", "向", "乙方", "采购", "铝锭", "500", "吨"]

smooth = SmoothingFunction().method1
score = sentence_bleu(reference, candidate, smoothing_function=smooth)
print(f"BLEU-4 分数: {score:.4f}")
```

批量：

```python
from nltk.translate.bleu_score import corpus_bleu

references = [...]  # 人工摘要
candidates = [...]  # AI 摘要
corpus_score = corpus_bleu(references, candidates)
```

### 5. 优缺点

| 优点 | 缺点 |
| :--- | :--- |
| 计算快、可复现 | 只看词形不看语义（good ≠ excellent） |
| 与人工评分有一定相关性 | 必须有参考答案 |
| 适合翻译、摘要 | 长文本易偏低；不适合开放对话 / 创意写作 |

### 6. 落地用法

| 场景 | 使用方式 |
| :--- | :--- |
| 合同摘要评估 | AI 摘要 vs 人工标准摘要 |
| RAG 答案评估 | AI 回答 vs 标准答案 |
| 模型迭代验证 | 新旧模型同批数据对比 |
| 自动化测试 | CI 分数下降超阈值则阻断 |

### 7. 局限性与建议

同义改写可能分数偏低。建议：BLEU 作辅助，配合人工抽查与 ROUGE；设及格线（如 > 0.5）；MVP 阶段更多是内部调试工具。

### 一句话总结

> **BLEU = 统计「AI 输出」与「标准答案」词重叠度的自动化工具。** 适合回归测试，不适合最终用户验收。

---

## ROUGE

> **感悟**：ROUGE 看看有没有漏关键点——总结是否遗漏关键信息。

全称 **Recall-Oriented Understudy for Gisting Evaluation**。日常读 **「如日」**（/ruːʒ/）即可。

### 和 BLEU 对比

| 指标 | 核心思路 | 通俗理解 |
| :--- | :--- | :--- |
| **BLEU** | AI 说出来的词，和标准答案有多少一样？ | 用词覆盖率（别漏词） |
| **ROUGE** | 标准答案里的关键信息，AI 提到了多少？ | 信息召回率（别漏关键点） |

例子：参考答案含「金额 / 付款周期 / 违约金」，AI 只写了前两项 → BLEU 可能仍高，ROUGE 会因漏「违约金」而下降。

### 常见变体

| 变体 | 计算方式 | 适合场景 |
| :--- | :--- | :--- |
| ROUGE-N | n-gram 重叠 | 通用摘要 |
| ROUGE-L | 最长公共子序列（LCS） | 长文本、词序重要 |
| ROUGE-S | Skip-Bigram | 对词序不敏感 |
| ROUGE-1 / ROUGE-2 | 单词 / 二元组 | 覆盖与短语连贯 |

### 计算实例

```python
from rouge_score import rouge_scorer

reference = "合同约定甲方采购铝锭500吨，单价18000元，总价900万元，付款周期60天"
candidate = "合同约定甲方采购铝锭500吨，总价900万元，付款周期60天"

scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=False)
scores = scorer.score(reference, candidate)

print("ROUGE-1:", scores['rouge1'])
print("ROUGE-2:", scores['rouge2'])
print("ROUGE-L:", scores['rougeL'])
```

关注 **Recall**（漏没漏）、**Precision**（有没有废话）、**F1**。

### ROUGE vs BLEU 选型

| 对比维度 | BLEU | ROUGE |
| :--- | :--- | :--- |
| 核心关注 | 用词准确性 | 信息覆盖度 |
| 更适合 | 机器翻译（答案较唯一） | 摘要、问答（答案可变化） |
| 计算侧重 | 更偏精确率 | 更偏召回率 |

### 组合拳建议

```text
用词准确性   →   BLEU
信息覆盖度   →   ROUGE-L
语义相似度   →   大模型评分
用户感受     →   CSAT
```

MVP 阶段优先 **ROUGE-L + 人工抽查**，BLEU 作辅助。

### 一句话总结

> **BLEU 检查「词对不对」，ROUGE 检查「关键点漏没漏」。**
