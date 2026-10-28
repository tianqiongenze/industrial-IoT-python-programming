# -*- coding: utf-8 -*-
"""分层工单闸门（D/C/B/A）测试——对齐工单 P5 验收表逐条拿真实测量证据。

口径出处：工单任务书/P5工单-产线数据仓库与ORM.md 验收标准表
  及格(D) 4表设计合理；ORM入库成功；2条统计查询可用
  良好(C) 数据字典完整；批量事务；溯源查询正确
  优秀(B) 索引优化有EXPLAIN证据；N+1问题已规避
  超优(A) 优秀+复杂查询(多表JOIN聚合)+导入P3仪表盘形成闭环演示

五件事，缺一不可：
  ① 在真实流水线上（临时目录）复算每一级判据，断言 tiers 与实测一致；
  ② 每一级都能"只改配置不改代码"被判为未达标（证伪性，防止橡皮图章）；
  ③ 报告「分层达标」行与 result.json 的 tiers/数字必须同源同值；
  ④ 墙钟红线：output/ 内不得出现实测毫秒，毫秒只在 runtime/bench.json；
  ⑤ 逐字对表：报告每档行首「」必须等于课程仓工单文件的验收表原文。
"""
import json
import os
import re

import pytest

from warehouse_orm import config as C
import warehouse_orm.pipeline as P

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, "..", "config", "rules.yaml")
MS_IN_TEXT = re.compile(r"\d+\.\d+\s*(ms|毫秒|秒)")
HANDOFF_NAME = "p3_dashboard_handoff.csv"

# 基线配置：与项目 rules.yaml 同源，只把库/缓冲改指临时目录并缩小基准，
# 使断言里的数字（716 行、57 告警、18 列…）由本次真实运行产生且可核。
BASE = {"index_bench_rows": 3000, "index_bench_reps": 3}


def _write_rules(tmp_path, **over):
    """只改 YAML 文本（不改代码）：已存在的键整行替换，缺失的键追加。"""
    text = open(RULES, encoding="utf-8").read()
    merged = dict(BASE)
    merged.update(over)
    merged.setdefault("db_url", "sqlite:///%s/warehouse.db" % tmp_path)
    merged.setdefault("buffer_db", "%s/absent-buffer.db" % tmp_path)
    for k, v in merged.items():
        value = '"%s"' % v if isinstance(v, str) else v
        line = "%s: %s" % (k, value)
        pat = re.compile(r"(?m)^%s:.*$" % re.escape(k))
        text = pat.sub(line, text) if pat.search(text) else text + "\n" + line + "\n"
    path = os.path.join(str(tmp_path), "rules.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _run(tmp_path, out_name="out", **over):
    out = os.path.join(str(tmp_path), out_name)
    cfg = C.load_config(_write_rules(tmp_path, **over))
    sections = P.run(cfg, out)
    data = json.loads(open(os.path.join(out, "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    return {"out": out, "data": data, "text": text, "sections": sections,
            "ev": data["evidence"], "tiers": data["tiers"],
            "crit": data["tier_criteria"],
            "lines": dict(sections)["分层达标"]}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("tier"))


# ---------------- ① 每一级判据 = 本次真实测量 ----------------

def test_d_layer_four_tables_orm_insert_and_two_stat_queries(built):
    ev, crit = built["ev"], built["crit"]
    assert crit["D"] == {"four_tables": True, "orm_insert_ok": True,
                         "stat_queries": True}
    assert ev["tables_created"] == ev["tables_required"] == 4
    assert ev["tables_missing"] == []
    assert ev["orm_rows_loaded"] == 716 == ev["orm_rows_expected"]
    assert ev["orm_rows_loaded"] == ev["seed_records"] + ev["buffer_written"] == 500 + 216
    assert ev["stat_query_rows"] == {"T4a": 3, "T4b": 3, "T4c": 10}
    assert ev["stat_queries_available"] == 3 >= ev["min_stat_queries"] == 2
    assert built["tiers"]["D"] is True


def test_c_layer_dictionary_bulk_transactions_and_traceability(built):
    ev, crit = built["ev"], built["crit"]
    assert crit["C"] == {"dictionary_complete": True, "bulk_transactions": True,
                         "traceability": True}
    # 数据字典完整：逐列清点，实测 18/18，未登记清单为空
    assert ev["dict_columns_total"] == 18
    assert ev["dict_columns_documented"] == ev["dict_columns_total"]
    assert ev["dict_undocumented"] == []
    # 批量事务：bulk_save_objects 分批提交，种子 5 批 + 缓冲 3 批
    assert ev["bulk_objects"] is True
    assert (ev["seed_commits"], ev["import_commits"], ev["commits_total"]) == (5, 3, 8)
    assert ev["batch_size"] == 100
    # 溯源正确：57 条告警全部沿四表 JOIN 反查到同刻读数，孤儿行 0
    assert ev["alarms_total"] == ev["alarms_traced"] == 57
    assert ev["trace_orphans"] == 0
    assert ev["trace_orphan_detail"] == {"records.point_id": 0,
                                         "points.device_id": 0,
                                         "alarms.device_id": 0}
    assert built["tiers"]["C"] is True


def test_b_layer_explain_evidence_and_n_plus_one_avoided(built):
    ev, crit = built["ev"], built["crit"]
    assert crit["B"] == {"explain_evidence": True, "n_plus_one_avoided": True}
    ib = ev["index_bench"]
    assert ib["bench_rows"] == 3000 and ib["hits"] == 240
    assert ib["scan_before"] is True and ib["index_search_after"] is True
    assert ib["before_plan"] == ["SCAN bench_records"]
    assert "SEARCH" in ib["after_plan"][0] and "idx_bench_dev_ts" in ib["after_plan"][0]
    n1 = ev["n_plus_one"]
    assert (n1["lazy_sql_count"], n1["joinedload_sql_count"],
            n1["selectinload_sql_count"], n1["devices"]) == (4, 1, 2, 3)
    assert n1["loader"] == "joinedload" and n1["mitigated"] is True
    assert built["tiers"]["B"] is True


def test_a_layer_complex_join_aggregate_and_p3_handoff(built):
    ev, crit, hd = built["ev"], built["crit"], built["ev"]["handoff"]
    assert crit["A"] == {"complex_join_aggregate": True, "p3_handoff": True}
    # 复杂查询：设备×小时四表 JOIN 聚合，且与逐行手算一致、记录/告警数守恒
    assert ev["summary_buckets"] == 30 and ev["summary_devices"] == 3
    assert ev["summary_matches_manual"] is True
    assert sum(r[3] for r in built["data"]["complex_summary"]) == ev["orm_rows_loaded"]
    assert ev["orm_raw_window_equal"] is True
    # P3 闭环交接文件：真实落盘、列符合 P3 CANON 子集、时间可解析、设备在册
    assert hd["disabled"] is False and hd["exists"] is True
    assert os.path.exists(hd["path"]) and os.path.basename(hd["path"]) == HANDOFF_NAME
    assert hd["rows"] == 30 and hd["columns"] == ["ts", "device_id", "line",
                                                  "temp", "vib", "status"]
    assert hd["missing_columns"] == [] and hd["ts_parse_failures"] == 0
    assert hd["unknown_devices"] == [] and hd["empty_cells"] == 0
    assert sum(hd["status_counts"].values()) == 30
    assert built["tiers"]["A"] is True


# ---------------- ③ 报告行与 result.json 同源同值 ----------------

def test_tier_section_exists_with_one_line_per_level(built):
    lines = built["lines"]
    assert len(lines) == 4
    assert [l.split(" ")[0] for l in lines] == ["D层", "C层", "B层", "A层"]
    for line in lines:
        assert line in built["text"]                       # 报告里逐字在案
        assert re.search(r"\d", line), line                 # 带真实数字，非口号
    # tiers 的 true/false 必须与行尾判定一致
    for k, line in zip("DCBA", lines):
        assert line.endswith("→ 达标") is (built["tiers"][k] is True)


def test_tier_lines_quote_the_measured_numbers(built):
    ev, lines = built["ev"], built["lines"]
    d, c, b, a = lines
    assert "建表 4/4 张" in d and "records 入库 716 行" in d
    assert "T4a 3 行、T4b 3 行、T4c 10 行；门槛 ≥2 条" in d
    assert "数据字典 18/18 列有成文含义" in c
    assert "分批提交 8 次（种子 5＋缓冲 3，每批≤100 条）" in c
    assert "命中 57/57 条告警、外键孤儿行 0" in c
    assert "bench_records 3000 行区间查询命中 240 行" in b
    assert "懒加载 4 条 SELECT vs joinedload 1 条（3 台设备）" in b
    assert "四表 JOIN 聚合 30 桶" in a and "与逐行手算一致=是" in a
    assert HANDOFF_NAME in a and "30 行×6 列" in a
    assert ev["bench_timings_in"] == "runtime/bench.json"
    assert "runtime/bench.json" in b                       # B 行指明毫秒去处


def test_tiers_are_cumulative_not_free_standing(built):
    """工单把 A 定义为「优秀+…」：低一级不达标，本级不得单独报喜。"""
    assert built["tiers"] == {"D": True, "C": True, "B": True, "A": True}
    assert set(built["crit"]) == {"D", "C", "B", "A"}
    assert set(built["crit"]["C"]) == {"dictionary_complete", "bulk_transactions",
                                       "traceability"}


# ---------------- ② 只改配置即可证伪（不改一行代码） ----------------

def test_d_layer_is_falsifiable_by_config_only(tmp_path):
    """n_records: 0 + buffer_stand_in_rows: 0 → ORM 入库 0 行、0 条查询可用。"""
    r = _run(tmp_path, "d_off", n_records=0, buffer_stand_in_rows=0)
    ev = r["ev"]
    assert ev["orm_rows_loaded"] == ev["orm_rows_expected"] == 0
    assert ev["stat_queries_available"] == 0
    assert r["crit"]["D"] == {"four_tables": True, "orm_insert_ok": False,
                              "stat_queries": False}
    assert r["tiers"]["D"] is False
    assert r["tiers"] == {"D": False, "C": False, "B": False, "A": False}
    assert "records 入库 0 行" in r["lines"][0]
    assert r["lines"][0].endswith("→ 未达标")
    assert "分层达标" in r["text"]


def test_c_layer_is_falsifiable_by_config_only(tmp_path):
    """batch_size: 1000 > 单批数据量 → 每段只提交 1 次，「批量事务」证据不成立。"""
    r = _run(tmp_path, "c_off", batch_size=1000)
    ev = r["ev"]
    assert (ev["seed_commits"], ev["import_commits"]) == (1, 1)   # 一次全提交
    assert ev["dict_columns_documented"] == ev["dict_columns_total"] == 18
    assert ev["alarms_traced"] == ev["alarms_total"]              # 溯源仍正确
    assert r["crit"]["C"] == {"dictionary_complete": True,
                              "bulk_transactions": False,
                              "traceability": True}
    assert r["tiers"]["D"] is True and r["tiers"]["C"] is False
    assert r["lines"][1].endswith("→ 未达标")


def test_b_layer_is_falsifiable_by_config_only(tmp_path):
    """n_plus_one_loader: lazy → 不预加载，规避证据消失 ⇒ B 未达标（D/C 仍达标）。"""
    r = _run(tmp_path, "b_off", n_plus_one_loader="lazy")
    n1 = r["ev"]["n_plus_one"]
    assert (n1["loader"], n1["eager_sql_count"], n1["lazy_sql_count"]) == ("lazy", 4, 4)
    assert n1["mitigated"] is False
    assert r["crit"]["B"] == {"explain_evidence": True, "n_plus_one_avoided": False}
    assert r["tiers"]["D"] is True and r["tiers"]["C"] is True
    assert r["tiers"]["B"] is False and r["tiers"]["A"] is False
    assert "懒加载 4 条 SELECT vs lazy 4 条" in r["lines"][2]
    assert r["lines"][2].endswith("→ 未达标")


WO_FILE = os.path.abspath(os.path.join(HERE, "..", "..", "..",
                                       "工单任务书", "P5工单-产线数据仓库与ORM.md"))
WO_ROW_RE = re.compile(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*\|\s*(.+?)\s*\|\s*$")
TIER_CN = {"D": "及格", "C": "良好", "B": "优秀", "A": "超优"}


def _workorder_rows():
    """直接读课程仓的工单文件，按行取验收表四行原文。"""
    rows = {}
    for line in open(WO_FILE, encoding="utf-8").read().splitlines():
        m = WO_ROW_RE.match(line)
        if m:
            rows[m.group(1)[m.group(1).index("(") + 1]] = m.group(2)
    return rows


def test_workorder_rows_are_quoted_verbatim(built):
    """报告每档行首的「」必须是工单原文逐字：改一个字（哪怕只加个空格）就红。
    线值/门槛只允许出现在「」之后的证据段，不得回写进原文。"""
    if not os.path.exists(WO_FILE):
        pytest.skip("工单任务书不在仓库相对位置，逐字对表无法执行")
    rows = _workorder_rows()
    assert sorted(rows) == ["A", "B", "C", "D"], rows
    assert P.WO_ROW == rows, (P.WO_ROW, rows)
    for k, line in zip("DCBA", built["lines"]):
        assert line.startswith("%s层 %s「%s」: " % (k, TIER_CN[k], rows[k])), line


def test_b_layer_is_falsifiable_by_bench_size_only(tmp_path):
    """index_bench_rows: 0 → 基准表空，区间命中 0 行 ⇒ EXPLAIN 证据不成立。"""
    r = _run(tmp_path, "b_off2", index_bench_rows=0)
    ib = r["ev"]["index_bench"]
    assert ib["bench_rows"] == 0 and ib["hits"] == 0
    assert r["crit"]["B"]["explain_evidence"] is False
    assert r["tiers"]["B"] is False and r["tiers"]["D"] is True


def test_a_layer_is_falsifiable_by_config_only(tmp_path):
    """p3_handoff 置空 → 不导出交接文件 ⇒ 闭环证据缺失，A 未达标（B/C/D 不受影响）。"""
    r = _run(tmp_path, "a_off", p3_handoff="")
    hd = r["ev"]["handoff"]
    assert hd["disabled"] is True and hd["exists"] is False and hd["rows"] == 0
    assert not os.path.exists(os.path.join(r["out"], HANDOFF_NAME))
    assert r["crit"]["A"] == {"complex_join_aggregate": True, "p3_handoff": False}
    assert r["tiers"]["B"] is True and r["tiers"]["A"] is False
    assert r["lines"][3].endswith("→ 未达标")
    assert "未启用" in r["lines"][3]


def test_stat_query_threshold_is_a_real_gate(tmp_path):
    """min_stat_queries: 4 > 本项目 3 条 ⇒ D 直接判未达标（门槛不是装饰）。"""
    r = _run(tmp_path, "d_min", min_stat_queries=4)
    assert r["ev"]["stat_queries_available"] == 3
    assert r["crit"]["D"]["stat_queries"] is False
    assert r["tiers"]["D"] is False


# ---------------- ④ 墙钟红线：output/ 不含实测毫秒 ----------------

def test_output_contains_no_wallclock_values(built):
    out = built["out"]
    text_files = [f for f in sorted(os.listdir(out))
                  if f.endswith((".txt", ".json", ".csv"))]
    assert {"report.txt", "result.json", HANDOFF_NAME} <= set(text_files)
    for name in text_files:
        raw = open(os.path.join(out, name), encoding="utf-8").read()
        assert not MS_IN_TEXT.search(raw), "output/%s 混入墙钟数值" % name
        for key in ("before_ms", "after_ms", "speedup_x"):
            assert key not in raw, (name, key)
    raw_result = json.dumps(built["data"])
    assert "p50_ms" not in raw_result and "\"ms\"" not in raw_result


def test_wallclock_timings_live_in_runtime_only(built):
    runtime = os.path.join(os.path.dirname(built["out"]), "runtime")
    bench = json.loads(open(os.path.join(runtime, "bench.json"),
                            encoding="utf-8").read())
    assert os.path.exists(os.path.join(runtime, "bench.db"))
    assert bench["unit"] == "ms" and "墙钟" in bench["note"]
    ib = bench["index_bench"]
    assert isinstance(ib["before_ms"], float) and ib["before_ms"] > 0
    assert isinstance(ib["after_ms"], float) and ib["after_ms"] > 0
    assert ib["speedup_x"] is None or ib["speedup_x"] > 0
    assert all(isinstance(s["ms"], float) for s in bench["slow_queries"])
    assert not os.path.exists(os.path.join(built["out"], "bench.json"))
    assert not os.path.exists(os.path.join(built["out"], "bench.db"))
    assert built["data"]["runtime_files"]["bench"] == "runtime/bench.json"


def test_bench_cache_invalidates_on_config_change(tmp_path):
    """基准参数变更必须重测——否则旧证据会冒充新配置（tiers 就成了橡皮图章）。"""
    r1 = _run(tmp_path, "cache", index_bench_rows=3000)
    assert r1["ev"]["index_bench"]["bench_rows"] == 3000
    assert r1["ev"]["index_bench"]["hits"] == 240
    r2 = _run(tmp_path, "cache", index_bench_rows=1500)   # 同一 out 目录再跑
    assert r2["ev"]["index_bench"]["bench_rows"] == 1500
    assert r2["ev"]["index_bench"]["hits"] == 10          # 区间只覆盖到第 1500 行
    cached = json.loads(open(os.path.join(os.path.dirname(r2["out"]), "runtime",
                                          "bench.json"), encoding="utf-8").read())
    assert cached["params"]["rows"] == 1500


def test_two_runs_agree_on_tiers_and_output(tmp_path):
    a = _run(tmp_path, "rep")
    text1 = a["text"]
    b = _run(tmp_path, "rep")                               # 复用 runtime 缓存
    strip = lambda t: "\n".join(l for l in t.splitlines()
                                if not l.startswith("生成时间"))
    assert b["tiers"] == a["tiers"] == {"D": True, "C": True, "B": True, "A": True}
    assert b["crit"] == a["crit"]
    assert b["lines"] == a["lines"]
    assert strip(b["text"]) == strip(text1)


def test_loader_selectinload_also_satisfies_b_gate(tmp_path):
    """换预加载策略（selectinload）仍是规避：B 层达标，且计数为 2 条 SELECT。"""
    r = _run(tmp_path, "sel", n_plus_one_loader="selectinload")
    assert r["ev"]["n_plus_one"]["eager_sql_count"] == 2
    assert r["crit"]["B"]["n_plus_one_avoided"] is True
    assert r["tiers"]["B"] is True
    assert "selectinload 2 条" in r["lines"][2]
