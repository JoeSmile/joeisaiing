---
title: "SSE 和 WebSocket 怎么选？为什么 LLM 聊天常用 fetch + ReadableStream"
date: 2026-04-17T10:00:00+08:00
slug: "sse-vs-websocket"
url: "/sse-vs-websocket.html"
categories:
  - "AI 工程"
tags:
  - "SSE"
  - "WebSocket"
  - "Streaming"
  - "LLM"
  - "ReadableStream"
draft: false
---

做 AI 聊天客户端时，常会碰到两个相近的问题：**SSE（Server-Sent Events，服务端推送事件）和 WebSocket 怎么选？** 以及 **明明后端已经是 SSE，前端为什么不用浏览器自带的 `EventSource`，而用 `fetch` + `ReadableStream` 自己解析？**

<!--more-->

## 一、先对齐概念

| 术语 | 全称 | 一句话 |
| :--- | :--- | :--- |
| **SSE** | Server-Sent Events | 基于 HTTP 的**单向**流：服务端 → 浏览器，文本格式通常是 `text/event-stream` |
| **WebSocket** | — | 在 TCP 上升级的全双工通道，客户端与服务端可**双向**实时发消息 |
| **EventSource** | — | 浏览器内置 API，专门消费 GET 方式的 SSE |
| **ReadableStream** | — | Fetch Response 的 `body` 流，可用 `getReader()` 按 chunk 读取任意 HTTP 响应体 |

下面默认说的 SSE，指 HTTP 长连接 + `Content-Type: text/event-stream` 这一类实现。

## 二、SSE vs WebSocket：对比表

| 维度 | SSE | WebSocket |
| :--- | :--- | :--- |
| **底层协议** | 普通 **HTTP/1.1 或 HTTP/2** 长连接，响应体不断追加 | HTTP **Upgrade** 到 `ws://` / `wss://`，独立帧协议 |
| **通信方向** | **单向**（服务端 → 客户端） | **双向**（客户端 ↔ 服务端） |
| **数据格式** | 文本为主（UTF-8），常见 `data:` 行 + JSON | 文本或二进制帧均可 |
| **浏览器 API** | `EventSource`（仅 GET）或 `fetch` + 流解析 | `WebSocket` |
| **鉴权** | 与 REST 相同：`Authorization` 头、Cookie、BFF 代理 | 握手阶段带 Cookie；自定义头依赖实现 |
| **穿透代理 / CDN** | 走标准 HTTP，配置相对简单 | 部分代理对 Upgrade 支持不一，需额外配置 |
| **自动重连** | `EventSource` **内置**断线重连 | 需自行实现心跳与重连 |
| **连接数** | 受浏览器对**同源 HTTP 连接数**限制（HTTP/1.1 时代更明显；HTTP/2 多路复用后缓解） | 单连接全双工，适合高频双向互动 |
| **速度** | 文本流式，LLM token 场景**足够**；非极致低延迟游戏场景 | 双向、二进制场景更灵活；**纯文本流式不一定更快** |
| **典型场景** | LLM 流式输出、日志 tail、行情推送、通知 | 在线协作、游戏、IM、音视频信令、高频双向指令 |
| **实现复杂度（聊天）** | 服务端推 token 即可，客户端解析流 | 需维护连接状态、心跳、重连、消息序 |

**选型建议（简化版）：**

- 主要是 **服务端持续推、客户端偶尔发**（例如 LLM 流式回复）→ **SSE 更合适**
- 需要 **毫秒级双向**、二进制、房间广播、游戏状态同步 → **WebSocket 更合适**

## 三、为什么很多 LLM API 用 SSE？

OpenAI、FastAPI 生态里的流式 Chat Completions，常见模式是：

```http
POST /v1/chat/completions
Content-Type: application/json
Accept: text/event-stream
```

响应体持续输出类似：

```text
data: {"event":"token","data":{"content":"你"}}

data: {"event":"token","data":{"content":"好"}}

data: {"event":"done","data":{"message_id":"..."}}
```

原因可以归纳为：

1. **语义匹配**：生成式回复是「服务端一边算一边推」，客户端主要是**收**，与 SSE 单向模型一致。
2. **HTTP 生态**：复用现有网关、负载均衡、JWT 鉴权、日志与监控，不必单独维护 WebSocket 集群。
3. **实现成本**：后端用 `StreamingResponse` / `text/event-stream` 即可；比 WebSocket 的连接管理轻量。
4. **防火墙友好**：企业网络对 443 上的 HTTP 流通常比自定义 WS 更省事。

WebSocket 并非不能做 LLM 流式，但在「HTTP POST 一问、流式多答」这一形态下，SSE 往往更直接。

## 四、AI Chat Client：为什么用 fetch + ReadableStream，而不是 EventSource？

Wire 格式仍是 SSE（`data:` + 空行分隔），但**生产级 AI 聊天前端**普遍不用 `EventSource`，而用 **`fetch` + `Response.body.getReader()`**。核心原因如下。

### 1. EventSource 只支持 GET —— 放不下聊天请求体

`EventSource` 的构造函数只接受 **URL 字符串**，等价于发起 **GET**，**无法携带 JSON body**。若硬要用 GET，只能把参数塞进 **Query String**：

```text
GET /api/chat/stream?conversation_id=...&content=用户很长的问题......
```

这会带来两类硬限制：

**（1）URL 长度上限**

| 层级 | 常见限制（量级） |
| :--- | :--- |
| 浏览器 / 历史实现 | 约 **2K～8K** 字符（因实现而异） |
| Nginx 默认 | `large_client_header_buffers`，URL 常按 **8K** 量级规划 |
| 部分网关 / CDN | 对 Request-URI 有独立上限 |

用户一条长消息、多个 ID（`conversation_id`、`client_message_id`）、regenerate 标志等，很容易顶到上限。**POST + JSON body** 通常按 **MB 级**配置（由服务端 `max body size` 决定），更适合聊天。

**（2）语义与安全**

- 问题正文出现在 URL 里，易进 **访问日志、Referer、浏览器历史**，不适合放敏感或长文本。
- REST 风格里，「发起一次 completion」是**有副作用的写操作**，用 GET 也不符合常规 API 设计。

真实接口因此几乎都是 **POST**：

```json
POST /api/v1/chat/completions
{
  "conversation_id": "...",
  "content": "用户问题",
  "client_message_id": "..."
}
```

对话上下文、会话 ID、幂等键在 body 里，**必须用 `fetch({ method: "POST", body })`**。

### 2. 需要自定义请求头（Bearer Token）

`EventSource` **不能**设置 `Authorization: Bearer <token>`（标准 API 无自定义 header 能力）。JWT 登录的 AI 产品几乎都要在 fetch 里带头：

```ts
await fetch("/api/v1/chat/completions", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  },
  body: JSON.stringify({ conversation_id, content }),
  signal,
});
```

### 3. 需要 AbortSignal：停止生成 / 切换会话

用户点「停止」时要 **abort 进行中的 fetch**，并配合服务端 cancel 接口。`EventSource` 只有 `close()`，与 `AbortController` 生态不如 fetch 统一。

```ts
const controller = new AbortController();
await fetch(url, { signal: controller.signal, /* ... */ });
// 用户点停止
controller.abort();
```

### 4. 事件类型不止一种：token、tool、sources、done

LLM + Agent 场景下，一条流里常有多种事件：

| event | 含义 |
| :--- | :--- |
| `start` | 流 ID，用于取消 |
| `token` | 增量文本 |
| `sources` | RAG 引用 |
| `tool_call` / `tool_result` | Agent 工具调用 |
| `done` | 结束与 message_id |
| `error` | 业务错误 |

`EventSource` 默认按 `event:` 字段分发，且长期用于「单一 message 流」。AI 项目里更常见的是 **`data:` 行内嵌 JSON**（`{"event":"token",...}`），需要自行 `JSON.parse` 与路由——用 ReadableStream 解析更可控。

示例（简化）：

```ts
const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const blocks = buffer.split("\n\n");
  buffer = blocks.pop() ?? "";

  for (const block of blocks) {
    for (const line of block.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const frame = JSON.parse(line.slice(5).trim());
      if (frame.event === "token") appendText(frame.data.content);
      if (frame.event === "done") onDone(frame.data);
    }
  }
}
```

### 5. 避免 EventSource 的「自动重连」误伤聊天

`EventSource` 断线后会**自动重连**同一 URL。对通知流这是特性；对 **一次性 completion 流**，重连可能导致重复消费、状态错乱。fetch 流由应用层控制生命周期，更符合「一次请求、一次回答」。

### 6. BFF / Next.js Route Handler 转发

Next.js 聊天页常走 **`/api/chat` 代理** 到 FastAPI：Route Handler 用 `fetch` 读上游 SSE，再转成 AI SDK 的 UI Message Stream。整条链路基于 **Streams API** 管道化，而不是页面里挂一个 `EventSource`。

```text
浏览器 fetch → Next.js Route Handler → FastAPI SSE
                ReadableStream 转换 → 前端 useChat
```

### 7. 错误响应要先于流处理（401 / 422 JSON）

`EventSource` 在 HTTP 非 2xx 时走 `onerror`，**很难在「开流之前」读到 JSON 错误体**（如 token 过期、会话不存在、内容审核拦截）。

`fetch` 可以先分支：

```ts
const res = await fetch(url, { method: "POST", /* ... */ });
if (!res.ok) {
  const err = await res.json(); // { code, message }
  showToast(err.message);
  return;
}
// 再 reader = res.body.getReader()
```

聊天产品里「鉴权失败 / 业务校验失败」很常见，这一路径用 fetch 更直接。

### 8. 跨域与 CORS：EventSource 不能带自定义头

跨域 SSE 若走 `EventSource`，浏览器**不会**让你加 `Authorization`。常见变通是 Cookie 同源或 URL 里塞 token（又回到长度与泄露问题）。

`fetch` 配合 CORS 预检（`OPTIONS`），可以规范地发送 `Authorization`、`Content-Type` 等头，与现有 REST API 一致。

### 9. 自动重连会带 `Last-Event-ID`

`EventSource` 断线重连时，浏览器可能自动带上 **`Last-Event-ID`**，希望服务端「从上次事件续传」。对**通知订阅**合理；对 **LLM 一次 completion** 可能让服务端误判为续流，产生重复 token 或状态不一致。fetch 流没有这一默认行为。

### 10. 同源连接数与多路并发

在 **HTTP/1.1** 下，浏览器对**同一域名**的并发连接数有限（常为 **6** 左右）。每个 `EventSource` 占一条长连接；多 Tab、多会话同时流式时会和其它 API 请求**抢连接**。

HTTP/2 多路复用后压力小一些，但 AI 客户端仍更倾向用 fetch 短生命周期流，并在应用层合并请求策略。

### 11. 响应头与可观测性

`fetch` 在读完 body 前就能访问 **`Response.headers`**（如 `X-Request-Id`、限流剩余次数、trace id），便于日志与排查。`EventSource` 对响应头的暴露有限，不利于统一链路追踪。

## 五、fetch 流 vs EventSource：对照

| 能力 | EventSource | fetch + ReadableStream |
| :--- | :--- | :--- |
| HTTP 方法 | **仅 GET** | GET / POST / … |
| 参数位置 | Query String（有** URL 长度**上限） | Request Body（通常 **MB 级**） |
| 自定义 Header | **不支持**（跨域鉴权受限） | 支持 `Authorization` 等 |
| Request Body | 不支持 | 支持 |
| AbortSignal | 仅 `close()` | 原生 `signal` + `AbortController` |
| 解析方式 | 浏览器解析 SSE | 自行按 `\n\n` / `data:` 解析 |
| 自动重连 | 内置（带 **Last-Event-ID**） | 自行决定（聊天通常不需要） |
| 非 2xx 响应 | `onerror`，难读 JSON 错误体 | 可先 `res.ok` 再 `res.json()` |
| 响应头 | 暴露有限 | 可读 `headers`（trace / 限流） |
| 连接占用 | 长连接占同源连接配额 | 同为长连接，但生命周期由应用控制 |

**结论**：Wire 格式可以仍是 SSE；**传输层用 fetch 流**，是为了满足 POST、鉴权、取消与多事件协议，而不是否定 SSE 本身。

## 六、什么时候仍然可以用 EventSource？

以下场景 EventSource 依然合适：

- **GET** 即可，且参数很短（远低于 URL 长度上限）
- 无需自定义 Header，或鉴权靠 Cookie 同源
- 单一 `message` 事件，无复杂 JSON 协议
- 希望浏览器帮你做断线重连（通知、看板类订阅）

AI Chat 产品若已走 POST + JWT + 长正文 body + 多事件 + 停止生成，**fetch + ReadableStream 是更常见的工程选择**。

## 七、总结

| 问题 | 简短回答 |
| :--- | :--- |
| SSE 和 WebSocket 怎么选？ | 以**服务端推、客户端收**为主（LLM 流式）→ SSE；**高频双向** → WebSocket |
| 为什么 LLM 常用 SSE？ | 单向流式、HTTP 生态、实现与运维成本低 |
| 为什么不用 EventSource？ | GET 与 **URL 长度**限制、POST body、Authorization、AbortSignal、多事件 JSON、错误 JSON、CORS、避免 Last-Event-ID 重连、BFF 转发等 |

## 相关

- [MDN：Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [MDN：ReadableStream](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream)
- [MDN：EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
