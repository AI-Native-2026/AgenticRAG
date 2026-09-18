"""端到端冒烟测试（v2 验收用）。

一键验证整条链路：登录 → 健康检查 → 提交文档(走队列) → 等消费者建索引
→ Agent 对话(SSE) → 指标报表 → 会话历史。

用法：
  python scripts/smoke_api.py            # 默认 http://localhost:8000
  python scripts/smoke_api.py --host 127.0.0.1 --port 8000
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests  # 用 requests 便于演示；若未装可改用 urllib
except ImportError:
    import urllib.request

    class requests:  # 极简兼容壳（教学兜底）
        class Response:
            pass

        @staticmethod
        def post(url, json=None, headers=None, stream=False):
            req = urllib.request.Request(url, data=json.dumps(json).encode(),
                                         headers={**(headers or {}), "Content-Type": "application/json"})
            return requests._Response(urllib.request.urlopen(req))

        class _Response:
            def __init__(self, resp):
                self.status_code = resp.status
                self._resp = resp

            def json(self):
                return json.loads(self._resp.read().decode())

        @staticmethod
        def get(url, headers=None):
            req = urllib.request.Request(url, headers=headers or {})
            return requests._Response(urllib.request.urlopen(req))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"
    results = []

    def check(name, fn):
        try:
            info = fn()
            print(f"[OK] {name}: {info}")
            results.append(True)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {name}: {e}")
            results.append(False)

    # 1. 登录
    def t_login():
        r = requests.post(f"{base}/v1/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, r.json()
        token = r.json()["access_token"]
        assert token, "无 token"
        globals()["_TOKEN"] = token
        return f"token={token[:20]}..."
    check("登录", t_login)

    def _headers():
        return {"Authorization": f"Bearer {globals().get('_TOKEN', '')}"}

    # 2. 健康检查
    check("healthz", lambda: requests.get(f"{base}/healthz").json())
    check("readyz", lambda: "ready" in requests.get(f"{base}/readyz").json())

    # 3. 提交文档（幂等键验证）
    doc_text = "# 冒烟测试文档\n\n这是通过 API 提交的测试内容，介绍 Agentic RAG 的冒烟测试。"
    def t_submit():
        r = requests.post(f"{base}/v1/documents", headers=_headers(),
                          json={"tenant": "tech", "idempotency_key": "smoke-1",
                                "docs": [{"doc_name": "smoke_test.md", "text": doc_text}]})
        assert r.status_code == 200, r.json()
        return f"accepted={r.json()['accepted']}"
    check("提交文档(队列)", t_submit)

    # 重试同一幂等键 → 不重复入队
    def t_idem():
        r = requests.post(f"{base}/v1/documents", headers=_headers(),
                          json={"tenant": "tech", "idempotency_key": "smoke-1",
                                "docs": [{"doc_name": "smoke_test.md", "text": doc_text}]})
        assert "duplicate" in r.json()["request_id"], r.json()
        return "重复请求被拦截"
    check("幂等键", t_idem)

    # 4. 等消费者建索引
    print("[等待] 消费者处理文档（5 秒）…")
    time.sleep(5)

    # 5. Agent 对话（SSE）
    def t_chat():
        r = requests.post(f"{base}/v1/chat", headers=_headers(),
                          json={"question": "冒烟测试文档讲了什么？", "session_id": "smoke-session"},
                          stream=True)
        assert r.status_code == 200, r.text
        body = ""
        for line in r.iter_lines(decode_unicode=True):
            if line.startswith("data: "):
                body += json.loads(line[6:]).get("content", "")
        assert body, "SSE 无内容"
        return f"回答({len(body)}字): {body[:40]}..."
    check("Agent 对话(SSE)", t_chat)

    # 6. 指标报表
    def t_metrics():
        r = requests.get(f"{base}/v1/metrics", headers=_headers())
        assert r.status_code == 200, r.json()
        return f"requests={r.json()['report'].get('request_count')}, tokens={r.json()['report'].get('total_tokens')}"
    check("指标报表", t_metrics)

    # 7. 会话历史
    def t_history():
        r = requests.get(f"{base}/v1/sessions/smoke-session", headers=_headers())
        assert r.status_code == 200, r.json()
        return f"消息数={len(r.json()['messages'])}"
    check("会话历史", t_history)

    print("\n" + "=" * 50)
    print(f"通过 {sum(results)}/{len(results)} 项")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
