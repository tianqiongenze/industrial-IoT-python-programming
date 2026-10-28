# -*- coding: utf-8 -*-
"""命令行入口：run.py 与 pyproject 的 [project.scripts] 共用同一份参数解析。"""
import argparse
import os

from . import config as C
from . import pipeline as P
from . import report as R

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_parser():
    ap = argparse.ArgumentParser(
        description="Pandas 数据清洗管道（七步 + 台账 + 质量门禁）")
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "rules.yaml"),
                    help="规则外置 YAML（改规则不改代码）")
    ap.add_argument("--input", default=None,
                    help="脏数据 CSV 路径，覆盖配置 io.input")
    ap.add_argument("--outdir", default=os.path.join(ROOT, "output"))
    ap.add_argument("--peek", action="store_true",
                    help="只预览摸底脏数据，不写 output/")
    ap.add_argument("--incremental", action="store_true",
                    help="增量处理：只算 state.json 基线之后的新行")
    ap.add_argument("--no-bench", dest="bench", action="store_false",
                    help="跳过 100 万行压测（A 层口径默认执行）")
    ap.add_argument("--quiet", action="store_true", help="只输出到文件，不打印控制台")
    ap.add_argument("--stamp", action="store_true",
                    help="报告头写入生成时间（会破坏逐字节复现，默认关闭）")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    cfg = C.load_config(a.config)
    stamp = R.now_stamp() if a.stamp else None
    if a.peek:
        sections = P.peek(cfg, a.input)           # 只预览，不写业务产物
    elif a.incremental:
        sections, _info = P.run_incremental(cfg, a.outdir, a.input, stamp=stamp)
    else:
        sections = P.run(cfg, out_dir=a.outdir, input_path=a.input,
                         bench=a.bench, stamp=stamp)
    if not a.quiet:
        for name, lines in sections:
            print("\n[%s]" % name)
            for line in lines:
                print("  " + str(line))
        if not a.peek:
            print("\n产物目录: %s" % a.outdir)
    return 0
