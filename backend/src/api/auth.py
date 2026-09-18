"""JWT 鉴权（对应 v2 手册 05 篇）。

为什么用 JWT：
  无状态 —— 服务端不存会话，token 自带身份信息（user/tenant/role），
  水平扩容友好。代价是"签发后无法主动吊销"，生产会配短过期 + 黑名单。

安全边界（教学版已明确）：
  - JWT_SECRET 来自 .env（v2 未上 Vault，属可接受的简化；生产必须换 secrets 管理）
  - 所有敏感信息只放 payload 白名单字段，不放任何 key
"""

import time
from typing import Any, Dict, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

import jwt

from src.config import get_env


def create_token(username: str, tenant: str, role: str, expires_hours: Optional[int] = None) -> str:
    """签发 JWT。payload 只含身份字段 + 过期时间。"""
    env = get_env()
    expires_hours = expires_hours or int(env["JWT_EXPIRE_HOURS"])
    payload = {
        "sub": username,
        "tenant": tenant,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_hours * 3600,
    }
    return jwt.encode(payload, env["JWT_SECRET"], algorithm="HS256")


def verify_token(token: str) -> Dict[str, Any]:
    """校验 JWT。过期/篡改会抛异常，由调用方转成 401。"""
    env = get_env()
    return jwt.decode(token, env["JWT_SECRET"], algorithms=["HS256"])


def get_current_user(token: str) -> Dict[str, Any]:
    """FastAPI 依赖用：从 Authorization: Bearer 里解析身份。"""
    payload = verify_token(token)
    return {
        "username": payload.get("sub"),
        "tenant": payload.get("tenant"),
        "role": payload.get("role"),
    }


# 演示用固定账号（生产换真实用户系统）
DEMO_USERS = {
    "admin": {"password": "admin123", "tenant": "tech", "role": "admin"},
    "alice": {"password": "alice123", "tenant": "tech", "role": "member"},
    "bob":   {"password": "bob123",   "tenant": "finance", "role": "member"},
}


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """校验用户名密码，返回身份信息；失败返回 None。"""
    user = DEMO_USERS.get(username)
    if user and user["password"] == password:
        return {"username": username, **user}
    return None


if __name__ == "__main__":
    tok = create_token("alice", "tech", "member")
    print("签发 token:", tok[:40] + "...")
    print("解析身份:", get_current_user(tok))
