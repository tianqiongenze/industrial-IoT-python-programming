# -*- coding: utf-8 -*-
"""合成脏数据 → 清洗 → 质量分 → 门禁 → 留痕。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    tmax = float(cfg.raw.get("temp_max", 120.0))
    target = float(cfg.raw.get("target_quality", 0.85))
    raw = core.make_dirty()
    n0 = len(raw)
    c = core.clean(raw.copy(), tmax)
    q = core.quality(c, tmax)
    ok = core.gate(q, target)
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_csv_rows(os.path.join(out_dir, "clean.csv"),
                            c.to_dict("records"))
    result = {"rows_before": n0, "rows_after": len(c), "removed": n0 - len(c),
              "quality": q, "target": target, "gate_passed": ok}
    sections = [("输入口径", ["原始 %d 行｜温度上限 %.0f℃｜质量目标 %.2f" % (n0, tmax, target)]),
                ("清洗留痕", ["%d 行 → %d 行（剔除 %d 行）" % (n0, len(c), n0 - len(c))]),
                ("质量分", ["%.4f（目标 %.2f）→ 门禁 %s" % (q, target, "通过" if ok else "未通过")]),
                ("结论与建议", ["规则已外置 YAML：改 temp_max/vib 区间只需改配置，代码零改动"])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    return sections
