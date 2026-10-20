# -*- coding: utf-8 -*-
"""造数 → 建索引 → 查询（有计划标注）→ 落盘。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    n = int(cfg.raw.get("n_records", 500))
    idx_col = str(cfg.raw.get("index_col", "device_id"))
    t = core.Table("sensor_log", ["device_id", "temp", "press"])
    for i in range(n):
        t.insert({"device_id": "DEV-%02d" % (i % 10 + 1),
                  "temp": round(20 + (i % 70) * 0.5, 1),
                  "press": round(0.2 + (i % 30) * 0.01, 3)})
    t.create_index(idx_col)
    q = {"device_id": "DEV-03"}
    hit = t.where(**q)
    import time
    t0 = time.time()
    for _ in range(200):
        t.where(**q)
    idx_ms = (time.time() - t0) / 200 * 1000
    t0 = time.time()
    for _ in range(20):
        t.where(temp=50.0)
    full_ms = (time.time() - t0) / 20 * 1000
    result = {"n_records": n, "index_col": idx_col, "hits": len(hit),
              "plan_indexed": t.explain(**q),
              "plan_full": t.explain(temp=50.0),
              "index_ms": round(idx_ms, 4), "full_ms": round(full_ms, 4)}
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    sections = [("输入口径", ["%d 条记录｜索引列 %s｜字段 device_id/temp/press" % (n, idx_col)]),
                ("查询计划", ["等值+索引: %s（%.4f ms）" % (t.explain(**q), idx_ms),
                          "无索引范围: %s（%.4f ms）" % (t.explain(temp=50.0), full_ms)]),
                ("查询结果", ["device_id=DEV-03 命中 %d 条" % len(hit)]),
                ("结论与建议", ["索引只加速'等值+高选择率'查询；范围/低选择率仍走全表扫描——"
                 "这就是生产库要写查询计划的原因"])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
