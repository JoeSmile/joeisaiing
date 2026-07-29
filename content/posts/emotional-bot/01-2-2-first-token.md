---
title: "第一个词如何产生：Decoder 自回归全流程"
date: 2026-07-16T10:00:00+08:00
slug: "first-token"
url: "/first-token.html"
categories:
  - "学习笔记"
tags:
  - "Decoder"
  - "Transformer"
  - "自回归"
draft: false
series: "情感机器人 · 大模型应用笔记"
series_order: 5
---

生成一开始只有 `<Start>`。第一个词来自：交叉注意力从 Encoder Memory 抽语义 → 线性投影到词表 → Softmax 取最高概率。

<!--more-->

## 三步速览

1. **交叉注意力**：`<Start>` 作 Q，与 Encoder 的全部 K/V 做注意力，得到融合全文语义的特征向量
2. **输出投影**：线性层映射到词表维度（如 3 万维），Softmax 成概率
3. **取词**：概率最高的 token 即为第一个输出词

## Decoder 解析

### 前置前提

源文本已由 Encoder 编码完毕，输出与源 token 一一对应的**全局上下文记忆（Memory）**，固定不变，供交叉注意力使用。

Decoder **自回归（Auto-Regressive）**：每轮只预测 1 个新词，追加后再开下一轮。

### 阶段 2：解码器输入

初始输入仅含 `<Start>`。后续为 `[<Start> + 已生成词]`。依次做 Embedding + **位置编码**，送入 N 层 Decoder。

#### 单层 Decoder 内部（固定顺序）

① **掩码多头自注意力（因果 Mask）**

- Q、K、V 均来自当前已生成目标序列
- 上三角因果掩码将未来 token 得分置为 −∞，Softmax 后权重为 0
- 首轮仅有 `<Start>` 时，无其他 token 可交互，仅保留自身特征映射

② **残差 + LayerNorm** —— 缓解梯度消失，稳定训练 / 推理

③ **交叉注意力 Cross-Attention**

- **Q** 来自解码器上一输出；**K、V** 来自 Encoder Memory
- 从源文本全文提取、加权汇总最相关语义，完成源 → 目标对齐
- 首轮即以 `<Start>` 为查询，从原文记忆中提取开篇语义

④ **残差 + LayerNorm**

⑤ **FFN**：两层全连接 + 激活（GELU/ReLU），**独立作用于每个 token**，不做 token 间交互

⑥ **残差 + LayerNorm** —— 完成本层计算

### 阶段 3：预测输出

取当前序列**最后一个位置**的输出向量 → 线性投影到词表 → Softmax → 推理常用贪心取最高概率 token。

### 阶段 4：循环生成

新词追加到目标序列末尾，重复「嵌入 + 位置编码 → 多层 Decoder → 概率预测」，直到预测出 `<End>`。
