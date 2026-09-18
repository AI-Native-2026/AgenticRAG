"""连接器框架（数据接入层的统一抽象）。

设计目标：屏蔽「文件 / 数据库 / Web」三类数据源的差异，向上层暴露一致的
发现(discover) → 描述(describe) → 读取(read) → 实时查询(live_query) 接口。

统一产物 RawDocument 会被 ingestion 流水线进一步切分、向量化。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple


@dataclass
class ResourceMeta:
    """一个可接入的资源（文件 / 表 / 集合 / 页面）。"""
    name: str
    kind: str                       # file | table | collection | page
    rows: int = 0
    columns: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RawDocument:
    """连接器产出的原始文档（未切分）。"""
    ref: str                        # 稳定标识：文件路径 / table:pk / url
    text: str
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaInfo:
    """资源的表结构描述（用于 Text-to-SQL / 前端展示）。"""
    name: str
    columns: List[Dict[str, Any]] = field(default_factory=list)
    ddl: str = ""
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    description: str = ""


class ConnectorError(Exception):
    """连接器统一异常。"""


class BaseConnector(abc.ABC):
    """所有连接器的基类。"""

    type: str = "base"              # file | database | web
    subtype: str = "base"           # directory | mysql | mongodb | url ...
    capabilities: Tuple[str, ...] = ("discover", "read")

    def __init__(self, datasource: Dict[str, Any], credentials: Optional[Dict[str, str]] = None):
        self.datasource = datasource
        self.ds_id = datasource.get("ds_id") or datasource.get("_id")
        self.name = datasource.get("name", "")
        self.tenant = datasource.get("tenant", "default")
        self.config: Dict[str, Any] = datasource.get("config") or {}
        self.credentials: Dict[str, str] = credentials or {}

    # ---------- 能力探测 ----------

    def supports(self, cap: str) -> bool:
        return cap in self.capabilities

    # ---------- 生命周期 ----------

    @abc.abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """返回 (是否连通, 描述信息)。"""

    @abc.abstractmethod
    def discover(self) -> List[ResourceMeta]:
        """列出可接入资源。"""

    @abc.abstractmethod
    def read(self, resource: Optional[str] = None, watermark: Any = None,
             limit: Optional[int] = None) -> Iterator[RawDocument]:
        """读取资源内容；watermark 用于增量。"""

    def describe(self, resource: str) -> SchemaInfo:
        """描述资源结构（默认不支持）。"""
        raise ConnectorError(f"{self.subtype} 连接器不支持 describe")

    def preview(self, resource: Optional[str] = None, limit: int = 10,
                max_chars: int = 2000) -> List[RawDocument]:
        """轻量预览：只取前 limit 条并截断文本，避免大文件占用资源。

        连接器可覆盖以做更省的读取（如文件只读头部）。
        """
        out: List[RawDocument] = []
        for i, doc in enumerate(self.read(resource=resource, limit=limit)):
            truncated = len(doc.text) > max_chars
            out.append(RawDocument(ref=doc.ref, text=doc.text[:max_chars], title=doc.title,
                                   metadata={**doc.metadata, "truncated": truncated}))
            if i + 1 >= limit:
                break
        return out

    def live_query(self, question: str, **kwargs) -> Dict[str, Any]:
        """实时查询（默认不支持）。"""
        raise ConnectorError(f"{self.subtype} 连接器不支持实时查询")

    def close(self) -> None:
        """释放资源。"""


# ---------- 注册中心 ----------

_REGISTRY: Dict[str, type] = {}


def register(subtype: str):
    def deco(cls: type) -> type:
        _REGISTRY[subtype] = cls
        return cls
    return deco


def get_connector_class(subtype: str) -> type:
    if subtype not in _REGISTRY:
        raise ConnectorError(f"未知连接器类型：{subtype}（已注册：{sorted(_REGISTRY)}）")
    return _REGISTRY[subtype]


def list_connectors() -> Dict[str, Dict[str, Any]]:
    return {
        k: {"type": c.type, "subtype": c.subtype, "capabilities": list(c.capabilities)}
        for k, c in sorted(_REGISTRY.items())
    }


def create_connector(datasource: Dict[str, Any], credentials: Optional[Dict[str, str]] = None) -> BaseConnector:
    """按数据源的 subtype 实例化连接器。"""
    cls = get_connector_class(datasource.get("subtype", ""))
    return cls(datasource, credentials)
