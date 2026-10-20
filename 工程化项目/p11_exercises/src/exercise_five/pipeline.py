# -*- coding: utf-8 -*-
"""五题闯关流水线：逐题运行并把结果写入台账。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    results = []
    results.append(("t1 单位换算", "36℃ → %.2f℉" % core.c_to_f(36.0)))
    roots = core.quad(1, -3, 2)
    results.append(("t2 一元二次", "x^2-3x+2 → %s" % roots))
    results.append(("t2 边界", "判别式<0 → %s" % core.quad(1, 0, 1)))
    reg = core.Registry()
    for i, d in enumerate(cfg.items or [], 1):
        reg.add(core.PLC(str(d.get("id", i)), str(d.get("name", "设备")),
                         scan_ms=100 * i))
    results.append(("t3 设备CRUD", "注册 %d 台，删除后 %d 台"
                   % (reg.count(), reg.count() - (1 if reg.remove("02") is not None else 0))))
    p = os.path.join(out_dir, "demo.txt")
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_text(p, "hello")
    results.append(("t4 PLC子类", "扫描周期 %dms"
                   % (list(reg._d.values())[0].scan_ms if reg.count() else 100)))
    results.append(("t5 安全读取", "存在→%s / 不存在→%s"
                   % (core.safe_read(p)[:5], core.safe_read("/no/such"))))
    result = {k: v for k, v in results}
    sections = [("输入口径", ["设备 %d 台｜题库 5 道（语法迁移）" % len(cfg.items or [])]),
                ("逐题结果", ["%s: %s" % (k, v) for k, v in results]),
                ("结论与建议", ["五题全过 = 及格（≥3题）；五题+边界断言+注释全齐 = 优秀（A层）"])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    return sections
