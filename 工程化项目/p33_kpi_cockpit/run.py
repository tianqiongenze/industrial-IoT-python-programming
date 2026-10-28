#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口 —— P3《产线KPI仪表盘与自动日报》。

所有工单条目都能从这里到达（标志 ↔ 工单条目对照见 python run.py --help，
详表见 docs/05 运行手册）。参数解析与流水线编排在 kpi_cockpit.cli，
与 pyproject [project.scripts] 的 p33_kpi_cockpit 入口共用同一份实现。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

from kpi_cockpit.cli import main  # noqa: E402  （sys.path 注入后方可导入，src 布局必需）

if __name__ == "__main__":
    sys.exit(main())
