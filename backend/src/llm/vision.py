"""视觉语言模型（VLM）惰性加载。

仅在使用图片描述（IMAGE_VLM_ENABLED=true）时才加载，避免常驻显存。
优先 transformers 的多模态基类，失败回退 Qwen2.5-VL 专用类。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Tuple

_cache: Dict[str, Tuple[Any, Any]] = {}
_lock = threading.Lock()


def get_vlm(model_path: str) -> Tuple[Any, Any]:
    """返回 (model, processor)，进程内缓存。"""
    if model_path in _cache:
        return _cache[model_path]
    with _lock:
        if model_path not in _cache:
            import torch

            model = None
            try:
                from transformers import AutoModelForImageTextToText, AutoProcessor

                model = AutoModelForImageTextToText.from_pretrained(
                    model_path, torch_dtype=torch.bfloat16, device_map="auto")
                processor = AutoProcessor.from_pretrained(model_path)
            except Exception:  # noqa: BLE001
                from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

                model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    model_path, torch_dtype=torch.bfloat16, device_map="auto")
                processor = AutoProcessor.from_pretrained(model_path)
            _cache[model_path] = (model, processor)
    return _cache[model_path]
