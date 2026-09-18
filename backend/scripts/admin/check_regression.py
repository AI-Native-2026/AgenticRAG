"""评测回归门禁（v2 admin CLI）。

作用：每次改动（切分/模型/检索参数）后跑一遍，指标比基线差超过阈值就报错。
这就是「效果回归 CI」的本地版——没有 git/CI 时，它可以在每次上线前手动执行。

用法：
  python scripts/05_eval.py --all --out data/baseline.json     # 先建立基线
  python scripts/admin/check_regression.py --current data/current.json   # 对比基线
  python scripts/admin/check_regression.py --current x.json --tolerance 0.03  # 容忍 3% 回退
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BASELINE = PROJECT_ROOT / "data" / "baseline.json"


def load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--current", required=True, help="本次评测结果 json")
    parser.add_argument("--tolerance", type=float, default=0.02, help="允许的回退幅度(绝对)")
    args = parser.parse_args()

    base = load(args.baseline)
    cur = load(args.current)
    print(f"基线: {args.baseline}")
    print(f"当前: {args.current}")

    failed = False
    for key in ("hit_rate", "mrr", "answer_hit"):
        b = base.get(key, 0)
        c = cur.get(key, 0)
        drop = b - c
        status = "OK" if drop <= args.tolerance else "FAIL"
        if drop > args.tolerance:
            failed = True
        print(f"  {key:<12} 基线={b:.3f} 当前={c:.3f} 回退={drop:.3f} -> {status}")

    if failed:
        print("\n[结论] 存在超容忍回退，禁止上线！请先排查改动。")
        sys.exit(1)
    print("\n[结论] 指标达标，可以上线。")


if __name__ == "__main__":
    main()
