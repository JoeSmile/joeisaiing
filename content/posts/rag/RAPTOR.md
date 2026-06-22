---
title: "别再死磕分块了！分层RAG才是长文档召回的终极答案"
date: 2026-05-12T12:00:00+08:00
slug: "RAPTOR"
url: "/RAPTOR.html"
categories:
  - "AI 工程"
tags:
  - "RAG"
  - "RAPTOR"
  - "分层RAG"
draft: false
---
做RAG开发的人，大概率都陷入过一个死循环：
召回效果不好→换Embedding模型→调chunk大小→调top_k→换分块算法→折腾一圈，复杂问题还是答非所问，跨章节的问题永远漏信息，宏观问题抓不住重点，细节问题又断上下文。

很多人把问题归因为“分块不够好”，但本质上，**单层固定分块的RAG，天生就解决不了长文档的多粒度查询问题**。

今天我们就聊透工业界解决长文档召回的核心思路——**分层RAG**，从最火的RAPTOR递归语义树，到4大类落地方案，再到不同场景的选型指南，看完你就知道为什么说“分块调得再好，不如分层做对”。

## 一、为什么普通单层RAG“越做越累”？
我们常规做的RAG，本质都是“单层扁平检索”：把文档切成固定大小的Chunk，每个Chunk生成一条向量，用户提问直接匹配这些Chunk。
这套逻辑对付短文档、FAQ没问题，但遇到长文档、多章节内容，三个天生缺陷就暴露了：

### 1. 粒度两难：粗了不准，细了断上下文
- chunk设大了：语义混杂，精准匹配差，用户问一个小参数，可能捞到一大段不相关的内容；
- chunk设小了：上下文断裂，匹配到的只是碎片句子，LLM看不到前因后果，很容易产生幻觉。
父子分块（ParentDocument Retriever）一定程度缓解了这个问题，但本质还是“两层固定结构”，没有从根本上解决多粒度匹配的问题。

### 2. 跨章节知识：散落在各处的知识点拼不起来
这是单层RAG最致命的短板：
比如你问“整篇RAG教程里，RRF、MMR、MultiVector三种优化方案有什么区别？”，这三个知识点分散在文档的第2、4、7章节，单层检索最多捞到2-3个碎片Chunk，根本没法全局整合信息，LLM自然答不全面。

### 3. 宏观问题完全抓瞎
用户问“这篇论文的核心结论是什么？”“这份白皮书的整体框架是什么？”，单层检索匹配到的都是底层细节Chunk，和宏观问题的语义相似度极低，直接漏召回。

说白了，单层RAG只有一种“信息粒度”，但用户的提问是多维度的——有问细节的、有问宏观的、有跨章节整合的，用一种粒度去适配所有需求，天然就有天花板。

## 二、RAPTOR递归语义树：给文档建一座“多层语义金字塔”
### 1. 什么是RAPTOR？
RAPTOR全称 **Recursive Abstractive Processing for Tree-Organized Retrieval**，是斯坦福2024年提出的分层RAG方案，核心思路非常朴素：
**给文档自动构建一座多层语义金字塔，底层放原文细节，中层放主题摘要，顶层放全文总览；用户问什么粒度的问题，就匹配对应层级的信息。**

就像图书馆的检索系统：
- 顶层：图书馆总导览，告诉你馆里有哪几大类书籍；
- 中层：分类书架导览，告诉你计算机类有哪些细分方向；
- 底层：具体的书本内容，翻书找细节参数。
用户问“图书馆有没有AI相关的书？”，匹配顶层就够了；问“RAG检索优化有哪些方案？”，匹配中层；问“MMR的λ参数推荐值是多少？”，直接匹配底层细节。

### 2. 怎么建这座语义树？全自动自底向上四步走
你可以把RAPTOR构建语义树的过程，理解成**给一本无目录的厚书自动生成多层分级目录**：最底层是细碎的原文段落，往上一层是小节主题总结，再往上是章节核心摘要，最顶层是整本书的一句话概括。整个过程完全不需要人工标注章节结构，全靠语义自动聚合，逐层提炼抽象。

完整的构建分为四步，其中「降维预处理」是很多入门教程一笔带过，但决定聚类效果和速度的关键环节：

![RAPTOR 递归语义树：自底向上聚类与摘要](RAPTOR/raptor.png)

#### 第一步：切碎原文，铺好最底层“树叶”
先把长文档切成大小均匀的细粒度文本块（Chunk），比如每块200-500字，这些原始文本块就是语义树的**叶子节点**——所有的原文细节、参数、代码都在这一层，是整棵树的信息基础。
之所以切这么细，是为了保证后续语义匹配的精度：粒度越细，越不容易把不相关的内容混进同一个主题里。

#### 第二步：向量编码+降维压缩，为聚类做预处理
这一步是很多简化教程里“藏起来”的关键环节，分两小步：
1. **向量化**：用Embedding模型把每个文本块转换成高维语义向量（比如1536维），让计算机能读懂文字之间的语义远近关系；
2. **降维**：直接用高维向量聚类会遇到「维度灾难」——不仅计算速度极慢，还会因为向量空间过于稀疏，导致“远近”的区分度急剧下降，聚类结果混乱。
   工业界标准方案是用**UMAP算法**把高维向量压缩到低维（通常5-15维）：这个过程就像把复杂的语义信息提炼成核心主题标签，既完整保留了“哪两段话语义相近”的相对关系，又能让后续聚类的计算速度提升几十倍，同时过滤掉高维里的噪声信息，聚类反而更准。

#### 第三步：语义聚类，自动“物以类聚”分主题
用**GMM高斯混合模型**对降维后的低维向量做软聚类，自动把主题相近的文本块归为同一簇。
- 所谓“软聚类”，就是一个文本块可以同时属于多个主题簇——比如一段内容同时讲了RRF和MMR，就会同时被分到两个组里，完美适配文档里语义交叉的真实情况，不会像硬分类（比如K-Means）那样一刀切。
- 最省心的是，GMM可以通过BIC准则自动算出最优的聚类数量，不用你提前手动定“要分几个主题”，完全自动化。

#### 第四步：生成摘要当上层节点，递归循环直到塔顶
把同一个簇里的所有文本内容拼接起来，调用大模型（LLM）生成一段精简的主题摘要，这段摘要就是上一层的**父节点**。
接下来，把这些新生成的摘要节点，当成新的“文本块”，重复「向量化→降维→聚类→生成摘要」的整套流程，再往上叠加一层。
一直循环这个过程，直到最后只剩下1个摘要节点——这就是整棵树的**根节点**，对应整篇文档的全局核心总结。

最终你得到的，就是一棵**越往上语义越抽象、覆盖范围越大**的语义金字塔：底层管细节，中层管主题，顶层管全局。它完全基于内容的语义自动构建，不受原文的标题、排版、章节顺序的限制，哪怕是跨章节、隔了几十页的相关内容，也会被自动聚合到同一个主题分支里。

---

### 附：可运行简化版RAPTOR构建代码（可自主选择UMAP降维）
我们完全可以手动实现RAPTOR的核心构建逻辑，**降维算法可以自由选择（UMAP/PCA均可）**，下面是工业界标准的UMAP降维+GMM聚类的完整实现，基于LangChain+OpenAI生态，可直接运行修改。

#### 第一步：安装依赖
```bash
pip install langchain langchain-openai umap-learn scikit-learn numpy tiktoken
```

#### 第二步：完整实现代码
```python
import numpy as np
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from umap import UMAP
from sklearn.mixture import GaussianMixture
from langchain_core.documents import Document

# ========== 1. 基础配置 ==========
LLM_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
# 叶子节点分块大小
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
# 降维目标维度（聚类用推荐5-15维，2-3维仅用于可视化）
REDUCE_DIM = 10
# 递归终止条件：当节点数小于等于该值时，停止递归，生成根节点
STOP_CLUSTER_NUM = 2

# 初始化模型
embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
llm = ChatOpenAI(model=LLM_MODEL, temperature=0)


# ========== 2. 工具函数封装 ==========
def split_text_to_chunks(raw_text: str) -> list[Document]:
    """第一步：文本分块，生成叶子节点"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", " ", ""]
    )
    return splitter.create_documents([raw_text])


def get_embeddings(docs: list[Document]) -> np.ndarray:
    """生成向量数组"""
    texts = [doc.page_content for doc in docs]
    return np.array(embeddings.embed_documents(texts))


def reduce_dimensions(vectors: np.ndarray, target_dim: int = REDUCE_DIM) -> np.ndarray:
    """
    降维预处理：默认用UMAP，可替换为PCA
    想换PCA的话，把下面UMAP换成PCA即可：
    from sklearn.decomposition import PCA
    reducer = PCA(n_components=target_dim, random_state=42)
    """
    reducer = UMAP(
        n_components=target_dim,
        n_neighbors=15,  # 平衡局部/全局语义，数值越大越关注全局结构
        min_dist=0.1,    # 簇的紧凑程度，数值越小簇越紧凑
        random_state=42,
        metric="cosine"  # 用余弦距离，适配语义向量
    )
    return reducer.fit_transform(vectors)


def gmm_clustering(low_dim_vectors: np.ndarray) -> list[int]:
    """GMM软聚类，返回每个向量所属的簇标签"""
    # 自动寻找最优聚类数（BIC准则）
    max_clusters = min(len(low_dim_vectors) // 3, 20)
    best_bic = float("inf")
    best_n = 2
    for n in range(2, max_clusters + 1):
        gmm = GaussianMixture(n_components=n, random_state=42, covariance_type="full")
        gmm.fit(low_dim_vectors)
        bic = gmm.bic(low_dim_vectors)
        if bic < best_bic:
            best_bic = bic
            best_n = n
    
    # 用最优簇数做最终聚类
    gmm = GaussianMixture(n_components=best_n, random_state=42)
    labels = gmm.fit_predict(low_dim_vectors)
    return labels.tolist()


def generate_cluster_summary(cluster_docs: list[Document]) -> str:
    """调用LLM生成单个簇的摘要，作为上一层节点"""
    combined_text = "\n\n".join([doc.page_content for doc in cluster_docs])
    prompt = f"""请将以下多段文本合并，生成一段精简的主题摘要，保留核心信息，不要丢失关键概念：
{combined_text}
"""
    return llm.invoke(prompt).content


# ========== 3. 递归构建RAPTOR语义树主函数 ==========
def build_raptor_tree(docs: list[Document], current_level: int = 0) -> dict:
    """
    自底向上递归构建语义树
    返回结构：{level: 层数, nodes: 该层所有节点文档, children: 子层节点}
    """
    print(f"正在构建第 {current_level} 层，当前节点数：{len(docs)}")
    
    # 递归终止条件：节点数足够少，生成根节点
    if len(docs) <= STOP_CLUSTER_NUM:
        root_summary = generate_cluster_summary(docs)
        root_doc = Document(page_content=root_summary, metadata={"level": current_level, "is_root": True})
        return {
            "level": current_level,
            "nodes": [root_doc],
            "children": None
        }
    
    # 1. 向量化
    vectors = get_embeddings(docs)
    
    # 2. UMAP降维（想换算法就在这里改）
    low_dim_vectors = reduce_dimensions(vectors)
    
    # 3. GMM聚类
    cluster_labels = gmm_clustering(low_dim_vectors)
    
    # 4. 按簇分组，生成摘要
    cluster_groups = {}
    for doc, label in zip(docs, cluster_labels):
        cluster_groups.setdefault(label, []).append(doc)
    
    upper_level_docs = []
    for cluster_id, cluster_docs in cluster_groups.items():
        summary = generate_cluster_summary(cluster_docs)
        upper_doc = Document(
            page_content=summary,
            metadata={
                "level": current_level + 1,
                "cluster_id": cluster_id,
                "child_count": len(cluster_docs)
            }
        )
        upper_level_docs.append(upper_doc)
    
    # 递归构建上一层
    upper_tree = build_raptor_tree(upper_level_docs, current_level + 1)
    
    return {
        "level": current_level,
        "nodes": docs,
        "children": upper_tree
    }


# ========== 4. 运行示例 ==========
if __name__ == "__main__":
    # 示例文本（替换为你的长文档/PDF提取文本）
    sample_text = """
    RAG（检索增强生成）是一种结合信息检索和大语言模型的技术框架。
    基础RAG分为文档分块、向量化存储、检索匹配、大模型生成四个核心环节。
    MMR（最大边际相关性）是一种重排算法，用于平衡检索结果的相关性和多样性，避免返回重复内容。
    RRF（倒数排名融合）是一种多路检索结果融合算法，常用于混合关键词检索和向量检索的结果排序。
    MultiVector多表征检索会为同一段文档生成摘要、假设问题等多个向量，提升召回率。
    RAPTOR递归语义树通过分层聚类和摘要构建多层索引，解决长文档跨章节召回的问题。
    向量数据库是RAG的核心存储组件，常见的有Chroma、Milvus、Pinecone等。
    自查询检索（SelfQuery）可以让大模型自动提取元数据过滤条件，实现结构化的精准检索。
    上下文压缩检索可以对召回的文档做二次精简，只保留和问题相关的片段，节省Token。
    """
    
    # 第一步：生成分块叶子节点
    leaf_docs = split_text_to_chunks(sample_text)
    print(f"叶子节点数量：{len(leaf_docs)}")
    
    # 第二步：构建RAPTOR语义树
    raptor_tree = build_raptor_tree(leaf_docs)
    
    # 输出结果
    print("\n=== RAPTOR树构建完成 ===")
    print(f"总层数：{raptor_tree['children']['level'] + 1}")
    root_node = raptor_tree['children']['nodes'][0]
    print(f"根节点摘要：{root_node.page_content}")
```

#### 代码关键说明
1. **默认使用UMAP降维**，和RAPTOR官方论文方案完全一致，可通过`n_neighbors`、`min_dist`参数调优聚类效果；
2. **降维算法可自由切换**：想换成PCA只需要修改`reduce_dimensions`函数里的降维器（代码注释已给出示例）。PCA速度更快，但语义保持能力弱于UMAP，适合超大数据量的快速预处理；
3. 递归终止条件、分块大小、降维维度都可以根据文档长度和业务场景自由调整；
4. 这是简化版核心实现，生产环境还需要加上缓存、异常处理、向量库持久化等配套逻辑。

### 3. 怎么查？两种模式适配所有问题
RAPTOR的检索也不是单一逻辑，针对不同类型的提问，有两种经典检索方式：
- **逐层遍历模式**：从根节点开始往下找，相似度高就继续深入子节点，一步步定位到最相关的细节片段。适合多步骤、需要推理的复杂问题，能精准锁定信息路径；
- **全层融合模式**：一次性检索树上所有层级的节点，再用RRF算法把多层结果融合排序。兼顾宏观主题和底层细节，是日常问答最通用的模式。

## 三、别搞混：RAPTOR vs 父子分块，根本不是一回事
很多人刚接触RAPTOR的时候，会觉得“这不就是高级版的父子分块吗？”，其实两者天差地别，核心逻辑完全不一样：

| 维度 | 父子分块（ParentDocument） | RAPTOR递归语义树 |
|------|------------------------------|------------------|
| 分层逻辑 | 人工固定双层，按文档顺序切割 | 自动多层递归，按语义聚类分组 |
| 上层内容 | 完整原始原文，无压缩 | LLM生成的聚类摘要，是语义抽象 |
| 关联规则 | 子块按顺序绑定父文档，不看语义 | 跨段落、跨章节的相似内容自动聚为一类 |
| 检索逻辑 | 只检索底层子块，上层不参与检索 | 所有层级都参与检索，多层信息融合 |
| 实现成本 | 仅文本分割，零额外LLM调用 | 多层递归摘要，预处理token成本高 |
| 核心解决 | 单片段上下文断裂 | 跨章节知识整合 + 多粒度查询适配 |

举个最直观的例子：
一篇RAG万字教程，MMR、RRF、MultiVector的知识点分散在第2、4、7章节。
- 父子分块：按顺序切割，三个知识点分属三个不同的父文档，检索一次最多命中一个，没法自动整合；
- RAPTOR：靠语义聚类自动把三处相关内容聚到同一个中层摘要节点，一次检索就能召回全部三处的关联信息，天然支持跨章节整合。

## 四、分层RAG全家桶：4大类落地方案全梳理
RAPTOR只是分层RAG里最火的一种，工业界根据不同的成本、精度、场景需求，衍生出了四大类分层方案，从简单到复杂全覆盖：

### 1. 扁平多表征型：最轻量的“伪分层”
代表方案：**MultiVector Retriever**（父子分块、摘要双表征、假设问句表征）
严格来说它不算树形分层，只是同一份文档生成多份不同粒度的表征向量，平铺在向量库里。
- 优势：实现最简单，全向量库兼容，开发成本最低，是生产环境最普及的方案；
- 劣势：没有真正的层级结构，跨章节整合能力弱，适合中小规模文档。

### 2. 固定结构分层：最省心的“结构化分层”
代表方案：**Hierarchical Chunker（标题分层分块）**
完全依靠文档自带的标题结构（# 一级、## 二级标题）构建层级树，每层标题和内容分别向量化。
- 优势：零LLM调用、速度极快，完全适配Markdown、结构化PDF、技术文档；
- 劣势：只能按排版分层，不能识别跨段落的语义关联，适合结构规整的文档。

### 3. 递归聚类树形：长文档召回的“性价比之王”
代表方案：**RAPTOR、TreeRAG、SPROUTRAG**
靠语义聚类自动构建多层抽象树，是长文档、多章节知识库的首选方案。
- RAPTOR：标准版，多层聚类+摘要，精度最高；
- TreeRAG：轻量化版，优化聚类算法，降低预处理成本；
- SPROUTRAG：极致轻量化，完全不用LLM生成摘要，零token成本，适合预算有限的海量文档场景。

### 4. 图结构分层：复杂推理的“天花板”
代表方案：**微软GraphRAG、nanoGraphRAG**
在分层的基础上，额外抽取文档里的实体、实体关系，构建知识图谱，上层是社区摘要，下层是原文内容。
- 优势：不仅能分层，还能梳理实体之间的逻辑关系，多轮推理、复杂逻辑问答能力远超纯树形方案；
- 劣势：预处理算力和token成本极高，实现复杂度大，适合法律、金融、小说等多实体复杂文档。

## 五、怎么选？不同场景选型速查表
不用盲目追新，也不用觉得“方案越复杂越好”，不同场景对应最优解，直接套用就行：

| 场景/文档类型 | 首选方案 | 核心原因 |
|--------------|----------|----------|
| 个人技术博客、Obsidian笔记、万字以内单篇教程 | MultiVector（父子分块+摘要双表征） | 开发简单，成本极低，单篇文档跨章节需求少，完全够用 |
| 结构化技术文档、API手册、Markdown规范文档 | 标题分层分块 + MultiVector | 零LLM成本，贴合文档结构，检索速度快 |
| 学术论文、书籍、多章节白皮书、万字以上长文档 | RAPTOR / TreeRAG | 自动语义聚类，跨章节知识整合能力强，多粒度查询适配好 |
| 高并发低延迟的线上生产服务 | 固定标题分层 + BM25+向量混合检索 | 延迟可控，稳定性高，避免递归遍历带来的性能开销 |
| 法律合同、金融报告、多实体业务文档 | GraphRAG | 实体关系梳理能力强，复杂逻辑推理精度高 |
| 预算有限、海量通用文档、预处理算力不足 | SPROUTRAG | 零LLM摘要成本，轻量化分层，性价比最高 |

给绝大多数开发者的落地建议：
**先把MultiVector（父子分块+摘要）做好，再叠加RRF混合检索、MMR去重，这一套基础优化能解决80%的场景问题；如果是长文档、复杂知识库，再考虑上RAPTOR，最后才是GraphRAG。**
不要上来就堆最复杂的方案，成本高、维护难，收益还不一定匹配。

## 六、落地避坑：3个最容易踩的误区
### 1. 分层了就不用重排？大错特错
分层检索会召回多层、多路的结果，反而更容易出现重复、冗余，**分层+RRF融合+MMR去重**才是完整链路：
- RRF负责融合不同层级的检索结果，平衡宏观和细节的权重；
- MMR负责剔除同源重复的文档，避免冗余内容占用上下文Token。

### 2. 所有文档都用同一种分层策略？
不要一刀切：
- 短文档、FAQ：不用分层，普通向量检索就够；
- 结构规整的技术文档：用标题分层，性价比最高；
- 无结构的长文本、书籍：用RAPTOR聚类分层。
根据文档类型混合策略，才是工业界的常态。

### 3. 盲目追求多层，忽略预处理成本
RAPTOR的递归摘要，会带来几倍的LLM调用成本，层数越多成本越高。
一般工业落地3层就足够了（叶子细节层+中层主题层+顶层全局层），再多的层数，收益边际递减，成本却直线上升。

## 最后总结
RAG优化的本质，从来不是“把分块切得更准”，而是**让检索的信息粒度，匹配用户的提问粒度**。
单层固定分块，是用一种粒度应对所有需求，注定有天花板；而分层RAG，是用多粒度的信息索引，去适配多维度的用户提问，从架构上解决了长文档召回的核心矛盾。

但还是那句话：没有最好的方案，只有最合适的方案。
做技术不用盲目追新，先把基础的分块、混合检索、重排做扎实，再根据业务场景逐步叠加分层优化，花最少的成本，拿最实在的效果，才是工程落地的核心。
