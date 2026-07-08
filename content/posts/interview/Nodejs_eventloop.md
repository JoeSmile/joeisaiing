---
title: "Nodejs EventLoop"
date: 2026-07-3T10:00:00+08:00
slug: "Nodejs_eventloop"
url: "/Nodejs_eventloop.html"
categories:
  - "interview"
tags:
  - "面试"
  - "nodejs"
draft: false
---


在 Node.js（v14+，基于 libuv）中，事件循环的**核心精髓**在于：**微任务的清空是“穿插”在宏任务之间的，且 `process.nextTick` 拥有“超车道”特权。**

下面我为你做一次**更为细致且严谨**的深层剖析，彻底厘清这些模糊点。

---

### 1. 最大误区修正：微任务到底什么时候执行？

原笔记说“每个阶段执行一批宏任务后，再清空微任务队列”。**这个说法是不准确的！**

**准确规则（Node.js 官方文档定义）：**

- **在执行每个宏任务（单个回调）之后**，Node.js 都会**立即**去清空微任务队列。
- **并非**等整个阶段的所有宏任务跑完才去清空微任务。

**但是，这里有一个极其重要的分层机制（优先级）：**

Node.js 将微任务分为了**两个优先级不同的队列**：

1. **`process.nextTick` 队列**（**最高优先级**）：在当前宏任务执行完后，**立即、彻底**清空。
2. **`Promise.then/catch/finally` 等常规微任务队列**（次优先级）：在 `nextTick` 队列清空后，再去清空 Promise 队列。

> **结论**：在执行任何一个宏任务的回调时，一旦调用栈清空，JS 引擎会死磕 `nextTick`，直到把当前所有的 `nextTick` 执行完，再执行所有的 `Promise`，之后才会去执行**下一个**宏任务。

---

### 2. 关于“一批宏任务”的真相（Poll 阶段的特殊机制）

原笔记提到的“一批”在 Node.js 中确实存在，但它只特指 **Poll（轮询）阶段**。

- **其他阶段（Timers、Check 等）**：执行该阶段队列里的**所有**到期宏任务（直到队列为空或达到系统最大限制）。
- **Poll 阶段（最特殊）**：它会执行**所有**可用的 I/O 回调。但如果队列里积压了成千上万个回调，为了防止主线程卡死，libuv 会设定一个 **`hard limit`（硬限制）**，分批处理。

---

### 3. Node.js 事件循环的完整执行流程图解（精细化）

为了让你深刻理解，我们把“微任务穿插”带入到 6 个阶段中：

**一次完整的 EventLoop 轮询（Tick）流程如下：**

```text
┌───────────────────────────┐
│        timers 阶段          │ 执行 setTimeout/setInterval 到期的回调
│   (执行完 1 个回调后，立刻清空 nextTick 和 Promise)
└─────────────┬─────────────┘
│ (循环执行，直到队列为空或达到上限)
┌─────────────▼─────────────┐
│   pending callbacks 阶段   │ 执行系统操作（如 TCP 错误）回调
└─────────────┬─────────────┘
┌─────────────▼─────────────┐
│     idle, prepare 阶段     │ 内部使用，忽略
└─────────────┬─────────────┘
┌─────────────▼─────────────┐
│         poll 阶段          │ ★ 核心 ★ 获取新的 I/O 事件
│   (执行 I/O 回调，同样每执行完 1 个，清空 nextTick 和 Promise)
└─────────────┬─────────────┘
┌─────────────▼─────────────┐
│         check 阶段         │ 执行 setImmediate 回调
└─────────────┬─────────────┘
┌─────────────▼─────────────┐
│      close callbacks 阶段  │ 执行 socket.on('close') 等关闭回调
└───────────────────────────┘
```

**关键细节补充（面试加分项）：**

- **Poll 阶段的“阻塞”机制**：如果 Poll 队列为空，且没有 `setImmediate` 待处理，且有 `timers` 未到期，EventLoop 会在这里**阻塞等待**（等待 I/O 事件进来或 timer 超时），而不是空转。
- **Check 阶段的触发**：`setImmediate` 之所以比 `setTimeout(fn, 0)` 在某些情况下快，是因为 `setImmediate` 在 Check 阶段执行，而 `setTimeout` 在 Timers 阶段执行（受限于系统时钟精度，通常 1ms 延迟）。

---

### 4. 决定执行顺序的“幕后黑手”：`process.nextTick` 与 `Promise` 的终极对决

我们来验证一下微观执行顺序：

**代码测试：**

```javascript
// 宏任务 1
setTimeout(() => {
  console.log('Timer1');
  process.nextTick(() => console.log('nextTick inside Timer'));
  Promise.resolve().then(() => console.log('Promise inside Timer'));
}, 0);

// 宏任务 2
setTimeout(() => {
  console.log('Timer2');
}, 0);

// 宏任务 3 (Check 阶段)
setImmediate(() => {
  console.log('Immediate');
});
```

**实际执行结果（Node.js v14+）：**

```text
Timer1
nextTick inside Timer
Promise inside Timer
Immediate   // 注意：这里并不一定总是先于 Timer2，取决于启动时的 CPU 状况
Timer2      // Timer2 和 Immediate 顺序并不固定，但一定是 Timer1 内部的微任务先清完
```

> **为什么会这样？** 当 `Timer1` 执行完毕，`nextTick` 和 `Promise` 必须**立刻清空**，才能去执行 EventLoop 的下一阶段（Check 或 Timers），绝不可能等到 `Timer2` 执行完再清微任务！

---

### 5. 浏览器 vs Node.js 终极差异（面试标准答案）

| 对比维度 | **浏览器** | **Node.js (v14+)** |
| :--- | :--- | :--- |
| **宏任务粒度** | 每次循环取 **1个** 宏任务执行 | 每个阶段会执行**一批/全部**宏任务（Poll 阶段有硬上限） |
| **微任务清空时机** | 执行完 **1个** 宏任务后，**清空全部**微任务 | 执行完 **1个** 宏任务后，先清空 `nextTick`，再清空 `Promise` |
| **UI 渲染** | 存在（在微任务之后，下一个宏任务之前） | **不存在**（服务器端无渲染） |
| **微任务优先级** | `Promise` 和 `MutationObserver` 同级 | **`process.nextTick` > `Promise.then`**（绝对优先级差异） |
| **阶段划分** | 简单循环（宏任务 -> 微任务 -> 渲染） | **六阶段严格划分**（Timers -> Poll -> Check 等，含阻塞等待） |

---

