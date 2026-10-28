# -*- coding: utf-8 -*-
"""数据仓库核心层：引擎/种子入库/P4缓冲批量导入/统计查询/窗口函数/数据字典/索引基准/N+1取证。

工程口径（对应工单 P5 与starter任务卡 T3/T4/T5）：
  T3 种子数据   —— seed_demo：3设备×各2测点 + n_records 条记录，vib 超阈值触发告警
  T4 统计查询   —— avg_vib_per_device / alarm_top_devices / records_per_hour（真实返回行）
  T5 索引优化   —— index_bench：建索引前后实测耗时 + sqlalchemy text() 取
                   EXPLAIN QUERY PLAN 真实行；小数据集若无加速会如实报告
批量入库一律 bulk_save_objects + 每批提交事务（工单工程化要求3，禁循环单条 add）。
分层闸门（D/C/B/A）取证函数：dictionary_coverage / traceability_check /
n_plus_one_demo / index_bench / device_hourly_summary / export_p3_handoff。
"""
import datetime as dt
import math
import os
import random
import sqlite3
import statistics
import time

from sqlalchemy import (and_, case, create_engine, distinct, event, func,
                        inspect, select, text)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from . import io_utils
from .models import (AlarmEvent, Base, Device, MODEL_TABLES, Record,
                     SensorPoint)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 数据字典「含义」列：与 docs/03 ER 图一致的成文契约（B层·数据字典完整）
FIELD_MEANINGS = {
    ("devices", "id"): "设备主键",
    ("devices", "code"): "设备编号（唯一，如 DEV-01）",
    ("devices", "name"): "设备名称",
    ("devices", "area"): "车间：设备归属产线车间",
    ("points", "id"): "测点主键",
    ("points", "device_id"): "外键→devices.id（设备1-N测点）",
    ("points", "metric"): "测点类型：temp=温度 / vib=振动",
    ("points", "unit"): "工程单位（℃ / mm·s⁻¹）",
    ("records", "id"): "记录主键",
    ("records", "point_id"): "外键→points.id（联合索引最左列）",
    ("records", "ts"): "采集时刻（UTC，DateTime 列，不存字符串）",
    ("records", "value"): "测点读数",
    ("alarms", "id"): "告警主键",
    ("alarms", "device_id"): "外键→devices.id（告警挂设备）",
    ("alarms", "ts"): "告警发生时刻",
    ("alarms", "level"): "级别：1=超预警线 2=超危险线",
    ("alarms", "message"): "告警描述",
    ("alarms", "resolved"): "是否已消警",
}

DEMO_DEVICES = [
    ("DEV-01", "贴片机1号", "SMT车间A"),
    ("DEV-02", "回流焊炉2号", "SMT车间B"),
    ("DEV-03", "注塑机3号", "装配车间C"),
]
DEMO_BASE_TS = dt.datetime(2026, 4, 1, 0, 0)

# A层闭环交接契约：p33_kpi_cockpit/src/kpi_cockpit/data_source.py 的 CANON 中，
# 本仓库能真实供给的 6 列（output/ok_qty/yield_pct 属生产计数，仓库里没有，
# 由 P3 按自身 from_clean 口径标注"合成·seed"，本项目不伪造）。
P3_CONTRACT_COLUMNS = ("ts", "device_id", "line", "temp", "vib", "status")
# P3 的 _DT_FORMATS 同序同值（data_source.py:19）：交接文件时间必须落在其中
P3_TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                 "%Y-%m-%d")


def resolve_db_url(url, project_root=PROJECT_ROOT):
    """把配置里的相对 sqlite:///output/warehouse.db 绝对化到本项目目录。

    保证写入只落在项目自身 output/，永不写入课程根目录。
    """
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
        if not os.path.isabs(path):
            return prefix + os.path.abspath(os.path.join(project_root, path))
    return url


def resolve_path(path, project_root=PROJECT_ROOT):
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(project_root, path))


def make_engine(db_url, echo=False):
    """建引擎并强制开启 SQLite 外键约束（PRAGMA foreign_keys=ON）。"""
    engine = create_engine(db_url, echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def init_db(engine, fresh=True):
    """建表：fresh=True 先 drop_all 保证每次运行从干净库出发（可复现）。"""
    if fresh:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return engine


def tables_created(engine):
    """D层取证：真实库里已存在的业务表名（inspector 读取，不看代码声明）。"""
    names = set(inspect(engine).get_table_names())
    return {"present": sorted(m for m in MODEL_TABLES if m in names),
            "missing": sorted(m for m in MODEL_TABLES if m not in names)}


def seed_demo(engine, seed=7, n_records=500, warn=4.5, danger=6.0,
              unit_vib="mm/s", batch_size=100):
    """种子数据（B层步骤1-2）：3设备×各2测点 + n_records 条记录。

    确定性：random.Random(seed) 高斯抽样；ts 从固定基线每分钟推进一条。
    vib 读数 ≥warn 触发1级告警、≥danger 触发2级告警（约5%样本越线）。
    记录用 bulk_save_objects 分批提交（每批 batch_size 条一个事务）。
    """
    rng = random.Random(seed)
    commits = 0
    with Session(engine) as s:
        devices = [Device(code=c, name=n, area=a) for c, n, a in DEMO_DEVICES]
        s.add_all(devices)
        s.flush()
        points = []
        for d in devices:
            points.append(SensorPoint(device_id=d.id, metric="temp", unit="℃"))
            points.append(SensorPoint(device_id=d.id, metric="vib", unit=unit_vib))
        s.add_all(points)
        s.commit()
        # 测点归属一律按 relationship 回读真实外键，不靠列表顺序猜：
        # 早前写法 zip(devices * 2, points) 里 `devices * 2` 是【序列重复】
        # [D1,D2,D3,D1,D2,D3] 而非逐设备重复 [D1,D1,D2,D2,...]，
        # 映射会错位——记录挂到别的设备的测点上，溯源/均值统计随之失真（C层缺陷）。
        pt_of = {(p.device.code, p.metric): p.id for p in points}
        dev_of = {d.code: d.id for d in devices}

        rows, alarms = [], []
        for i in range(n_records):
            dev_code = DEMO_DEVICES[i % 3][0]
            ts = DEMO_BASE_TS + dt.timedelta(minutes=i)
            if i % 2 == 0:  # 偶数槽=振动，奇数槽=温度
                value = max(0.0, round(rng.gauss(3.6, 1.15), 3))
                level = 2 if value >= danger else (1 if value >= warn else 0)
                if level:
                    alarms.append(AlarmEvent(
                        device_id=dev_of[dev_code],
                        ts=ts, level=level,
                        message="vib=%.3f 超%s线(%.1f)" % (value,
                                "危险" if level == 2 else "预警",
                                danger if level == 2 else warn)))
            else:
                value = round(rng.gauss(62.0, 8.0), 2)
                level = 0
            rows.append(Record(point_id=pt_of[(dev_code, "vib" if i % 2 == 0 else "temp")],
                               ts=ts, value=value))
        for start in range(0, len(rows), batch_size):
            s.bulk_save_objects(rows[start:start + batch_size])
            s.commit()                       # 每批一个事务（工单工程化要求3）
            commits += 1
        s.add_all(alarms)
        s.commit()
        stats = {
            "devices": s.query(Device).count(),
            "points": s.query(SensorPoint).count(),
            "records": s.query(Record).count(),
            "alarms": s.query(AlarmEvent).count(),
            "seed": seed, "n_records": n_records,
            "warn": warn, "danger": danger,
            # C层批量事务取证：真实提交次数（bulk 分批，非循环单条 add）
            "commits": commits, "batch_size": batch_size,
        }
    return stats


def _buffer_rows(buffer_path, seed, stand_in_rows=108):
    """读 P4 缓冲库；文件缺失时用内置确定性替代源（seed 生成同构行）。

    行数由配置 buffer_stand_in_rows 决定（默认 108）——设 0 即"无缓冲数据"，
    分层闸门会据此判 D 层不达标，而不是把空库硬说成达标。
    """
    if buffer_path and os.path.exists(buffer_path):
        con = sqlite3.connect("file:%s?mode=ro" % buffer_path, uri=True)
        try:
            rows = con.execute(
                "SELECT source, ts, temp, vib FROM records ORDER BY rowid").fetchall()
        finally:
            con.close()
        return rows, "P4缓冲库 %s（%d 行）" % (os.path.basename(buffer_path), len(rows))
    rng = random.Random(seed)
    rows = []
    base = 1791804937.0
    for i in range(int(stand_in_rows)):
        rows.append(("plc@%d" % (5020 + i % 3), base + i * 0.2,
                      round(rng.gauss(62.0, 8.0), 1), round(rng.gauss(3.6, 1.1), 1)))
    return rows, "内置确定性替代源（buffer.db 不存在，seed=%d 生成 %d 行）" % (
        seed, len(rows))


def import_buffer(engine, buffer_path, batch_size=100, seed=7, stand_in_rows=108):
    """P4 缓冲入库（C层→B层步骤2）：每条缓冲行拆 temp+vib 两条记录，
    每批 batch_size 条提交一次事务（bulk_save_objects，禁逐条 add）。"""
    rows, source_note = _buffer_rows(buffer_path, seed, stand_in_rows)
    with Session(engine) as s:
        devices = s.query(Device).order_by(Device.code).all()
        if not devices:
            raise RuntimeError("请先 seed_demo 建设备/测点，再导入缓冲数据")
        pts = {}
        for d in devices:
            for p in d.points:
                pts[(d.code, p.metric)] = p.id
        codes = [d.code for d in devices]
        pending = []
        commits = 0
        imported = 0
        for source, ts_epoch, temp, vib in rows:
            # 稳定的散列映射：同一 source 恒落同一设备（内置 hash() 随
            # PYTHONHASHSEED 变化，会破坏可复现性，故用 hash_of）
            dev = codes[hash_of(source) % len(codes)]
            ts = dt.datetime.fromtimestamp(ts_epoch, dt.timezone.utc).replace(tzinfo=None)
            pending.append(Record(point_id=pts[(dev, "temp")], ts=ts, value=float(temp)))
            pending.append(Record(point_id=pts[(dev, "vib")], ts=ts, value=float(vib)))
            while len(pending) >= batch_size:
                chunk, pending = pending[:batch_size], pending[batch_size:]
                s.bulk_save_objects(chunk)
                s.commit()
                commits += 1
                imported += len(chunk)
        if pending:
            s.bulk_save_objects(pending)
            s.commit()
            commits += 1
            imported += len(pending)
    return {"source": source_note, "buffer_rows": len(rows),
            "records_written": imported, "batch_size": batch_size,
            "commits": commits}


def hash_of(text):
    """稳定字符串散列（不用内置 hash()，它随 PYTHONHASHSEED 变化，破坏可复现性）。"""
    acc = 0
    for ch in str(text):
        acc = (acc * 131 + ord(ch)) % 1_000_003
    return acc


# ---------------- 统计查询（C层步骤3 / starter任务卡 T4，真实返回行） ----------------

def avg_vib_per_device(session):
    """T4a 各设备平均vib：Device↔SensorPoint↔Record 三表 JOIN + GROUP BY + func.avg。"""
    stmt = (select(Device.code, func.round(func.avg(Record.value), 4),
                   func.count(Record.id))
            .select_from(Record)
            .join(SensorPoint, Record.point_id == SensorPoint.id)
            .join(Device, SensorPoint.device_id == Device.id)
            .where(SensorPoint.metric == "vib")
            .group_by(Device.code)
            .order_by(Device.code))
    return [tuple(r) for r in session.execute(stmt)]


def alarm_top_devices(session, topk=3):
    """T4b 告警Top3设备：告警 JOIN 设备 GROUP BY 计数，按次数降序取前 topk。"""
    cnt = func.count(AlarmEvent.id)
    stmt = (select(Device.code, Device.area, cnt)
            .select_from(AlarmEvent)
            .join(Device, AlarmEvent.device_id == Device.id)
            .group_by(Device.code, Device.area)
            .order_by(cnt.desc(), Device.code)
            .limit(topk))
    return [tuple(r) for r in session.execute(stmt)]


def records_per_hour(session):
    """T4c 按小时聚合记录数：SQLite 无 date_trunc → func.strftime('%Y-%m-%d %H:00')。"""
    hour = func.strftime("%Y-%m-%d %H:00", Record.ts).label("hour")
    stmt = (select(hour, func.count(Record.id))
            .group_by(hour).order_by(hour))
    return [tuple(r) for r in session.execute(stmt)]


def hourly_growth_orm(session):
    """A层·窗口函数按小时聚合+环比（ORM 形态）：func.lag().over() 生成 LAG。"""
    hour = func.strftime("%Y-%m-%d %H:00", Record.ts).label("hour")
    sub = select(hour.label("hour"), func.count(Record.id).label("cnt")) \
        .group_by("hour").subquery()
    prev = func.lag(sub.c.cnt).over(order_by=sub.c.hour).label("prev_cnt")
    stmt = (select(sub.c.hour, sub.c.cnt, prev,
                   func.round(sub.c.cnt * 1.0 / func.nullif(prev, 0) - 1.0, 4)
                   .label("growth"))
            .order_by(sub.c.hour))
    return [tuple(r) for r in session.execute(stmt)]


def hourly_growth_raw(engine):
    """A层·同一环比查询的裸 SQL 形态（session.execute(text(...))）——两条腿走路。"""
    sql = text(
        "WITH h AS (SELECT strftime('%Y-%m-%d %H:00', ts) AS hour, COUNT(*) AS cnt "
        "FROM records GROUP BY hour) "
        "SELECT hour, cnt, LAG(cnt) OVER (ORDER BY hour) AS prev_cnt, "
        "ROUND(cnt * 1.0 / NULLIF(LAG(cnt) OVER (ORDER BY hour), 0) - 1.0, 4) AS growth "
        "FROM h ORDER BY hour")
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(sql)]


# ---------------- 数据字典（B层：从真实库 introspection 生成，非手写表） ----------------

def data_dictionary(engine):
    """列/类型/PK/FK/可空 + 含义，全部来自 SQLAlchemy inspector 读取真实库结构。"""
    insp = inspect(engine)
    rows = []
    for table in ("devices", "points", "records", "alarms"):
        pk = set(insp.get_pk_constraint(table)["constrained_columns"])
        fk_map = {}
        for fk in insp.get_foreign_keys(table):
            for col, tgt in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_map[col] = "%s.%s" % (fk["referred_table"], tgt)
        for col in insp.get_columns(table):
            rows.append({
                "table": table,
                "column": col["name"],
                "type": str(col["type"]),
                "pk": "PK" if col["name"] in pk else "",
                "fk": fk_map.get(col["name"], ""),
                "nullable": "NULL" if col["nullable"] else "NOT NULL",
                "meaning": FIELD_MEANINGS.get((table, col["name"]), ""),
            })
    return rows


def dictionary_coverage(engine):
    """C层「数据字典完整」的实测量：逐列核对是否在册（含义契约 FIELD_MEANINGS）。

    口径：
      columns_total       —— inspector 从真实库读到的列数（不是代码里数出来的）
      columns_documented  —— 其中在 FIELD_MEANINGS 里有成文含义的列数
      columns_commented   —— ORM 模型 Column(comment=...) 声明了列注释的列数
                             （SQLite 不把 COMMENT 持久化，故它是补充证据而非主证据）
    """
    insp = inspect(engine)
    total = documented = commented = 0
    undocumented = []
    for table in MODEL_TABLES:
        names = [c["name"] for c in insp.get_columns(table)]
        total += len(names)
        for name in names:
            if FIELD_MEANINGS.get((table, name)):
                documented += 1
            else:
                undocumented.append("%s.%s" % (table, name))
        commented += sum(1 for c in Base.metadata.tables[table].columns
                         if c.name in names and c.comment)
    return {"columns_total": total, "columns_documented": documented,
            "columns_commented": commented, "undocumented": undocumented}


# ---------------- 溯源查询（C层：告警沿外键链反查原始读数） ----------------

def traceability_check(engine, sample=3):
    """C层「溯源查询正确」取证：两条真实测量。

    1) 孤儿行数：records.point_id / points.device_id / alarms.device_id 三个外键
       沿 LEFT JOIN 反查父行缺失数——必须全为 0（外键约束 + 入库链路自洽）；
    2) 溯源命中：alarms→devices→points→records 四表 JOIN，按同设备同刻反查
       触发该告警的原始读数，统计"可溯源告警数 / 告警总数"。
    """
    orphans = {}
    with engine.connect() as c:
        for child, col, parent in (("records", "point_id", "points"),
                                   ("points", "device_id", "devices"),
                                   ("alarms", "device_id", "devices")):
            orphans["%s.%s" % (child, col)] = c.execute(text(
                "SELECT COUNT(*) FROM %s ch LEFT JOIN %s p ON ch.%s=p.id "
                "WHERE p.id IS NULL" % (child, parent, col))).scalar()
        alarms_total = c.execute(text("SELECT COUNT(*) FROM alarms")).scalar()
    stmt = (select(func.count(distinct(AlarmEvent.id)))
            .select_from(AlarmEvent)
            .join(Device, AlarmEvent.device_id == Device.id)
            .join(SensorPoint, SensorPoint.device_id == Device.id)
            .join(Record, and_(Record.point_id == SensorPoint.id,
                               Record.ts == AlarmEvent.ts))
            .where(SensorPoint.metric == "vib"))
    detail = (select(AlarmEvent.id, Device.code, AlarmEvent.ts, AlarmEvent.level,
                     Record.value)
              .select_from(AlarmEvent)
              .join(Device, AlarmEvent.device_id == Device.id)
              .join(SensorPoint, SensorPoint.device_id == Device.id)
              .join(Record, and_(Record.point_id == SensorPoint.id,
                                 Record.ts == AlarmEvent.ts))
              .where(SensorPoint.metric == "vib")
              .order_by(AlarmEvent.ts, AlarmEvent.id)
              .limit(sample))
    with Session(engine) as s:
        traced = s.execute(stmt).scalar()
        rows = [tuple(r) for r in s.execute(detail)]
    return {"alarms_total": int(alarms_total), "alarms_traced": int(traced),
            "orphan_rows": orphans, "orphan_total": sum(orphans.values()),
            "join_tables": 4, "samples": rows}


# ---------------- N+1 取证（B层优秀标准：规避证据） ----------------

N_PLUS_ONE_LOADERS = ("joinedload", "selectinload", "lazy")


def n_plus_one_demo(engine, loader="joinedload"):
    """真实计数各种写法的 SELECT 条数：懒加载 N+1 条 vs 预加载一条/两条。

    计数用 SQLAlchemy 事件监听 before_cursor_execute，纯计数不计时，
    与墙钟无关（两次运行数字必然一致）。loader 由配置 n_plus_one_loader
    决定"本项目实际采用的规避手段"：设成 lazy 即不规避，B 层闸门据此判负。
    """
    if loader not in N_PLUS_ONE_LOADERS:
        raise ValueError("n_plus_one_loader 只支持 %s，收到 %r"
                         % ("/".join(N_PLUS_ONE_LOADERS), loader))
    counters = {"n": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, many):
        if statement.lstrip().upper().startswith("SELECT"):
            counters["n"] += 1

    def _measure(options=()):
        with Session(engine) as s:
            counters["n"] = 0
            devices = s.query(Device).options(*options).all()
            for d in devices:
                _ = len(d.points)      # 懒加载时每台设备触发一条 SELECT（N+1 现场）
            return counters["n"], devices

    try:
        lazy, devices = _measure()
        joined, _ = _measure((joinedload(Device.points),))
        selectin, _ = _measure((selectinload(Device.points),))
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    counts = {"joinedload": joined, "selectinload": selectin, "lazy": lazy}
    eager = counts[loader]
    return {"lazy_sql_count": lazy, "joinedload_sql_count": joined,
            "selectinload_sql_count": selectin, "devices": len(devices),
            "loader": loader, "eager_sql_count": eager,
            "mitigated": loader != "lazy" and eager < lazy}


# ---------------- 索引基准（工程化要求2：EXPLAIN 前后对比实测） ----------------

BENCH_QUERY = ("SELECT COUNT(*) AS c FROM bench_records "
               "WHERE point_id=:p AND ts>=:a AND ts<:b")


def _explain_plan(engine, sql, params):
    with engine.connect() as c:
        return [r[3] for r in c.execute(text("EXPLAIN QUERY PLAN " + sql), params)]


def index_bench(engine, rows=20000, reps=7, seed=7, batch_size=1000):
    """records 的联合索引 idx_dev_ts 同构基准：在等结构 bench_records 副本表上
    实测建索引前/后同一区间查询的中位耗时，并用 sqlalchemy text() 取
    EXPLAIN QUERY PLAN 真实行（SCAN→SEARCH 为生效证据）。

    诚实声明：样本量过小可能测不出加速，本函数原样报告，不做任何粉饰；
    生产表 records 上的 idx_dev_ts 由 models.Record.__table_args__ 声明。
    """
    rng = random.Random(seed)
    params = {"p": 3,
              "a": (DEMO_BASE_TS + dt.timedelta(days=1)).isoformat(sep=" "),
              "b": (DEMO_BASE_TS + dt.timedelta(days=2)).isoformat(sep=" ")}
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS bench_records"))
        c.execute(text("CREATE TABLE bench_records (id INTEGER PRIMARY KEY, "
                       "point_id INTEGER NOT NULL, ts DATETIME NOT NULL, value FLOAT NOT NULL)"))
        payload = [(1 + i % 6,
                    (DEMO_BASE_TS + dt.timedelta(minutes=i)).isoformat(sep=" "),
                    round(rng.gauss(3.6, 1.15), 3)) for i in range(rows)]
        for start in range(0, rows, batch_size):
            c.execute(text("INSERT INTO bench_records(point_id, ts, value) "
                           "VALUES (:a, :b, :c)"),
                      [{"a": p, "b": t, "c": v} for p, t, v in
                       payload[start:start + batch_size]])
    before_plan = _explain_plan(engine, BENCH_QUERY, params)

    def _timed():
        out = []
        with engine.connect() as c:
            for _ in range(reps):
                t0 = time.perf_counter()
                got = c.execute(text(BENCH_QUERY), params).scalar()
                out.append((time.perf_counter() - t0) * 1000.0)
        return statistics.median(out), got

    before_ms, n_hit = _timed()
    with engine.begin() as c:
        c.execute(text("CREATE INDEX idx_bench_dev_ts ON bench_records(point_id, ts)"))
    after_plan = _explain_plan(engine, BENCH_QUERY, params)
    after_ms, n_hit2 = _timed()
    assert n_hit == n_hit2, "加索引不应改变结果集"
    speedup = before_ms / after_ms if after_ms > 0 else float("inf")
    honest = ("实测 %.3f ms → %.3f ms（提速 %.1fx）" % (before_ms, after_ms, speedup)
              if after_ms < before_ms else
              "本数据集规模下未观察到加速（前 %.3f ms / 后 %.3f ms），如实报告"
              % (before_ms, after_ms))
    return {
        "bench_rows": rows, "reps": reps, "hits": n_hit,
        "before_ms": round(before_ms, 4), "after_ms": round(after_ms, 4),
        "speedup_x": round(speedup, 2) if math.isfinite(speedup) else None,
        "before_plan": before_plan, "after_plan": after_plan,
        # B层闸门用「计划形态」判定（SCAN→SEARCH USING INDEX 是确定性的，
        # 而 ms 是墙钟值，只写 runtime/bench.json，不进 output/）
        "scan_before": any("SCAN" in p for p in before_plan),
        "index_search_after": any("SEARCH" in p and "INDEX" in p
                                  for p in after_plan),
        "note": honest,
        "production_index": "records 表 idx_dev_ts(point_id, ts) 由 ORM __table_args__ 声明；"
                            "基准在等结构副本表 bench_records 上做大样本实测以免污染业务表",
    }


SLOW_QUERY_CANDIDATES = [
    ("全表聚合：按小时统计记录数",
     "SELECT strftime('%Y-%m-%d %H:00', ts) h, COUNT(*) FROM records GROUP BY h", {}),
    ("三表JOIN：各设备平均vib",
     "SELECT d.code, AVG(r.value) FROM records r JOIN points p ON r.point_id=p.id "
     "JOIN devices d ON p.device_id=d.id WHERE p.metric='vib' GROUP BY d.code", {}),
    ("无最左前缀：仅按 ts 范围查（idx_dev_ts 不生效→教学案例）",
     "SELECT COUNT(*) FROM records WHERE ts BETWEEN '2026-04-01 00:00:00' AND '2026-04-01 08:00:00'", {}),
    ("告警溯源：告警JOIN设备",
     "SELECT d.code, COUNT(*) FROM alarms a JOIN devices d ON a.device_id=d.id "
     "GROUP BY d.code ORDER BY COUNT(*) DESC LIMIT 3", {}),
]


def slow_query_report(engine, top=3, reps=3):
    """A层·慢查询报告：对代表性查询实测中位耗时并附 EXPLAIN QUERY PLAN 行，
    取最慢 top 条（耗时为真实测量值，两次运行会有毫秒级抖动，属预期）。"""
    out = []
    for name, sql, params in SLOW_QUERY_CANDIDATES:
        times = []
        with engine.connect() as c:
            for _ in range(reps):
                t0 = time.perf_counter()
                c.execute(text(sql), params).fetchall()
                times.append((time.perf_counter() - t0) * 1000.0)
        plan = _explain_plan(engine, sql, params)
        out.append({"name": name, "ms": round(statistics.median(times), 3),
                    "plan": plan})
    out.sort(key=lambda r: r["ms"], reverse=True)
    return out[:top]


def integrity_check(engine):
    """外键约束取证：插入孤儿记录必须被库拒绝（IntegrityError）。"""
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO points(device_id, metric, unit) "
                           "VALUES (999999, 'vib', 'mm/s')"))
    except IntegrityError:
        return {"orphan_rejected": True}
    return {"orphan_rejected": False}


# ---------------- A层：复杂查询（四表 JOIN 聚合）+ P3 仪表盘闭环交接 ----------------

def device_hourly_summary(session):
    """超优口径「复杂查询(多表JOIN聚合)」：设备×小时 四表 JOIN 聚合。

    records↔points↔devices 三条内连接 + alarms 一条按 (device_id, 小时) 对齐的
    外连接；聚合列：记录数、平均温度、平均振动、告警数、最高告警级。
    组内每条记录被复制的次数恒等于该设备该小时的告警数（无告警则 1 次），
    等倍数复制不改变均值，故 avg 仍精确；计数一律 count(distinct)。
    """
    hour = func.strftime("%Y-%m-%d %H:00", Record.ts)
    alarm_hour = func.strftime("%Y-%m-%d %H:00", AlarmEvent.ts)
    stmt = (select(Device.code, Device.area, hour.label("hour"),
                   func.count(distinct(Record.id)).label("n_records"),
                   func.round(func.avg(case((SensorPoint.metric == "temp",
                                             Record.value), else_=None)), 3)
                   .label("avg_temp"),
                   func.round(func.avg(case((SensorPoint.metric == "vib",
                                             Record.value), else_=None)), 3)
                   .label("avg_vib"),
                   func.count(distinct(AlarmEvent.id)).label("n_alarms"),
                   func.max(AlarmEvent.level).label("max_level"))
            .select_from(Device)
            .join(SensorPoint, SensorPoint.device_id == Device.id)
            .join(Record, Record.point_id == SensorPoint.id)
            .outerjoin(AlarmEvent, and_(AlarmEvent.device_id == Device.id,
                                       alarm_hour == hour))
            .group_by(Device.code, Device.area, hour)
            .order_by(hour, Device.code))
    return [tuple(r) for r in session.execute(stmt)]


def device_hourly_manual(engine):
    """同口径的 Python 逐行手算（交叉验证四表 JOIN 聚合是否算对，非第二套说法）。"""
    buckets = {}
    with Session(engine) as s:
        for d in s.query(Device).order_by(Device.code):
            for p in d.points:
                for r in p.records:
                    key = (d.code, d.area, r.ts.strftime("%Y-%m-%d %H:00"))
                    b = buckets.setdefault(key, {"temp": [], "vib": [],
                                                  "n": 0, "alarms": 0,
                                                  "max_level": None})
                    b["n"] += 1
                    b["temp" if p.metric == "temp" else "vib"].append(r.value)
        for a in s.query(AlarmEvent):
            key = (a.device.code, a.device.area, a.ts.strftime("%Y-%m-%d %H:00"))
            b = buckets.setdefault(key, {"temp": [], "vib": [], "n": 0,
                                         "alarms": 0, "max_level": None})
            b["alarms"] += 1
            b["max_level"] = (a.level if b["max_level"] is None
                              else max(b["max_level"], a.level))
    out = []
    for (code, area, hour), b in sorted(buckets.items(),
                                        key=lambda kv: (kv[0][2], kv[0][0])):
        out.append((code, area, hour, b["n"],
                    sum(b["temp"]) / len(b["temp"]) if b["temp"] else None,
                    sum(b["vib"]) / len(b["vib"]) if b["vib"] else None,
                    b["alarms"], b["max_level"]))
    return out


def summary_matches_sql(sql_rows, manual_rows, tol=0.005):
    """四表 JOIN 聚合 vs 逐行手算：逐桶比对（均值按 tol 容差，计数/级别须全等）。"""
    if len(sql_rows) != len(manual_rows):
        return False
    for a, b in zip(sql_rows, manual_rows):
        if a[0] != b[0] or a[1] != b[1] or a[2] != b[2]:
            return False
        if a[3] != b[3] or a[6] != b[6] or (a[7] or 0) != (b[7] or 0):
            return False
        for x, y in ((a[4], b[4]), (a[5], b[5])):
            if (x is None) != (y is None):
                return False
            if x is not None and abs(float(x) - float(y)) > tol:
                return False
    return True


def p3_status_of(max_level):
    """告警级 → P3 的 status 口径（DOWN=2级停机 / WARN=1级预警 / RUN=正常）。"""
    if (max_level or 0) >= 2:
        return "DOWN"
    return "WARN" if max_level == 1 else "RUN"


def export_p3_handoff(engine, path):
    """A层闭环交接：把四表 JOIN 聚合结果按 P3 读取契约导出为 CSV。

    列口径 = P3_CONTRACT_COLUMNS（p33_kpi_cockpit data_source.CANON 中本仓库
    真实可供给的 6 列）；生产计数 output/ok_qty/yield_pct 仓库里没有，
    由 P3 按自身 provenance 规则标"合成·seed"，本项目不伪造。
    """
    with Session(engine) as s:
        summary = device_hourly_summary(s)
        codes = sorted(d.code for d in s.query(Device))
    payload = [{"ts": "%s:00" % r[2], "device_id": r[0], "line": r[1],
                "temp": "" if r[4] is None else "%.3f" % r[4],
                "vib": "" if r[5] is None else "%.3f" % r[5],
                "status": p3_status_of(r[7])} for r in summary]
    io_utils.write_csv_rows(path, payload, fields=list(P3_CONTRACT_COLUMNS))
    status_counts = {}
    for row in payload:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    return {"rows": len(payload), "columns": list(P3_CONTRACT_COLUMNS),
            "devices": len(codes),
            "hours": len({r["ts"] for r in payload}),
            "status_counts": dict(sorted(status_counts.items())),
            "empty_cells": sum(1 for r in payload
                               for c in ("temp", "vib") if r[c] == "")}


def validate_p3_handoff(engine, path):
    """按 P3 的读取口径校验交接文件（列名/时间可解析/设备编号在册）。"""
    check = {"exists": os.path.exists(path), "rows": 0, "empty_cells": 0,
             "columns": [], "missing_columns": list(P3_CONTRACT_COLUMNS),
             "ts_parse_failures": 0, "unknown_devices": []}
    if not check["exists"]:
        return check
    rows = io_utils.read_csv_rows(path)
    check["rows"] = len(rows)
    if not rows:
        return check
    check["columns"] = [c for c in P3_CONTRACT_COLUMNS if c in rows[0]]
    check["missing_columns"] = [c for c in P3_CONTRACT_COLUMNS
                                if c not in rows[0]]
    check["empty_cells"] = sum(1 for r in rows for c in P3_CONTRACT_COLUMNS
                               if str(r.get(c, "")).strip() == "")
    seen = {r["device_id"] for r in rows}
    for r in rows:
        for fmt in P3_TS_FORMATS:
            try:
                dt.datetime.strptime(str(r.get("ts", "")).strip(), fmt)
                break
            except ValueError:
                continue
        else:
            check["ts_parse_failures"] += 1
    with Session(engine) as s:
        in_db = {d.code for d in s.query(Device)}
    check["unknown_devices"] = sorted(seen - in_db)
    return check
