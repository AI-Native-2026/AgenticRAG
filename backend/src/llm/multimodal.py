"""统一 Embedder：文本 / 多模态。

- EMBED_BACKEND=text（默认）：bge-small-zh 文本向量；图片走 OCR 文本
- EMBED_BACKEND=vl          ：Qwen3-VL-Embedding，文本与图片映射到同一向量空间，
                              支持"以文搜图 / 以图搜图"

对外统一接口 embed_items(items)，items 为 [{text, modality, media_path}]，
按顺序返回向量。向量维度由后端决定。
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env

logger = logging.getLogger(__name__)

_lock = threading.RLock()


class BaseEmbedder:
    name: str = "base"
    supports_image: bool = False
    dim: int = 0

    def embed_items(self, items: List[Dict[str, Any]]) -> List[List[float]]:
        raise NotImplementedError


class TextEmbedder(BaseEmbedder):
    """文本向量（LlamaIndex HuggingFaceEmbedding）。"""

    name = "text"

    def __init__(self, model, dim: int):
        self.model = model
        self.dim = dim
        self.supports_image = False

    def embed_items(self, items: List[Dict[str, Any]]) -> List[List[float]]:
        texts = [it.get("text") or "" for it in items]
        if not texts:
            return []
        with _lock:
            return self.model.get_text_embedding_batch(texts)


class VLEmbedder(BaseEmbedder):
    """多模态向量（Qwen3-VL-Embedding，SentenceTransformers 接口）。"""

    name = "vl"
    supports_image = True

    def __init__(self, path: str, device: str = "cpu"):
        from sentence_transformers import SentenceTransformer

        logger.info("加载多模态 Embedding 模型 %s ...", path)
        try:
            self.model = SentenceTransformer(path, device=device, trust_remote_code=True)
        except TypeError:
            self.model = SentenceTransformer(path, device=device)
        try:
            self.dim = int(self.model.get_sentence_embedding_dimension())
        except Exception:  # noqa: BLE001
            self.dim = 0
        logger.info("多模态 Embedding 就绪，维度=%s", self.dim)

    def _to_input(self, it: Dict[str, Any]):
        media = it.get("media_path")
        if it.get("modality") == "image" and media and os.path.exists(media):
            try:
                from PIL import Image
                return Image.open(media).convert("RGB")
            except Exception as e:  # noqa: BLE001
                logger.warning("读取图片失败 %s: %s", media, e)
        return it.get("text") or ""

    def embed_items(self, items: List[Dict[str, Any]]) -> List[List[float]]:
        if not items:
            return []
        inputs = [self._to_input(it) for it in items]
        with _lock:
            vecs = self.model.encode(inputs, normalize_embeddings=True, batch_size=16)
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vecs]

    def embed_image(self, path: str) -> List[float]:
        return self.embed_items([{"modality": "image", "media_path": path}])[0]


_embedder: Optional[BaseEmbedder] = None


def get_embedder() -> BaseEmbedder:
    """进程级单例 Embedder。"""
    global _embedder
    if _embedder is not None:
        return _embedder
    env = get_env()
    if env.get("EMBED_BACKEND") == "vl":
        _embedder = VLEmbedder(env["VL_EMBEDDING_PATH"], env["DEVICE"])
    else:
        from src.llm.gateway import build_embed_model

        _embedder = TextEmbedder(build_embed_model(), int(env["EMBED_DIM"]))
    return _embedder


def image_cache_key(path: str) -> str:
    try:
        st = os.stat(path)
        return "img:" + hashlib.md5(f"{path}:{st.st_mtime}:{st.st_size}".encode()).hexdigest()
    except OSError:
        return "img:" + hashlib.md5(path.encode()).hexdigest()
