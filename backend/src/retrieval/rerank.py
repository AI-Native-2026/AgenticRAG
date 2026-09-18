"""重排器（对应学习手册 04 篇）。

重排解决的问题：混合召回 top-50 里可能只有 3 条真正相关，直接全塞给 LLM
既浪费 token 又稀释答案质量。于是引入"精排"阶段，把最相关的 top-5 挑出来。

两种后端（可切换，教学对照）：
1. cross_encoder —— 本地 bge-reranker-base。交叉编码器把 query 与每段文本拼接
   一起打分，比向量内积(双塔)精度高得多。离线免费，是生产首选。
2. llm          —— 用 DeepSeek 给候选打分。零下载、可解释，但每次查询多 1 次
   API 调用（成本 + 延迟），适合量小或需要解释的场合。
"""

import logging
import time
from typing import Any, Dict, List

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env
from src.llm.gateway import ModelExecutor

logger = logging.getLogger(__name__)


class Reranker:
    """统一重排接口。backend = "cross_encoder" | "vl" | "llm" | "auto"。

    - cross_encoder：本地 bge-reranker-base（默认，快）
    - vl           ：多模态 Qwen3-VL-Reranker（统一重排文本/图片/表格内容）
    - llm          ：DeepSeek 打分（对照）
    - auto         ：优先 vl，加载失败回退 cross_encoder，再回退 llm
    """

    def __init__(self, backend: str = "cross_encoder"):
        self.env = get_env()
        self._ce = None
        self.backend = self._resolve_backend(backend)
        if self.backend in ("cross_encoder", "vl"):
            self._load_ce()
        elif self.backend == "llm":
            from src.llm.gateway import LLMGateway
            self.llm = LLMGateway().build_llm()

    def _resolve_backend(self, backend: str) -> str:
        if backend == "auto":
            for b in ("vl", "cross_encoder"):
                try:
                    if b == "vl":
                        self._try_load_vl()
                    else:
                        self._try_load_ce(self.env["RERANKER_PATH"])
                    logger.info("auto 选择重排后端：%s", b)
                    self.backend = b
                    return b
                except Exception as e:  # noqa: BLE001
                    logger.warning("重排后端 %s 加载失败，尝试下一个：%s", b, e)
            logger.warning("多模态/交叉重排均不可用，回退 llm")
            return "llm"
        return backend

    def _try_load_ce(self, path: str):
        from sentence_transformers import CrossEncoder
        logger.info("加载本地重排模型 %s ...", path)
        self._ce = CrossEncoder(path, device=self.env["DEVICE"])

    def _try_load_vl(self):
        from sentence_transformers import CrossEncoder
        path = self.env["VL_RERANKER_PATH"]
        logger.info("加载多模态重排模型 %s ...", path)
        try:
            self._ce = CrossEncoder(path, device=self.env["DEVICE"], trust_remote_code=True)
        except TypeError:
            self._ce = CrossEncoder(path, device=self.env["DEVICE"])

    def _load_ce(self):
        if self.backend == "vl":
            self._try_load_vl()
        else:
            self._try_load_ce(self.env["RERANKER_PATH"])

    def rerank(self, query: str, candidates: List[Dict], top_n: int = 5) -> List[Dict]:
        """对混合召回结果精排，返回 top_n 条（带新 score）。"""
        if self.backend in ("cross_encoder", "vl"):
            return self._rerank_cross_encoder(query, candidates, top_n)
        return self._rerank_llm(query, candidates, top_n)

    # ---------- 后端 1/2：CrossEncoder（文本 / 多模态） ----------

    def _pairs(self, query: str, candidates: List[Dict]):
        """构造 (query, doc) 对；vl 后端且开启时，图片类 chunk 传真实图片。"""
        import os

        use_media = self.backend == "vl" and str(self.env.get("VL_RERANK_MEDIA", "false")).lower() == "true"
        pairs = []
        for c in candidates:
            media = (c.get("metadata") or {}).get("media_path")
            if use_media and media and os.path.exists(media):
                try:
                    from PIL import Image
                    pairs.append((query, Image.open(media).convert("RGB")))
                    continue
                except Exception:  # noqa: BLE001
                    pass
            pairs.append((query, c["text"]))
        return pairs

    def _rerank_cross_encoder(self, query: str, candidates: List[Dict], top_n: int) -> List[Dict]:
        if not candidates:
            return []
        scores = ModelExecutor.rerank(self._ce, self._pairs(query, candidates))  # GPU 单写者锁保护
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)[:top_n]
        return [{**c, "rerank_score": float(s), "rerank_backend": self.backend} for c, s in ranked]

    # ---------- 后端 2：LLM 重排（教学对照） ----------

    def _rerank_llm(self, query: str, candidates: List[Dict], top_n: int) -> List[Dict]:
        # 组装成打分题，让 LLM 输出 JSON：{"<idx>": 分数}
        items = "\n".join(f"[{i}] {c['text'][:120]}..." for i, c in enumerate(candidates))
        prompt = (
            f"你是检索重排助手。根据与用户问题“{query}”的相关性，给下面每条候选打分(0-10分)。\n"
            f"只输出 JSON，格式: {{\"0\": 8, \"1\": 3, ...}}。\n{items}"
        )
        resp = self.llm.complete(prompt)
        text = str(resp)
        # 简易解析：把冒号后的数字抠出来
        import json
        import re

        match = re.search(r"\{.*\}", text, re.DOTALL)
        scores = {}
        if match:
            try:
                scores = {str(k): float(v) for k, v in json.loads(match.group()).items()}
            except Exception:  # noqa: BLE001 —— 解析失败退化为 0 分
                pass
        ranked = sorted(
            [(c, scores.get(str(i), 0.0)) for i, c in enumerate(candidates)],
            key=lambda x: x[1],
            reverse=True,
        )[:top_n]
        return [{**c, "rerank_score": s, "rerank_backend": "llm"} for c, s in ranked]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rr = Reranker(backend="cross_encoder")
    cands = [
        {"node_id": "n1", "text": "苹果公司发布了新款 iPhone，主打拍照。"},
        {"node_id": "n2", "text": "特斯拉新款电动车续航大幅提升。"},
        {"node_id": "n3", "text": "某地举行美食节活动，人山人海。"},
    ]
    print(rr.rerank("苹果发布了什么新手机", cands, top_n=2))
