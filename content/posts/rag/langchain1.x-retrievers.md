---
title: "LangChain 1.x（0.1+）全主流 Retriever 分类详解"
date: 2026-06-20T10:00:00+08:00
slug: "langchain1.x-retrievers"
url: "/langchain1.x-retrievers.html"
categories:
  - "AI 工程"
tags:
  - "RAG"
  - "LangChain"
  - "Retriever"
draft: false
---
分为4大类：**基础向量检索器、LLM增强检索器、混合/多路融合检索器、专用数据源检索器**，每个包含：导入、核心原理、使用方法、适用场景、优缺点。
> 统一版本说明：LangChain 0.1.x/0.2.x/0.3.x 导入路径统一，废弃0.0.x旧路径，所有Retriever均实现`BaseRetriever`，标准调用`.invoke(query)`。

## 一、基础向量检索器（VectorStoreRetriever，最底层标配）
### 1. VectorStore.as_retriever() 内置三种检索模式（无独立类，所有向量库通用）
向量库：Chroma / FAISS / Milvus / Pinecone / PGVector 等
#### 三种模式
1. **similarity 纯相似度检索（默认）**
```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

vectorstore = Chroma.from_texts(["RAG多查询重写", "Go Gin开发"], embedding=OpenAIEmbeddings())
# 基础相似度检索
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
docs = retriever.invoke("RAG优化方案")
```
- **原理**：query向量化，取距离最近Top-k向量
- **场景**：简单内部知识库、FAQ、低并发Demo、术语匹配精准的场景
- **优点**：速度最快、无额外LLM调用、成本极低
- **缺点**：用户提问模糊、同义改写会漏召回；返回结果高度重复

2. **mmr 最大边际相关性**
```python
retriever = vectorstore.as_retriever(search_type="mmr", search_kwargs={"k":4, "fetch_k":10, "lambda_mult":0.6})
```
- **原理**：先取更多候选，平衡「相似度」+「多样性」，剔除高度重复文档
- **场景**：需要多角度资料、教程/文档类问答、避免重复片段
- `lambda_mult`：0=纯多样性，1=纯相关性

3. **similarity_score_threshold 阈值过滤**
```python
retriever = vectorstore.as_retriever(search_type="similarity_score_threshold", search_kwargs={"score_threshold":0.7})
```
- **原理**：低于阈值的文档直接丢弃，过滤低相关噪音
- **场景**：精准问答、客服FAQ，不希望返回无关内容

## 二、LLM增强检索器（langchain.retrievers.* 高频工业级）
### 2. SelfQueryRetriever 自查询检索器（你之前问的元数据过滤路由）
```python
from langchain.retrievers import SelfQueryRetriever
from langchain_core.structured_query.schema import AttributeInfo

# 1. 定义元数据字段（年份、分类、价格等结构化条件）
metadata_fields = [
    AttributeInfo(name="year", description="文档发布年份", type="int"),
    AttributeInfo(name="category", description="技术分类", type="str")
]
retriever = SelfQueryRetriever.from_llm_and_db(
    llm=ChatOpenAI(temperature=0),
    db=vectorstore,
    document_content_description="技术博客文档",
    metadata_field_info=metadata_fields
)
# 自然语言自动拆解过滤条件：2025年的LLM安全文章
docs = retriever.invoke("2025年发布的RAG优化技术文章")
```
- **原理**：LLM自动拆分自然语言=「语义向量查询」+「结构化元数据过滤条件」，向量库同时做相似度+过滤
- **场景**：带元数据筛选知识库（年份、分类、作者、产品型号、价格）；企业文档库、电商商品知识库
- **优点**：无需手动解析用户过滤意图，天然轻量化LLM分类路由
- **缺点**：依赖向量库支持元数据过滤；额外LLM调用增加耗时

### 3. MultiQueryRetriever 多查询重写检索（模板路由基础实现）
```python
from langchain.retrievers import MultiQueryRetriever

base_retriever = vectorstore.as_retriever(k=3)
retriever = MultiQueryRetriever.from_llm(retriever=base_retriever, llm=ChatOpenAI(temperature=0))
# LLM自动生成多条同义子查询并行检索，合并去重
docs = retriever.invoke("LangChain SelfQuery怎么落地")
```
- **原理**：LLM生成3~5个同义/多角度改写query，分别检索后合并去重，拓宽召回范围
- **场景**：用户口语化提问、术语不统一、模糊查询、行业术语多的技术知识库（你截图RAG文档场景完美适配）
- **优点**：大幅提升召回率，解决单query语义覆盖不足；可并行检索压缩耗时
- **缺点**：多一次LLM调用，token消耗上升；简单合并无加权排序，高价值文档易被截断

### 4. ParentDocumentRetriever 父子文档检索（解决Chunk语义割裂）
```python
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore
from langchain.text_splitter import RecursiveCharacterTextSplitter

# 子分割器：细粒度小块用于检索；父分割器：完整长文档返回
child_splitter = RecursiveCharacterTextSplitter(chunk_size=400)
parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000)
docstore = InMemoryStore() # 存储完整父文档

retriever = ParentDocumentRetriever(
    vectorstore=vectorstore,
    docstore=docstore,
    child_splitter=child_splitter,
    parent_splitter=parent_splitter
)
# 检索细粒度子块，自动返回完整父文档上下文
```
- **原理**：大文档拆细粒度子块入库做检索，匹配到子块后返回完整父文档，解决小块上下文断裂
- **场景**：合同、白皮书、长技术PDF、法律文档、教程，需要完整上下文理解
- **优点**：兼顾检索精度与完整上下文，是生产RAG标配优化
- **缺点**：需要额外文档存储层，内存/存储占用更高

### 5. ContextualCompressionRetriever 上下文压缩检索（解决Token超限）
```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor

# 压缩器：LLM只提取和query相关的片段，删除冗余内容
compressor = LLMChainExtractor.from_llm(ChatOpenAI(temperature=0))
base_retriever = vectorstore.as_retriever(k=15) # 先多取候选
retriever = ContextualCompressionRetriever(base_retriever=base_retriever, base_compressor=compressor)
docs = retriever.invoke("RAG RRF融合原理")
```
- **原理**：先批量召回较多文档，再用LLM/正则过滤压缩每个文档，只保留和问题相关片段
- **场景**：LLM上下文窗口小、长文档检索、大量冗余文本，严格控制输入token
- **优点**：大幅减少送入LLM的上下文长度，降低成本、减少幻觉
- **缺点**：二次LLM调用增加延迟；极端情况会丢失少量关键信息

## 三、混合/多路融合检索器（生产级高精度RAG必备）
### 6. EnsembleRetriever 多路融合检索（RRF倒数排名融合）
```python
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

# 1. 关键词BM25检索器
bm25_ret = BM25Retriever.from_texts(texts)
bm25_ret.k = 3
# 2. 语义向量检索器
vec_ret = vectorstore.as_retriever(k=3)
# 3. RRF融合多路结果
ensemble_ret = EnsembleRetriever(retrievers=[bm25_ret, vec_ret], weights=[0.5,0.5])
docs = ensemble_ret.invoke("Go Web 高并发优化")
```
- **原理**：支持同时接入任意多个Retriever（BM25+向量、多向量库、MultiQuery+SelfQuery），使用**RRF倒数排名融合**加权重排
- **场景**：混合关键词+语义检索（工业标准方案）、多知识库融合检索、追求高召回+高精准
- **优点**：互补单一检索短板，BM25擅长精准术语匹配，向量擅长语义理解，综合效果最优
- **缺点**：多路并行检索，IO开销翻倍，并发高时需做限流优化

### 7. BM25Retriever 纯关键词检索（配套Ensemble使用）
```python
from langchain_community.retrievers import BM25Retriever
docs = [Document(page_content="RAG多查询重写"), Document(page_content="RRF融合算法")]
retriever = BM25Retriever.from_documents(docs)
retriever.k = 4
```
- **原理**：传统TF-IDF关键词检索，无向量、不理解语义，精准匹配专业名词、代码、专有术语
- **场景**：和向量检索做混合检索（Ensemble标配）、代码库、技术文档、有大量专有名词的知识库
- **缺点**：纯字面匹配，无法处理同义改写，单独使用召回差

## 四、专用外部数据源Retriever（联网/第三方知识库）
### 8. TavilySearchAPIRetriever 联网搜索检索器
```python
from langchain_community.retrievers import TavilySearchAPIRetriever
retriever = TavilySearchAPIRetriever(k=3)
# 实时联网获取互联网最新资料
docs = retriever.invoke("2026最新RAG优化方案")
```
- **场景**：实时资讯、时效性内容、本地知识库不存在的外网资料、Agent联网问答

### 9. WikipediaRetriever / ArxivRetriever
- WikipediaRetriever：检索维基百科通用知识
- ArxivRetriever：检索学术论文、技术预印本
- 场景：科普、学术调研、论文类问答

## 五、补充小众但实用Retriever
1. **TimeWeightedVectorStoreRetriever**：带时间权重排序，新闻、日志、产品更新文档，优先返回最新内容
2. **MultiVectorRetriever**：一份文档生成多组向量（摘要向量、问题向量、原文向量），多路检索融合，超长文档优化
3. **MergerRetriever**：简单合并多路检索（无RRF重排，仅去重），轻量多路合并替代Ensemble

# 生产RAG检索器选型速查表（对应你RAG优化文档）
| 业务需求 | 首选Retriever组合 |
|---------|------------------|
| 简单内部FAQ、轻量Demo | VectorStoreRetriever(similarity/mmr) |
| 用户提问模糊、口语化、漏召回严重 | MultiQueryRetriever |
| 文档带年份/分类/型号等筛选条件 | SelfQueryRetriever |
| 长PDF/合同/白皮书，Chunk上下文断裂 | ParentDocumentRetriever |
| 输入Token严格受限、文档冗余多 | ContextualCompressionRetriever |
| 代码/技术文档，专有名词多，兼顾语义 | EnsembleRetriever(BM25+向量) |
| 需要最新互联网实时资料 | TavilySearchAPIRetriever + 本地向量库融合 |
| 完整工业级RAG最优链路 | MultiQuery → Ensemble(BM25+向量) → ParentDocument → ContextCompression |
