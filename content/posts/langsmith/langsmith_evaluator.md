---
title: "LangSmith Evaluator 实战：从选型到 Trace Feedback"
date: 2026-06-30T10:00:00+08:00
slug: "langsmith-evaluator"
url: "/langsmith-evaluator.html"
categories:
  - "AI 工程"
tags:
  - "LangSmith"
  - "Evaluator"
  - "LLM-as-a-Judge"
  - "RAG"
draft: false
---
> 以 MemoryOS 世界杯 RAG 项目为例，记录如何在 LangSmith 里配置 Evaluator，并把评分结果挂到 Trace 的 Feedback 上。

---

## 引言：Evaluator 解决什么问题？

在 RAG / Agent 项目里，**Trace 只能告诉你「发生了什么」**，Evaluator 才能回答 **「这次回答好不好」**。

LangSmith Evaluator 的核心价值是：对线上或采样 Trace **自动打分**，把结果写进 **Feedback**，方便你做：

- 回归对比（改 Prompt / 改检索后，分数是否下降）
- 质量监控（Hallucination、Conciseness、Correctness 等指标趋势）
- 问题定位（点进 Evaluator trace，看 Judge 模型的 reasoning）

下面按实际操作顺序，走一遍完整配置流程。

---

## 一、选择 Evaluator：从零创建还是套模板？

进入 LangSmith → **Configure Evaluator**，首先面临两种路径：

![选择 Evaluator 入口](/langsmith_evaluators/select_one_evaluator.png)

### 1.1 Create from scratch（从零创建）

| 类型 | 适用场景 |
| :--- | :--- |
| **LLM-as-a-Judge Evaluator** | 用自然语言 Rubric 评语义质量（正确性、简洁性、是否幻觉） |
| **Code Evaluator** | 规则明确、可编程（Exact Match、JSON schema 校验、正则） |

### 1.2 Create from a template（模板库）

LangSmith 内置大量模板，左侧按类别浏览：

- **Recommended**：PII Leakage、Prompt Injection、Toxicity、Hallucination、Correctness…
- **Security / Safety / Quality / Conversation / Trajectory** 等

![Evaluator 模板分类](/langsmith_evaluators/evaluators_templates.png)

**选型建议**：

- 有标准答案 → 优先 **Correctness** 或 **Exact Match**
- 开放问答 → **Hallucination + Conciseness** 组合
- 多轮对话 → **Conversation / Thread** 类（User Satisfaction、Task Completion）

---

## 二、Evaluator 类型速览

| 类型 | 标签 | 输入粒度 | 典型用途 |
| :--- | :--- | :--- | :--- |
| **LLM-as-a-Judge** | 单条 Run | `input` + `output` | 语义正确性、相关性、毒性 |
| **Code** | 单条 Run | 结构化字段 | 精确匹配、断言、格式校验 |
| **Thread** | 整段会话 | 多轮 messages | 用户满意度、任务是否完成 |

本文示例以 **LLM-as-a-Judge** 为主——配置灵活，适合 RAG 开放问答。

---

## 三、基础配置：Name、Application、Prompt

点击模板或「Create from scratch」后，进入 Evaluator 编辑页。

![Evaluator 基础配置](/langsmith_evaluators/evaluator_config_1.png)

关键字段：

| 字段 | 示例 | 说明 |
| :--- | :--- | :--- |
| **Name** | `worldcup_conciseness_evaluator` | 会出现在 Feedback 的 Source 里，建议 `{项目}_{指标}_evaluator` |
| **Application** | `My First App` / `memoryOS` | 绑定到具体 LangSmith Project |
| **Model** | `qwen3-max` | 充当 Judge 的模型（见下一节如何配非 GPT） |
| **Prompt** | 含 `<Rubric>` 的评分指令 | 定义 0–10 分或 true/false 的判定标准 |

示例 Rubric（世界杯 QA）：

```text
You are an expert evaluator for a World Cup football QA system (worldcup-rag).

<Rubric>
Score from 0 to 10:
9-10: Correct, complete, factual; directly answers the question; concise.
7-8:  Main facts correct; minor omissions or slight verbosity.
0-6:  Wrong numbers/players, off-topic, hallucination, or refuses when data exists.
```

**要点**：Rubric 要绑定你的业务域（worldcup-rag），并明确「什么算错」——数字错误、拒答、跑题、幻觉各怎么扣分。

---

## 四、模型配置：接入非 OpenAI 模型（如 Qwen）

Evaluator 默认列表里常见 GPT 系列。若 Judge 要用 **通义 qwen3-max** 等 OpenAI 兼容端点，点 Model 旁的设置，打开 **Model Configuration**：

![Model Configuration](/langsmith_evaluators/model_configuration.png)

| 字段 | 配置值 | 说明 |
| :--- | :--- | :--- |
| **Provider** | OpenAI Compatible Endpoint | 走 OpenAI 协议兼容网关 |
| **Model** | `qwen3-max` | DashScope 模型名 |
| **API Key Name** | `OPENAI_API_KEY` | 环境变量名（按你部署实际填写） |
| **Base URL** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云兼容端点 |
| **Temperature** | `0` | Judge 建议低温，减少评分随机性 |

配好后 **Save as preset**，Workspace 内其他 Prompt / Evaluator 可复用同一 preset。

> Judge 模型不必和线上 Answering 模型相同。线上用便宜快模型，评测用强模型，是常见做法。

---

## 五、Prompt 映射与 Feedback 格式

Evaluator 需要知道「评什么」。在 Prompt 编辑器下方，把 Trace 字段映射到模板变量：

![Feedback 配置与变量映射](/langsmith_evaluators/evaluator_config_2.png)

常见映射（MemoryOS `worldcup_chat`）：

| 变量 | 映射字段 | 含义 |
| :--- | :--- | :--- |
| `<userQuestion>` | `input.query` | 用户问题 |
| `<assistantAnswer>` | `output.answer` | 助手最终回答 |
| `<graph>` | `output.workflow` | 可选，用于评 Agent 轨迹 |

**Feedback configuration** 区定义输出格式：

| 选项 | 本文示例 | 说明 |
| :--- | :--- | :--- |
| **Feedback Key** | `conciseness` | Feedback 面板里的指标名 |
| **Include reasoning** | ✅ | 输出 `reason` 字段，便于人工复核 |
| **Response Format** | Boolean / Score | Boolean → 1/0；也可选数值分 |

勾选 **Include reasoning** 后，Trace 里会同时看到 `score` 和中文 `reason`，排障效率远高于裸分数。

---

## 六、Source 与 Filter：评哪些 Trace？

Evaluator 不会评全库所有 Run，需要配置 **数据来源 + 过滤条件**。

![Source 与 Filter](/langsmith_evaluators/evaluator_config_3.png)

示例 filter（世界杯 chat）：

```
Status is success
Run Name contains chat
Is Trace is true
```

含义：

- 只评**成功**的 Trace（失败 run 往往是 infra 问题，会污染质量分）
- 只评 **chat** 相关 Run Name（排除 embed、retrieve 等子 span）
- **Is Trace = true**：评根 Trace，而非某个中间 span

LangSmith 支持 **Copy filter(s) to use when filtering via API or SDK**——同一套条件可同步到离线评测脚本，保证线上自动评与离线 Benchmark 口径一致。

**Sampling Rate** 设为 100% 适合 QA / 回归期；生产可降到 5%–20% 控成本。

---

## 七、结果在哪里看？—— Tracing → Feedback

配置完成并触发评测后，打开任意一条 `worldcup_chat` Trace，切到 **Feedback** 面板：

![Evaluator 结果出现在 Feedback](/langsmith_evaluators/evaluator_result_in_feedback.png)

你会看到：

| 字段 | 示例 | 说明 |
| :--- | :--- | :--- |
| **score** | `10.00` | Evaluator 给出的数值分 |
| **reason** | 「答案准确完整，进球数和年份分布与事实一致…」 | Judge 的 reasoning |
| **Source** | `worldcup_conciseness_evaluator` | 哪条 Evaluator 产生的 |
| **Evaluator trace** | 链接 | 点进去看 Judge 模型完整调用链 |

左侧 Waterfall 仍是业务 Trace（`worldcup_chat` → `chat` → `simple_qa` → `ChatOpenAI` → `player_stats`）；右侧 Feedback 是**叠加在业务 Trace 上的质量层**，两者互不替代。

---

## 八、实践 Checklist

| 步骤 | 检查项 |
| :--- | :--- |
| 1 | 选对模板或 LLM-as-a-Judge，指标与业务目标一致 |
| 2 | Name / Application 命名规范，便于多 Evaluator 共存 |
| 3 | Judge 模型 preset 配好（兼容端点 + temperature=0） |
| 4 | `<userQuestion>` / `<assistantAnswer>` 映射与真实 Trace 字段对齐 |
| 5 | Filter 只覆盖目标 Run，避免评到子 span 或失败请求 |
| 6 | 开启 reasoning，并在 Evaluator trace 里抽查 Judge 逻辑 |
| 7 | 采样率与成本平衡；回归期 100%，生产期按需下调 |

---

## 九、总结

LangSmith Evaluator 的配置可以压缩成一条链路：

```
选类型/模板 → 配 Judge 模型 → 写 Rubric + 字段映射 → 设 Filter → 结果进 Feedback
```

它和自研 Benchmark（如 `golden.json` + `benchmark.py`）的关系是：

- **Benchmark**：发版前批量回归，门禁清晰
- **LangSmith Evaluator**：线上/采样 Trace 持续评分，发现 drift 和 corner case

两者指标口径尽量对齐（同一套 Rubric、同一 Judge 模型），评测结果才有可比性。

---

**相关阅读**：[如何为 RAG 系统编写高质量的 Benchmark](/rag-benchmark.html)
