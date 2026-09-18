"""启动 HTTP API 服务（v2）。

用法：python scripts/run_api.py            # 前台
      nohup python scripts/run_api.py > /root/autodl-tmp/agentic_rag_v2/logs/api.log 2>&1 &
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_env  # noqa: E402


def main():
    env = get_env()
    import uvicorn

    print(f"API 服务启动: http://{env['API_HOST']}:{env['API_PORT']}")
    uvicorn.run(
        "src.api.main:app",
        host=env["API_HOST"],
        port=int(env["API_PORT"]),
        reload=False,
    )


if __name__ == "__main__":
    main()
