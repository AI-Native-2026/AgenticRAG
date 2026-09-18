"""存储层 —— 职责分离（对应学习手册 03 篇）。

- docstore.py     : MongoDB，保存 node 文本 + metadata（真相源 / Source of Truth）
- index_store.py  : MongoDB，保存索引结构与元数据（哪个索引覆盖哪些 node）
- vector_store.py : ChromaDB，保存向量 + ANN 索引（只负责"找得快"）
- cache.py        : Redis，缓存（embedding / 检索结果 / 语义缓存）

为什么这么拆（大规模场景核心思想）：
  真相源(文档)可重建向量索引；向量库只管检索；缓存管性能。
  三者任一故障/替换，其余不受影响。
"""
