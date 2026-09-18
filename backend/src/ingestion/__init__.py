"""离线索引流水线（对应学习手册 02/03 篇）。

loader.py   : 从磁盘读取原始文档（支持多种文件类型）
chunker.py  : 把长文档切分成检索单元 Chunk（node）
dedup.py    : 基于 hash 的去重 + 变更检测 + 版本号（增量更新）
pipeline.py : 把上面串起来：读 → 切 → 去重 → embedding → 写库
"""
