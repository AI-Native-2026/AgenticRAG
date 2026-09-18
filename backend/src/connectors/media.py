"""多媒体 / 富文档抽取。

统一把「图片 / PDF / Office 文档」转成可索引文本，并标注 modality：
  image    —— OCR（tesseract）+ 可选 VLM 描述
  document —— PDF 按页抽取正文与表格；docx/pptx 用 unstructured 抽取
  table    —— 表格转 Markdown（保留行列结构）

设计为可插拔、可降级：任何能力缺失时退回上一种策略，绝不让入库失败。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}


# ---------- 图片 ----------

def ocr_image(path: Path, lang: str = "chi_sim+eng") -> str:
    """调用 tesseract 命令行 OCR（无需 pytesseract）。"""
    try:
        res = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", lang],
            capture_output=True, text=True, timeout=90,
        )
        text = (res.stdout or "").strip()
        if text:
            return text
        if res.returncode != 0:
            # 语言包缺失时退化为英文
            res = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng"],
                                 capture_output=True, text=True, timeout=90)
            return (res.stdout or "").strip()
    except FileNotFoundError:
        logger.warning("未安装 tesseract，跳过 OCR")
    except Exception as e:  # noqa: BLE001
        logger.warning("OCR 失败 %s: %s", path, e)
    return ""


def image_meta(path: Path) -> Dict[str, Any]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return {"width": im.width, "height": im.height, "mode": im.mode}
    except Exception:  # noqa: BLE001
        return {}


def describe_image_vlm(path: Path, model_path: str) -> str:
    """可选：用 Qwen2.5-VL 生成图片描述（较慢，默认关闭）。"""
    try:
        from src.llm.vision import caption_image
        return caption_image(str(path))
    except Exception as e:  # noqa: BLE001
        logger.warning("VLM 描述失败: %s", e)
        return ""


def extract_image(path: Path, config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    meta = image_meta(path)
    parts: List[str] = []
    if config.get("ocr", True):
        txt = ocr_image(path, config.get("tesseract_lang", "chi_sim+eng"))
        if txt:
            parts.append("【OCR 文本】\n" + txt)
    vlm_path = config.get("vlm_model_path")
    if config.get("vlm", False) and vlm_path:
        desc = describe_image_vlm(path, vlm_path)
        if desc:
            parts.append("【图片描述】\n" + desc)
    if not parts:
        parts.append(f"图片文件 {path.name}（{meta.get('width', '?')}x{meta.get('height', '?')}）")
    return "\n\n".join(parts), {**meta, "modality": "image", "media_path": str(path)}


# ---------- 表格 ----------

def table_to_markdown(rows: List[List[Any]]) -> str:
    if not rows:
        return ""
    header = [str(c) if c is not None else "" for c in rows[0]]
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(["---"] * len(header)) + " |"]
    for r in rows[1:]:
        cells = [str(c) if c is not None else "" for c in r]
        cells += [""] * (len(header) - len(cells))
        lines.append("| " + " | ".join(cells[:len(header)]) + " |")
    return "\n".join(lines)


# ---------- PDF ----------

def extract_pdf(path: Path, config: Dict[str, Any],
                max_pages: Optional[int] = None) -> List[Tuple[int, str, Dict[str, Any]]]:
    """按页返回 (页码, 文本, 元数据)。优先 PyMuPDF，失败回退 llama-index。"""
    pages: List[Tuple[int, str, Dict[str, Any]]] = []
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            text = page.get_text("text").strip()
            tables_md: List[str] = []
            try:
                for t in page.find_tables():
                    md = table_to_markdown(t.extract())
                    if md:
                        tables_md.append(md)
            except Exception:  # noqa: BLE001
                pass
            body = text
            if tables_md:
                body += "\n\n【表格】\n" + "\n\n".join(tables_md)
            if not body.strip() and config.get("pdf_ocr", False):
                try:
                    pix = page.get_pixmap(dpi=150)
                    tmp = path.with_suffix(f".p{i}.png")
                    pix.save(str(tmp))
                    body = ocr_image(tmp, config.get("tesseract_lang", "chi_sim+eng"))
                    tmp.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
            if body.strip():
                pages.append((i + 1, body, {"modality": "document", "page": i + 1,
                                            "has_table": bool(tables_md)}))
        doc.close()
        return pages
    except Exception as e:  # noqa: BLE001
        logger.warning("PyMuPDF 解析失败，回退 llama-index: %s", e)
        from llama_index.core import SimpleDirectoryReader
        docs = SimpleDirectoryReader(input_files=[str(path)]).load_data()
        for i, d in enumerate(docs):
            pages.append((i + 1, d.text, {"modality": "document", "page": i + 1}))
        return pages


# ---------- Office ----------

def _extract_docx(path: Path) -> str:
    """python-docx：段落 + 表格（转 Markdown）。"""
    import docx

    d = docx.Document(str(path))
    blocks: List[str] = []
    for p in d.paragraphs:
        t = (p.text or "").strip()
        if t:
            blocks.append(t)
    for tbl in d.tables:
        rows = [[c.text.strip() for c in row.cells] for row in tbl.rows]
        md = table_to_markdown(rows)
        if md:
            blocks.append("【表格】\n" + md)
    return "\n\n".join(blocks)


def _extract_pptx(path: Path) -> str:
    """python-pptx：逐页文本框 + 表格。"""
    from pptx import Presentation

    prs = Presentation(str(path))
    blocks: List[str] = []
    for i, slide in enumerate(prs.slides):
        parts: List[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [[c.text for c in row.cells] for row in shape.table.rows]
                parts.append("【表格】\n" + table_to_markdown(rows))
        if parts:
            blocks.append(f"## 幻灯片 {i + 1}\n" + "\n".join(parts))
    return "\n\n".join(blocks)


def extract_office(path: Path) -> List[Tuple[int, str, Dict[str, Any]]]:
    """docx/pptx：优先 python-docx / python-pptx（稳定、无重依赖），失败回退。"""
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            text = _extract_docx(path)
        elif suffix == ".pptx":
            text = _extract_pptx(path)
        else:
            text = ""
        if text.strip():
            return [(1, text, {"modality": "document"})]
    except Exception as e:  # noqa: BLE001
        logger.warning("python-docx/pptx 解析失败，回退：%s", e)

    # 回退 1：unstructured（若可用）
    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=str(path))
        blocks = []
        for el in elements:
            txt = str(el).strip()
            if not txt:
                continue
            cat = getattr(el, "category", "")
            blocks.append(("【表格】\n" + txt) if "Table" in cat else txt)
        text = "\n\n".join(blocks)
        if text.strip():
            return [(1, text, {"modality": "document"})]
    except Exception as e:  # noqa: BLE001
        logger.warning("unstructured 解析失败，回退 llama-index：%s", e)

    # 回退 2：llama-index
    from llama_index.core import SimpleDirectoryReader

    docs = SimpleDirectoryReader(input_files=[str(path)]).load_data()
    return [(i + 1, d.text, {"modality": "document", "part": i}) for i, d in enumerate(docs)]
