---
title: "前端面试题：如何设计 ChatGPT 式的 Markdown 流式渲染"
date: 2026-06-08T10:00:00+08:00
slug: "how-to-design-markdown-render-in-FE-like-chatgpt"
url: "/how-to-design-markdown-render-in-FE-like-chatgpt.html"
categories:
  - "前端 & Next.js"
tags:
  - "面试"
  - "Markdown"
  - "SSE"
  - "React"
  - "流式渲染"
draft: false
---

## 一道面试题

面试官问：“在 AI 对话界面中，如何实现像 ChatGPT 那样的 Markdown 实时流式渲染？”

解析面试官真正想问的是：
1. **SSE 数据流和渲染层之间怎么协调？**——不是「rAF 或背压二选一」，而是 **BFF 背压管网络缓冲，rAF 管 DOM 更新**，各管一层。
2. **代码块和 LaTeX 在流式状态下怎么处理？**——不仅仅是「用 highlight.js」，而是「未闭合的标签怎么防止样式炸裂」？
3. **用户点 Stop 或刷新页面时，落盘以谁为准？**——不仅仅是「存 Redis」，而是「UI 已渲染的 100 个 token，和 BFF 已收到的 130 个 token，落盘选哪个？」
4. **这套方案在 React 19 的新 Hook 下怎么落地？**

下面我们把这些问题一个一个拆开，给出**能落地的工程答案**。

---

## 第一章：流式 Markdown 渲染的底层架构（不是“用什么库”，而是“怎么设计”）

### 1.1 先定数据流：SSE + 前端 Buffer + rAF 渲染

SSE（Server-Sent Events）是 AI 对话最常用的传输协议，因为它支持服务端单向推送，且自带断线重连机制。

但在前端，**不能每收到一个 token 就操作一次 DOM**。原因很简单：

| 每秒 Token 数 | 每秒 DOM 操作次数 | 浏览器表现 |
| :--- | :--- | :--- |
| 60 | 60 | 勉强撑住（掉帧） |
| 200 | 200 | 页面卡死（主线程阻塞） |
| 500+ | 500+ | 直接无响应 |

因此，前端必须有一个 **Buffer 层 + 渲染节流层**：

```typescript
class StreamRenderer {
  private buffer = '';
  private rafId: number | null = null;

  onTokenReceived(token: string) {
    this.buffer += token;
    this.scheduleRender();
  }

  private scheduleRender() {
    if (this.rafId !== null) return;
    this.rafId = requestAnimationFrame(() => {
      this.doRender();
      this.rafId = null;
    });
  }

  private doRender() {
    // 这里只渲染“已闭合”的内容，未闭合的暂时保留
    this.renderSafeContent(this.buffer);
  }
}
```

**为什么不用 `setTimeout(0)`？** `requestAnimationFrame` 和屏幕刷新率同步（约 60fps），而 `setTimeout` 会在主线程空闲时立刻执行，可能导致一帧内多次渲染，浪费 CPU。

### 1.2 BFF 背压和前端 rAF 各管什么？（不是二选一）

面试官可能会追问：「既然 rAF 是前端节流，为什么还要在 BFF 做背压？」

**答案**：背压和 rAF 解决的是**不同层面**的问题，必须组合使用——BFF 背压管「管道里堆多少数据」，rAF 管「主线程多久画一次」。

| 层面 | 控制点 | 目的 |
| :--- | :--- | :--- |
| **BFF 背压** | BFF 读上游（LLM/API）与写下游（浏览器 SSE）的速度差 | 防止 BFF 一次把上游读穿、内部队列撑爆（见 [BFF 背压](/bff-stream-backpressure.html)） |
| **前端 rAF** | DOM / React 更新频率 | 防止主线程被 Markdown 重渲染阻塞，保护 UI 流畅度 |

BFF 侧的典型做法是：`pull()` 里**读一点、转一点、有产出就停**，并观察下游 `WritableStream` 的 `desiredSize`——消费者慢时暂停继续 `read()`：

```typescript
// 伪代码：BFF 中转流 —— 尊重下游消费速度
const upstream = llmResponse.body!; // ReadableStream
const downstream = new TransformStream(); // 转给 SSE / UI stream

// pull 语义：下游要数据时才读上游，不要一次 read() 到 done
async function pull(controller) {
  const { value, done } = await upstreamReader.read();
  if (done) { controller.close(); return; }
  controller.enqueue(transform(value));
  // 若 controller.desiredSize <= 0，本轮 pull 结束，等下游消费后再继续
}
```

**背压控制「管道里积多少」，rAF 控制「屏幕多久画一次」**。缺了 BFF 背压，浏览器还没消费，BFF 内存先爆；缺了 rAF，数据到了浏览器，主线程照样卡死。

---

## 第二章：代码块和 LaTeX —— 流式渲染中真正的“雷区”

### 2.1 代码块的“未闭合”问题

`highlight.js` 和 `prismjs` 都不支持流式输入。如果给它们传 ````js\nconst a = `，它们会直接报错或返回乱码。

**正确做法：延迟激活高亮**

```typescript
function renderCodeBlock(code: string, lang: string, isComplete: boolean) {
  if (!isComplete) {
    // 未闭合：纯文本展示，不做高亮
    return `<pre><code>${escapeHTML(code)}</code></pre>`;
  }
  // 已闭合：才走 highlight.js
  return `<pre><code>${hljs.highlight(code, { language: lang }).value}</code></pre>`;
}
```

**用户看到的效果**：
- 代码块输入过程中：纯黑色文本，逐字出现。
- 代码块闭合后：瞬间变成彩色高亮。

**关键**：高亮计算放在 `requestIdleCallback` 或微任务中执行，不阻塞主线程。

### 2.2 LaTeX 数学公式：更严格的边界检测

LaTeX 的问题比代码块更复杂，因为 `$` 字符在普通文本中也会出现（如“售价 $99.9”）。

**三段式处理策略**：

```typescript
function renderLaTeX(text: string) {
  // 1. 匹配已闭合的 $$...$$ 块
  const closedBlocks = text.match(/\$\$(.*?)\$\$/gs) || [];

  // 2. 检查是否存在未闭合的 $$（出现次数为奇数则块未闭合）
  const delimiterCount = (text.match(/\$\$/g) || []).length;
  const hasUnclosedBlock = delimiterCount % 2 !== 0;

  // 3. 渲染策略：
  //    - 已闭合的 → KaTeX 渲染
  //    - 未闭合的 → 纯文本展示（不报错）
  //    - 行内 $...$ → 只匹配成对边界，避免误判价格（如 $99.9）
}
```

**进阶做法**：维护一个 LaTeX 状态机，记录当前是否处于公式块内：

```typescript
enum LaTeXState {
  NORMAL,
  INLINE_OPEN,
  BLOCK_OPEN
}
```

这样，新收到的 token 可以准确判断是追加到公式缓存，还是直接渲染为普通文本。

### 2.3 安全截断：不是「增量 AST」，而是「只 Markdown 化已闭合前缀」

每次收到新 token 都对**全文**做完整 Markdown 解析，复杂度接近 O(n²)。

更务实的做法是**找到「安全截断点」**——在此之前的结构已闭合，可以走 Markdown 管线；尾部 `pending` 区只做纯文本 append：

```typescript
function findSafeCutPoint(text: string): number {
  // 代码围栏：只有 ``` 出现偶数次，最后一个 ``` 才是闭合
  const fenceCount = (text.match(/```/g) || []).length;
  const lastFenceEnd = fenceCount >= 2 && fenceCount % 2 === 0
    ? text.lastIndexOf('```') + 3
    : -1;

  // LaTeX 块：$$ 出现偶数次才算闭合
  const latexCount = (text.match(/\$\$/g) || []).length;
  const lastLatexEnd = latexCount >= 2 && latexCount % 2 === 0
    ? text.lastIndexOf('$$') + 2
    : -1;

  const lastParagraphEnd = text.lastIndexOf('\n\n');

  return Math.max(lastParagraphEnd, lastFenceEnd, lastLatexEnd);
}
```

**渲染流程**：
1. `fullText` 累积所有 token。
2. `safeText` = `fullText` 截取到安全截断点。
3. 只渲染 `safeText` 的 Markdown（已完成的部分）。
4. 未完成的部分（`pendingText`）以纯文本追加到 DOM 底部。

这样即使网络中断，页面上也不会出现半个标签导致的全局样式崩盘。

---

## 第三章：用户点击 Stop 或刷新页面 —— 落盘以谁为准？

### 3.1 数据分布情况（关键认知）

在用户点击 Stop 的瞬间，各层数据量**通常**如下（Stop 后 BFF 还应 **drain 上游** 再 finalize，见下节）：

| 位置 | 相对数据量 | 原因 |
| :--- | :--- | :--- |
| LLM 已生成 | 最多 | Stop 信号传到 LLM 有延迟，上游可能仍在吐字 |
| BFF 已缓冲 / 已落库 | 次多 | 若缺少背压，BFF 可能已读完上游但浏览器还没消费 |
| 浏览器 SSE 已收到 | 略少 | TCP / EventSource 缓冲 + 前端尚未 `onmessage` 处理 |
| 前端已渲染（UI） | 最少 | rAF 节流 + Markdown 安全截断，屏幕更新滞后于 buffer |

**如果只存 UI 已渲染的 100 个 token**：用户刷新后会感觉「少了一段」。
**如果只存 BFF 已推送给浏览器的 120 个 token**：仍可能少于 LLM 实际生成量，Stop 后 drain 未完成会丢尾巴。

### 3.2 标准落盘方案：全量 finalize + 可见位置标记

**核心原则**：
1. **持久化以 BFF drain 完上游后的全量文本为准**（保证数据不丢）。
2. **展示以用户 Stop 时 UI 已看到的字符偏移为准**（保证视觉一致）。

> 这与 MemoryOS 的实践一致：浏览器 abort 后，BFF 继续读完 FastAPI 流再 finalize，同时前端 cancel 回传 `visibleLength`。

```python
# BFF 在 Stop + drain 上游完成后执行
def on_stop(session_id: str, visible_char_offset: int):
    full_text = ''.join(buffer_after_drain)  # drain 完上游后的全量

    # 1. 全量落盘（DB / Redis，保证刷新不丢）
    save_message(session_id, full_text)

    # 2. 记录 UI 已展示到的字符偏移（非 token 数，除非一 token 一 char）
    save_meta(session_id, visible_until=visible_char_offset)
```

**前端在 Stop 时**：

```javascript
fetch('/api/chat/cancel', {
  method: 'POST',
  body: JSON.stringify({
    session_id: sessionId,
    visible_char_offset: getVisiblePlainTextLength(), // 用户实际看到的纯文本长度
  }),
});
```

**用户刷新后**：

```python
def get_history(session_id):
    full_text = load_message(session_id)
    visible_until = load_meta(session_id, "visible_until")

    # 返回全量 + 展示边界；前端首次只渲染 full_text[:visible_until]
    return {"full_text": full_text, "display_until": visible_until}
```

**兜底逻辑**：若前端未回传 `visible_char_offset`（直接关页），默认展示 `full_text` 全文——**数据完整性优先于视觉一致性**。

---

## 第四章：React 19 新 Hook 如何融入这个体系？

### 4.1 `useOptimistic`：发送消息时的乐观 UI

`useOptimistic` 适合 **「用户刚点发送、真实响应还没回来」** 这一小段——立刻把用户消息插进列表。流式正文更新仍应走 `setMessages` / `useChat` 的 `append`，不要指望 optimistic 状态承载 SSE 增量。

```tsx
import { startTransition, useOptimistic, useState } from 'react';

function Chat({ sendMessage }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [optimisticMessages, addOptimistic] = useOptimistic(
    messages,
    (state, newMsg: Message) => [...state, newMsg]
  );

  const handleSend = async (text: string) => {
    startTransition(async () => {
      // 乐观插入用户消息
      addOptimistic({ id: 'tmp-user', role: 'user', content: text });
      addOptimistic({ id: 'tmp-ai', role: 'assistant', content: '', isStreaming: true });

      // 真实请求：SSE 流式 append 到 messages，完成后 optimistic 自动回退
      await sendMessage(text, {
        onChunk: (chunk) => setMessages((prev) => appendAssistantChunk(prev, chunk)),
      });
    });
  };

  // 渲染 optimisticMessages，而非 messages
  return <MessageList items={optimisticMessages} />;
}
```

### 4.2 `useDeferredValue`：延迟处理“重度依赖”的数据

如果聊天界面中有“关键词高亮”或“情感分析”等重计算任务，可以用 `useDeferredValue` 延迟执行，避免阻塞主渲染。

```tsx
function ChatMessage({ text }: { text: string }) {
  const deferredText = useDeferredValue(text);

  // 重计算绑定 deferredText，避免每个 token 都触发 analyze
  const highlights = useMemo(
    () => analyzeHighlights(deferredText),
    [deferredText]
  );

  // 展示仍用最新 text（打字机效果），高亮可滞后一拍
  return <div>{renderWithHighlights(text, highlights)}</div>;
}
```

### 4.3 `use` API 与流式渲染的关系

`use` 可以在组件中直接消费 Promise，配合 `Suspense` 实现数据加载状态的扁平化管理。

但在流式对话场景中，**`use` 不直接处理流式数据**，因为流式数据是持续推送的，不是一个单次 resolve 的 Promise。

`use` 更适合用于“单次异步加载”场景，比如加载历史对话列表、用户信息等。

---

## 第五章：纯前端技术选型 —— 在外企“没得选”的情况下怎么答？

在外企面试中，前端技术栈通常是 React + Next.js（或 Remix）。面试官不考“选哪个框架”，而是考“在 React 生态内，你怎么做架构决策”。

### 5.1 SPA vs SSR：决策的核心维度

| 评估维度 | SPA（如 Vite + React Router） | SSR（Next.js App Router） |
| :--- | :--- | :--- |
| 首屏加载（LCP） | 较慢（需下载 JS 后渲染） | 快（服务端直接吐 HTML） |
| SEO | 差（爬虫难以抓取动态内容） | 好（服务端渲染完整 DOM） |
| 服务器成本 | 低（只需静态托管 CDN） | 高（需 Node.js 服务器持续运行） |
| 交互响应（INP / TTI） | 首屏交互取决于 JS 下载执行 | 需等待 Hydration 后交互才完整可用 |
| 适用场景 | 后台管理、Dashboard、工具型应用 | 官网、电商、营销落地页、内容型产品 |

### 5.2 针对 AI 对话产品的选型判断

以 RAG 对话产品为例：

> **主聊天页** → **Client Component / CSR**（在 Next.js 里可以是 `'use client'` 路由，不必 SSR 消息列表）。对话内容是实时生成的，强依赖客户端状态（`messages`、`loading`、滚动位置）。对**动态消息体**做 SSR 收益低，还会增加 Hydration 一致性成本；常见做法是 SSR/SSG **外壳**（布局、侧栏），消息区纯客户端渲染。

> **文档站 / 博客 / 营销页** → **Next.js SSG 或 ISR**。把 Markdown 文档预编译为静态 HTML，利用 CDN 加速全球访问。

> **用户个人中心（登录态）** → 视 SEO 需求而定；纯 App 内页可用 CSR，公开资料页可 ISR。

### 5.3 面试时的标准回答框架

> 「在 React / Next.js 技术栈下，聊天主界面默认 **Client Component + CSR**；只有营销页、文档页等需要 SEO / 首屏静态内容的路由，才上 SSG / ISR / 局部 SSR。」

### 5.4 加分关键词

| 关键词 | 用法 |
| :--- | :--- |
| **Hydration Mismatch** | 解释为什么**流式消息体**不适合 SSR，而非「整个 App 不能做 Next.js」。 |
| **Time-To-Interactive (TTI) / INP** | 强调 SSR 外壳虽快，聊天区仍要等 Hydration 后才能稳定交互。 |
| **ISR (Incremental Static Regeneration)** | 展示你对 Next.js 高级能力的掌握。 |
| **Edge Runtime** | 体现你能把 SSR 放到边缘节点，降低全球延迟。 |

---

## 结尾：这些技术点是怎么串起来的？

回到最开始的面试题——“如何实现 ChatGPT 那样的流式 Markdown 渲染？”

一个能落地的完整答案，应该包含以下层次：

| 层面 | 技术点 |
| :--- | :--- |
| **网络层** | SSE + BFF 背压控制 + 断线重连 |
| **渲染层** | `requestAnimationFrame` 节流 + 增量解析器 + 安全截断点 |
| **代码块 / LaTeX** | 延迟激活高亮 + 状态机 + 未闭合内容纯文本展示 |
| **断点续传 / Stop** | 全量 finalize（drain 上游）+ `visible_char_offset` 标记 + 刷新展示策略 |
| **框架层** | `useOptimistic` 管理乐观 UI，`useDeferredValue` 延迟重计算 |
| **技术选型** | 在 React 生态内，SPA vs SSR 的 ROI 权衡 |

这六个层面不是孤立的，而是一个完整的工程链路。每一个决策都有它的理由，每一个方案都有它的代价。

这就是我们从一道面试题出发，一路聊到 React 19、流式渲染、断点续传和前端架构选型的完整过程。希望能对你有所帮助。

---
