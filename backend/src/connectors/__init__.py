"""连接器框架。

导入本包即完成所有内置连接器的注册：
  - file / directory          文件与目录（多格式）
  - mysql / postgresql / sqlite / mssql / oracle   关系型数据库
  - mongodb                   MongoDB
  - web / url                 Web 抓取
"""

from src.connectors.base import (  # noqa: F401
    BaseConnector, ConnectorError, RawDocument, ResourceMeta, SchemaInfo,
    create_connector, get_connector_class, list_connectors, register,
)

# 触发注册
from src.connectors import file_connector  # noqa: F401,E402
from src.connectors import sql_connector  # noqa: F401,E402
from src.connectors import mongo_connector  # noqa: F401,E402
from src.connectors import web_connector  # noqa: F401,E402

__all__ = [
    "BaseConnector", "ConnectorError", "RawDocument", "ResourceMeta", "SchemaInfo",
    "create_connector", "get_connector_class", "list_connectors", "register",
]
