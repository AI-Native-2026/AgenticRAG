"""Text-to-SQL 安全护栏测试。"""

import pytest

from src.connectors.base import ConnectorError
from src.connectors.text2sql import enforce_limit, validate_sql


def test_select_allowed():
    assert validate_sql("SELECT id, name FROM users") == "SELECT id, name FROM users"


def test_trailing_semicolon_stripped():
    assert validate_sql("SELECT 1;") == "SELECT 1"


def test_with_cte_allowed():
    sql = "WITH t AS (SELECT 1 AS x) SELECT * FROM t"
    assert validate_sql(sql).lower().startswith("with")


@pytest.mark.parametrize("sql", [
    "INSERT INTO users VALUES (1)",
    "UPDATE users SET name='x'",
    "DELETE FROM users",
    "DROP TABLE users",
    "ALTER TABLE users ADD COLUMN a int",
])
def test_write_statements_rejected(sql):
    with pytest.raises(ConnectorError):
        validate_sql(sql)


def test_multi_statement_rejected():
    with pytest.raises(ConnectorError):
        validate_sql("SELECT 1; SELECT 2")


def test_comment_rejected():
    with pytest.raises(ConnectorError):
        validate_sql("SELECT * FROM users -- drop")


def test_whitelist_enforced():
    with pytest.raises(ConnectorError):
        validate_sql("SELECT * FROM secret", allowed_tables=["users"])
    assert validate_sql("SELECT * FROM users", allowed_tables=["users"])


def test_enforce_limit():
    assert enforce_limit("SELECT * FROM t", 50).endswith("LIMIT 50")
    assert enforce_limit("SELECT * FROM t LIMIT 5", 50).endswith("LIMIT 5")
