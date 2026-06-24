---
title: "Agent Tool 开发备忘录（LangChain + LangGraph）"
date: 2026-05-25T10:00:00+08:00
slug: "agnet-tool"
url: "/agnet-tool.html"
categories:
  - "AI 工程"
tags:
  - "LangChain"
  - "LangGraph"
  - "Agent"
  - "Tool"
  - "MemoryOS"
draft: false
---

> **说明**：下文以 LangChain / LangGraph 生态为主，兼写 **企业自研 Registry + Executor** 路线（如 MemoryOS）。RAG 上下文、用户记忆等常通过 **Graph 节点 + system prompt** 注入，与 Tool 并行，并非「一切能力都必须是 Tool」。

## 一、核心基础认知（必须吃透）

1. **工具本质**：Tool 是 LLM **主动决定调用**的外部能力接口；LLM 仅通过 `name`、`description`、参数 Schema 决策，看不到 handler 源码。
2. **与被动上下文的区别**
   - **Tool**：模型输出 `tool_calls` 后才执行（如联网搜索、下单、查实时 API）
   - **RAG / Memory**：编排层在 `call_model` 前注入 system / 检索结果，**不经过** tool_calls
3. **核心三要素**
   - `name`：唯一标识，语义清晰
   - `description`：使用说明书，是选 tool 的核心依据
   - `args_schema` / JSON Schema：约束入参类型与必填项
4. **Function Calling vs Tool**
   - Function Calling：模型原生结构化调用指令
   - Tool（LangChain）：Runnable 封装；企业项目也常用 **自研 `ToolDefinition` + OpenAI schema**
5. **标准消息链路**
   `用户提问 → LLM 生成 tool_calls → 执行 Tool → ToolMessage（带 tool_call_id）→ LLM 生成回答`

<!--more-->

## 二、工具定义规范（调用准确率的根基）

### 1. 定义方式怎么选

| 方式 | 适用 |
|------|------|
| `@tool` 装饰器 | 脚本、Demo、LangChain 原生栈 |
| 继承 `BaseTool` | 需要复杂生命周期、同步/异步分支 |
| **`ToolDefinition` + Registry** | 企业生产：统一注册、OpenAI schema、handler 注入 Context |

### 2. 黄金原则：描述即契约

Docstring / `description` 建议写清：

1. **适用场景**：什么时候必须调
2. **禁止场景**：何时不要用（避免与 RAG、其他 tool 重叠）
3. **效果说明**：返回什么、粒度多大

示例（MemoryOS `tavily_search`）：*Use when retrieved knowledge does not answer the user's question…*

### 3. 参数约束

- 简单参数：函数签名 + 文档说明
- 复杂参数：Pydantic `args_schema` 或 JSON Schema（`required`、`enum`、`type`）
- 避免裸 `query` / `data` 无说明

### 4. 返回值：自然语言 or 结构化 JSON

**不必强行自然语言。** 面向 LLM 的 ToolMessage 关键是 **字段稳定、语义清晰**：

```json
{"success": true, "summary": "…", "output": {…}, "duration_ms": 120}
{"success": false, "error": "tool_timeout: tavily_search", "summary": "…"}
```

- 单工具、短结果：自然语言 OK
- 多工具并行、需程序解析：**JSON + `success` / `error`** 更稳
- 超长结果：截断 + 摘要，避免撑爆上下文

### 5. 错误处理：Handler 内 or Executor 外（二选一，推荐后者）

| 模式 | 做法 |
|------|------|
| Handler 内 catch | 每个 tool 自己 try/except，返回可读错误 |
| **Executor 统一兜底（推荐）** | Handler 可抛错；Executor 设 timeout、捕获异常、包装成统一 `ToolExecutionResult` |

企业项目优先 **Executor 层**，便于统一超时、指标、审计；避免每个 handler 重复 boilerplate。

---

## 三、LLM 绑定与调用

1. **绑定**：`llm.bind_tools(schemas)` — 未注入 schema 的 tool，模型感知不到
2. **`bind_tools` 与 `with_structured_output`**
   - 若**同一 Runnable**既要 tool 又要结构化输出，顺序敏感，易冲突
   - **常见拆法**：tool 轮用 `bind_tools().ainvoke`；最终用户可见回答用**自然语言流式**，不在同一链上叠 structured output（MemoryOS 即如此）
3. **单轮工具数量**：经验上 ≤8；按场景动态加载 tool 集更稳
4. **System Prompt 补强**
   > 涉及库外事实、实时信息，须先 tool 或明确说明无法获取；禁止编造；tool 失败可修正参数重试，仍失败须告知用户。
5. **模型适配**
   - 原生 FC（GPT、Qwen、GLM）：`bind_tools` 即可
   - 弱 FC 模型：`create_react_agent` + `handle_parsing_errors=True`，或 ReAct 文本协议

---

## 四、LangGraph 架构

### 1. 标准 ReAct 环

```text
START → trim / retrieve / memory … → call_model（bind_tools）
    → 条件路由
        ├─ 有 tool_calls → execute_tools → 回到 call_model
        └─ 无 tool_calls → END
```

RAG 检索通常在 **call_model 之前** 完成，结果进 system prompt，与 tool 环并行。

### 2. ToolNode vs 自研 execute 节点

| | LangChain `ToolNode` | 自研 `execute_tools` + Executor |
|--|----------------------|----------------------------------|
| 适用 | 快速原型、标准 @tool | 生产：DB 会话、user_id、统一 timeout |
| tool_call_id | 自动 | 手写时必须严格透传 |
| 异常 | 内置捕获 | Executor 统一包装 ToolMessage |

**不是「禁止手写」**——MemoryOS 采用 Registry + `ToolExecutor` + `execute_tools`，未使用 `ToolNode`。

### 3. 状态设计

- 消息列表：`Annotated[list, add_messages]`
- **防死循环（二选一或并用）**
  - **图级**：`graph.invoke(..., config={"recursion_limit": N})`（MemoryOS：`AGENT_MAX_ITERATIONS`）
  - **State 级**：`iterate_count` / `retry_count` + 条件边（细粒度日志、退避）
- State **只存可序列化数据**；`db`、模型实例通过 `configurable` / `graph_db_session` / `ToolContext` 注入

### 4. Checkpointer：何时需要

| 场景 | 建议 |
|------|------|
| Human-in-the-loop、中断恢复、同 thread 跨请求续跑 | SqliteSaver / PostgresSaver |
| **普通 Chat（消息已落 PostgreSQL）** | 用 DB 历史拼 state 即可，**非必须** Checkpointer |

### 5. 多模态 / 分支 tool 集

按输入类型（图/音/文）条件加载不同 tool 集，降低单轮 schema 数量。

---

## 五、高频致命坑

| 序号 | 现象 | 根因 | 修复 |
|------|------|------|------|
| 1 | 从不调 tool | 未 `bind_tools` | 注入 OpenAI function schemas |
| 2 | 选错 tool | 描述重叠、无禁止场景 | 差异化 description；RAG 与 Tavily 边界写清 |
| 3 | `tool_call_id` 报错 | 手写节点 ID 丢失 | 对齐官方 ToolNode 或严格透传 id |
| 4 | 无限循环 | 无 iteration 上限 | `recursion_limit` + 无 tool_calls 即 END |
| 5 | 参数/schema 冲突 | bind_tools 与 structured output 同链 | 拆分 invoke 职责 |
| 6 | 持久化失败 | State 存不可序列化对象 | Context 注入，State 只存 JSON 友好字段 |
| 7 | 一次 tool 异常整段 Chat 挂 | 异常冒泡出 Graph | Executor 捕获 → ToolMessage(success:false) |
| 8 | 多 tool 结果难辨 | 返回无标识 | JSON 带 `name`/`summary`；控制并行 tool 数量 |

---

## 六、工程化落地

1. **工具注册表**：`ToolRegistry`，按域注册，支持按需加载
2. **Executor 横切**：timeout、校验、指标、统一错误格式
3. **ToolContext**：`user_id`、`db` 等运行时上下文，不写入 Graph State
4. **缓存**：检索类 tool 可 Redis 缓存相同 query
5. **可观测**：SSE `tool_call` / `tool_result`、耗时、失败率（不只 `draw_mermaid_png`）
6. **Mock**：`use_mock_*` 环境开关，Harness 离线测 Agent 环
7. **安全**：敏感 tool 鉴权、结果 provenance；输入 Guard 在 **进 Graph 前** 完成

---

## 七、MemoryOS 对照（当前实现）

| 项 | 做法 |
|----|------|
| 定义 | `ToolDefinition` + `ToolRegistry`（如 `tavily_search`） |
| 绑定 | `call_model` → `llm.bind_tools(registry.list_openai_schemas())` |
| 执行 | `execute_tools` → `ToolExecutor.run`（10s timeout） |
| 返回 | JSON ToolMessage：`success` / `summary` / `error` |
| RAG | `retrieve_knowledge` 节点 → system prompt，**非 tool** |
| 何时搜网 | `compute_rag_sufficient` + unified ReAct prompt 引导 Tavily |
| 防死循环 | `recursion_limit = agent_max_iterations`（默认 5） |
| 持久化 | PostgreSQL `messages`，无 LangGraph Checkpointer |

与 [重试 / 降级 / 兜底](/retry-fallback-degrade.html) 配合：Tool 失败走 ToolMessage，由 LLM 在 Graph 内修正；全链路失败走 SSE `stream_failed`。

---

## 八、快速自检清单

- [ ] 每个 tool 有适用 / 禁止场景描述，与 RAG 不重叠
- [ ] 复杂参数有 Schema 校验
- [ ] 异常在 **Executor 或 handler** 层处理，不中断 Graph
- [ ] LLM 已 `bind_tools`，且未滥用 structured output 同链冲突
- [ ] 有 `recursion_limit` 或 state 计数，不会死循环
- [ ] State 无可序列化对象；DB 通过 Context 注入
- [ ] 单轮 tool 数量可控；有 mock / 监控 / 超时配置
