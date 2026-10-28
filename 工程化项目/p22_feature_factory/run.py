#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口。

用法:
  python run.py                 # 按默认配置跑完整流水线并输出报告
  python run.py --config x.yaml # 指定配置文件
  python run.py --outdir out/   # 指定输出目录
  python run.py --quiet         # 只输出到文件，不打印到控制台
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

from feat_factory.cli import main  # noqa: E402  （sys.path 注入后方可导入，src 布局必需）

if __name__ == "__main__":
    sys.exit(main())
