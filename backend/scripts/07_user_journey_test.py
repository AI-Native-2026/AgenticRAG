#!/usr/bin/env python
"""用户旅程测试（07）——不同角色/场景的端到端验证。

旅程：
  A. 管理员：接入数据源 → 同步 → 建知识库 → 看指标/审计/租户
  B. 业务分析师(alice/tech)：检索、对话、会话持久化、评测
  C. 数据合规(bob/finance)：跨租户隔离、越权拦截、预览脱敏
用法：python scripts/07_user_journey_test.py
前置：API 运行中；建议先跑 06_multiformat_test.py 造好数据。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE", "http://127.0.0.1:18000")
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  ({detail})" if detail else ""))


def call(method, path, body=None, token=None, timeout=240):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, {}


def login(user, pwd):
    _, r = call("POST", "/v1/auth/login", {"username": user, "password": pwd})
    return r["access_token"]


def journey_admin():
    print("\n[A] 管理员旅程")
    tok = login("admin", "admin123")
    s, ds = call("GET", "/v1/datasources", token=tok)
    check("管理员可见数据源", len(ds.get("datasources", [])) > 0, f"{len(ds.get('datasources', []))} 个")
    s, kb = call("GET", "/v1/knowledge-bases", token=tok)
    check("管理员可见知识库", s == 200, f"{len(kb.get('knowledge_bases', []))} 个")
    s, m = call("GET", "/v1/metrics", token=tok)
    check("管理员可看指标", s == 200 and "report" in m)
    s, a = call("GET", "/v1/audit?limit=5", token=tok)
    check("管理员可看审计", s == 200 and "audit" in a)
    s, t = call("GET", "/v1/tenants", token=tok)
    check("管理员可看租户配额", s == 200 and len(t.get("tenants", [])) > 0)


def journey_analyst():
    print("\n[B] 业务分析师(alice/tech)旅程")
    tok = login("alice", "alice123")

    # 检索
    s, r = call("POST", "/v1/retrieval/search",
                {"query": "E2E-MD-7788", "top_k": 20, "top_n": 5, "rerank": True}, tok)
    check("分析师可检索", s == 200 and len(r.get("results", [])) > 0)

    # 对话（非流式）
    s, c = call("POST", "/v1/chat",
                {"question": "E2E-MD-7788 是什么？", "session_id": "journey-alice", "stream": False}, tok)
    ans = c.get("answer", "") if isinstance(c, dict) else ""
    check("分析师对话返回答案", s == 200 and len(ans) > 0)
    check("答案无 assistant 前缀", not ans.strip().lower().startswith("assistant"))

    # 会话持久化
    s, sess = call("GET", "/v1/sessions", token=tok)
    ids = [x["session_id"] for x in sess.get("sessions", [])]
    check("会话已持久化", "journey-alice" in ids)
    s, hist = call("GET", "/v1/sessions/journey-alice", token=tok)
    check("会话历史可回读", s == 200 and len(hist.get("messages", [])) >= 2)

    # 评测
    s, _ = call("POST", "/v1/eval/set", {"query": "E2E-MD-7788", "golden_docs": ["e2e_sample.md"]}, tok)
    check("分析师可新增评测项", s == 200)
    s, rep = call("POST", "/v1/eval/run", token=tok)
    check("评测可运行", s == 200 and "hit_rate" in rep.get("report", {}))

    # 清理会话
    s, _ = call("DELETE", "/v1/sessions/journey-alice", token=tok)
    check("会话可删除", s == 200)


def journey_isolation():
    print("\n[C] 数据合规(bob/finance)旅程")
    tok = login("bob", "bob123")

    s, ds = call("GET", "/v1/datasources", token=tok)
    names = [d["name"] for d in ds.get("datasources", [])]
    check("租户隔离：看不到 tech 数据源", all("E2E" not in n for n in names), f"{names}")

    s, r = call("POST", "/v1/retrieval/search",
                {"query": "E2E-MD-7788", "top_k": 20, "top_n": 5, "rerank": True}, tok)
    check("租户隔离：检索不到 tech 文档", len(r.get("results", [])) == 0,
          f"{len(r.get('results', []))} 条")

    s, _ = call("GET", "/v1/metrics", token=tok)
    check("越权拦截：member 不可看指标(403)", s == 403, f"HTTP {s}")
    s, _ = call("GET", "/v1/tenants", token=tok)
    check("越权拦截：member 不可看租户(403)", s == 403, f"HTTP {s}")


def journey_masking():
    print("\n[D] 隐私合规：预览脱敏")
    tok = login("admin", "admin123")
    s, ds = call("GET", "/v1/datasources", token=tok)
    dbs = [d for d in ds["datasources"] if d["type"] == "database"]
    db = next((d for d in dbs if "biz_demo" in str((d.get("config") or {}).get("path", ""))),
              dbs[0] if dbs else None)
    if not db:
        check("存在数据库数据源", False)
        return
    s, pv = call("GET", f"/v1/datasources/{db['ds_id']}/preview?resource=customers&limit=3", token=tok)
    text = " ".join(p["text"] for p in pv.get("preview", []))
    check("预览默认脱敏", pv.get("masked") is True)
    check("手机号已脱敏", ("13812345678" not in text) and ("***" in text), text[:120])


def main():
    print("=" * 70)
    print("用户旅程测试")
    print("=" * 70)
    journey_admin()
    journey_analyst()
    journey_isolation()
    journey_masking()
    print("-" * 70)
    print(f"结果：{len(PASS)} 通过 / {len(PASS) + len(FAIL)} 项")
    if FAIL:
        print("失败项：", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
