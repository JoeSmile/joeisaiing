---
title: "分场景选型：tRPC / gRPC / Connect-RPC 与流式方案怎么落地"
date: 2026-04-23T10:00:00+08:00
slug: "rpc-scenario"
url: "/rpc-scenario.html"
categories:
  - "AI 工程"
tags:
  - "gRPC"
  - "tRPC"
  - "Connect-RPC"
  - "RPC"
  - "WebSocket"
  - "Streaming"
draft: false
---

# 分场景选型指南：tRPC / gRPC / Connect-RPC + 流式方案落地决策

先梳理四种 RPC 流模式的能力边界（**务必区分「服务端程序」和「浏览器」**），再按真实业务拆分「该用什么、为什么、别用什么」，覆盖 **Unary、Server Stream、Client Stream、Bidi** 四类需求。

> 协议层对比与架构图见姊妹篇：[gRPC、tRPC、Connect-RPC 怎么选？](rpc-grpc-trpc.html)

<!--more-->

## 前置基础：四种流模式 + 谁在调用

同一种流，**内网微服务互调**和**浏览器调 BFF** 能力完全不同。下表分两列写清楚：

| 模式 | 含义 | 内网 gRPC / Connect 服务端 | 浏览器（Fetch） |
| ---- | ---- | ---- | ---- |
| **Unary** | 一问一答 | tRPC / gRPC / Connect ✅ | tRPC / Connect ✅ |
| **Server Stream** | 客户端发 1 次，服务端持续推 | gRPC / Connect ✅ | tRPC（Subscription / 流式 query）、Connect ✅ |
| **Client Stream** | 客户端持续发，服务端最后汇总返回 | gRPC / Connect ✅ | Connect ⚠️ 实验性、浏览器支持不全；更常见是 **分片 HTTP / WebSocket** |
| **Bidi** | 两端同时异步收发 | gRPC / Connect ✅ | Connect / gRPC ❌ **暂无稳定真双工**；浏览器侧通常用 **WebSocket** |

**记一句**：LLM「往下吐 token」= Server Stream，三种栈在浏览器里都能做；「浏览器和服务器在同一条连接上同时双向流」在 2026 年仍不能指望 Connect / gRPC 在浏览器里原生搞定。

---

## 一、仅需普通接口（无流式）→ Next.js + tRPC（BFF）+ 内网 gRPC

### 场景 1：后台管理、订单查询、表单提交、权限校验

1. **业务**：查询 / 增删改；无实时推送、无持续上传；每次交互是独立短请求。
2. **选型**：前端 + BFF 用 **tRPC**，内网微服务用 **gRPC**。
3. **理由**：
   - 全栈 TS，tRPC + Zod 类型共享，Next.js 集成成熟，迭代快；
   - 公网 HTTP JSON，Fetch 直连 BFF，无需 protobuf 编译链；
   - 内网 gRPC + HTTP/2 二进制，适合多语言微服务。
4. **不选 Connect / gRPC 直连浏览器**：简单 CRUD 不必维护 `.proto`，JSON 调试更直观。

### 场景 2：AI 基础对话（仅服务端往下推 token）

1. **业务**：用户发完整提问，服务端持续返回 token；生成过程中**不在同一条流里**追加追问或改参数（新意图要新请求）。
2. **选型**：**tRPC 流式 query / Subscription**（或 SSE）+ 内网 gRPC。
3. **理由**：单向推送即可，tRPC 足够；不必为这类场景引入 Protobuf 工具链。
4. **关于 Stop（别和 Bidi 混为一谈）**：
   - **停止生成**不需要 Bidi：前端对 Fetch 调 `AbortController.abort()`，BFF 再转发 cancel 到下游即可（见 [AbortController 双发 abort](abort-controller.html)）。
   - 本文说的「局限」是：**不能在同一条 server stream 上继续发追问、改温度**——那是交互模型问题，不是「没法 Stop」。

---

## 二、需要客户端持续上传（Client Stream 语义）→ 看调用方是谁

### 先分清：浏览器上传大文件，不一定非要 gRPC Client Stream

| 调用方 | 常见做法 |
| ---- | ---- |
| **浏览器 → BFF** | 分片 HTTP（多次 POST / multipart）、专用上传接口、tus 等；或 **WebSocket** 推二进制块 |
| **服务 → 服务** | gRPC / Connect **Client Stream** 很合适 |

tRPC **没有** gRPC 式的 Client Stream RPC，但大文件可以走 **独立上传路由**（REST / tRPC mutation 传 chunk 元数据），不等于「只能一次性传整个文件」。

### 场景 1：大文件 / 知识库批量导入（浏览器发起）

1. **业务**：前端把几十 MB～GB 文档切成分片上传；全部传完后后端解析、向量化，返回导入报告。
2. **选型（浏览器侧）**：
   - **优先**：分片 HTTP + BFF 聚合（或对象存储直传 + 回调），实现简单、CDN / 网关友好；
   - **可选**：WebSocket 持续推块；
   - **慎用**：Connect Client Stream——浏览器 Fetch 对「流式请求体」支持有限（Chromium 半双工实验、Safari / Firefox 更弱）。
3. **选型（纯内网上传，无浏览器）**：内网 **gRPC / Connect Client Stream**。
4. **为什么不用 tRPC 单请求塞整个文件**：一次 JSON / body 过大易超时、占内存；应分片或走对象存储，而不是硬塞进一个 Unary。

### 场景 2：录音分片上传后统一转写（浏览器发起）

1. **业务**：前端切音频分片持续上传，结束后服务端一次性转写。
2. **选型**：与场景 1 相同思路——**分片 HTTP 或 WebSocket** 到 BFF；内网转写服务可用 gRPC Client Stream。
3. **若强依赖 Protobuf 类型**：BFF 用 Connect **服务端客户端**调下游，浏览器侧仍建议 HTTP 分片，而非假设「Connect 浏览器原生 Client Stream」。

---

## 三、长连接双向实时交互 → 先问「是不是浏览器」

很多场景被写成「必须 Connect Bidi」，实际要拆两层：

| 层级 | 更合适的技术 |
| ---- | ---- |
| **浏览器 ↔ BFF** | **WebSocket**（或 SSE 下行 + HTTP 上行「双通道」） |
| **BFF ↔ 微服务 / 微服务互调** | gRPC / Connect **Bidi** |

tRPC 在 HTTP 下没有 gRPC 式 Bidi，但可用 **WebSocket link**（mutation 上行 + subscription 下行）做双向交互——语义不同于单条 Bidi RPC，产品体验上可以等价。

### 场景 1：高级 AI 对话（生成中要 Stop、改参数、追问）

1. **业务**：生成过程中要能 Stop、改温度、追问；服务端并行推 token、日志、工具调用结果。
2. **选型（务实组合）**：
   - **下行**：Server Stream（tRPC 流式 / SSE / Connect Server Stream）；
   - **上行控制**：独立 HTTP（cancel API、tRPC mutation）或 **WebSocket**；
   - **内网**：gRPC / Connect 调 LLM 服务。
3. **不必强上 Bidi 的原因**：
   - 浏览器侧 Connect Bidi 并非稳定真双工；
   - MemoryOS 等实践：**AbortController + Cancel API** 即可 Stop，无需同流双发。
4. **若坚持「单连接双向」**：浏览器侧选 **WebSocket**，不是 Connect Bidi。

### 场景 2：在线协同文档 / 白板

1. **业务**：多人同时发光标、编辑操作；服务端广播所有人状态。
2. **选型**：**WebSocket**（行业主流）+ 内网可用 gRPC 做持久化 / 鉴权服务。
3. **不用 Connect Bidi 直连浏览器**：Fetch 做不到稳定双向；Connect Bidi 适合 **服务间** 同步层，不是浏览器首选。

### 场景 3：实时语音 + 翻译字幕

1. **业务**：持续上传麦克风音频；同时收对方音频和字幕；中途改语种、静音。
2. **选型**：**WebSocket** 或 **WebRTC**（音视频常走 WebRTC）；内网推理链可用 gRPC Stream。
3. **SSE + 单独上传**：两条连接、时序难对齐——这是真问题；但解法通常是 **一条 WebSocket / WebRTC**，而非 Connect Bidi from browser。

### 场景 4：联机小游戏

1. **业务**：高频上行操作 + 服务端广播状态。
2. **选型**：**WebSocket**（或 WebRTC / 专用 UDP）；内网房间服务可用 **gRPC Bidi**。
3. **关于「比 WebSocket JSON 省带宽」**：WebSocket 也可发二进制；游戏更关注协议设计和 tick，不宜笼统说 gRPC 一定优于 WebSocket。

### 场景 5：Web SSH / 容器终端

1. **业务**：键盘输入与终端输出实时双向。
2. **选型**：**WebSocket**（xterm.js + 终端网关是常见模式）。
3. **Connect Bidi**：适合 **网关 ↔ 容器** 的内网段，不适合作为浏览器第一选择。

---

## 四、内网微服务互调（无浏览器）→ 纯 gRPC

### 场景：支付、订单、计费、LLM 推理集群互调

1. **业务**：仅机房内多语言服务互调；高 QPS、要低延迟。
2. **选型**：**纯 gRPC**。
3. **理由**：HTTP/2 + Protobuf 二进制；四流齐全；生态（负载均衡、拦截器、服务网格）成熟。
4. **不选 Connect 的原因**：内网无浏览器诉求时，Connect 的浏览器友好层是额外复杂度；需要时可由 **connect-go 多协议** 渐进引入，而非默认全换 Connect。

---

## 极简选型速查表

| 业务特征 | 推荐组合 | 常见误区 |
| ---- | ---- | ---- |
| Next.js 全 TS、CRUD / 基础 AI 流式（只往下推） | tRPC BFF + 内网 gRPC | 把「Stop」误判为必须 Bidi（AbortController 即可） |
| 浏览器大文件 / 分片上传 | 分片 HTTP、对象存储直传、WebSocket | 以为 Connect 浏览器已成熟支持 Client Stream |
| 浏览器长连接双向（协同、终端、游戏、语音信令） | **WebSocket**（± WebRTC）；内网段可用 gRPC Bidi | 在浏览器上选 Connect / gRPC Bidi |
| 仅内网服务互调、要完整四流 | **纯 gRPC**（或 connect-go 多协议） | 为了「统一」强行让浏览器说 gRPC |
| 统一 `.proto`、浏览器 Fetch + server stream、内网要四流 | Connect 网关 + 内网 gRPC 二进制 | 以为「一套协议」= 浏览器也能 Bidi |

---

## 参考

### 本站姊妹篇

- [gRPC、tRPC、Connect-RPC 怎么选？](/rpc-grpc-trpc.html) — 对比表、架构 1 / 2、浏览器流式能力矩阵
- [SSE 和 WebSocket 怎么选？](/sse-vs-websocket.html) — 浏览器长连接选型；双向交互为何常落 WebSocket
- [AI 聊天 Stop 为什么要「双发 abort」？](/abort-controller.html) — 「高级 AI 对话」不必 Bidi 即可 Stop

### MemoryOS 项目技术方案

| 文档 | 与本文场景的对应 |
| ---- | ---- |
| [EP02 流式对话史诗](https://github.com/JoeSmile/memoryOS/blob/main/docs/tasks/epics/EP02-streaming-chat.md) | **场景 2** 基础流式问答的整体交付顺序 |
| [ep02-chat-sse 设计](https://github.com/JoeSmile/memoryOS/blob/main/openspec/changes/archive/2026-06-03-ep02-chat-sse/design.md) | SSE Server Stream 选型记录（对照第三节「WebSocket 双向」） |
| [聊天 Stop / Cancel](https://github.com/JoeSmile/memoryOS/blob/main/docs/tech/chat-stream-cancel.md) | **场景 1 高级 AI** — Stop 用双发 abort，非 Connect Bidi |
| [聊天 RAG 流式与 BFF](https://github.com/JoeSmile/memoryOS/blob/main/docs/tech/chat-rag-stream.md) | BFF 聚合上游 SSE、结构化 `sources` 下行 |
| [L02 学习笔记](https://github.com/JoeSmile/memoryOS/blob/main/docs/tasks/learning/L02-streaming-langgraph.md) | `fetch` + ReadableStream、`AbortController` 竞态 |
| [LangGraph 对话编排](https://github.com/JoeSmile/memoryOS/blob/main/docs/tech/langgraph-chat.md) | 内网推理层编排（若 BFF 与推理服务拆 gRPC，可对照架构 1 内网段） |

仓库：[JoeSmile/memoryOS](https://github.com/JoeSmile/memoryOS)

### 协议官方文档

- [Connect RPC — FAQs](https://connectrpc.com/docs/faq) — 浏览器 Client Stream / Bidi 限制
- [tRPC — Subscriptions](https://trpc.io/docs/server/subscriptions) — HTTP 下单向推送 vs WebSocket 双向组合
