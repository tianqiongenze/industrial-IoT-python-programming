#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口（P2.1《Pandas 数据处理管道》）。

用法:
  python run.py                    # 七步管道全流程 + 报告（含 A 层增量/压测证据）
  python run.py --peek             # 课前导学单：只预览脏数据，不写业务产物
  python run.py --input 路径.csv   # 覆盖输入（默认读课程根目录 p21_raw.csv）
  python run.py --no-bench         # 跳过 100 万行压测（课堂快跑）
  python run.py --incremental      # 按 output/state.json 基线只处理增量
  python run.py --outdir out/      # 指定输出目录
  python run.py --quiet            # 只落盘，不打印
  python run.py --stamp            # 报告头写入墙钟（默认关闭以保证逐字节可复现）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

from pd_clean.cli import main  # noqa: E402  （sys.path 注入后方可导入，src 布局必需）

if __name__ == "__main__":
    sys.exit(main())
