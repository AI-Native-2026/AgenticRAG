"""Agentic RAG 知识中台 —— 统一配置层。

配置来源优先级：进程环境变量 > 项目 .env > 内置默认值。

设计要点：
1. 路径可移植：AutoDL 场景默认落到数据盘 /root/autodl-tmp；
   其它环境（本地/Docker）默认落到项目内 .data/，均可用环境变量覆盖。
2. 所有敏感项（API Key / DB 凭证 / JWT）只从环境或 .env 读取，不硬编码。
3. 数据库连接器默认只读、超时、行数上限，安全护栏可配置。
"""

import os
from pathlib import Path
from typing import Any, Dict, List

# ---------- 路径常量 ----------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# AutoDL 数据盘存在则用之，否则用项目内 .data（本地/Docker）
_AUTODL_DISK = Path("/root/autodl-tmp")
_DEFAULT_DATA_ROOT = _AUTODL_DISK if _AUTODL_DISK.exists() else (PROJECT_ROOT / ".data")


def _env_path(key: str, default: Path) -> Path:
    return Path(os.environ.get(key, str(default)))


# ---------- 极简 .env 解析 ----------

def _load_dotenv(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


_PROJECT_ENV = _load_dotenv(PROJECT_ROOT / ".env")
_LEGACY_ENV = _load_dotenv(Path("/root/autodl-tmp/labs/07/test.env"))


def _get(key: str, default: Any = None) -> Any:
    return os.environ.get(key) or _PROJECT_ENV.get(key) or _LEGACY_ENV.get(key) or default


# ---------- 缓存目录（防默认写系统盘） ----------

HF_HOME = str(_env_path("HF_HOME", _DEFAULT_DATA_ROOT / ".cache/huggingface"))
MODELSCOPE_CACHE = str(_env_path("MODELSCOPE_CACHE", _DEFAULT_DATA_ROOT / ".cache/modelscope"))
os.environ.setdefault("HF_HOME", HF_HOME)
os.environ.setdefault("MODELSCOPE_CACHE", MODELSCOPE_CACHE)


def get_env() -> Dict[str, Any]:
    """读取全部配置为字典。"""
    data_root = _env_path("DATA_ROOT", _DEFAULT_DATA_ROOT)

    config: Dict[str, Any] = {}

    # ---- LLM ----
    config["DEEPSEEK_API_KEY"] = _get("DEEPSEEK_API_KEY")
    config["LLM_BASE_URL"] = _get("LLM_BASE_URL", "https://api.deepseek.com")
    config["LLM_MODEL"] = _get("LLM_MODEL", "deepseek-chat")
    config["LLM_PROVIDER"] = _get("LLM_PROVIDER", "deepseek")
    config["DEEPSEEK_TEMPERATURE"] = float(_get("DEEPSEEK_TEMPERATURE", "0.3"))
    config["DEEPSEEK_MAX_TOKENS"] = int(_get("DEEPSEEK_MAX_TOKENS", "1024"))
    config["TAVILY_API_KEY"] = _get("TAVILY_API_KEY")

    # ---- 路径 ----
    config["PROJECT_ROOT"] = str(PROJECT_ROOT)
    config["DATA_ROOT"] = str(data_root)
    config["DATA_DISK"] = str(_AUTODL_DISK)
    config["BGE_EMBED_PATH"] = str(_env_path("BGE_EMBED_PATH", _AUTODL_DISK / "bge-small-zh-v1.5"))
    config["RERANKER_PATH"] = str(_env_path("RERANKER_PATH", _AUTODL_DISK / "models/bge-reranker-base"))
    config["CHROMA_PATH"] = str(_env_path("CHROMA_PATH", data_root / "chroma"))
    config["SAMPLE_DOCS_DIR"] = str(_env_path("SAMPLE_DOCS_DIR", PROJECT_ROOT / "data/sample_docs"))
    config["UPLOAD_DIR"] = str(_env_path("UPLOAD_DIR", data_root / "uploads"))
    config["LOG_DIR"] = str(_env_path("LOG_DIR", PROJECT_ROOT / "logs"))
    config["HF_HOME"] = HF_HOME
    config["MODELSCOPE_CACHE"] = MODELSCOPE_CACHE

    # ---- 存储 ----
    config["MONGO_URI"] = _get("MONGO_URI", "mongodb://localhost:27017/")
    config["REDIS_URI"] = _get("REDIS_URI", "redis://localhost:6379/0")
    config["MONGO_DB"] = _get("MONGO_DB", "agentic_rag")
    config["SECRET_KEY"] = _get("SECRET_KEY", "dev-secret-change-me")  # 凭证加密

    # ---- 检索 / 索引 ----
    config["EMBED_DIM"] = int(_get("EMBED_DIM", "512"))
    config["EMBED_MODEL_NAME"] = _get("EMBED_MODEL_NAME", "bge-small-zh-v1.5")
    config["CHUNK_SIZE"] = int(_get("CHUNK_SIZE", "256"))
    config["CHUNK_OVERLAP"] = int(_get("CHUNK_OVERLAP", "20"))
    config["TOP_K_RECALL"] = int(_get("TOP_K_RECALL", "30"))
    config["TOP_K_RERANK"] = int(_get("TOP_K_RERANK", "5"))
    config["RERANK_BACKEND"] = _get("RERANK_BACKEND", "cross_encoder")
    config["SEMANTIC_CACHE_THRESHOLD"] = float(_get("SEMANTIC_CACHE_THRESHOLD", "0.92"))
    config["DEVICE"] = "cuda" if (os.path.exists("/usr/local/cuda") or os.path.exists("/dev/nvidia0")) else "cpu"

    # ---- 会话上下文管理 ----
    config["MEMORY_TOKEN_LIMIT"] = int(_get("MEMORY_TOKEN_LIMIT", "10000"))      # 短期记忆 token 预算
    config["MEMORY_RECENT_TURNS"] = int(_get("MEMORY_RECENT_TURNS", "6"))        # 保留最近 N 轮原文
    config["MEMORY_SUMMARY_ENABLED"] = _get("MEMORY_SUMMARY_ENABLED", "true").lower() == "true"

    # ---- 预览性能 ----
    config["PREVIEW_MAX_CHARS"] = int(_get("PREVIEW_MAX_CHARS", "2000"))         # 单条预览最大字符
    config["PREVIEW_PAGE_SIZE"] = int(_get("PREVIEW_PAGE_SIZE", "10"))           # 文件列表每页
    config["DISCOVER_MAX_FILES"] = int(_get("DISCOVER_MAX_FILES", "5000"))       # 目录扫描上限

    # ---- 隐私合规（预览脱敏） ----
    config["PII_MASK_ENABLED"] = _get("PII_MASK_ENABLED", "true").lower() == "true"
    config["PII_MASK_EXTRA"] = [p for p in _get("PII_MASK_EXTRA", "").split("||") if p.strip()]
    config["PII_MASK_COLUMNS"] = [c.strip().lower() for c in _get(
        "PII_MASK_COLUMNS",
        "name,phone,mobile,tel,email,mail,id_card,idcard,id_no,ssn,passport,bank,card,account,address,addr"
    ).split(",") if c.strip()]

    # ---- 多媒体 / 富文档 ----
    config["IMAGE_OCR_ENABLED"] = _get("IMAGE_OCR_ENABLED", "true").lower() == "true"
    config["TESSERACT_LANG"] = _get("TESSERACT_LANG", "chi_sim+eng")
    config["IMAGE_VLM_ENABLED"] = _get("IMAGE_VLM_ENABLED", "false").lower() == "true"
    config["VLM_MODEL_PATH"] = _get("VLM_MODEL_PATH", "/root/autodl-tmp/models/Qwen2.5-VL-3B-Instruct")
    config["PDF_OCR_ENABLED"] = _get("PDF_OCR_ENABLED", "false").lower() == "true"

    # ---- 多模态模型（可选） ----
    config["VL_RERANKER_PATH"] = _get("VL_RERANKER_PATH", "/root/autodl-tmp/models/Qwen3-VL-Reranker-2B")
    config["VL_EMBEDDING_PATH"] = _get("VL_EMBEDDING_PATH", "/root/autodl-tmp/models/Qwen3-VL-Embedding-8B")
    config["VL_RERANK_MEDIA"] = _get("VL_RERANK_MEDIA", "false")

    # ---- 队列 ----
    config["KAFKA_BOOTSTRAP"] = _get("KAFKA_BOOTSTRAP", "localhost:9092")
    config["QUEUE_BACKEND"] = _get("QUEUE_BACKEND", "kafka")  # kafka | dev
    config["TOPIC_DOC_INGEST"] = _get("TOPIC_DOC_INGEST", "doc_ingest")
    config["TOPIC_DOC_DLQ"] = _get("TOPIC_DOC_DLQ", "doc_ingest_dlq")
    config["TOPIC_DS_SYNC"] = _get("TOPIC_DS_SYNC", "ds_sync")
    config["CONSUMER_GROUP"] = _get("CONSUMER_GROUP", "ingest-group")
    config["MAX_RETRY_DOC"] = int(_get("MAX_RETRY_DOC", "3"))

    # ---- API / 安全 ----
    config["JWT_SECRET"] = _get("JWT_SECRET", "dev-secret-change-me")
    config["JWT_ALGORITHM"] = _get("JWT_ALGORITHM", "HS256")
    config["JWT_EXPIRE_HOURS"] = int(_get("JWT_EXPIRE_HOURS", "24"))
    config["API_HOST"] = _get("API_HOST", "0.0.0.0")
    config["API_PORT"] = int(_get("API_PORT", "8000"))
    config["CORS_ORIGINS"] = [
        o.strip() for o in _get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()
    ]
    config["RATE_LIMIT_CAPACITY"] = int(_get("RATE_LIMIT_CAPACITY", "20"))
    config["RATE_LIMIT_RATE"] = float(_get("RATE_LIMIT_RATE", "10"))

    # ---- 数据库连接器安全护栏 ----
    config["DB_QUERY_TIMEOUT"] = int(_get("DB_QUERY_TIMEOUT", "5"))
    config["DB_MAX_ROWS"] = int(_get("DB_MAX_ROWS", "200"))
    config["DB_SYNC_BATCH"] = int(_get("DB_SYNC_BATCH", "500"))
    config["DB_ALLOW_WRITE"] = _get("DB_ALLOW_WRITE", "false").lower() == "true"
    return config


def get_config() -> Dict[str, Any]:
    return get_env()


def get_cors_origins() -> List[str]:
    return get_env()["CORS_ORIGINS"]


def setup_global_env() -> None:
    os.environ.setdefault("HF_HOME", HF_HOME)
    os.environ.setdefault("MODELSCOPE_CACHE", MODELSCOPE_CACHE)
    Path(HF_HOME).mkdir(parents=True, exist_ok=True)
    Path(MODELSCOPE_CACHE).mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    for k, v in get_env().items():
        if "KEY" in k or "TOKEN" in k or "SECRET" in k or "PASSWORD" in k:
            v = "<masked>" if v else v
        print(f"{k} = {v}")
