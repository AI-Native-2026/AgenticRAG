"""JWT 鉴权 + 工具注册中心测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.registry import ToolRegistry  # noqa: E402
from src.api.auth import create_token, get_current_user  # noqa: E402


def test_jwt_roundtrip():
    token = create_token("alice", "tech", "member", expires_hours=1)
    user = get_current_user(token)
    assert user["username"] == "alice"
    assert user["tenant"] == "tech"
    assert user["role"] == "member"


def test_tool_permission_gate():
    reg = ToolRegistry()
    reg.register("secret_tool", fn=lambda: 1, roles=["admin"])
    assert reg.can_call("secret_tool", "admin")
    assert not reg.can_call("secret_tool", "member")  # 越权被拒


def test_unknown_tool_denied():
    reg = ToolRegistry()
    assert not reg.can_call("ghost", "admin")
