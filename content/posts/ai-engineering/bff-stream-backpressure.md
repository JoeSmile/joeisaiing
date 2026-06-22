---
title: "BFF 背压：为什么 Chat 流式不能「中转站一次扛完」"
date: 2026-05-09T10:00:00+08:00
slug: "bff-stream-backpressure"
url: "/bff-stream-backpressure.html"
categories:
  - "AI 工程"
tags:
  - "Next.js"
  - "BFF"
  - "ReadableStream"
  - "SSE"
  - "背压"
  - "MemoryOS"
draft: false
---

> **说明**：下文来自 MemoryOS Chat 流式链路的一次真实「假死」排查。后端连接池、中间件等问题见姊妹篇 [Chat SSE 假死：FastAPI Depends 占死连接池](/shit-fastapi-depend-redis.html)；本文只讲 **BFF 与浏览器之间** 为什么要做背压、怎么做、为什么不能全扔给前端。

用户问：「2022 世界杯射手榜前 10 名」。终端里 SQL 已经 `COMMIT`，刷新页面却能看到完整回答——聊天框却停在「正在生成…」，只吐出几个字，甚至最后 `network error`。

这不是 LLM 没算完，是 **管道某一截憋住了**。其中很大一块，出在 **Next.js BFF 怎么读 FastAPI、又怎么喂给浏览器**。

<!--more-->

## 一、先忘掉「背压」这个词，想成三条水管

Chat 流式不是一根直管，而是 **三段速度不一样的水管**：

```text
FastAPI（出水快）
    ↓  MemoryOS SSE
Next.js BFF（中转站）
    ↓  AI SDK UI stream
浏览器 + React（接水慢）
```

- **FastAPI**：模型一旦开始吐字，几秒内推完几百个小包很常见（每个 SSE 事件有时只有一个字）。
- **BFF**：要把「自家 SSE 协议」翻译成「AI SDK / useChat 能吃的 UI 流」。
- **浏览器**：每收到一帧就要更新消息；React 还要重绘聊天区，长文 + Markdown 更慢。

**背压**想解决的就一件事：**出水不能比接水快太多，否则中间池子先满，再爆。**

调试时有个很有用的分辨法：

| 现象 | 往往说明 |
| :--- | :--- |
| 刷新后 DB 里有全文 | 后端写完了，断在 **送到 UI** 的路上 |
| 刷新也没有 | 先查 API finalize，再查 BFF |

姊妹篇讲的是后端为什么也会「像冻住」；本文专注 **BFF 这一截**。

---

## 二、以前出了什么事？用时间线说

假设 API 在 **3 秒内** 发完 493 个字，每个字一个 SSE 事件。

**旧 BFF 相当于**：中转站员工 **一次把 493 杯水全倒进柜台后面的桶**，然后才歇着。

- 柜台（浏览器）每秒只能端走几杯。
- 桶（内存里的队列）越堆越高。
- 顾客很久才喝到第一口 → UI 像冻住。
- 再久一点 → 超时 → `network error`。
- 同时 DB 已经写完 → **刷新能看见全文**。

这就是那次「假死」的典型画面：**不是没生成，是中间憋住了。**

当时 BFF 里 `ReadableStream` 的 `pull()` 大致是：循环 `upstream.read()`，直到 FastAPI 流结束才 `return`。一次 `pull` 调用就把上游读穿——下游还没来得及消费，内部已经 enqueue 了几百帧 UI 事件。

---

## 三、为什么要专门设计这层背压？

因为要同时解决 **三件不同的事**，它们叠在一起才会像「卡死」。

### 3.1 别让中转站一次吞完上游（流量控制）

顾客要一杯，中转站才去上游接一杯；倒进柜台就停，等顾客下次再要。

在 Web 里：**浏览器慢读 BFF 的 Response body → BFF 的 `pull()` 就不会疯狂 `read()` FastAPI**。下游慢，上游就别拼命抽——这就是背压的本意。

若 BFF 不管下游节奏、自己把 FastAPI 读光，爆的是 **BFF 内部队列**，前端再聪明也救不了这一段。

### 3.2 别 493 次晃 React（合并展示）

就算背压对了，若每个字仍变成一个 `text-delta`，React 仍要更新 493 次。长回复时渲染可能只有 **每秒几个字**，体感还是「卡」。

所以在 BFF 里 **攒够大约 16 个字符再发一帧**（token 合并）。用户仍是流式打字感，但 React 从「每字一次」变成「每十几字一次」。

### 3.3 用户点 Stop 时，后端还要能落库（善后）

用户点停止，浏览器会 **掐断和 BFF 的连接**。若 BFF 也立刻掐 FastAPI，后端可能来不及把「用户已经看到的那一段」写入数据库。

所以 BFF 在 abort 后会 **继续默默读完上游**（drain），但 **不再往浏览器 enqueue**；前端再调 cancel，带上「用户看到多长」。这样 UI 停了，库里的 assistant 仍能对齐用户快照。

---

## 四、一张图：以前 vs 现在

```text
【以前：假死】
FastAPI  ████████████ 493 字 / 3 秒
           ↓ 一口气读完
BFF      [||||||||||||||||||||]  队列堆满
           ↓ 慢慢吐
浏览器   ··· 几个字 ··· 卡死 ··· network error
DB       ✓ 全文已在（刷新能看见）


【现在】
FastAPI  ████ 仍可能很快
           ↓ 你慢读我才多读（背压）
BFF      攒 ~16 字 → 发一帧 → 停，等浏览器
           ↓ 少量 text-delta
浏览器   流式更新，次数少很多
Stop     浏览器掐 BFF → BFF 仍读完 API（不展示）→ cancel 带「看到多长」
```

背压不是炫技术语，就是 **接水的速度决定抽水的速度**。BFF 正好是「快 API」和「慢浏览器」之间的水龙头。

---

## 五、这层背压能不能放在前端做？

**可以分块说，不能整块搬家。**

| 能力 | 放 FE 行不行 | 原因 |
| :--- | :--- | :--- |
| **少更新 React（合并字）** | 可以部分做 | 例如在 hook 里攒字、`requestAnimationFrame` 再更新。能减轻「493 次渲染」。 |
| **慢下来才读 FastAPI** | 单靠 FE **不够** | 背压发生在 **谁在读谁的 body**。浏览器慢读 BFF 时，BFF 才会慢读 FastAPI；若 BFF 仍一次读完上游，**爆的是 BFF 内部**，FE 管不到。 |
| **SSE → UI 协议转换** | 今天绑在 BFF | 浏览器直连 FastAPI 可以不要 BFF，但要在 FE 写整套转换 + 鉴权代理，架构会变。 |
| **Stop 后 drain FastAPI** | **必须在 BFF（或等价层）** | 浏览器 abort 的是 `/api/chat`；只有 BFF 还握着对 FastAPI 的连接，才能「对用户掐断、对后端读完」。 |

结论：

- **「合并 token、少渲染」** → 可以挪到 FE，但 wire 上仍可能有很多小 chunk，FE 要自己节流。
- **「别让 BFF 一次吞完上游」** → 必须在 BFF 的流转换里做（或改成 FE 直连 API 并在那一层做同样逻辑）。
- **「Stop 时让后端写完」** → 必须在 **BFF ↔ API** 这一段。

MemoryOS 选在 BFF **合并 + pull 策略 + drain**，是因为 **一处改、三层都受益**：API 不会被无脑狂读、到浏览器的事件更少、React 更轻，且 Stop 链路和 BFF 天然在一起。

---

## 六、实现上只记三句话（不堆函数名）

打开 `memoryos-upstream.ts` 时，不必逐行啃，盯住三个语义就够：

1. **有输出就停一下** — `pull()` 里 enqueue 了 UI 帧就 return，等浏览器下次 `read()` 再接着干。对应「背压」。
2. **攒够一批再发** — 大约 16 个字符合并成一个 `text-delta`；遇到 sources、tool、done 前强制 flush。对应「少晃 React」。
3. **停了仍把上游读完但不给用户** — `clientStopped` 后只 drain、不 enqueue；配合 cancel API。对应「Stop 能落库」。

BFF 路由 `app/api/chat/route.ts` 再把 **客户端 abort** 接到 **drain FastAPI**：浏览器掐线 → BFF 继续读完后端 → 再 abort upstream fetch。

单元测试里用「慢上游 + 慢消费者」模拟背压：上游每 15ms 一个字、消费者每 40ms 读一次，仍要在几秒内看到首字且全文正确——防止回归成「一次灌满」或「空手 pull 卡死」。

---

## 七、和「LLM 慢」别混在一起

背压解决的是 **管道憋住、UI 假死**；不解决：

- 首 token 前 Graph 串行（embed、检索、首轮非流式 LLM）— 那是 API 侧 TTFT；
- FastAPI `Depends(get_db)` 占满连接池 — 见姊妹篇。

若 **长时间只有 Thinking、一个字都不出**，先查 API；若 **DB 已有全文、UI 卡住或 network error**，先查 BFF 与前端管道。

---

## 八、给做 Chat BFF 的三条 Checklist

1. **流转换要尊重背压** — `pull()` 是「读一点、转一点、有产出就停」，不要一次 `read()` 穿上游。
2. **高频率 UI 事件要 batch** — 每字一帧在长文场景会拖死 React；在 BFF 或 FE 至少一层合并。
3. **Stop 要 drain 上游** — 对用户掐断、对 API 读完，再配合 cancel 携带可见长度。

---

## 参考

- MemoryOS 全链路假死（后端 + BFF）：[Chat SSE 假死：FastAPI Depends 占死连接池](/shit-fastapi-depend-redis.html)
- 代码：`memoryos-upstream.ts`（BFF 流转换）· `app/api/chat/route.ts`（abort → drain）· `use-chat-session.ts`（Stop + cancel）
