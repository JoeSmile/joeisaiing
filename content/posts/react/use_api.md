---
title: "巧用 React 19 `use` 提升 TTFB：原理、数据流与实战场景"
date: 2026-06-06T10:00:00+08:00
slug: "react-use-api"
url: "/react-use-api.html"
categories:
  - "前端 & Next.js"
tags:
  - "React"
  - "React 19"
  - "use"
  - "SSR"
  - "Next.js"
draft: false
---
> 深入理解 `use` 在服务端渲染中的角色，看懂 Promise 何时等待、数据如何流动，以及它在哪一环节真正提速。

---

### 一、引言：`use` 不是客户端数据请求工具

React 19 引入的 `use` API 是一个**在渲染期间读取 Promise 或 Context 的原语**。在 Next.js 等 RSC 架构下，典型用法是：Server Component **创建但不 await** Promise，Client Component 用 `use(promise)` 挂起等待——这样 Server Component 本身不会被阻塞，页面可以更早开始流式输出。

这篇文章讲清楚三件事：

1. **`use` 在哪里提速？** —— 提速发生在 **SSR 流式输出阶段**（React 18 起已支持），`use` 的作用是让 **Client Component 侧**不必等数据就绪就能先输出 Suspense fallback。
2. **Promise 在哪里等待？** —— 请求在 **服务端发起**；**挂起与恢复**发生在 Client Component 调用 `use()` 时（流式 SSR 先推送 fallback，数据就绪后再推送真实 UI）。
3. **数据流向是怎样的？** —— 数据在服务端获取，通过 **流式响应（HTML + RSC payload）** 推送到浏览器，Client Component 用 `use` 解包已 resolve 的值。

---

### 二、传统 SSR 的性能瓶颈：服务端阻塞

在 **未使用流式 SSR** 的传统 `renderToString` 模型中，一个典型的页面渲染流程是：

```
1. 服务端收到请求
2. 执行数据获取（如 fetch 数据库/API）—— 阻塞 2-5 秒
3. 等待数据返回后，渲染组件树生成完整 HTML
4. 将完整 HTML 一次性返回给浏览器
```

**TTFB（首字节时间）** 等于数据获取耗时 + 渲染耗时。用户在此期间看到的是白屏。

这是典型的 **“服务端阻塞渲染”** 模式。

---

### 三、`use` + Suspense 的提速机制：流式 SSR

**流式 SSR** 自 React 18 起已支持（`renderToPipeableStream` 等）；React 19 的 `use` 进一步让 Server Component 可以把 **未 resolve 的 Promise** 交给 Client Component，而不必在 Server Component 里 `await` 阻塞整页。

典型流程如下：

```
1. 服务端收到请求
2. 在 Server Component 中创建 Promise（但不 await）
3. 将 Promise 作为 props 传递给 Client Component
4. 服务端渲染 Client Component 树，执行 `use(Promise)` 时：
   a. 若 Promise 未 resolve → 抛出 Suspense 异常
   b. React 渲染 fallback（骨架屏）并继续输出后续 HTML
5. 服务端将“包含骨架屏的 HTML 流”立即返回给浏览器 → **TTFB 大幅提前**（具体取决于 shell 中 Suspense 边界之前是否还有其它内容）
6. Promise 在服务端 resolve 后，React 重新渲染该 Suspense 边界内的真实 UI
7. 真实 UI 通过同一个 HTTP 连接流式推送到浏览器
```

**TTFB 从“等待全部数据 + 渲染整页”降低为“先输出 shell / fallback 即可发送首字节”。** 这是流式 SSR + `use` 组合带来的核心提速点。

> **补充**：若子组件是纯 Server Component、无需 `'use client'`，官方更推荐直接在 async Server Component 里 `await`，同样配合 Suspense 流式输出，不必绕 Client Component + `use`。

---

### 四、Promise 在哪里等待？—— 请求在服务端，挂起在 Client Component

关键认知：**数据请求在服务端发起**（Promise 由 Server Component 创建），但 **Client Component 无法使用 `async/await`**，因此通过 `use(promise)` 在渲染时挂起；挂起点之后的 fallback 会先被流式输出，Promise resolve 后再补发真实 UI。

完整时序如下：

| 序号 | 发生位置 | 动作 |
| :--- | :--- | :--- |
| 1 | 服务端 | 执行 Server Component，创建 `fetchPlayer(id)` 返回的 Promise（pending 状态） |
| 2 | 服务端 | 将 Promise 通过 props 传递给 Client Component（如 `<PlayerCard dataPromise={playerPromise} />`） |
| 3 | 服务端（SSR 渲染 Client 树） | 渲染 Client Component，执行 `const data = use(dataPromise)` |
| 4 | 服务端（SSR） | `use` 检测到 Promise 未 resolve → 抛出 Suspense，输出 fallback |
| 5 | 服务端 → 浏览器 | 将 fallback HTML 写入响应流并发送（**首屏可见；TTFB 通常在此之前或此时完成**） |
| 6 | 服务端 | 等待 Promise resolve（fetch 仍在服务端执行） |
| 7 | 服务端 | Promise resolve 后，再次渲染该 Client Component，`use` 返回已 resolve 的数据 |
| 8 | 服务端 → 浏览器 | 将真实 UI 片段写入响应流并推送 |
| 9 | 浏览器 | 接收后续 chunk，React 将 fallback 替换为真实内容并完成水合 |

**重点：Server Component 不会因该 Promise 而阻塞；挂起发生在 Client Component 的 `use()` 调用处。数据 fetch 在服务端完成，浏览器不会为此 Promise 额外发起请求。**

---

### 五、数据流向图（文字版）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 服务端（Next.js Server）                                                    │
│                                                                             │
│  ① 请求进入 → 执行 Server Component                                        │
│  ② const promise = fetchData()  // pending，不 await                       │
│  ③ <Child dataPromise={promise} />                                        │
│  ④ 渲染 Child，调用 use(promise) → 未 resolve → 抛出 Suspense              │
│  ⑤ 输出 fallback HTML → 立即发送 → 【TTFB 完成】                           │
│  ⑥ 后台等待 promise resolve...                                             │
│  ⑦ resolve 后，再次渲染 Child → use(promise) 返回数据 → 生成真实 UI HTML   │
│  ⑧ 将真实 UI HTML 通过流推送到浏览器                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ 同一个 HTTP 连接，分块传输
┌─────────────────────────────────────────────────────────────────────────────┐
│ 浏览器                                                                    │
│                                                                             │
│  ⑨ 接收并展示 fallback HTML（骨架屏可见）                                   │
│  ⑩ 接收真实 UI chunk → React 合并流式更新 → 替换 fallback              │
│  ⑪ 水合完成，组件可交互                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 六、`use` 提速的具体环节拆解

| 环节 | 传统 SSR | 使用 `use` + 流式 SSR | 提速效果 |
| :--- | :--- | :--- | :--- |
| **服务端数据获取** | 阻塞等待完成后才开始渲染 | 不等待，立即开始渲染 fallback | TTFB 减少 2-5 秒 |
| **首屏 HTML 输出** | 一次性输出完整 HTML | 分块输出：先 fallback，后真实内容 | 首屏可见时间提前 |
| **客户端数据请求** | 可能需要 `useEffect` + fetch 二次请求 | 数据在服务端 fetch，结果经流式响应送达，无需客户端再请求同一数据 | 减少一次 RTT |
| **水合等待** | 必须等待完整 HTML 加载完成才能水合 | 流式水合：已到达的片段先水合 | 交互时间提前 |

---

### 七、`use` 的适用边界与限制

#### ✅ 适用的场景

- **首屏必须快速渲染**：如营销页、落地页、直播详情页等。
- **数据获取耗时较长**：如调用第三方 API、数据库查询、AI Agent 推理。
- **页面结构允许流式加载**：页面的不同区域可以独立展示骨架屏。

#### ❌ 不适用的场景

- **非首屏数据**：用户交互后才触发的数据加载（如点击按钮后请求），应使用 `react-query` 或 `useEffect`。
- **数据需要在多个组件间共享**：`use` 不提供缓存机制，跨组件共享应使用 `react-query` 或 Server Component 的数据透传。
- **需要轮询或重新验证的数据**：`use` 是单次消费，不具备缓存失效和重新获取的能力。

#### ⚠️ 注意事项

1. **Client Component 不支持 `async/await`**，因此需要交互的组件才用 `use(promise)`；纯展示、无 `'use client'` 的子树应优先用 **async Server Component + `await`**。
2. **Promise 的 resolve 值必须可序列化**（如 JSON 数据）；Promise 本身通过 RSC 协议传递，函数等不可序列化的类型不能作为 resolve 结果。
3. **不要在 Client Component 的 render 里临时 `fetch` 再 `use`**——每次 render 都会新建 Promise，导致反复 Suspense；Promise 应在 Server Component 或事件处理器中创建后传入。

---

### 八、工程实践示例

```tsx
// app/player/[id]/page.tsx —— Server Component
import { Suspense } from 'react';
import { PlayerCard } from '@/components/PlayerCard';
import { fetchPlayer } from '@/lib/fetchPlayer';

export default function Page({ params }: { params: { id: string } }) {
  // 在服务端创建 Promise，不 await
  const playerPromise = fetchPlayer(params.id);

  return (
    <div>
      <h1>球员档案</h1>
      <Suspense fallback={<div>正在加载球员信息...</div>}>
        <PlayerCard dataPromise={playerPromise} />
      </Suspense>
    </div>
  );
}
```

```tsx
// components/PlayerCard.tsx —— Client Component
'use client';
import { use } from 'react';

type Props = {
  dataPromise: Promise<{ name: string; goals: number }>;
};

export function PlayerCard({ dataPromise }: Props) {
  // 消费 Server Component 传入的 Promise，不在 render 里重新 fetch
  const data = use(dataPromise);

  return (
    <div>
      <h2>{data.name}</h2>
      <p>进球数：{data.goals}</p>
    </div>
  );
}
```

---

### 九、总结

`use` 在 SSR 场景下的核心价值，可以用一句话概括：

> **`use` 让服务端不再等待数据即可开始输出 HTML，TTFB 的提速来源于此。**

它不是客户端数据请求工具，而是 **Server Component 与 Client Component 之间的 Promise 传递桥梁**（纯 Server 场景下更推荐直接 `await`）。它改变了服务端渲染的时序：

- **之前**：获取数据 → 渲染完整 HTML → 发送
- **之后**：发送骨架屏 → 后台等待数据 → 流式推送真实 UI

这一模式对 **RAG 类应用**尤其有价值——后端 Agent 推理耗时较长（2-5 秒），使用 `use` + 流式 SSR 可以避免用户长时间白屏等待，显著提升首屏体验。

另: 使用use不算两次水合.
水合是指：React 在服务端生成 HTML 后，在客户端首次加载时，为 DOM 节点绑定事件监听和内部状态的过程。
使用use,是在一次水合中,分2次“读取”数据和1次“重新渲染”