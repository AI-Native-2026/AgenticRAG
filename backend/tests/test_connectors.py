"""连接器框架测试（不依赖外部服务）。"""

import json
from pathlib import Path

from src.connectors import create_connector, list_connectors
from src.connectors.file_connector import FileConnector
from src.storage.crypto import decrypt, encrypt


def test_registry_has_core_types():
    ks = set(list_connectors())
    assert {"file", "directory", "mysql", "postgresql", "mongodb", "web"} <= ks


def test_crypto_roundtrip():
    for v in ["", "p@ss", "中文密码123"]:
        assert decrypt(encrypt(v)) == v


def test_file_connector_reads_formats(tmp_path: Path):
    (tmp_path / "a.md").write_text("# 标题\n\n正文内容", encoding="utf-8")
    (tmp_path / "b.csv").write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps([{"k": 1}, {"k": 2}]), encoding="utf-8")

    ds = {"ds_id": "ds-test", "name": "t", "tenant": "tech", "subtype": "directory",
          "config": {"path": str(tmp_path)}}
    conn = create_connector(ds, {})
    assert isinstance(conn, FileConnector)

    ok, _ = conn.test_connection()
    assert ok

    resources = conn.discover()
    assert len(resources) == 3

    docs = list(conn.read())
    assert len(docs) >= 4  # md(1) + csv(2) + json(2)
    assert all(d.metadata["source_type"] == "file" for d in docs)
    assert all(d.metadata["datasource_id"] == "ds-test" for d in docs)
