# -*- coding: utf-8 -*-
"""KPI 行 → 派生指标 → 等宽表 → JSON（streamlit 可选降级）。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    rows = [core.derive(r) for r in (cfg.items or [])]
    if not rows:
        raise ValueError("config/rules.yaml 的 lines 为空")
    tbl = core.table_rows(rows)
    worst = min(rows, key=lambda r: r["good_rate"])
    result = {"rows": rows, "worst": worst["line"]}
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_json(os.path.join(out_dir, "kpi.json"), result)
    try:
        note = "streamlit 已安装——可运行 `streamlit run app.py` 升级为交互仪表盘"
    except ImportError:
        note = "未装 streamlit：本次输出文本版（特性探测降级，主流程不受影响）"
    sections = [("输入口径", ["产线 %d 条｜5 个 KPI（合格率/OEE/告警/在线/达成）" % len(rows)]),
                ("KPI 驾驶舱", core.render(tbl[1:], tbl[0]).splitlines()),
                ("关注项", ["最低合格率 %.2f%%（%s）需当日复盘"
                 % (worst["good_rate"] * 100, worst["line"])]),
                ("升级路径", [note])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    return sections
