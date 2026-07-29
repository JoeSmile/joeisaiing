---
title: "可复制流程：意图指纹、三级记忆与 Query 前置处理"
date: 2026-07-26T10:00:00+08:00
slug: "replicable-pipeline"
url: "/replicable-pipeline.html"
categories:
  - "学习笔记"
tags:
  - "意图指纹"
  - "记忆系统"
  - "缓存"
  - "Agent"
draft: false
series: "情感机器人 · 大模型应用笔记"
series_order: 10
---

把系统从「能用」升级到「可维护、可进化」：区分**意图指纹**与**高频缓存**，把三级记忆插进流程，串成完整的 Query → LLM 前置处理链路。

<!--more-->

## 补充点 1：意图指纹 vs 高频缓存

两者常被混在 Redis 里讲，关系是：**指纹是钥匙（Key），缓存是柜子（Value）**，功能边界不同。

### 1. 意图指纹（Intent Fingerprint）——标准化查重器

把千变万化的自然语言，归一成**稳定、去重后的标准字符串**，判断「这句话和之前哪句本质上一个意思」。

```python
def generate_fingerprint(raw_query, intent_id, entities):
    # 1. 实体标准化（北京/首都/京城 → beijing）
    normalized_entities = normalize(entities)  # {"city": "beijing"}

    # 2. 按固定顺序排序（避免 key 顺序不同导致指纹不同）
    sorted_entities = json.dumps(normalized_entities, sort_keys=True)

    # 3. 拼装：intent_id + 实体哈希
    fingerprint = f"{intent_id}:{hash(sorted_entities)}"
    # 例：weather_query:{ "city":"beijing","date":"2026-07-29" }
    # → "weather_query:abc123def"
    return fingerprint
```

**用途**：

- **去重日志**：「北京明天天气」与「明天北京天气如何」聚合到同一指纹
- **防重复执行**：同会话连续同义问，指纹命中可直接返回，连缓存层都可短路

### 2. 高频缓存（Template Cache）——预制件仓库

存 **意图指纹 → 预制答案（或执行指令）**：

| 存储内容 | Key（指纹） | Value |
| :--- | :--- | :--- |
| 静态答案缓存 | `weather_query:abc123def` | `"北京明天晴，22°C"` |
| 动态指令缓存 | `calculator:xyz789` | `{"action": "eval", "expr": "{user_input}"}` |

协作关系：

> Query → 提取意图+实体 → 生成意图指纹 → 用指纹查 Redis 高频缓存 → 命中直接返回，未命中走 Skill 或 LLM

## 补充点 2：把记忆系统插进流程

每个子任务不能当「瞎子」——要知道你是谁、刚聊了什么、默认城市是哪。

### 插入点 A：意图识别之前（上下文增强）

先拉当前用户记忆，塞进 `context`，供后续模块共用。

### 插入点 B：Skill 执行之后（记忆更新）

把新信息写回记忆库（如用户问过北京天气）。

### 中小企业级三级记忆（可手搓）

| 层级 | 存储介质 | 存储内容 | 读写时机 |
| :--- | :--- | :--- | :--- |
| **L1 热记忆（会话级）** | Redis（TTL 约 1h） | 最近 5 轮完整对话 | 每次 Query 读，每轮结束写 |
| **L2 温记忆（用户画像）** | SQLite / PostgreSQL | `preferred_city=北京`、`role=工程师` | 意图识别时读，Skill 确认后写 |
| **L3 冷记忆（语义摘要）** | ChromaDB / PGVector | 每 10 轮压缩后的历史摘要向量 | 复杂 Query 检索；凌晨批量压缩 |

## 完整版：Query → LLM 前置处理流程

### 第 1 步：原始输入 + 会话上下文加载（<5ms）

用户输入：「明天呢？」（上一轮问过北京天气）

- 从 Redis 读 `hot_memory`（最近 3 轮）
- 输出：`context = {"history": [...], "user_id": "u123"}`

### 第 2 步：精确缓存拦截（<1ms）

用 `exact:u123:明天呢？` 查 Redis（防刷），几乎不中则跳过。

### 第 3 步：温记忆加载（<5ms）

查用户偏好，如 `{"preferred_city": "北京"}`，**塞进 context**。

### 第 4 步：上下文增强（纯字符串，<1ms）

```text
[用户背景] 默认城市：北京。
[近期对话] 用户刚才问了北京今天的天气，助手回复了晴天。
[当前Query] 明天呢？
```

让后面的小模型能利用上下文，而不是只看孤立一句。

### 第 5 步：意图识别 + 实体抽取（并行，5~10ms）

- BERT：`weather_query`（置信度 0.95）
- NER + 温记忆兜底：城市缺失则用 `preferred_city`；时间 = 明天
- 输出：`intent` + `entities={"city":"北京", "date":"2026-07-29"}`

### 第 6 步：生成意图指纹（<1ms）

```python
fingerprint = generate_fingerprint(intent, entities)
# weather_query:abc123def
```

### 第 7 步：指纹级缓存命中（<1ms）

```python
cached = redis.get(f"template:{fingerprint}")
```

命中则直接返回，**LLM 和 Skill 都不调**；未命中进入路由。

### 第 8 步：路由分发（<1ms）

| 意图类型 | 执行逻辑 |
| :--- | :--- |
| `weather_query` | 调 `weather.py` Skill |
| `calculator` | 调 `calculator.py` |
| `reminder` | 调 `reminder.py` |
| `unknown` 或置信度 < 0.8 | 兜底调 LLM API |

### 第 9 步：Skill 执行（示例 ~200ms）

天气 API → 填充模板：`"北京明天多云，气温25°C"`

### 第 10 步：异步更新记忆（非阻塞）

- **热**：本轮追加到 Redis，保留最近 5 轮
- **温**：首次问北京则写入 `preferred_city`
- **冷**：轮次达 10 的倍数时异步压缩摘要 → 向量库

### 第 11 步：写指纹缓存

```python
redis.setex(f"template:{fingerprint}", 86400, "北京明天多云，气温25°C")
```

### 第 12 步：返回用户

```text
北京明天多云，气温25°C
```

## 完整流程图（文字版）

```text
用户Query
    ↓
① 加载热记忆（Redis 会话历史）→ 注入 context
    ↓
② 加载温记忆（SQLite 用户画像）→ 注入 context
    ↓
③ 精确缓存拦截（全量匹配）→ 命中则直接返回
    ↓
④ 上下文增强（拼接背景 + 历史 + 当前 Query）
    ↓
⑤ 意图识别（小 BERT）+ 实体抽取（小 NER，缺省从温记忆补全）
    ↓
⑥ 生成标准化意图指纹（intent + 规范化实体）
    ↓
⑦ 指纹缓存命中（Redis template_cache）→ 命中则直接返回
    ↓ (未命中)
⑧ 路由分发
    ├─ 确定性任务 → 调对应 Skill
    └─ 模糊 / 复杂任务 → 调 LLM API（兜底）
    ↓
⑨ Skill / LLM 执行
    ↓
⑩ 更新三级记忆（热 Redis、温 SQLite、异步冷向量库）
    ↓
⑪ 写入指纹缓存
    ↓
返回最终结果
```

## 改造项目的最小行动清单

1. **温记忆表（SQLite）**：`user_memory(user_id, key, value)`
2. **热记忆（Redis）**：`session:{session_id}:history`，最近 5 轮
3. **意图识别输入**：从「纯 Query」改为「增强后的上下文文本」
4. **实体抽取**：抽不到时降级从温记忆取默认值
5. **意图指纹函数**：`generate_fingerprint(intent, entities)`，替换原文直查缓存
6. **缓存分两层**：`exact:` 精确防刷；`template:{指纹}` 模板缓存

这 6 步改完，系统从「无状态路由器」进化成「有记忆、会复用经验的智能体」。
