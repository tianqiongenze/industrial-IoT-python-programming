#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口：注入 src 路径后调用 exercise_five.cli.main()。

用法:
  python run.py                  # 默认配置跑五题 + 断言 + 分层达标 + 笔记
  python run.py --tier B         # 按 B 档（工单"优秀"）验收线高亮
  python run.py --quiet          # 只落盘 output/，不打印报告
  python run.py --no-notes       # 本次不重写 docs/09 迁移笔记
  python run.py --list-tools     # 探测 pylint/flake8/black/pre-commit
  python run.py --config X --outdir Y
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

from exercise_five import cli  # noqa: E402  （src 布局需先注入 sys.path）


def main(argv=None):
    """只做调用与退出码传递（一题一函数，主函数不掺业务）。"""
    return cli.main(argv)


if __name__ == "__main__":
    sys.exit(main())
