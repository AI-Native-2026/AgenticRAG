"""脚本 02：执行索引流水线（加载→切分→去重→embedding→写库）。

用法：python scripts/02_ingest.py [--force]
  --force 忽略去重，强制全量重建（教学对照）
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from src.ingestion.pipeline import IngestionPipeline  # noqa: E402
from src.llm.gateway import build_embed_model, setup_settings  # noqa: E402
from src.storage.cache import CacheClient  # noqa: E402
from src.storage.docstore import MongoDocStore  # noqa: E402
from src.storage.index_store import MongoIndexStore  # noqa: E402
from src.storage.vector_store import ChromaVectorStore  # noqa: E402


def main():
    setup_settings()  # 初始化全局 Settings（embed_model 等）
    embed_model = build_embed_model()

    pipe = IngestionPipeline(
        embed_model=embed_model,
        docstore=MongoDocStore(),
        vector_store=ChromaVectorStore(),
        index_store=MongoIndexStore(),
        cache=CacheClient(),
    )
    stats = pipe.run()
    print("\n======== 流水线统计 ========")
    print(f"  扫描文档 : {stats['total']}")
    print(f"  新增     : {stats['insert']}")
    print(f"  更新     : {stats['update']}")
    print(f"  跳过     : {stats['skip']}")
    print(f"  新增chunk: {stats['chunks']}")
    print(f"  docstore节点数: {pipe.docstore.count()}")
    print(f"  向量数        : {pipe.vector_store.count()}")
    print("再次运行本脚本会全部 skip（验证增量/幂等）。")


if __name__ == "__main__":
    main()
