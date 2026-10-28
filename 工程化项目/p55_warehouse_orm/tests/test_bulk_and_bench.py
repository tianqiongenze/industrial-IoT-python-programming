# -*- coding: utf-8 -*-
"""批量入库（P4 缓冲 + 事务分批）与索引基准/N+1 取证测试。"""
import math
import os
import sqlite3

import pytest

from warehouse_orm import core
from warehouse_orm.models import Record
from sqlalchemy.orm import Session

BUF_SCHEMA = "CREATE TABLE records(source TEXT, ts REAL, temp REAL, vib REAL)"


@pytest.fixture()
def engine(tmp_path):
    eng = core.make_engine("sqlite:///%s" % (tmp_path / "wh.db"))
    core.init_db(eng)
    core.seed_demo(eng, seed=7, n_records=60)
    return eng


def _make_buffer(path, n=250):
    con = sqlite3.connect(path)
    con.execute(BUF_SCHEMA)
    rows = [("plc@%d" % (5020 + i % 3), 1791804937.0 + i * 0.2,
             60.0 + i % 7, 3.0 + (i % 40) / 10.0) for i in range(n)]
    con.executemany("INSERT INTO records VALUES(?,?,?,?)", rows)
    con.commit()
    con.close()
    return n


def test_bulk_import_from_buffer_db(engine, tmp_path):
    buf = str(tmp_path / "buffer.db")
    n = _make_buffer(buf, 250)
    before = 60
    stats = core.import_buffer(engine, buf, batch_size=100, seed=7)
    assert stats["buffer_rows"] == n
    assert stats["records_written"] == 2 * n           # 每源行拆 temp+vib 两条
    assert stats["commits"] == math.ceil(2 * n / 100)  # 每批 100 条一个事务
    with Session(engine) as s:
        assert s.query(Record).count() == before + 2 * n
        # 时间戳为 DateTime 往返：可读且随源递增
        ts_list = [r.ts for r in s.query(Record).order_by(Record.id).limit(5)]
        assert all(hasattr(t, "year") for t in ts_list)


def test_seed_demo_also_batches_transactions(engine, tmp_path):
    """C层批量事务：种子入库同样 bulk 分批提交，提交次数=ceil(记录数/批量)。"""
    buf = str(tmp_path / "none.db")
    stats = core.import_buffer(engine, buf, batch_size=100, seed=7,
                               stand_in_rows=0)
    assert stats["records_written"] == 0 and stats["commits"] == 0
    eng = core.make_engine("sqlite:///%s" % (tmp_path / "seed.db"))
    core.init_db(eng)
    st = core.seed_demo(eng, seed=7, n_records=250, batch_size=100)
    assert st["records"] == 250
    assert st["commits"] == math.ceil(250 / 100) == 3   # 3 批 3 个事务
    assert st["batch_size"] == 100


def test_buffer_stand_in_rows_is_configurable(engine, tmp_path):
    """替代源行数由配置决定：设 0 即"无缓冲数据"，闸门不会被假数据撑达标。"""
    missing = str(tmp_path / "nope.db")
    zero = core.import_buffer(engine, missing, batch_size=100, seed=7,
                              stand_in_rows=0)
    assert zero["records_written"] == 0
    some = core.import_buffer(engine, missing, batch_size=100, seed=7,
                              stand_in_rows=4)
    assert some["buffer_rows"] == 4 and some["records_written"] == 8


def test_buffer_missing_uses_deterministic_stand_in(engine, tmp_path):
    a = core.import_buffer(engine, str(tmp_path / "nope.db"), batch_size=100, seed=42)
    assert a["records_written"] > 0 and "替代源" in a["source"]
    # 替代源同 seed 两次行数一致（确定性）
    b = core.import_buffer(engine, str(tmp_path / "nope2.db"), batch_size=100, seed=42)
    assert b["records_written"] == a["records_written"]


def test_real_project_buffer_db_readable():
    """课程链真实数据：仓库根 buffer.db 若能读到则必须 ≥100 行。"""
    path = os.path.join(core.PROJECT_ROOT, "..", "..", "buffer.db")
    if not os.path.exists(path):
        pytest.skip("buffer.db 不在课程根目录（离线/单项目检出场景）")
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        cnt = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    finally:
        con.close()
    assert cnt >= 100


def test_index_bench_returns_measured_numbers(engine):
    res = core.index_bench(engine, rows=5000, reps=3, seed=7)
    for key in ("before_ms", "after_ms"):
        assert isinstance(res[key], float) and res[key] > 0
    assert res["hits"] > 0 and res["bench_rows"] == 5000
    assert any("SCAN" in p for p in res["before_plan"])          # 真实计划行：全表扫
    assert any("idx_bench_dev_ts" in p and "SEARCH" in p
               for p in res["after_plan"])                       # 真实计划行：走索引
    # B层闸门读的是这两个"计划形态"布尔（确定性，与墙钟无关）
    assert res["scan_before"] is True and res["index_search_after"] is True
    if res["after_ms"] >= res["before_ms"]:
        assert "未观察到加速" in res["note"]                      # 诚实口径必在
    else:
        assert res["speedup_x"] > 1


def test_n_plus_one_demo_counts_real_sql(engine):
    res = core.n_plus_one_demo(engine)
    assert res["devices"] == 3
    assert res["joinedload_sql_count"] == 1
    assert res["lazy_sql_count"] > res["joinedload_sql_count"]   # N+1 现场
