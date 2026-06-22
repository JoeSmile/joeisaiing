---
title: "LLM 聊天与 RAG 安全怎么落地？纵深防御、快失败与第三方 Guard 选型"
date: 2026-04-24T10:00:00+08:00
slug: "chat-security"
url: "/chat-security.html"
categories:
  - "AI 工程"
tags:
  - "Prompt Injection"
  - "RAG"
  - "LLM Guard"
  - "Security"
  - "MemoryOS"
draft: false
---

> **说明**：下文是 RAG 聊天场景的**安全思路 + MemoryOS 里真实做过的取舍**。不是现网配置承诺，规则阈值与 Prompt 原文不公开。  
> **落地对照**（分层、包名、时序）：[MemoryOS 聊天安全一张图](/memoryos-security-map.html)

做 AI 聊天应用时，安全往往被排在「能跑起来」之后。但真正上线后，**Prompt 注入**、**RAG 间接注入**、**工具链滥用**和**成本失控**会一起找上门。最近在 MemoryOS 里梳理聊天/RAG 安全方案，把内部工程文档整理成一篇可发布的总结，方便对照和迭代。

核心结论先说：

1. **快失败**：在调用 LLM **之前**用廉价检查拒绝或清洗，而不是先让攻击进模型再反应。
2. **纵深防御**：用户输入、知识库 chunk、Prompt 结构、限流配额，多层叠加，不指望单一银弹。
3. **自研规则做底座**，第三方 Guard 经 **Adapter + 配置开关** 按需叠加；CI 与本地开发应能走不依赖 GPU 的轻量路径。

<!--more-->

## 一、威胁从哪来？

一个典型的 RAG 聊天链路，至少有四类输入需要当成「不可信」：

```text
用户输入 ──► 直接 Prompt 注入（角色劫持、指令覆盖、越狱）
RAG 知识库 ──► 间接注入（文档内藏「覆盖系统规则」类话术）
工具回灌 ──► 联网搜索 / 外部 API 结果被模型当上下文
滥用请求 ──► 超长输入、高频刷接口、Agent 多轮烧钱
```

| 威胁 | 典型来源 | 后果 | 主要防线 |
| :--- | :--- | :--- | :--- |
| 直接注入 | 用户消息 | 偏离人设、泄露 system、越权 | 长度限制、输入 Guard、策略层 Prompt |
| 间接注入 | 检索到的文档块 | 模型执行资料内指令 | 入库 + 检索后 **双点** 内容清洗 |
| 工具链滥用 | Agent 工具调用 | 成本、外泄 query | 限流、Token 配额、参数校验 |
| DoS / 烧钱 | API 滥用 | 延迟、账单 | 限流、配额 |
| 日志泄露 | 链路追踪 / 应用日志 | 隐私 | 脱敏、采样 |

**间接注入**往往是 RAG 场景里最容易被低估的：用户输入很干净，但知识库资料里埋了覆盖类指令，模型照样可能中招。

## 二、纵深防御：一层不够，叠多层

「纵深防御」不是堆重复的正则，而是**在不同阶段、用不同成本**挡不同攻击面：

```text
┌─ FE/BFF（可选，可绕过）────────────────────────────┐
│  轻量 Prompt Guard：早反馈、减无效请求                │
└───────────────────────────┬──────────────────────────┘
                            ▼
┌─ API 用户输入（权威）────────────────────────────────┐
│  L0  长度 / 格式校验 → 拒绝                           │
│  L0  规则 / 启发式检测 → 拒绝                          │
│  L0' 可选 ML / 中间件 Guard（按环境启用）               │
└───────────────────────────┬──────────────────────────┘
                            ▼
┌─ RAG 管道（不可信数据）──────────────────────────────┐
│  入库前：内容清洗                                     │
│  检索后：再清一次（漏网 chunk）                        │
│  可选：DeSyntax 类组件（打碎命令句式）                 │
└───────────────────────────┬──────────────────────────┘
                            ▼
┌─ Prompt 结构（软防线）────────────────────────────────┐
│  策略区 + 文档区 + 工具说明；用户输入单独成消息         │
└───────────────────────────┬──────────────────────────┘
                            ▼
                       LLM / Tools
                            ▼
┌─ 输出（可选）────────────────────────────────────────┐
│  输出扫描；canary / 外泄检测                          │
└──────────────────────────────────────────────────────┘
```

### 什么叫「快失败」？

很多人把「快失败」理解成「先让模型挨一次打，看回复怪不怪」。在 LLM 安全里，更合理的定义是：

> **在发起 LLM 请求之前**，用字符数检查、规则匹配、轻量 ML 分类等**低成本手段**，直接拒绝或清洗，避免把恶意内容送进 prefill。

BFF 层的 Guard 可以被绕过（直连 API），所以 **API 层必须是权威校验**；BFF 的价值主要是 UX——早点告诉用户「这条输入有问题」，少浪费一轮网络往返。

## 三、自研底座：别一上来就绑大包

无论是否引入第三方库，建议先有一套**可测、可共享、不依赖 GPU** 的自研能力：

| 能力 | 职责 |
| :--- | :--- |
| 输入校验 | 长度、空内容、基础格式 |
| 用户侧 Guard | 可疑 override / 越狱模式 → 拒绝 |
| 检索内容清洗 | Unicode 规范化、控制字符、可疑短语处理、单块上限 |
| 分层 Prompt | 策略 / 文档 / 工具说明分区 |

**检索内容清洗要在两个时机用同一套逻辑**：

1. **入库前**——尽量不让「毒文档」进索引  
2. **检索之后**——对漏网 chunk 进 Prompt 前再处理一次  

Prompt 分层示意（软防线，和 OWASP spotlighting 思路一致）——**以下为结构示例，非生产原文**：

```text
[SystemMessage]  ← 每次调用 LLM 前临时组装一条（不是每条消息都套壳）
  <POLICY>
  （简短、固定的助手行为与边界；具体措辞按产品定制，此处不公开）
  </POLICY>
  <DOCS>
  [1] …（本轮 retrieve 到的、经清洗后的检索正文）
  </DOCS>
  <TOOL_POLICY>
  （仅 Agent / ReAct 路径：时间语境、工具用法、检索是否足够等）
  </TOOL_POLICY>

[HumanMessage] 用户真实输入（历史各轮同理）
[AIMessage]    助手历史回复
[ToolMessage]  工具返回（若有）
```

**常见误解**：`<POLICY>` / `<DOCS>` / `<TOOL_POLICY>` **不是**给对话里每个 role 各包一层，而是 **拼进同一条 `SystemMessage` 的正文分区**。顺序 **POLICY → DOCS → TOOL_POLICY** 表示：先读固定规则，再看不可信资料，最后看工具策略。

**每轮怎么用？** 用户每发一条新消息、图跑到「调用模型」节点时，通常会：

1. 用 **本轮最后一条用户话** 做 retrieve，得到 **本轮** 的检索块；
2. **重新拼** 一条 system（POLICY + 本轮 DOCS + 可选 TOOL_POLICY）；
3. 再拼上 **整段对话历史**（多轮 Human / AI / Tool），一起发给 LLM。

因此：

| 内容 | 放在哪 | 是否每轮重建 |
| :--- | :--- | :--- |
| 永久规则 | `<POLICY>`（system 内） | 文案固定，随 system 每轮带上 |
| 检索到的知识库正文 | `<DOCS>`（system 内） | **每轮按 retrieve 结果重建** |
| 工具 / 时间语境 | `<TOOL_POLICY>`（system 内） | ReAct 时每轮带上 |
| 用户当前与历史问题 | `HumanMessage` | 历史原样保留，**不**塞进 system |

**和「入库 chunk」的区别**：ETL 阶段把文档切成块写入向量库；`<DOCS>` 里是 **运行时从库里读出来、准备进 Prompt 的那几条正文**，不是给库里每条记录再套一层 POLICY。

常见踩坑：

- **把用户原文拼进 system 的专用区块**（例如 `<USER_QUERY>`）。角色边界一糊，覆盖指令的成功率会高很多。用户输入应只出现在 `HumanMessage`。
- **以为 DOCS 包的是「数据库里所有 chunk」**。实际只有 **本轮检索命中、且过分数阈值** 的少数几条会进 `<DOCS>`。

## 四、第三方包：可以试，但别当唯一防线

以下是在 RAG 项目里**常见、值得试一把**的开源组件；是否启用按环境决定，公开文不写死开关。

### 前端 / BFF

| 包 | 适用层 | 说明 |
| :--- | :--- | :--- |
| [llm-prompt-guard](https://github.com/shanemhamilton/llm-prompt-guard) | Next BFF | 零依赖、亚毫秒；可用「标记可疑、由 API 决断」模式 |
| rag-poison-guard（npm） | — | Node 专用；与 Python ETL 栈不一致时，往往用自研清洗更合适 |

### Python API

| 包 | 适用层 | 说明 |
| :--- | :--- | :--- |
| [LLM Guard](https://github.com/protectai/llm-guard) | 用户输入 / 可选输出 | Prompt 注入、不可见字符等；要额外 pip，本地体感一下延迟再决定 |
| [llm-injection-guard](https://github.com/maheshmakvana/llm-injection-guard) | FastAPI 中间件 | 轻量；适合与自研规则**对照** |
| [EntropyShield](https://pypi.org/project/entropyshield/) | 低信任检索 / 工具 snippet | DeSyntax 打碎句法；用几条**业务正例**看有没有误伤 |

接入模式（示意，阈值与开关按环境配置）：

```python
# LLM Guard：输入扫描链
scanners = [InvisibleText(), PromptInjection(threshold=...)]
sanitized, results_valid, _ = scan_prompt(scanners, user_text)
if not all(results_valid):
    raise ...  # 统一业务错误，不向外暴露规则细节

# 检索块：规则清洗 → 可选 DeSyntax 链
def sanitize_chunk(text: str) -> str:
    base = rule_based_sanitizer(text)
    if optional_desyntax_enabled():
        return desyntax_shield(base)
    return base
```

### 红队 / CI（非热路径）

| 工具 | 用途 |
| :--- | :--- |
| [Garak](https://github.com/NVIDIA/garak) | 自动化探针（注入、越狱、泄露）；适合 nightly 或发版前 |
| 契约 / 集成测试 | 业务正例 + 合成反例；PR 门禁 |
| Lakera Guard（云 API） | 高检出率；有预算与合规需求时再评估 |

CI 无 GPU 时，应保证流水线走**不下载大模型**的轻量路径；ML Guard 的启用范围与 CI 策略分开规划。

## 五、策略对比：先知道有哪些牌

下面表格是**选型参考**（机制、成本、经验上的误杀风险），**不是**我们在 MemoryOS 里跑出来的实测报表。

### 按防线类型（定性）

| 策略 | 机制 | 延迟 | 成本 | 间接注入检出 | 误杀风险 | 建议阶段 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 长度限制 | 字符/token 上限 | 极低 | $0 | — | 低 | **必做** |
| 规则 / 启发式 | 模式与短语表 | 极低 | $0 | 中 | 中 | **必做** |
| Unicode 规范化 | 规范化 + 可疑字符处理 | 极低 | $0 | 中 | 低 | **必做** |
| 策略/文档分层 | Prompt 结构 + 角色分离 | 无 | $0 | 中（软） | 低 | **必做** |
| DeSyntax | 打碎命令句式 | 低 | $0 | 中高 | 中 | 可选试用 |
| ML 分类 | 小模型 / 分类器 | 中–高 | CPU/GPU | 高 | 中 | 可选试用 |
| LLM-as-Judge | 第二模型审输入 | 高 | $$ | 很高 | 低–中 | 高价值场景 |
| 云 API | 托管检测 | 中 | $$$ | 很高 | 较低 | 生产高合规 |
| NeMo Guardrails | 可编程对话轨 | 高 | 中 | 高（行为） | 中 | 复杂 Agent |
| Garak 红队 | 持续探针回归 | — | 低 | — | — | 发版前，非运行时替代 |

### 按场景选组合

| 场景 | 推荐最小集 | 加强选项 |
| :--- | :--- | :--- |
| 本地 demo / CI 无 Key | 自研规则 + 双点清洗 + 分层 Prompt | 暂不叠 ML |
| 垂直领域 RAG | 上栏 + 限流 | + ML Guard + DeSyntax（手点几条正例） |
| 公网多租户 SaaS | 上栏 + ML Guard + 输出扫描 + 审计 | + 云 Guard / NeMo + Garak |
| 高敏感（金融/医疗） | 全套 + PII 处理 + 人工审核 | 专用合规网关 |
| 仅防烧钱 | 长度 + 限流 + Token 配额 | 与注入无关但必配 |

### 高级方案什么时候上？

| 方案 | 适用 | 不适用 |
| :--- | :--- | :--- |
| **LLM-as-Judge** | 输入复杂、规则误杀多、预算允许 | 延迟敏感、离线 CI |
| **NeMo Guardrails** | 多步 Agent、强合规话术、工具白名单 | 单一 RAG 问答、团队无轨维护力 |
| **Instruction Hierarchy / StruQ** | 自托管模型、可改权重 | 仅用 OpenAI 兼容 API |
| **向量库投毒检测** | 开放上传、多租户 KB | 固定 ETL、数据源可信 |
| **输出 exfil 扫描** | 公网、担心回复泄露 system | 纯内部 demo |

## 六、怎么验：我们没搞「拦截率 dashboard」

行业文章爱写：建正/反例库，算**拦截率、误杀率、p50/p99 延迟**。方向没错，但 MemoryOS **目前没做到这一层**——没有独立样本文件，也没有自动化的指标看板。

### 现在实际在用的

| 手段 | 干什么 | 门槛 |
| :--- | :--- | :--- |
| **Harness 契约** | `test_chat_security_contract`：一条足球分析正例（要 200）、一条 `ignore previous instructions…` 反例（要 422，且消息不落库） | PR **必绿** |
| **单元测试** | `rag_sanitizer`、ETL、BFF `prompt-guard`、中间件等；句子直接写在 `test_*.py` 里，改规则时顺手补一条 | 本地 / CI |
| **人肉冒烟** | 预发自己点几条：正常战术问句、带「失误/无视」的中文、典型英文注入 | 发版前习惯动作 |
| **Garak**（默认关） | `pnpm security:garak`，走上游 `promptinject` 探针；报告人眼看，**失败不挡 PR** | nightly / 想扫的时候 |

所谓「正例 / 反例」在我们这儿是**两类测试思路**，不是两套成体系的 dataset。`harness/cases/*.yaml` 还在 backlog 里。

### 够用吗？

对小团队、垂直领域 MVP：**Harness + 单测 + 偶尔 Garak** 往往比先搭评测平台划算。真正上线公网、多租户之前，再考虑把样本抽成文件、记延迟分位数——那是后话。

### 试用第三方 Guard 的顺序（我们走的）

1. 自研长度 + 规则 + RAG 双点清洗 + 分层 Prompt（底座，先写测试）  
2. BFF `llm-prompt-guard`（`tag` 体验；`quarantine` 可选）  
3. `llm-injection-guard` 中间件（和自研规则对照）  
4. `LLM Guard`（能接受 pip/延迟再开）  
5. EntropyShield on 低信任 chunk（先看足球正例误不误伤）  
6. Garak（冷路径，别当运行时替代）  

## 七、配置与运维（几条硬习惯）

- 开关、长度上限：**环境变量**，别写死在文章或前端。  
- 拒绝统一 `422` + 固定 `message`，**别**把命中哪条规则返回给客户端。  
- 改 `injection_patterns` / Prompt 分区：**走 CR**，看 Harness 和几条手点用例。  
- 开发可以关 ML / Garak；**合并主分支前**至少保证 Harness 契约绿。

## 八、小结

没有「装一个 npm 包就安全」的捷径。MemoryOS 的路径很土但很实在：

- **必做**：长度、自研规则、RAG 入库+检索双洗、Prompt 分区、API 权威校验  
- **按需叠**：BFF 早反馈、中间件/ML Guard、低信任 EntropyShield、Garak 冷路径  
- **怎么验**：Harness 两条 + 单测里内嵌句子 + 预发手点；**还没**拦截率/误杀率报表  

细节与包名对照见 [MemoryOS 聊天安全一张图](/memoryos-security-map.html)。若你也在做垂直 RAG，建议先把**间接注入 + 快失败**补齐，再考虑 ML——性价比通常最高。

## 参考

- [OWASP LLM Top 10 — LLM01 Prompt Injection](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [LLM Guard 文档](https://protectai.github.io/llm-guard/)
- [llm-prompt-guard（npm）](https://github.com/shanemhamilton/llm-prompt-guard)
- [EntropyShield（PyPI）](https://pypi.org/project/entropyshield/)
- [Garak](https://github.com/NVIDIA/garak)
