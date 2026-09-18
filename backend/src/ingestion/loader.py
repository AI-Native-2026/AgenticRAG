"""文档加载器（对应学习手册 02 篇）。

约定：data/sample_docs/{tenant}/{文件} 
  - 子文件夹名 = 租户（多租户隔离的入门教学）
  - 支持 .md / .txt / .pdf 等（用 llama-index SimpleDirectoryReader）
返回统一结构：
  {
    "ref_doc_id": 文档唯一 id（文件名 hash，稳定不变）
    "doc_name"   : 文件名
    "tenant"     : 租户
    "doc_type"   : 文件扩展名
    "text"       : 全文
    "source_path": 源路径（供追溯）
  }
"""

import hashlib
from pathlib import Path
from typing import Dict, List

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


def ref_doc_id_of(path: Path) -> str:
    """文档唯一 id：用绝对路径的 hash，保证同一文件无论读多少次 id 稳定。"""
    return "doc-" + hashlib.md5(str(path).encode("utf-8")).hexdigest()[:16]


class DocumentLoader:
    """从目录批量加载文档。"""

    def __init__(self, data_dir: str | None = None):
        env = get_env()
        self.data_dir = Path(data_dir or (env["PROJECT_ROOT"] + "/data/sample_docs"))

    def load(self) -> List[Dict[str, str]]:
        """扫描 data/sample_docs/{tenant}/ 下所有受支持的文件并解析。"""
        docs: List[Dict[str, str]] = []
        files = sorted(self.data_dir.rglob("*"))  # 递归找文件
        for f in files:
            if not f.is_file():
                continue
            # 父文件夹名即租户
            tenant = f.parent.name
            ext = f.suffix.lstrip(".").lower()

            if ext in ("md", "txt", "text"):
                text = f.read_text(encoding="utf-8")
            elif ext in ("pdf", "docx", "pptx"):
                text = self._load_binary(f)
            else:
                continue  # 忽略不支持的类型

            if not text.strip():
                continue
            docs.append({
                "ref_doc_id": ref_doc_id_of(f),
                "doc_name": f.name,
                "tenant": tenant,
                "doc_type": ext,
                "text": text,
                "source_path": str(f),
            })
        return docs

    def _load_binary(self, path: Path) -> str:
        """用 llama-index 的 SimpleDirectoryReader 解析二进制文档。"""
        from llama_index.core import SimpleDirectoryReader

        reader = SimpleDirectoryReader(input_files=[str(path)])
        return "\n".join(doc.text for doc in reader.load_data())


if __name__ == "__main__":
    loader = DocumentLoader()
    loaded = loader.load()
    print(f"共加载 {len(loaded)} 篇文档")
    for d in loaded[:5]:
        print(f"- [{d['tenant']}] {d['doc_name']} ({len(d['text'])}字)")
