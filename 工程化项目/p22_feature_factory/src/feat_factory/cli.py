# -*- coding: utf-8 -*-
"""命令行入口：run.py 与 pyproject 的 [project.scripts] 共用同一份参数解析。"""
import argparse
import os

from . import config as C
from . import pipeline as P

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_parser():
    ap = argparse.ArgumentParser(description="特征工厂")
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "rules.yaml"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "output"))
    ap.add_argument("--quiet", action="store_true", help="只落盘，不打印结论")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    cfg = C.load_config(a.config)
    result = P.run(cfg, out_dir=a.outdir)
    if not a.quiet:
        # pipeline.run 返回的是 dict（sections/text/ledger/...），报告节在 "sections" 键；
        # 旧代码按列表直接 result[-1] 索引，非 --quiet 路径当场 KeyError: -1。
        sections = result["sections"]
        print("\n".join(sections[-1][1]) if sections else "")
    return 0
