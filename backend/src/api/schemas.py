"""API 请求/响应模型（Pydantic 自动校验）。"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    session_id: str = Field(default="default", description="会话 id，同 id 共享多轮记忆")
    stream: bool = Field(default=True, description="是否流式返回")
    kb_ids: List[str] = Field(default_factory=list, description="检索范围：选中的知识库 id（空=全部）")
    datasource_ids: List[str] = Field(default_factory=list, description="可选：直接限定数据源")


class ChatResponse(BaseModel):
    answer: str
    request_id: str


class DocSubmit(BaseModel):
    doc_name: str
    doc_type: str = "md"
    text: str


class DocSubmitRequest(BaseModel):
    docs: List[DocSubmit] = Field(..., min_length=1)
    tenant: Optional[str] = Field(default=None, description="仅 admin 可指定，否则以登录租户为准")
    datasource_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None)


class DocSubmitResponse(BaseModel):
    accepted: int
    request_id: str


# ---------- 数据源 ----------

class DatasourceCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., description="file | database | web")
    subtype: str = Field(..., description="directory | mysql | postgresql | mongodb | web ...")
    config: Dict[str, Any] = Field(default_factory=dict)
    credentials: Dict[str, str] = Field(default_factory=dict)
    kb_id: Optional[str] = None


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    credentials: Optional[Dict[str, str]] = None
    kb_id: Optional[str] = None


class SyncRequest(BaseModel):
    mode: str = Field(default="full", description="full | incremental")
    limit: Optional[int] = None
    resources: Optional[List[str]] = None


class TestConnectionRequest(BaseModel):
    subtype: str
    config: Dict[str, Any] = Field(default_factory=dict)
    credentials: Dict[str, str] = Field(default_factory=dict)


# ---------- 知识库 ----------

class KBCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    slug: Optional[str] = None
    datasource_ids: List[str] = Field(default_factory=list)


class KBUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    datasource_ids: Optional[List[str]] = None


# ---------- 检索调试 ----------

class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    kb_id: Optional[str] = None
    datasource_id: Optional[str] = None
    top_k: int = 30
    top_n: int = 5
    rerank: bool = True


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None
