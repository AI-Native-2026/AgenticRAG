"""共享 MongoDB 连接。

所有存储模块共用一个 MongoClient（连接池），避免每个 Store 各开一个连接池
造成的连接数浪费与建连开销——这是大规模场景下的关键性能/资源优化。
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

import pymongo

from src.config import get_env

_lock = threading.Lock()
_clients: Dict[str, "pymongo.MongoClient"] = {}


def get_client(uri: Optional[str] = None) -> "pymongo.MongoClient":
    env = get_env()
    uri = uri or env["MONGO_URI"]
    client = _clients.get(uri)
    if client is not None:
        return client
    with _lock:
        if uri not in _clients:
            _clients[uri] = pymongo.MongoClient(
                uri,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=int(env.get("MONGO_MAX_POOL", 100)),
                minPoolSize=2,
                retryWrites=True,
            )
        return _clients[uri]


def get_db(db_name: Optional[str] = None):
    env = get_env()
    return get_client(env["MONGO_URI"])[db_name or env["MONGO_DB"]]
