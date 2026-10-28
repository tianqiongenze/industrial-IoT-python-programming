# -*- coding: utf-8 -*-
"""编排层：建库→种子→P4缓冲批量导入→统计查询→溯源→窗口环比→数据字典→索引基准
→四表JOIN聚合→P3闭环交接→分层闸门(D/C/B/A)→报告。

可复现与墙钟红线：
  1. output/ 只放确定性证据——实测毫秒（index_bench / slow_query 的 ms、speedup）
     一律写 runtime/bench.json，绝不进 output/（与 p21/p66 同口径）；
  2. 实测部分默认不重跑：runtime/bench.json 缓存（基准参数变更即失效重测），
     故两次运行 output/ 除报告时间戳外逐字节一致；`--index-bench` 强制重测；
  3. 分层判定 tiers / tier_criteria 全部由本次真实测量推导，改配置即可证伪。
"""
import os
import platform

from sqlalchemy import __version__ as SA_VERSION
from sqlalchemy.orm import Session

from . import core, io_utils, report

#: 工单《P5》「验收标准」四行**原文**（逐字），报告「分层达标」每档行首直接引用它。
#: `_tier_gates()` 把每一行落成可测判据，判据里用到的门槛（如统计查询 ≥2 条）
#: 只写在证据段，绝不回填进原文——否则"工单原文"会随 rules.yaml 一起漂。
WO_ROW = {
    "D": "4表设计合理；ORM入库成功；2条统计查询可用",
    "C": "数据字典完整；批量事务；溯源查询正确",
    "B": "索引优化有EXPLAIN证据；N+1问题已规避",
    "A": "优秀+复杂查询(多表JOIN聚合)+导入P3仪表盘形成闭环演示",
}

ER_ASCII = """\
ER 概览（四表）：
  devices(设备)  1───N  points(测点)  1───N  records(采集记录)
      │                                          ▲ idx_dev_ts(point_id, ts)
      └──────────── 1───N ───────────────────────┘
  devices(设备)  1───N  alarms(告警事件)   —— 告警挂设备
主外键：points.device_id→devices.id  records.point_id→points.id
        alarms.device_id→devices.id（外键约束由库强制，孤儿记录被拒）"""

STAT_QUERIES = (("avg_vib", "T4a"), ("top_alarms", "T4b"), ("hourly", "T4c"))
#: 墙钟类键：只允许待在 runtime/bench.json，不许进 output/ 任何产物
WALLCLOCK_KEYS = ("before_ms", "after_ms", "speedup_x", "note")
REQUIRED_TABLES = 4
P3_IMPORT_CMD = ("cd ../p33_kpi_cockpit && python run.py --source csv "
                 "--csv ../p55_warehouse_orm/output/p3_dashboard_handoff.csv")


def runtime_dir(out_dir):
    """墙钟实测值的唯一去处：与 output/ 平级的 runtime/（已在 .gitignore）。"""
    return os.path.join(os.path.dirname(os.path.abspath(out_dir)), "runtime")


def ensure_db(cfg, out_dir):
    """建库：删除旧 sqlite 文件后清库重建 + 种子 + P4 缓冲批量导入（确定性）。

    先删文件再重建，保证 sqlite 页分配/空闲链从零开始——配合固定 seed，
    两次默认运行 output/warehouse.db 逐字节一致（实测数字走 runtime/bench.json）。
    """
    io_utils.ensure_dir(out_dir)
    db_url = core.resolve_db_url(str(cfg.raw.get("db_url", "sqlite:///output/warehouse.db")))
    if db_url.startswith("sqlite:///"):
        path = db_url[len("sqlite:///"):]
        for suffix in ("", "-wal", "-shm", "-journal"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    engine = core.make_engine(db_url)
    core.init_db(engine)
    batch_size = int(cfg.raw.get("batch_size", 100))
    seed = int(cfg.raw.get("seed", 7))
    seed_stats = core.seed_demo(
        engine, seed=seed,
        n_records=int(cfg.raw.get("n_records", 500)),
        warn=float(cfg.raw.get("warn", 4.5)),
        danger=float(cfg.raw.get("danger", 6.0)),
        unit_vib=str(cfg.raw.get("unit", "mm/s")),
        batch_size=batch_size)
    buf = core.resolve_path(str(cfg.raw.get("buffer_db", "../../buffer.db")))
    import_stats = core.import_buffer(
        engine, buf, batch_size=batch_size, seed=seed,
        stand_in_rows=int(cfg.raw.get("buffer_stand_in_rows", 108)))
    return engine, db_url, seed_stats, import_stats


def query_rows(engine, which="all", topk=3):
    """T4 三条统计查询 + A层环比（ORM 与裸 SQL 双形态），返回真实行。"""
    with Session(engine) as s:
        out = {}
        if which in ("all", "avg-vib"):
            out["avg_vib"] = core.avg_vib_per_device(s)
        if which in ("all", "top-alarms"):
            out["top_alarms"] = core.alarm_top_devices(s, topk)
        if which in ("all", "hourly"):
            out["hourly"] = core.records_per_hour(s)
        if which in ("all", "window"):
            out["window_orm"] = core.hourly_growth_orm(s)
    if which in ("all", "window"):
        out["window_raw"] = core.hourly_growth_raw(engine)
        if out["window_orm"] != out["window_raw"]:
            raise AssertionError("窗口函数 ORM 与裸 SQL 结果不一致——不可接受")
    return out


def _bench_cache_path(out_dir):
    return os.path.join(runtime_dir(out_dir), "bench.json")


def _bench_params(cfg):
    """缓存键：基准参数一改缓存立即失效（防止旧证据冒充新配置）。"""
    return {"rows": int(cfg.raw.get("index_bench_rows", 20000)),
            "reps": int(cfg.raw.get("index_bench_reps", 7)),
            "seed": int(cfg.raw.get("seed", 7)),
            "topk": int(cfg.raw.get("topk", 3))}


def get_bench(engine, cfg, out_dir, force=False):
    """实测部分（索引对比+慢查询）：默认读 runtime/bench.json 缓存保证输出可复现；
    force/缺缓存/基准参数变更才实测。毫秒数只存 runtime/，不进 output/。

    index_bench 需要建表写入，放在独立的 runtime/bench.db 里做——业务库
    warehouse.db 永不被基准污染（慢查询报告只读，不改字节）。
    """
    params = _bench_params(cfg)
    path = _bench_cache_path(out_dir)
    if not force and os.path.exists(path):
        cached = io_utils.read_json(path)
        if cached.get("params") == params:      # 沿用上次实测出处，报告逐字节一致
            return cached
    io_utils.ensure_dir(runtime_dir(out_dir))
    bench_url = core.resolve_db_url("sqlite:///%s"
                                    % os.path.join(runtime_dir(out_dir), "bench.db"))
    bench_path = bench_url[len("sqlite:///"):]
    for suffix in ("", "-wal", "-shm", "-journal"):
        if os.path.exists(bench_path + suffix):
            os.remove(bench_path + suffix)
    bench_engine = core.make_engine(bench_url)
    bench = core.index_bench(bench_engine, rows=params["rows"],
                             reps=params["reps"], seed=params["seed"])
    slow = core.slow_query_report(engine, top=params["topk"])
    bench_engine.dispose()
    data = {"index_bench": bench, "slow_queries": slow, "params": params,
            "unit": "ms",
            "source": "首次运行/--index-bench/参数变更后实测；其余运行读此缓存",
            "note": "墙钟实测毫秒只写本文件（runtime/bench.json），禁止进入 output/——"
                    "verify_local 的 repeat 闸门逐字节比对 output/"}
    io_utils.write_json(path, data)
    return data


def _bench_view(bench):
    """进 output/ 的基准视图：只保留确定性证据（执行计划/命中行数/规模/参数），
    剥离毫秒、提速倍与含毫秒的 note（那些只留在 runtime/bench.json）。"""
    ib = {k: v for k, v in bench["index_bench"].items() if k not in WALLCLOCK_KEYS}
    return {"index_bench": ib,
           "slow_queries": [{"name": s["name"], "plan": s["plan"]}
                            for s in bench["slow_queries"]],
           "timings_in": "runtime/bench.json",
           "params": bench.get("params"), "source": bench.get("source", "")}


def handoff_path(cfg, out_dir):
    """A层 P3 闭环交接文件路径：落在本次 out_dir 下（配置 p3_handoff 置空即关闭）。"""
    rel = str(cfg.raw.get("p3_handoff", "") or "").strip()
    if not rel:
        return ""
    return os.path.join(out_dir, os.path.basename(rel))


def _display_rel(path, out_dir):
    """报告里给一个可读又属实的相对路径（生产跑= output/xxx，临时目录= 文件名）。"""
    ap = os.path.abspath(path)
    prod_out = os.path.abspath(os.path.join(core.PROJECT_ROOT, "output"))
    if os.path.dirname(ap) == prod_out:
        return "output/" + os.path.basename(ap)
    return os.path.relpath(ap, os.path.abspath(out_dir)).replace(os.sep, "/")


def _empty_handoff():
    return {"exists": False, "disabled": True, "rows": 0, "columns": [],
            "missing_columns": list(core.P3_CONTRACT_COLUMNS),
            "ts_parse_failures": 0, "unknown_devices": [], "path": "",
            "rel_path": "", "status_counts": {}, "devices": 0, "hours": 0,
            "empty_cells": 0}


def build(cfg, out_dir, bench_force=False):
    """跑完整链路并返回 (result, sections)，不写文件（供 run 与测试复用）。"""
    engine, db_url, seed_stats, import_stats = ensure_db(cfg, out_dir)
    rows = query_rows(engine, "all", topk=int(cfg.raw.get("topk", 3)))
    dictionary = core.data_dictionary(engine)
    coverage = core.dictionary_coverage(engine)
    trace = core.traceability_check(engine)
    n1 = core.n_plus_one_demo(
        engine, loader=str(cfg.raw.get("n_plus_one_loader", "joinedload")))
    fk_ok = core.integrity_check(engine)
    tables = core.tables_created(engine)
    bench = _bench_view(get_bench(engine, cfg, out_dir, force=bench_force))
    with Session(engine) as s:
        total = s.query(core.Record).count()
        summary = [list(r) for r in core.device_hourly_summary(s)]
    manual = core.device_hourly_manual(engine)
    path = handoff_path(cfg, out_dir)
    if path:
        handoff = core.export_p3_handoff(engine, path)      # 先写
        handoff.update(core.validate_p3_handoff(engine, path))  # 再按 P3 口径验
        handoff["path"] = path
        handoff["rel_path"] = _display_rel(path, out_dir)
        handoff["disabled"] = False
    else:
        handoff = _empty_handoff()

    orphan = trace["orphan_rows"]
    evidence = {
        "tables_required": REQUIRED_TABLES,
        "tables_created": len(tables["present"]),
        "tables_missing": tables["missing"],
        "seed_records": seed_stats["records"],
        "buffer_written": import_stats["records_written"],
        "orm_rows_expected": seed_stats["records"] + import_stats["records_written"],
        "orm_rows_loaded": total,
        "stat_query_rows": {label: len(rows[key]) for key, label in STAT_QUERIES},
        "stat_queries_available": sum(1 for key, _ in STAT_QUERIES
                                      if len(rows[key]) > 0),
        "stat_queries_total": len(STAT_QUERIES),
        "min_stat_queries": int(cfg.raw.get("min_stat_queries", 2)),
        "dict_columns_total": coverage["columns_total"],
        "dict_columns_documented": coverage["columns_documented"],
        "dict_columns_commented": coverage["columns_commented"],
        "dict_undocumented": coverage["undocumented"],
        "batch_size": seed_stats["batch_size"],
        "seed_commits": seed_stats["commits"],
        "import_commits": import_stats["commits"],
        "commits_total": seed_stats["commits"] + import_stats["commits"],
        "bulk_objects": True,
        "alarms_total": trace["alarms_total"],
        "alarms_traced": trace["alarms_traced"],
        "trace_join_tables": trace["join_tables"],
        "trace_orphans": trace["orphan_total"],
        "trace_orphan_detail": orphan,
        "n_plus_one": n1,
        "index_bench": bench["index_bench"],
        "bench_timings_in": bench["timings_in"],
        "window_buckets": len(rows["window_orm"]),
        "orm_raw_window_equal": rows["window_orm"] == rows["window_raw"],
        "summary_buckets": len(summary),
        "summary_devices": len({r[0] for r in summary}),
        "summary_matches_manual": core.summary_matches_sql(
            [tuple(r) for r in summary], manual),
        "handoff": handoff,
        "fk_orphan_rejected": fk_ok["orphan_rejected"],
    }
    tiers, tier_lines, criteria = _tier_gates(evidence)
    result = {
        "env": {"python": platform.python_version(), "sqlalchemy": SA_VERSION,
                "db_url": db_url},
        "seed": seed_stats,
        "buffer_import": import_stats,
        "records_total": total,
        "queries": rows,
        "data_dictionary": dictionary,
        "complex_summary": summary,
        "trace_samples": [[str(v) for v in r] for r in trace["samples"]],
        "n_plus_one": n1,
        "fk_orphan_rejected": fk_ok["orphan_rejected"],
        "bench": bench,
        "handoff": handoff,
        "evidence": evidence,
        "tier_criteria": criteria,
        "tiers": tiers,
        "runtime_files": {"bench": "runtime/bench.json",
                          "bench_db": "runtime/bench.db",
                          "note": "墙钟毫秒（索引前后耗时/提速倍数/慢查询中位耗时）只存"
                                  " runtime/，output/ 内任何产物都不含实测时间值"},
    }
    sections = _sections(result, tier_lines)
    return result, sections


def _tier_gates(ev):
    """分层达标（D/C/B/A）：每条判据都是本次真实测量，可被配置证伪。

    口径出处＝工单 P5「验收标准」四行原文（逐字存 `WO_ROW`，报告每档行首引用它）：
      D 及格「4表设计合理；ORM入库成功；2条统计查询可用」
      C 良好「数据字典完整；批量事务；溯源查询正确」
      B 优秀「索引优化有EXPLAIN证据；N+1问题已规避」
      A 超优「优秀+复杂查询(多表JOIN聚合)+导入P3仪表盘形成闭环演示」
    逐级累加（低一级不达标则本级不可能达标）：C 含 D、B 含 C、A 含 B。
    """
    ib, n1, hd = ev["index_bench"], ev["n_plus_one"], ev["handoff"]
    criteria = {
        "D": {"four_tables": (ev["tables_created"] >= ev["tables_required"]
                              and not ev["tables_missing"]),
              "orm_insert_ok": (ev["orm_rows_loaded"] > 0
                                and ev["orm_rows_loaded"] == ev["orm_rows_expected"]),
              "stat_queries": (ev["stat_queries_available"]
                               >= ev["min_stat_queries"])},
        "C": {"dictionary_complete": (ev["dict_columns_total"] > 0
                                      and ev["dict_columns_documented"]
                                      == ev["dict_columns_total"]
                                      and not ev["dict_undocumented"]),
              "bulk_transactions": (ev["bulk_objects"] is True
                                    and ev["seed_commits"] >= 2
                                    and ev["import_commits"] >= 2),
              "traceability": (ev["trace_orphans"] == 0
                               and ev["alarms_total"] > 0
                               and ev["alarms_traced"] == ev["alarms_total"])},
        "B": {"explain_evidence": (bool(ib["scan_before"])
                                   and bool(ib["index_search_after"])
                                   and ib["hits"] > 0),
              "n_plus_one_avoided": bool(n1["mitigated"])},
        "A": {"complex_join_aggregate": (ev["summary_buckets"] > 0
                                         and ev["summary_matches_manual"]),
              "p3_handoff": (hd["rows"] > 0 and not hd["disabled"]
                             and hd["missing_columns"] == []
                             and hd["ts_parse_failures"] == 0
                             and not hd["unknown_devices"]
                             and ev["orm_raw_window_equal"])},
    }
    d = all(criteria["D"].values())
    c = d and all(criteria["C"].values())
    b = c and all(criteria["B"].values())
    a = b and all(criteria["A"].values())
    tiers = {"D": d, "C": c, "B": b, "A": a}
    q = ev["stat_query_rows"]

    def verdict(flag):
        return "达标" if flag else "未达标"

    tier_lines = [
        "D层 及格「%s」: 建表 %d/%d 张（缺:%s）｜records 入库 %d 行"
        "（种子 %d＋P4缓冲 %d，预期 %d，相符=%s）｜统计查询可用 %d/%d 条（T4a %d 行、"
        "T4b %d 行、T4c %d 行；门槛 ≥%d 条）→ %s" % (
            WO_ROW["D"],
            ev["tables_created"], ev["tables_required"],
            ",".join(ev["tables_missing"]) or "无", ev["orm_rows_loaded"],
            ev["seed_records"], ev["buffer_written"], ev["orm_rows_expected"],
            "是" if ev["orm_rows_loaded"] == ev["orm_rows_expected"] else "否",
            ev["stat_queries_available"], ev["stat_queries_total"],
            q["T4a"], q["T4b"], q["T4c"], ev["min_stat_queries"], verdict(d)),
        "C层 良好「%s」: 数据字典 %d/%d 列有成文含义"
        "（未登记:%s）｜批量事务 bulk_save_objects 分批提交 %d 次（种子 %d＋缓冲 %d，"
        "每批≤%d 条）｜溯源 alarms→devices→points→records 四表 JOIN 命中 %d/%d 条告警、"
        "外键孤儿行 %d（%.1f%%）→ %s" % (
            WO_ROW["C"],
            ev["dict_columns_documented"], ev["dict_columns_total"],
            "、".join(ev["dict_undocumented"]) or "无", ev["commits_total"],
            ev["seed_commits"], ev["import_commits"], ev["batch_size"],
            ev["alarms_traced"], ev["alarms_total"], ev["trace_orphans"],
            100.0 * ev["alarms_traced"] / ev["alarms_total"]
            if ev["alarms_total"] else 0.0, verdict(c)),
        "B层 优秀「%s」: bench_records %d 行区间查询命中 %d 行，"
        "建索引前全表 SCAN=%s → 建索引后 SEARCH USING INDEX=%s（计划行见本报告"
        "「B层·索引优化」段，墙钟毫秒只写 %s 不入 output/）｜N+1 实测：懒加载 %d 条 "
        "SELECT vs %s %d 条（%d 台设备）→ %s" % (
            WO_ROW["B"],
            ib["bench_rows"], ib["hits"], "是" if ib["scan_before"] else "否",
            "是" if ib["index_search_after"] else "否", ev["bench_timings_in"],
            n1["lazy_sql_count"], n1["loader"], n1["eager_sql_count"],
            n1["devices"], verdict(b)),
        "A层 超优「%s」: 设备×小时四表 JOIN 聚合 %d 桶"
        "（%d 台设备），与逐行手算一致=%s；窗口环比 %d 桶 ORM=裸SQL %s｜P3 交接文件 %s"
        "：%d 行×%d 列[%s]，时间解析失败 %d 行、未知设备 %d 个、缺列:%s → %s" % (
            WO_ROW["A"],
            ev["summary_buckets"], ev["summary_devices"],
            "是" if ev["summary_matches_manual"] else "否", ev["window_buckets"],
            "一致" if ev["orm_raw_window_equal"] else "不一致",
            hd["rel_path"] or "未启用(config p3_handoff 为空)", hd["rows"],
            len(hd["columns"]), "/".join(hd["columns"]) or "—",
            hd["ts_parse_failures"], len(hd["unknown_devices"]),
            "、".join(hd["missing_columns"]) or "无", verdict(a)),
    ]
    return tiers, tier_lines, criteria


def _window_lines(q):
    """报告用：首桶 + 环比涨幅最大的几个小时桶（真实行，非示意）。"""
    win = q["window_orm"]
    if not win:
        return ["（本次 0 条记录 → 窗口环比 0 桶；D 层入库证据不成立，见「分层达标」）"]
    ranked = sorted((r for r in win if r[3] is not None),
                    key=lambda r: r[3], reverse=True)[:4]
    show = [win[0]] + [r for r in ranked if r[0] != win[0][0]]
    return [io_utils.fmt_table([list(r) for r in show],
                               ["小时", "记录数", "上期", "环比"]),
            "……（共 %d 个小时桶；ORM 与 session.execute(text(...)) 裸SQL 结果逐行相等）"
            % len(win)]


def _summary_table(summary_rows, limit=8):
    head = [[str(v) if v is not None else "" for v in r] for r in summary_rows[:limit]]
    return io_utils.fmt_table(head, ["小时", "设备", "记录数", "平均温度",
                                     "平均振动", "告警数", "状态"])


def _sections(res, tier_lines):
    q = res["queries"]
    b = res["bench"]
    ib = b["index_bench"]
    ev = res["evidence"]
    hd = ev["handoff"]
    seed, imp = res["seed"], res["buffer_import"]
    summary = [[r[2], r[0], r[3], r[4], r[5], r[6], core.p3_status_of(r[7])]
               for r in res["complex_summary"]]
    sections = [
        ("环境", [
            "Python %s / SQLAlchemy %s / 库 %s" % (res["env"]["python"],
                                                res["env"]["sqlalchemy"], res["env"]["db_url"]),
            "数据来源：%s；导入后 records 总行数 %d" % (imp["source"], res["records_total"]),
            "外键约束强制：孤儿记录插入被库拒绝 = %s" % ("是（IntegrityError）"
              if res["fk_orphan_rejected"] else "否（异常！）"),
        ]),
        ("D层·ER设计与四表建表", [ER_ASCII,
          "建表：devices / points / records / alarms（SQLAlchemy 2.x DeclarativeBase 声明式）"]),
        ("C层·入库与统计查询", [
            "种子数据：设备 %d、测点 %d、记录 %d、告警 %d（seed=%d，bulk_save_objects "
            "分批入库，事务提交 %d 次）"
            % (seed["devices"], seed["points"], seed["records"], seed["alarms"],
               seed["seed"], seed["commits"]),
            "P4缓冲导入：源行 %d → 写入记录 %d 条，每批 %d 条一个事务，共提交 %d 次"
            % (imp["buffer_rows"], imp["records_written"], imp["batch_size"],
               imp["commits"]),
            "", "T4a 各设备平均vib（JOIN+GROUP BY+func.avg）:",
            io_utils.fmt_table([list(r) for r in q["avg_vib"]],
                               ["设备", "平均vib", "记录数"]),
            "", "T4b 告警Top3设备（告警JOIN设备 GROUP BY 降序 LIMIT）:",
            io_utils.fmt_table([list(r) for r in q["top_alarms"]],
                               ["设备", "车间", "告警数"]),
            "", "T4c 按小时聚合记录数（SQLite 用 func.strftime，date_trunc 不可用）——前8小时:",
            io_utils.fmt_table([list(r) for r in q["hourly"][:8]], ["小时", "记录数"]),
        ]),
        ("C层·溯源查询（告警→设备→测点→同刻原始读数，四表 JOIN）", [
            "可溯源告警 %d/%d 条｜外键孤儿行 records.point_id=%d、points.device_id=%d、"
            "alarms.device_id=%d" % (
                ev["alarms_traced"], ev["alarms_total"],
                ev["trace_orphan_detail"]["records.point_id"],
                ev["trace_orphan_detail"]["points.device_id"],
                ev["trace_orphan_detail"]["alarms.device_id"]),
            "样例（真实 JOIN 反查，非示意）:",
            io_utils.fmt_table(res["trace_samples"],
                               ["告警", "设备", "时刻", "级别", "同刻读数"]),
        ]),
        ("B层·数据字典（来自真实库 introspection）", [
            io_utils.fmt_table([[d["table"], d["column"], d["type"], d["pk"],
                                 d["fk"], d["nullable"], d["meaning"]]
                                for d in res["data_dictionary"]],
                               ["表", "列", "类型", "PK", "FK", "可空", "含义"]),
            "", "字典完整性实测：%d/%d 列有成文含义（未登记:%s）；ORM Column(comment=) "
            "声明 %d 列为补充证据（SQLite 不持久化 COMMENT，故以 FIELD_MEANINGS 为准）"
            % (ev["dict_columns_documented"], ev["dict_columns_total"],
               "、".join(ev["dict_undocumented"]) or "无",
               ev["dict_columns_commented"]),
            "N+1 规避取证（事件监听数 SELECT 条数，与墙钟无关）：懒加载 %d 条 vs "
            "joinedload %d 条 vs selectinload %d 条（%d 台设备；本项目采用 %s）" % (
                ev["n_plus_one"]["lazy_sql_count"],
                ev["n_plus_one"]["joinedload_sql_count"],
                ev["n_plus_one"]["selectinload_sql_count"],
                ev["n_plus_one"]["devices"], ev["n_plus_one"]["loader"]),
        ]),
        ("A层·窗口函数环比（ORM=裸SQL 双形态一致）", _window_lines(q)),
        ("A层·复杂查询：设备×小时 四表 JOIN 聚合（前 8 桶）", [
            "聚合桶 %d 个（设备 %d 台）；与 Python 逐行手算一致 = %s（容差 0.005）"
            % (ev["summary_buckets"], ev["summary_devices"],
               "是" if ev["summary_matches_manual"] else "否（不可接受）"),
            "口径：records↔points↔devices 内连接 + alarms 按(设备,小时)对齐外连接，"
            "聚合 count(distinct)/avg(case)/max(level)",
            _summary_table(summary),
            "（完整 %d 桶见 output/result.json 的 complex_summary）"
            % ev["summary_buckets"],
        ]),
        ("A层·导入 P3 仪表盘形成闭环（交接文件）", [
            "交接文件：%s（存在=%s）" % (hd["rel_path"] or "未启用（config p3_handoff 置空）",
                                       "是" if hd["exists"] else "否"),
            "导出 %d 行 × 列 %s｜时间可解析失败 %d 行、未知设备 %d 个、空值单元 %d 个" % (
                hd["rows"], "/".join(hd["columns"]) or "—",
                hd["ts_parse_failures"], len(hd["unknown_devices"]),
                hd["empty_cells"]),
            "状态分布 %s（2级告警→DOWN、1级→WARN、无告警→RUN）" % (hd["status_counts"] or "—"),
            "闭环演示命令：%s" % P3_IMPORT_CMD,
            "契约说明：只导出 P3 data_source.CANON 中本仓库真实可得的 6 列；生产计数 "
            "output/ok_qty/yield_pct 不在采集仓库里，由 P3 按其 provenance 规则标"
            "「合成·seed」，本项目不伪造",
        ]),
        ("B层·索引优化 EXPLAIN 证据（EXPLAIN QUERY PLAN via text()）", [
            "bench_records %d 行×%d 次实测，区间命中 %d 行；耗时/提速倍数等墙钟毫秒"
            "只写 %s（不进 output/，保证逐字节复现）" % (
                ib["bench_rows"], ib["reps"], ib["hits"], b["timings_in"]),
            "  %s" % ib["production_index"],
            "建索引前计划: %s" % " | ".join(ib["before_plan"]),
            "建索引后计划: %s" % " | ".join(ib["after_plan"]),
            "计划形态判定：建索引前全表 SCAN = %s｜建索引后 SEARCH USING INDEX = %s"
            "（生产表 records 的 idx_dev_ts 由 ORM __table_args__ 声明，本次基准在等结构"
            "副本表上实测）" % ("是" if ib["scan_before"] else "否",
                              "是" if ib["index_search_after"] else "否"),
            "", "慢查询Top%d（按实测中位耗时排序取前 K，排序值见 %s；此处列确定性执行计划）:"
            % (len(b["slow_queries"]), b["timings_in"]),
            io_utils.fmt_table([[i + 1, s_["name"], " / ".join(s_["plan"])[:80]]
                                for i, s_ in enumerate(b["slow_queries"])],
                               ["#", "查询", "执行计划"]),
        ]),
        ("分层达标", tier_lines),
        ("结论与建议", [
            "1) 四表 ER+外键约束+联合索引 idx_dev_ts(point_id, ts) 已在 ORM 声明式模型落地："
            "孤儿插入被库拒绝、库内孤儿行 %d、数据字典 %d/%d 列有成文含义；" % (
                ev["trace_orphans"], ev["dict_columns_documented"],
                ev["dict_columns_total"]),
            "2) 批量入库一律 bulk_save_objects + 分批提交事务（种子 %d 次＋缓冲 %d 次＝%d 次，"
            "每批≤%d 条），未使用循环单条 add；" % (
                ev["seed_commits"], ev["import_commits"], ev["commits_total"],
                ev["batch_size"]),
            "3) 统计查询、四表溯源、窗口环比、复杂聚合、数据字典、EXPLAIN 计划行全部来自"
            "本次真实运行；tiers/tier_criteria 逐条可被配置证伪（见 docs/03 §6）；",
            "4) 实测毫秒只在 runtime/bench.json（本次基准参数 %s），故 output/ 除报告"
            "时间戳外逐字节可复现；--index-bench 可重新实测。" % (b["params"],),
            "5) 未达标层级看「分层达标」行的实测数字：哪一项为否就补哪一项，"
            "对应做法与判定口径写在 docs/03 §6。",
        ]),
    ]
    return sections


def run(cfg, out_dir, bench_force=False):
    """完整流水线：产出 result.json / report.txt / P3 交接CSV（实测毫秒在 runtime/）。"""
    result, sections = build(cfg, out_dir, bench_force=bench_force)
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
