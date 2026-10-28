#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口（P5 产线数据仓库与ORM · SQLAlchemy 2.x）。

用法:
  python run.py                    # 完整流水线：建库→种子→批量导入→查询→报告
  python run.py --query all        # 只打印统计查询结果（avg-vib/top-alarms/hourly/window/all）
  python run.py --index-bench      # 强制重新实测索引前后耗时与 EXPLAIN（刷新 runtime/bench.json）
  python run.py --buffer PATH      # 指定 P4 缓冲库（默认 config/rules.yaml 的 buffer_db）
  python run.py --config x.yaml    # 指定配置文件
  python run.py --outdir out/      # 指定输出目录（默认本项目 output/）
  python run.py --quiet            # 只落盘不打印

产物分两处（墙钟红线）：
  output/   report.txt、result.json、warehouse.db、p3_dashboard_handoff.csv——确定性证据
  runtime/  bench.json、bench.db——索引基准实测毫秒与基准副本库，不进 output/（已在 .gitignore）
分层达标（D/C/B/A）逐条实测见 output/report.txt 的「分层达标」段。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import warehouse_orm.config as C  # noqa: E402  （sys.path 注入后方可导入，属 src 布局必需）
import warehouse_orm.io_utils as U  # noqa: E402
import warehouse_orm.pipeline as P  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="产线数据仓库与ORM（SQLAlchemy 2.x + SQLite）")
    ap.add_argument("--config", default=os.path.join(HERE, "config", "rules.yaml"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "output"))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--query", choices=["avg-vib", "top-alarms", "hourly", "window", "all"],
                    help="只运行并打印指定统计查询")
    ap.add_argument("--index-bench", action="store_true",
                    help="强制重新实测索引前后耗时（写回 output/bench.json）")
    ap.add_argument("--buffer", help="覆盖 P4 缓冲库路径（如 ../../buffer.db）")
    a = ap.parse_args(argv)

    cfg = C.load_config(a.config)
    if a.buffer:
        cfg.raw["buffer_db"] = a.buffer

    if a.query:
        engine, _url, _seed, imp = P.ensure_db(cfg, a.outdir)
        rows = P.query_rows(engine, a.query, topk=int(cfg.raw.get("topk", 3)))
        headers = {"avg-vib": ["设备", "平均vib", "记录数"],
                   "top-alarms": ["设备", "车间", "告警数"],
                   "hourly": ["小时", "记录数"],
                   "window": ["小时", "记录数", "上期", "环比"]}
        key = {"avg-vib": "avg_vib", "top-alarms": "top_alarms",
               "hourly": "hourly", "window": "window_orm"}
        which = [a.query] if a.query != "all" else ["avg-vib", "top-alarms",
                                                    "hourly", "window"]
        for w in which:
            print("\n== %s ==" % w)
            data = rows[key[w]][:12]
            print(U.fmt_table([list(r) for r in data], headers[w]))
        if a.query == "all":
            print("（hourly/window 仅显示前12行，完整结果见 output/result.json）")
        if "window_orm" in rows:
            print("\n[校验] 裸SQL(text()) 与 ORM 窗口环比结果逐行一致: %s"
                  % (rows["window_orm"] == rows["window_raw"]))
        return 0

    sections = P.run(cfg, out_dir=a.outdir, bench_force=a.index_bench)
    if not a.quiet:
        print("\n".join(sections[-1][1]) if sections else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
