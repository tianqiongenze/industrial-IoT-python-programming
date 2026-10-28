# -*- coding: utf-8 -*-
"""命令行入口（pyproject 的 [project.scripts] 指向这里）。

run.py 只做 sys.path 注入后调用本模块，保证"一个入口、两种启动方式"
（python run.py / 安装后的 p11_exercises 命令）行为完全一致。
"""
import argparse
import os
import sys

from . import config as config_mod
from . import pipeline

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))


def build_parser():
    """CLI 参数定义（所有分层任务都能从这里直达）。"""
    ap = argparse.ArgumentParser(
        prog="p11_exercises",
        description="Python 基础练习五题（工单 P1.1）——五题执行+内置断言"
                    "+分层达标+规范度量+迁移笔记")
    ap.add_argument("--config", default=os.path.join(HERE, "config",
                                                     "rules.yaml"),
                    help="配置文件路径（默认 config/rules.yaml）")
    ap.add_argument("--outdir", default=os.path.join(HERE, "output"),
                    help="输出目录（默认 output/）")
    ap.add_argument("--root", default=HERE,
                    help="项目根（迁移笔记写入 docs/ 的定位用）")
    ap.add_argument("--tier", choices=list(config_mod.TIERS),
                    help="按工单哪一档验收线高亮显示：D 及格/C 良好/B 优秀/"
                         "A 超优（默认取配置 meta.tier）")
    ap.add_argument("--no-notes", dest="notes", action="store_false",
                    help="不重写 docs/09 迁移笔记（只跑流水线）")
    ap.add_argument("--list-tools", action="store_true",
                    help="只探测 pylint/flake8/black/pre-commit 是否可用")
    ap.add_argument("--quiet", action="store_true",
                    help="只落盘，不打印报告正文")
    return ap


def main(argv=None):
    """入口主函数：只做"调用 + 输出"，不含业务判定。"""
    args = build_parser().parse_args(argv)
    if args.list_tools:
        from . import stylecheck
        for name, info in sorted(stylecheck.probe().items()):
            state = ("可用 " + info["version"]) if info["available"] \
                else ("不可用：%s" % (info["reason"] or "未安装"))
            print("%-11s %s" % (name, state))
        return 0
    cfg = config_mod.load_config(args.config)
    sections, _ = pipeline.run(cfg, out_dir=args.outdir, root=args.root,
                               tier=args.tier, want_notes=args.notes)
    if not args.quiet:
        from . import report
        report.console(sections)
    else:
        print("已生成 %s" % os.path.join(args.outdir, "report.txt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
