---
title: "RAG召回率提不上？吃透MultiVector多表征向量索引就够了"
date: 2026-05-11T10:00:00+08:00
slug: "MultiVectorRetriever"
url: "/MultiVectorRetriever.html"
categories:
  - "AI 工程"
tags:
  - "RAG"
  - "LangChain"
  - "MultiVector"
  - "ParentDocument"
draft: false
---

> **说明**：MultiVector / 父子块是 **路径 B（原始长文档）** 的检索优化；与 [RRF vs MMR](/RRF-vs-MMR.html) 搭配时，先分清「多表征入库」和「多路 Retriever 融合」是两层事。LangChain 实现见 `langchain_classic.retrievers.multi_vector`（0.3+ 部分能力在 `langchain-classic` 包）。

Embedding 换了几轮、分块调了无数遍，仍然漏召回——Often 不是模型不够强，而是 **一个 Chunk 只有一条向量，只能对齐一种问法**。多表征索引（MultiVector）的核心很朴素：**同一父文档挂多条检索用向量，命中任意一条都回到同一份完整上下文**。

<!--more-->

## 一、什么是多表征向量索引？

### 1.1 单向量检索的局限

常规 RAG：固定 Chunk → 一条 Embedding → 相似度 Top-K。

- 宏观问法可能对不上细节 Chunk
- 细节问法可能对不上概括段
- 小 Chunk 命中后上下文断裂

### 1.2 核心思想

**同一份父文档**，生成多份「检索用短文本」（子块、摘要、假设问句、标题片段等），分别 embed 入库；**检索命中任一短文本，通过 `doc_id` 取回父文档（或父块）** 再送进 LLM。

与 LangChain **ParentDocumentRetriever** 的关系：父子块是 MultiVector 家族里最常用、**零额外 LLM** 的基础款；HQ / 摘要属于在子块之外 **再加向量**。

### 1.3 两层存储（检索 / 文档解耦）

| 层 | 存什么 | 作用 |
|----|--------|------|
| **向量库** | 多条短文本 + embedding + metadata（含 `doc_id`） | 相似度 / MMR 检索 |
| **文档库（docstore / byte_store）** | `doc_id` → 父文档全文或父块 | 返回 LLM 用的上下文 |

流程：`Query embed → 向量库 Top-K 子向量 → 收集 doc_id（去重）→ docstore 取父文档 →（可选）重排 / 压缩 → LLM`

**企业落地注意**：「完整原文」常需 **按 token 预算截断或 sliding window**，不必也不应把整本 PDF 塞进 prompt。返回的是 **父块级上下文**，不是无上限全文。

### 1.4 向量库兼容性

MultiVector 是 **应用层模式**：Chroma、FAISS、Milvus、Qdrant、**PGVector** 等标准接口均可。多条表征在库里就是多条独立向量，靠 metadata 里的 `doc_id` 关联。

文档库选型：

| 规模 | 常见选型 |
|------|----------|
| Demo | `InMemoryStore` |
| 生产 | **PostgreSQL**（`documents` 表 + `document_id`）、Redis、MongoDB |
| MemoryOS V1 | `documents` + `document_chunks`，一行 Gold 卡 = 一 doc 一块（见 §五） |

---

## 二、四种主流多表征方案

### 2.1 摘要双表征

- **做法**：Chunk + LLM 摘要（100–200 字）分别 embed，共用 `doc_id`
- **适合**：白皮书、长教程、宏观 + 细节并存的文档
- **成本**：离线多一倍 LLM 调用
- **不适合**：极短 FAQ（摘要≈原文，收益低）

### 2.2 假设问句（Hypothetical Questions）

- **做法**：每 Chunk 生成 3–5 条用户可能问法，逐条 embed
- **适合**：客服 KB、产品手册、口语化 ToC 提问
- **成本**：LLM 调用与向量条数暴涨；问句可能有 **幻觉**，需抽检或模板约束
- **不适合**：工程师搜 API 名 / 代码（关键词 + 结构化片段更有效）

### 2.3 父子分块（优先落地的「基础款」）

- **做法**：父块（大，进 docstore）+ 子块（小，进向量库），**无需额外 LLM**
- **适合**：合同、论文、长 PDF、强上下文文档
- **注意**：向量条数随子块线性增长，需监控索引体积与检索 `fetch_k`

### 2.4 自定义关键片段

- **做法**：标题、术语、API 名、代码块等单独 embed，与正文 Chunk 互补
- **适合**：API 手册、规范、术语密集行业文
- **成本**：规则 / 解析 pipeline 开发量高

---

## 三、选型：别四种全堆

全堆会导致：**离线 embed 成本爆炸、索引膨胀、同源 doc_id 重复命中、重排复杂度上升**。

**原则**：**父子分块作底座（长文档必选）→ 最多再叠一种 LLM 增值表征（摘要 or HQ or 关键片段）**。

| 文档类型 | 建议组合 |
|----------|----------|
| 技术长文 / 白皮书 | 父子 + 摘要 |
| 产品说明 / 客服 FAQ | 父子 + 假设问句 |
| 合同 / 法律 / 论文 | **仅父子** |
| API / 代码文档 | 父子 + 关键片段 |
| 短文（<1000 字） | 基础分块即可，不必 MultiVector |

---

## 四、和 RRF / MMR / 混合检索怎么配合（易混点）

### 4.1 两层不要混为一谈

| 层次 | 含义 | 例子 |
|------|------|------|
| **多表征入库** | 同一 `doc_id` 多条向量 | 子块 + 摘要 + HQ |
| **多路 Retriever** | 多个独立检索通道，再融合 | 向量 MultiVector **+ BM25** |

- 多条表征在 **同一个 vectorstore** 里：一次（或按 collection 多次）相似度搜索即可，命中后 **按 `doc_id` 去重**。
- **RRF** 典型用于 **多路 Retriever**（如 `EnsembleRetriever` 里 vector + BM25），不是「把摘要向量和 HQ 向量各跑一路再 RRF」的默认姿势——除非你把不同表征 **拆成不同 Retriever / collection** 刻意多路。

### 4.2 推荐在线链路

```text
Query
  → MultiVector 检索（子向量 Top-K，fetch_k 略大）
  → 按 doc_id 去重
  →（可选）Cross-Encoder / LLM ReRank
  →（可选）MMR：在候选 **doc 级** 做多样性（若已在 vectorstore 用 MMR，避免重复做两遍）
  → 上下文压缩 / token 预算裁剪
  → LLM
```

**MMR 放哪**：可在 `MultiVectorRetriever.search_type = SearchType.mmr` 于 **chunk 级** 选子向量；若已取父文档且 doc 候选仍冗余，再在 **doc 级** 做 MMR。不要无意义地链式叠两层相同 MMR。

### 4.3 LangChain 示意（API 以 classic 包为准）

```python
from langchain_classic.retrievers import EnsembleRetriever
from langchain_classic.retrievers.multi_vector import MultiVectorRetriever, SearchType

# 多表征向量 + 父文档 docstore
retriever = MultiVectorRetriever(
    vectorstore=vectorstore,
    byte_store=byte_store,  # 或 docstore
    id_key="doc_id",
)
retriever.search_type = SearchType.mmr
retriever.search_kwargs = {"k": 4, "fetch_k": 20}

# 混合检索：MultiVector（语义）+ BM25（关键词）— Ensemble 为加权合并，非 RRF；
# 若需 RRF 见 LangChain Ensemble 文档或自研融合层
ensemble = EnsembleRetriever(
    retrievers=[retriever, bm25_retriever],
    weights=[0.6, 0.4],
)

docs = ensemble.invoke("MMR 的 λ 推荐取值？")
```

入库时务必：`sub_doc.metadata["doc_id"] = parent_id`，并与 docstore 中父文档 key 一致。

---

## 五、MemoryOS 对照（V1 vs 演进）

| 项 | MemoryOS 现状 |
|----|---------------|
| 数据路径 | **路径 A**：Gold JSONL 事实卡，ETL 已写好 `text` |
| 切块 | **不二次切块**；`chunk_index=0`，一卡一块 |
| 存储 | PostgreSQL `documents` + `document_chunks` + pgvector |
| MultiVector | **V1 未上**；长 PDF / 用户上传（路径 B）再考虑父子块或多表征 |
| 检索 | 单向量 cosine + `min_score`；Agent 侧 `rag_sufficient` 决定是否 Tavily |

世界杯场景：**结构化摘要卡** 已足够，MultiVector 属于文档上传、长 PDF 知识库阶段的优化，而非 V1 必做项。

---

## 六、企业落地检查清单

- [ ] 父 / 子块大小与 overlap 有 token 上限依据
- [ ] `doc_id` 去重逻辑明确，避免同源父文档重复进 prompt
- [ ] 离线 ingest：embed 批次重试、失败批次可重跑（幂等 upsert）
- [ ] 在线检索：`top_k` / `fetch_k` / 超时预算可配置
- [ ] HQ / 摘要类表征有 **质检抽样**，控制幻觉问句
- [ ] 监控：索引条数、P95 检索延迟、命中率 / 空结果率

---

## 七、总结

MultiVector 的本质是 **用多条检索向量对齐多种问法，用 doc_id 拉回同一份父上下文**——不绑特定向量库，成本可控、收益在 long-doc 场景最明显。

落地顺序建议：**父子分块 →（按需）一种增值表征 → 混合检索 / ReRank → 再考虑更重的 Query 变换**。与 RRF、MMR 的分工见 [RRF vs MMR](/RRF-vs-MMR.html)；Query 侧优化见 [RAG 查询转换](/rag-retriever-optimize.html)。
