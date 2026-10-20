# -*- coding: utf-8 -*-
"""工程化入口：加载→管道→评分（python run.py [--peek]）"""
import os
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from cleaning.loader import make_raw, load                    # noqa: E402
from cleaning.cleaner import CleaningPipeline, quality_score  # noqa: E402


def main(peek: bool = False):
    root = os.path.dirname(os.path.abspath(__file__))
    rules = yaml.safe_load(open(os.path.join(root, "config", "rules.yaml"),
                                encoding="utf-8"))
    data_dir = os.path.join(root, "data")
    os.makedirs(data_dir, exist_ok=True)
    raw_path = make_raw(os.path.join(data_dir, "W03_raw.csv"))
    df = load(raw_path)
    raw_rows = len(df)

    pipe = CleaningPipeline(rules)
    df = pipe.run(df)
    score, detail = quality_score(df, rules.get("score_weights", {}))

    print("=" * 52)
    print(" P2.1 清洗管道 · 工程化示范运行（多文件+配置外置+审计）")
    print("=" * 52)
    for a in pipe.audit:
        print(f"  [{a['step']}] {a}")
    print("-" * 52)
    print(f" 原始 {raw_rows} 行 → 干净 {len(df)} 行")
    print(f" 质量评分: {score} / 100   [及格线 {rules.get('pass_score', 85)}]")
    print(f" 明细: {detail}")
    if peek:
        print(df.head(5).to_string(index=False))


if __name__ == "__main__":
    main(peek="--peek" in sys.argv)
