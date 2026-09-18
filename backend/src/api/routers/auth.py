"""认证路由。"""

from fastapi import APIRouter, Request

from src.api.auth import authenticate, create_token
from src.api.deps import AppError, get_bearer
from src.api.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    user = authenticate(body.username, body.password)
    if not user:
        raise AppError(401, "UNAUTHORIZED", "用户名或密码错误")
    token = create_token(user["username"], user["tenant"], user["role"])
    return LoginResponse(access_token=token, user=user)


@router.get("/me")
def me(request: Request):
    return get_bearer(request)
