---
title: "Chat SSE 假死：FastAPI Depends 占死连接池，BFF ReadableStream 灌满队列"
date: 2026-05-03T10:00:00+08:00
slug: "shit-fastapi-depend-redis"
url: "/shit-fastapi-depend-redis.html"
categories:
  - "AI 工程"
tags:
  - "FastAPI"
  - "SSE"
  - "Redis"
  - "ReadableStream"
  - "MemoryOS"
draft: false
---

> **说明**：下文来自 MemoryOS 一次真实 Chat SSE「假死」排查与修复。症状、时间线与改法均基于生产级调试日志；不是框架 bug 公告，而是 **长连接 + Depends 生命周期 + 流式背压** 三类常见坑叠在一起的故事。

用户问：「2022 世界杯射手榜前 10 名」。终端里 SQL 已经 `COMMIT`，`memories` 表也在更新——聊天框却停在「正在生成分析…」，只吐出几个字；**刷新页面，完整答案却在**。

这不是 LLM 慢，也不是 Redis 挂了。这是一次典型的 **假死**：数据其实写进库了，但 **SSE 管道某一截没有把字节送到浏览器**。

<!--more-->

## 一、先建立正确的心智模型

Chat 流式回复不是一条线，而是 **三段管道**：

```text
浏览器 (useChat)
    ↓  POST /api/chat              ← Next.js BFF
    ↓  转成 AI SDK UI stream
    ↓  POST /api/v1/chat/completions   ← FastAPI SSE
    ↓  LangGraph + LLM + 短 DB/Redis
```

**假死可能发生在任意一段**，症状却很像：

| 段 | 典型症状 |
| :--- | :--- |
| FastAPI | 终端最后一条是 `COMMIT`，之后「没动静」 |
| BFF | API 日志显示 persist 完成，UI 只出几个字 |
| 浏览器 | 一直「生成中」，刷新后从 DB 读到全文 |

调试第一原则：**先证明数据在哪一层已经完整，再查下一层为什么没送到。**

---

## 二、我们一开始容易错怪谁？

### 误判 A：「Redis 坏了 / 连接池满了」

日志里看到 Redis、DB、`memories` 的 `INSERT`/`COMMIT`，很容易以为是 Redis 或 memory 任务把系统拖死。

**真相**：那段 SQL 往往是 **后台 memory-extract**，与当前 SSE **并行**，不是阻塞主链路。它反而说明 **主请求已在收尾**。

### 误判 B：「SSE 根本没开始」

UI 完全空白时，会怀疑 FastAPI 没发 stream。

**真相**：有时是 BFF 的 `ReadableStream` **读了上游却不 enqueue**，浏览器永远等不到第一帧 UI 事件——API 正常，UI 仍空白。

### 误判 C：「前端 React bug」

吐一点就停，像渲染卡死。

**真相**：API 在 2～3 秒内已发完 493 个 token，BFF 也 finalize；但 **493 个 `text-delta` → 493 次 React 更新**，消费 ~3 字/秒，像假死——是 **管道下游太慢**，不是 LLM 慢。

---

## 三、后端：FastAPI Depends 如何「占死」整个 API

### 3.1 `Depends(get_db)` 的生命周期陷阱

很多项目这样写 SSE：

```python
async def chat(..., db=Depends(get_db), redis=Depends(get_redis)):
    return StreamingResponse(event_generator(), ...)
```

若 `get_db` / `get_redis` 是 **yield 型依赖**，生命周期是：

> **从进入路由 → 到整个 HTTP 响应结束**（含 SSE 流全部发完）

一条 Chat 流可能 30～120 秒。意味着：

- **一条 DB 连接**被占 30～120 秒
- **Redis 依赖**同样可能被占着
- 连接池默认几个连接 → embedding、memory、别的请求 **排队**
- 终端「最后一次 COMMIT」可能是 **别的请求或后台任务**；当前 stream 占池，整体像冻住

这不是 Redis 算法 bug，是 **把短资源当成了长资源**。

**正确姿势：短会话**

```text
① 短 DB：写 user message → commit → 关
② 短 DB：读 history → 关
③ 计算：LangGraph + LLM（不持 DB）
④ 短 DB：写 assistant → commit → 关
Redis：按需点查，不挂在 Depends 上拖全程
```

SSE 路由改用 **JWT-only 鉴权**（`get_current_user_id`），不在 Depends 里挂 `get_db`；需要 DB 时用 `async with AsyncSessionLocal()` 包一小段。LangGraph 节点用 `graph_db_session`，**按 node 开短连接**，不在整段 SSE 里借一条 session。

### 3.2 中间件：`receive()` 不能断

InjectionGuard 为扫描 body 会先读完整 POST，再用 `replay_receive` 回放。

若 replay **只回放一次**，之后不再调用原始 `receive()`：

- `request.is_disconnected()` 一直阻塞
- 用户点 Stop 无效
- 流无法 cancel/finalize

**改法**：replay 一次后 **delegate 回原始 `receive()`**，SSE 期间仍能感知 `http.disconnect`。

### 3.3 BackgroundTasks：流结束了，请求还没结束

memory-extract、summary 若挂在 Starlette `BackgroundTasks` 上：

> **SSE body 发完后，还要等 background 跑完，HTTP 才真正结束**

BFF 的 fetch 也会多等；memory 的 COMMIT 出现在「UI 已卡住」的时间点，进一步误导。

**改法**：`asyncio.create_task` detached 后台任务，带失败日志—— **不阻塞 SSE 关闭**。

### 3.4 SSE priming：首帧要尽早出去

部分环境下，`StreamingResponse` 返回后 consumer 才连上 generator。若首 token 要等 LangGraph 跑完才 yield，BFF/浏览器长时间无数据。

**改法**：`await gen.__anext__()` 先产出 `start` 帧，再包进 `stream_body()` 返回；generator 内 `skip_start_event` 避免重复 start。

---

## 四、BFF：API 写完了，为什么 UI 还在等？

用一次真实时间线（修复前）：

| 时间 | BFF | 浏览器 |
| :--- | :--- | :--- |
| +2.9s | 一次 `pull()` 读完全部上游，493 token 入队 | — |
| +8s | — | 收到第 1 个字 |
| +109s | 早已 finalize | 才收齐 493 字，然后 `network error` |

### Bug 1：`pull()` 一次读穿上游

```typescript
async pull(controller) {
  while (true) {
    const { done, value } = await upstream.read();
    // enqueue…直到 upstream 结束才 return
  }
}
```

一次 pull 把几百个 UI 事件塞进队列。下游按自己节奏消费，队列堆满，最终超时。

**改法**：每次 `pull()` 只读 **一块** upstream，处理完就 return，让 **backpressure** 生效。

### Bug 2：493 token = 493 次 React 更新

即使增量 pull，每个 token 一个 `text-delta`，长对话 + markdown 仍 ~3 字/秒。

**改法**：BFF 合并 token（如每 **16 字符** 一个 `text-delta`）；tool/source/done 前强制 flush。

### Bug 3：合并后的「空 pull」

`pending < 16` 就 return 且 **本轮没有 enqueue** → stream 假死，~60s 后 `TypeError: network error`。

**改法**：单次 `pull()` 内 **循环读 upstream**，直到至少 emit 一批 UI 帧，或 upstream 结束——**不要空手 return**。

### 兜底：error 时从 DB sync

stream error 但 assistant 已有部分内容时，**从 DB 拉回持久化消息**。刷新能看全，说明落盘 OK——这是合理的 safety net。

---

## 五、一张总图

```text
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Browser   │────▶│  Next BFF    │────▶│  FastAPI SSE    │
│  useChat    │◀────│  pull+合并   │◀────│  短DB+primed    │
└─────────────┘     └──────────────┘     └─────────────────┘
       │                    │                      │
       │  慢：493次渲染      │  曾：一次灌满493帧    │  曾：Depends占池30s+
       │  改：合并delta      │  改：增量pull+防空pull │  改：短session+detach
       ▼                    ▼                      ▼
   刷新读DB OK          network error 60s        COMMIT 正常
```

---

## 六、给架构师的五条 Checklist

1. **流式接口禁用长生命周期 Depends** — DB/Redis 不能绑在整个 `StreamingResponse` 上；按「写-算-写」拆短事务。
2. **中间件读 body 必须恢复 `receive` 链** — replay + delegate，否则 disconnect/cancel 全瞎。
3. **后台任务别挂在 HTTP 生命周期上** — post-stream 用 detached task 或队列，并考虑 shutdown。
4. **BFF 流转换要尊重 backpressure** — `pull()` 是「读一点、转一点」；高频率 UI 事件要 batch。
5. **用「落盘 vs 送达」区分问题** — 刷新能看全 → 查 SSE/BFF；刷新也没有 → 查 API finalize。

---

## 七、调试方法论

1. **分层打点**：API（stream start / persist / ASGI done）、BFF（pull 次数、finalize）、FE（status、lastTextLen）。
2. **对齐时间线**：同一请求看「API 何时 persist」「BFF 何时 finalize」「UI 何时到 N 字」。
3. **先证伪再修复**：曾以为 Redis；日志证明 stream 期间 pool `checkedout: 0` 后，才转向 BFF。
4. **一次只改一层**：pull 修复后仍慢 → 加 token 合并；合并后空 pull → 加 inner loop。

---

## 八、结语

这次假死没有单一罪魁祸首，而是三个常见假设撞在一起：

- HTTP 请求 ≈ 短 RPC（实际是 **分钟级长连接**）
- stream 转发 ≈ 内存拷贝（实际是 **有背压的生产者-消费者**）
- token 级 streaming ≈ 更好 UX（在 React 里可能是 **493 次重渲染**）

修完之后的目标架构很简单：**连接只借一小会儿，数据像水管一节一节流，而不是一次性灌满水桶。**

若你在做 Chat + SSE + BFF，不妨扫一眼自己的 `Depends`、`middleware receive` 和 `ReadableStream pull`——很多问题还没爆，只是并发还不够大。

---

**相关阅读**

- [SSE 和 WebSocket 怎么选？](/sse-vs-websocket.html)
- [LLM 聊天与 RAG 安全怎么落地？](/chat-security.html)
- [MemoryOS 聊天安全一张图](/memoryos-security-map.html)

*MemoryOS 修复 commit：`fix(chat): unblock SSE streaming across API and BFF`*
