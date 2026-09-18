"""视觉语言模型（VLM）—— 图片理解 / 视觉问答。

默认使用 Qwen2.5-VL-3B-Instruct，惰性加载并缓存。
设备可通过 VLM_DEVICE 配置：auto（默认，有显存用 GPU，否则 CPU/offload）| cuda | cpu。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env

logger = logging.getLogger(__name__)

_cache: Dict[str, Tuple[Any, Any]] = {}
_lock = threading.Lock()


def get_vlm(model_path: Optional[str] = None, device: Optional[str] = None) -> Tuple[Any, Any]:
    """返回 (model, processor)，进程内缓存。"""
    env = get_env()
    model_path = model_path or env.get("VLM_MODEL_PATH")
    device = device or env.get("VLM_DEVICE", "auto")
    key = f"{model_path}:{device}"
    if key in _cache:
        return _cache[key]
    with _lock:
        if key not in _cache:
            import torch
            from transformers import AutoProcessor

            logger.info("加载视觉模型 %s（device=%s）...", model_path, device)
            dtype = torch.bfloat16
            kwargs: Dict[str, Any] = {"torch_dtype": dtype, "low_cpu_mem_usage": True}
            if device == "cpu":
                kwargs["device_map"] = None
            else:
                kwargs["device_map"] = device  # auto / cuda
            model = None
            try:
                from transformers import AutoModelForImageTextToText

                model = AutoModelForImageTextToText.from_pretrained(model_path, **kwargs)
            except Exception:  # noqa: BLE001
                from transformers import Qwen2_5_VLForConditionalGeneration

                model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model_path, **kwargs)
            if device == "cpu":
                model = model.to("cpu")
            model.eval()
            processor = AutoProcessor.from_pretrained(model_path)
            _cache[key] = (model, processor)
            logger.info("视觉模型就绪")
    return _cache[key]


def answer_image(image_path: str, question: str, system: Optional[str] = None,
                 max_new_tokens: int = 320) -> str:
    """对图片进行视觉问答（VQA）。"""
    import torch

    model, processor = get_vlm()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({
        "role": "user",
        "content": [
            {"type": "image", "image": str(image_path)},
            {"type": "text", "text": question},
        ],
    })
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[str(image_path)], return_tensors="pt")
    try:
        device = next(model.parameters()).device
    except StopIteration:  # noqa: BLE001
        device = "cpu"
    inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens)
    gen = out[:, inputs["input_ids"].shape[1]:]
    return processor.batch_decode(gen, skip_special_tokens=True)[0].strip()


def caption_image(image_path: str) -> str:
    return answer_image(image_path, "请用中文简要描述这张图片的内容，并提取其中的文字。")
