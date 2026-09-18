"""API 依赖与错误类型。"""

from typing import Any, Dict

from fastapi import Request

from src.api.auth import get_current_user


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def get_bearer(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AppError(401, "UNAUTHORIZED", "缺少 Authorization: Bearer <token>")
    try:
        return get_current_user(auth.removeprefix("Bearer ").strip())
    except Exception:  # noqa: BLE001
        raise AppError(401, "UNAUTHORIZED", "token 无效或已过期")


def require_admin(user: Dict[str, Any]) -> None:
    if user.get("role") != "admin":
        raise AppError(403, "FORBIDDEN", "需要管理员权限")
