# ChromaDB 使用指南

## 什么是 ChromaDB

ChromaDB 是一个开源的向量数据库，专门用于存储和检索 embedding 向量。
它的特点是轻量、易用、支持持久化。底层使用 SQLite 存储数据，并采用 WAL
（Write-Ahead Log）机制保证写入不丢失。

## 安装与快速开始

首先安装：pip install chromadb。

创建一个持久化客户端并写入数据：

    import chromadb
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection("my_docs")
    collection.add(
        ids=["id1", "id2"],
        documents=["苹果发布了新手机", "特斯拉发布新款电动车"],
    )

## 检索与过滤

ChromaDB 支持相似度检索和元数据过滤：

    collection.query(query_texts=["新款手机"], n_results=2)

同时可以使用 where 参数按元数据过滤，例如 where={"category": "tech"}。

## 性能与规模

ChromaDB 的 HNSW 索引在查询时会整体加载到内存，因此适合单机百万级向量。
当规模进一步扩大时，需要考虑迁移到 Milvus 或 Qdrant 等分布式向量数据库。
