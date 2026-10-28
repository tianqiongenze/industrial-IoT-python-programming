# -*- coding: utf-8 -*-
"""命令行入口：run.py 与 pyproject 的 [project.scripts] 共用同一份参数解析。

修复记录：pyproject.toml 曾声明 proj_template.cli:main 而该模块不存在（断裂脚手架），
现在该模块真实存在且导出 main，脚本入口与 run.py 走同一条路径。
"""
import argparse
import os

from . import config as C
from . import pipeline as P

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_parser():
    ap = argparse.ArgumentParser(description="标准工程模板生成（03-P1.2）")
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "rules.yaml"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "output"))
    ap.add_argument("--quiet", action="store_true", help="只落盘，不打印结论")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    cfg = C.load_config(a.config)
    sections = P.run(cfg, out_dir=a.outdir)
    if not a.quiet:
        print("\n".join(sections[-1][1]) if sections else "")
    return 0
