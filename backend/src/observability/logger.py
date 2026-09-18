"""结构化 JSON 日志。

为什么必须结构化（一行一个 JSON）：
  1. 每行自包含时间/级别/组件/request_id，用 grep / jq 就能按任意字段过滤
  2. 采集系统（ELK/Loki）和告警脚本能直接消费，不用解析人类文本
  3. 天然避免"日志里带敏感信息"——我们在记录前统一脱敏（mask 函数）

用法：
  from src.observability.logger import get_logger
  log = get_logger("api")
  log.info("chat_start", tenant="tech", request_id=rid)
"""

import json
import logging
import sys
import time
from typing import Any, Dict, Optional

# 需要打码的敏感字段（key / token / password / secret）
_SENSITIVE_KEYS = ("api_key", "key", "token", "password", "secret", "authorization")


def mask(value: Any, key: str = "") -> Any:
    """脱敏：敏感字段只保留前 3 位，其余打 *。"""
    if key.lower() in _SENSITIVE_KEYS and isinstance(value, str) and len(value) > 3:
        return value[:3] + "***"
    return value


class JsonLogHandler(logging.Handler):
    """把 logging 记录转成一行 JSON 写往 stdout。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            fields: Dict[str, Any] = {
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if hasattr(record, "extra_fields"):
                for k, v in record.extra_fields.items():
                    fields[k] = mask(v, k)
            # 逐字段脱敏后再序列化，防止密钥进日志
            print(json.dumps(fields, ensure_ascii=False, default=str), flush=True)
        except Exception:  # noqa: BLE001 —— 日志不能成为故障源
            self.handleError(record)


def get_logger(name: str) -> logging.Logger:
    """获取一个输出 JSON 行的 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = JsonLogHandler()
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, level: str, msg: str, **fields: Any) -> None:
    """打一条带任意字段的结构化日志（自动补时间/脱敏）。"""
    fields["ts"] = time.time()
    record = logging.LogRecord(
        name=logger.name,
        level=getattr(logging, level.upper(), logging.INFO),
        pathname="", lineno=0, msg=msg, args=(), exc_info=None,
    )
    record.extra_fields = fields
    logger.handle(record)


if __name__ == "__main__":
    log = get_logger("demo")
    log_event(log, "info", "请求开始", request_id="req-test", tenant="tech")
    log_event(log, "error", "LLM 调用失败", request_id="req-test", api_key="sk-abcdef123456")
    print("（注意上方 api_key 已被脱敏为 sk-***）")
