# -*- coding: utf-8 -*-
"""端到端流水线测试：报告四段齐全、真实数字、可复现性（除时间戳）。

墙钟口径：索引基准/慢查询的实测毫秒一律写 runtime/bench.json（与 output/
平级、已 .gitignore），output/ 内任何产物都不含实测时间值——故本文件里
「实测数字仍在」的断言读 runtime/，「output/ 干净」的断言读 output/。
"""
import json
import os

from warehouse_orm import config as C
import warehouse_orm.pipeline as P

BENCH_KEYS = ("before_ms", "after_ms", "speedup_x", "note")


def _cfg(tmp_path, **over):
    d = {"db_url": "sqlite:///%s/warehouse.db" % tmp_path,
         "buffer_db": "%s/does-not-exist.db" % tmp_path,
         "seed": 7, "n_records": 200, "batch_size": 100,
         "warn": 4.5, "danger": 6.0, "unit": "mm/s", "topk": 3,
         "index_bench_rows": 3000, "index_bench_reps": 3}
    d.update(over)
    return C.Settings.from_dict(d)


def _runtime_bench(out):
    """实测毫秒的唯一落点（与 out 平级的 runtime/bench.json）。"""
    return os.path.join(os.path.dirname(os.path.abspath(out)),
                        "runtime", "bench.json")


def test_pipeline_writes_all_artifacts(tmp_path):
    cfg = _cfg(tmp_path)
    out = str(tmp_path / "out")
    sections = P.run(cfg, out)
    text_ = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    for token in ("D层", "C层", "B层", "A层", "数据字典", "idx_dev_ts",
                  "EXPLAIN", "JOIN", "strftime", "环比", "分层达标",
                  "溯源", "p3_dashboard_handoff.csv"):
        assert token in text_
    result = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    assert result["seed"]["records"] == 200
    assert result["fk_orphan_rejected"] is True
    assert len(result["queries"]["avg_vib"]) == 3
    # 实测数字（含毫秒）必须真实存在——在 runtime/，不在 output/
    bench = json.load(open(_runtime_bench(out), encoding="utf-8"))
    assert all(k in bench["index_bench"] for k in BENCH_KEYS)
    assert os.path.exists(os.path.join(out, "p3_dashboard_handoff.csv"))
    assert not os.path.exists(os.path.join(out, "bench.json"))
    assert not os.path.exists(os.path.join(out, "bench.db"))
    assert sections and sections[-1][0] == "结论与建议"


def test_pipeline_two_runs_identical_except_timestamp(tmp_path):
    out = str(tmp_path / "out")
    cfg = _cfg(tmp_path)
    P.run(cfg, out)
    first = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    json1 = open(os.path.join(out, "result.json"), encoding="utf-8").read()
    csv1 = open(os.path.join(out, "p3_dashboard_handoff.csv"),
                encoding="utf-8").read()
    P.run(cfg, out)                       # 第二次读 runtime/bench.json 缓存，不再计时
    second = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    json2 = open(os.path.join(out, "result.json"), encoding="utf-8").read()
    csv2 = open(os.path.join(out, "p3_dashboard_handoff.csv"),
                encoding="utf-8").read()
    strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("生成时间"))
    assert strip(first) == strip(second)
    assert json1 == json2
    assert csv1 == csv2                   # 交接文件也是 output/ 产物，须逐字节稳定


def test_force_bench_refreshes_cache(tmp_path):
    out = str(tmp_path / "out")
    cfg = _cfg(tmp_path)
    P.run(cfg, out)
    p = _runtime_bench(out)
    old = json.load(open(p, encoding="utf-8"))
    P.run(cfg, out, bench_force=True)
    new = json.load(open(p, encoding="utf-8"))
    assert old["index_bench"]["before_plan"] == new["index_bench"]["before_plan"]
    assert isinstance(new["index_bench"]["after_ms"], float)


def test_data_dictionary_complete(tmp_path):
    cfg = _cfg(tmp_path)
    out = str(tmp_path / "out")
    result, _ = P.build(cfg, out)
    dd = result["data_dictionary"]
    tables = {r["table"] for r in dd}
    assert tables == {"devices", "points", "records", "alarms"}
    assert all(r["meaning"] for r in dd)                     # 每列有含义
    pk = {(r["table"], r["column"]) for r in dd if r["pk"] == "PK"}
    assert ("records", "id") in pk
    fk = {(r["table"], r["column"], r["fk"]) for r in dd if r["fk"]}
    assert ("points", "device_id", "devices.id") in fk
    assert ("records", "point_id", "points.id") in fk
    assert ("alarms", "device_id", "devices.id") in fk
    # 字典完整性要有实测数（不是"看着挺全"）：逐列清点 + 未登记清单为空
    ev = result["evidence"]
    assert ev["dict_columns_total"] == len(dd) == 18
    assert ev["dict_columns_documented"] == ev["dict_columns_total"]
    assert ev["dict_undocumented"] == []
    assert ev["dict_columns_commented"] > 0
