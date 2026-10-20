#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口。

用法:
  python run.py                 # 按默认配置跑完整流水线并输出报告
  python run.py --config x.yaml # 指定配置文件
  python run.py --outdir out/   # 指定输出目录
  python run.py --quiet         # 只输出到文件，不打印到控制台
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import ml_service.config as C  # noqa: E402  （sys.path 注入后方可导入，属 src 布局必需）
import ml_service.pipeline as P  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="模型训练与服务")
    ap.add_argument("--config", default=os.path.join(HERE, "config", "rules.yaml"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "output"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    cfg = C.load_config(a.config)
    sections = P.run(cfg, out_dir=a.outdir)
    if not a.quiet:
        print("\n".join(sections[-1][1]) if sections else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
