"""文件连接器：多格式目录 / 单文件接入。

支持格式：md / txt / text / html / htm / csv / tsv / xlsx / xls / json /
         pdf / docx / pptx

- 目录模式：递归发现文件，逐文件解析
- 单文件模式：直接解析
- 结构化（csv/xlsx/json）：按行/记录产出 RawDocument，保留列元数据
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.connectors.base import BaseConnector, RawDocument, ResourceMeta, register

SUPPORTED_TEXT = {".md", ".markdown", ".txt", ".text", ".log", ".yaml", ".yml"}
SUPPORTED_HTML = {".html", ".htm"}
SUPPORTED_TABULAR = {".csv", ".tsv"}
SUPPORTED_EXCEL = {".xlsx", ".xls"}
SUPPORTED_JSON = {".json", ".jsonl", ".ndjson"}
SUPPORTED_DOC = {".pdf", ".docx", ".pptx"}
SUPPORTED = SUPPORTED_TEXT | SUPPORTED_HTML | SUPPORTED_TABULAR | SUPPORTED_EXCEL | SUPPORTED_JSON | SUPPORTED_DOC


class _TextExtractor(HTMLParser):
    """极简 HTML 正文抽取（不依赖第三方库）。"""

    def __init__(self):
        super().__init__()
        self._parts: List[str] = []
        self._skip = 0
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if getattr(self, "_in_title", False):
            self.title += data.strip()
        if not self._skip:
            t = data.strip()
            if t:
                self._parts.append(t)

    def text(self) -> str:
        return "\n".join(self._parts)


@register("file")
@register("directory")
class FileConnector(BaseConnector):
    type = "file"
    subtype = "file"
    capabilities = ("discover", "read", "describe")

    # ---------- 基础 ----------

    def _root(self) -> Path:
        raw = self.config.get("path") or self.config.get("uri") or ""
        return Path(raw).expanduser()

    def _iter_files(self) -> List[Path]:
        root = self._root()
        if root.is_file():
            return [root]
        if not root.exists():
            return []
        files: List[Path] = []
        for dirpath, _dirs, names in os.walk(root):
            for n in sorted(names):
                p = Path(dirpath) / n
                if p.suffix.lower() in SUPPORTED:
                    files.append(p)
        return files

    def test_connection(self) -> Tuple[bool, str]:
        root = self._root()
        if root.exists():
            kind = "文件" if root.is_file() else "目录"
            return True, f"{kind}存在：{root}"
        return False, f"路径不存在：{root}"

    def discover(self) -> List[ResourceMeta]:
        out: List[ResourceMeta] = []
        for p in self._iter_files():
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            out.append(ResourceMeta(name=str(p), kind="file", rows=size,
                                    extra={"suffix": p.suffix.lower(), "size": size,
                                           "name": p.name}))
        return out

    def preview(self, resource: Optional[str] = None, limit: int = 10,
                max_chars: int = 2000) -> List[RawDocument]:
        """预览只读文件头部，避免大文件整体加载。"""
        targets = [Path(resource)] if resource else self._iter_files()
        out: List[RawDocument] = []
        for p in targets:
            if not p.exists() or not p.is_file():
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            text = self._head(p, max_chars)
            out.append(RawDocument(
                ref=str(p), text=text, title=p.name,
                metadata={**self._base_meta(p), "size": size,
                          "truncated": size > max_chars},
            ))
            if len(out) >= limit:
                break
        return out

    def _head(self, p: Path, max_chars: int) -> str:
        """只读文件头部内容（文本类按字符，表格类按行，二进制文档回退）。"""
        suffix = p.suffix.lower()
        if suffix in SUPPORTED_TEXT or suffix in SUPPORTED_HTML:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                return f.read(max_chars)
        if suffix in SUPPORTED_TABULAR:
            lines: List[str] = []
            with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f, delimiter="\t" if suffix == ".tsv" else ",")
                for i, row in enumerate(reader):
                    if i >= 20:
                        break
                    lines.append(", ".join(row))
            return "\n".join(lines)[:max_chars]
        if suffix in SUPPORTED_DOC:
            try:
                return next(iter(self._read_document(p, self._base_meta(p)))).text[:max_chars]
            except Exception:  # noqa: BLE001
                return "(无法预览该文件)"
        return ""

    def describe(self, resource: str) -> Any:
        from src.connectors.base import SchemaInfo
        p = Path(resource)
        cols: List[Dict[str, Any]] = []
        rows: List[Dict[str, Any]] = []
        if p.suffix.lower() in SUPPORTED_TABULAR:
            with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f, delimiter="\t" if p.suffix.lower() == ".tsv" else ",")
                header = next(reader, [])
                cols = [{"name": h, "type": "string"} for h in header]
                for i, row in enumerate(reader):
                    if i >= 5:
                        break
                    rows.append({header[j] if j < len(header) else f"col{j}": v
                                 for j, v in enumerate(row)})
        return SchemaInfo(name=str(p), columns=cols, sample_rows=rows)

    # ---------- 读取 ----------

    def read(self, resource: Optional[str] = None, watermark: Any = None,
             limit: Optional[int] = None) -> Iterator[RawDocument]:
        targets = [Path(resource)] if resource else self._iter_files()
        count = 0
        for p in targets:
            if not p.exists():
                continue
            for doc in self._read_file(p):
                yield doc
                count += 1
                if limit and count >= limit:
                    return

    def _base_meta(self, p: Path) -> Dict[str, Any]:
        rel = str(p)
        try:
            root = self._root()
            if root.is_dir():
                rel = str(p.relative_to(root))
        except Exception:  # noqa: BLE001
            pass
        return {
            "source_type": "file",
            "datasource_id": self.ds_id,
            "doc_name": p.name,
            "doc_type": p.suffix.lstrip(".").lower(),
            "path": str(p),
            "rel_path": rel,
        }

    def _read_file(self, p: Path) -> Iterator[RawDocument]:
        suffix = p.suffix.lower()
        meta = self._base_meta(p)
        if suffix in SUPPORTED_TEXT:
            text = p.read_text(encoding="utf-8", errors="replace")
            yield RawDocument(ref=str(p), text=text, title=p.stem, metadata={**meta, "page": 1})
        elif suffix in SUPPORTED_HTML:
            raw = p.read_text(encoding="utf-8", errors="replace")
            ex = _TextExtractor()
            ex.feed(raw)
            yield RawDocument(ref=str(p), text=ex.text(), title=ex.title or p.stem,
                              metadata={**meta, "page": 1})
        elif suffix in SUPPORTED_TABULAR:
            yield from self._read_csv(p, meta)
        elif suffix in SUPPORTED_EXCEL:
            yield from self._read_excel(p, meta)
        elif suffix in SUPPORTED_JSON:
            yield from self._read_json(p, meta)
        elif suffix in SUPPORTED_DOC:
            yield from self._read_document(p, meta)
        else:
            yield RawDocument(ref=str(p), text=p.read_text(encoding="utf-8", errors="replace"),
                              title=p.stem, metadata={**meta, "page": 1})

    def _read_csv(self, p: Path, meta: Dict[str, Any]) -> Iterator[RawDocument]:
        delim = "\t" if p.suffix.lower() == ".tsv" else ","
        with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for i, row in enumerate(reader):
                yield self._row_doc(p, meta, i, row, sheet=None)

    def _read_excel(self, p: Path, meta: Dict[str, Any]) -> Iterator[RawDocument]:
        try:
            import openpyxl
        except ImportError as e:  # noqa: BLE001
            raise RuntimeError("解析 Excel 需要 openpyxl：pip install openpyxl") from e
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        idx = 0
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = [str(h) if h is not None else f"col{j}" for j, h in enumerate(next(rows, []))]
            for row in rows:
                rec = {header[j] if j < len(header) else f"col{j}": ("" if v is None else v)
                       for j, v in enumerate(row)}
                yield self._row_doc(p, meta, idx, rec, sheet=ws.title)
                idx += 1
        wb.close()

    def _read_json(self, p: Path, meta: Dict[str, Any]) -> Iterator[RawDocument]:
        text = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() in (".jsonl", ".ndjson"):
            for i, line in enumerate(text.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    rec = {"text": line}
                yield self._json_doc(p, meta, i, rec)
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            yield RawDocument(ref=str(p), text=text, title=p.stem, metadata={**meta, "page": 1})
            return
        if isinstance(data, list):
            for i, rec in enumerate(data):
                yield self._json_doc(p, meta, i, rec)
        elif isinstance(data, dict):
            yield self._json_doc(p, meta, 0, data)
        else:
            yield RawDocument(ref=str(p), text=str(data), title=p.stem, metadata={**meta, "page": 1})

    def _read_document(self, p: Path, meta: Dict[str, Any]) -> Iterator[RawDocument]:
        """PDF / DOCX / PPTX：交给 llama-index readers。"""
        try:
            from llama_index.core import SimpleDirectoryReader
        except ImportError as e:  # noqa: BLE001
            raise RuntimeError("解析 PDF/DOCX/PPTX 需要 llama-index-readers-file") from e
        reader = SimpleDirectoryReader(input_files=[str(p)])
        docs = reader.load_data()
        for i, d in enumerate(docs):
            page = d.metadata.get("page_label") or d.metadata.get("page") or i + 1
            yield RawDocument(ref=f"{p}#{i}", text=d.text, title=p.stem,
                              metadata={**meta, "page": page, "part": i})

    def _row_doc(self, p: Path, meta: Dict[str, Any], idx: int, rec: Dict[str, Any],
                 sheet: Optional[str]) -> RawDocument:
        text = "\n".join(f"{k}: {v}" for k, v in rec.items() if str(v).strip() != "")
        md = {**meta, "row_id": idx, "page": 1}
        if sheet:
            md["sheet"] = sheet
        return RawDocument(ref=f"{p}#{sheet or ''}#{idx}", text=text, title=f"{p.stem} #{idx}",
                           metadata=md)

    def _json_doc(self, p: Path, meta: Dict[str, Any], idx: int, rec: Any) -> RawDocument:
        if isinstance(rec, dict):
            text = "\n".join(f"{k}: {v}" for k, v in rec.items())
        else:
            text = str(rec)
        return RawDocument(ref=f"{p}#{idx}", text=text, title=f"{p.stem} #{idx}",
                           metadata={**meta, "row_id": idx, "page": 1})


def file_ref_doc_id(path: str) -> str:
    return "doc-" + hashlib.md5(path.encode("utf-8")).hexdigest()[:16]
