"""凭证加密。

优先使用 cryptography.Fernet（AES-128-CBC + HMAC）；未安装时退化为
基于 SECRET_KEY 的 HMAC-XOR 流密码（仅用于本地开发，强度有限）。

设计：加密结果统一为 "enc:v1:<token>" 字符串，便于识别与迁移。
"""

import base64
import hashlib
import hmac
import os
from typing import Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env

_PREFIX = "enc:v1:"


def _secret() -> bytes:
    return get_env()["SECRET_KEY"].encode("utf-8")


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except Exception:  # noqa: BLE001
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(_secret()).digest())
    return Fernet(key)


def _xor_stream(data: bytes, nonce: bytes) -> bytes:
    """HMAC-SHA256 计数器模式派生密钥流，做 XOR。"""
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hmac.new(_secret(), nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out))


def encrypt(plain: str) -> str:
    if plain is None:
        return ""
    if plain.startswith(_PREFIX):
        return plain
    f = _fernet()
    if f is not None:
        return _PREFIX + "f:" + f.encrypt(plain.encode("utf-8")).decode("ascii")
    nonce = os.urandom(8)
    ct = _xor_stream(plain.encode("utf-8"), nonce)
    return _PREFIX + "x:" + base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: Optional[str]) -> str:
    if not token:
        return ""
    if not token.startswith(_PREFIX):
        return token
    body = token[len(_PREFIX):]
    kind, _, payload = body.partition(":")
    if kind == "f":
        f = _fernet()
        if f is None:
            raise RuntimeError("需要 cryptography 库才能解密 Fernet 凭证")
        return f.decrypt(payload.encode("ascii")).decode("utf-8")
    raw = base64.b64decode(payload)
    nonce, ct = raw[:8], raw[8:]
    return _xor_stream(ct, nonce).decode("utf-8")


def mask(value: Optional[str]) -> str:
    """用于日志/响应脱敏。"""
    if not value:
        return ""
    s = str(value)
    if len(s) <= 2:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 2) + s[-1]


if __name__ == "__main__":
    for v in ["hello", "p@ssw0rd!中文", ""]:
        e = encrypt(v)
        assert decrypt(e) == v, (v, e, decrypt(e))
        print(f"{mask(v)!r:14} -> {e[:40]}... -> {decrypt(e)!r}")
