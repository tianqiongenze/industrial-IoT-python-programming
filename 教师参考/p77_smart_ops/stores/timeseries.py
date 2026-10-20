# -*- coding: utf-8 -*-
"""存储引擎② 时序：DuckDB —— 振动高频采样 + ASOF对齐 + 窗口降采样

时序场景三板斧（对比SQLite逐行扫描的数量级差异）：
  1) ASOF JOIN —— 把"不规则采样"对齐到整点（取每个整点前最近一条）
  2) time_bucket 窗口聚合 —— 10Hz原始值 → 1分钟均值/最大值（降采样）
  3) 滚动特征 —— 最近N分钟均值/斜率，直接喂P6诊断模型

单独运行: /opt/anaconda3/bin/python -m stores.timeseries
"""
import duckdb

from config import DUCK_FILE

TABLE = """
CREATE OR REPLACE TABLE vib(
  ts TIMESTAMP, device VARCHAR, vib_rms DOUBLE, temp DOUBLE
)"""


def seed(n_per_device=3600 * 2):
    """两台设备×2小时×10Hz级采样（合成：PUMP-03 后半程振动爬升）"""
    con = duckdb.connect(DUCK_FILE)
    con.execute(TABLE)
    con.execute("""
    INSERT INTO vib
    SELECT TIMESTAMP '2026-09-09 08:00:00' + (i * INTERVAL 1 SECOND),
           dev,
           base + slope * greatest(i - 5000, 0) * 0.0002 + (random()-0.5)*0.15,
           40 + (random()-0.5)*2
    FROM generate_series(1, {n}) t(i),
         (VALUES ('PUMP-03', 4.2, 1.0), ('FAN-02', 3.1, 0.2)) v(dev, base, slope)
    """.format(n=n_per_device))
    con.close()


def window_feats(device: str, minutes: int = 10) -> dict:
    """最近N分钟的时序特征（模型推理的实时特征源）"""
    con = duckdb.connect(DUCK_FILE, read_only=True)
    mx = con.execute("SELECT max(ts) FROM vib WHERE device = $dev",
                     {"dev": device}).fetchone()[0]
    row = con.execute("""
        SELECT count(*) n, avg(vib_rms) avg_v, max(vib_rms) max_v,
               avg(vib_rms) - min_by(vib_rms, ts) slope,
               last(vib_rms ORDER BY ts) last_v
        FROM vib
        WHERE device = $dev AND ts > $cut - to_minutes($mins)
    """, {"dev": device, "cut": mx, "mins": minutes}).fetchone()
    con.close()
    n, avg_v, max_v, slope, last_v = row
    return {"samples": n, "avg_vib": round(avg_v, 3), "max_vib": round(max_v, 3),
            "slope": round(slope, 4), "last_vib": round(last_v, 3)}


def asof_grid(device: str) -> list:
    """ASOF对齐演示：把不规则采样对齐到每分钟整点（每点取整点前最近采样）"""
    con = duckdb.connect(DUCK_FILE, read_only=True)
    rows = con.execute("""
        WITH grid AS (
          SELECT unnest(generate_series(
            date_trunc('minute', min(ts)), max(ts), INTERVAL 1 MINUTE)) g
          FROM vib WHERE device = ?
        )
        SELECT g, v.ts, v.vib_rms
        FROM grid ASOF LEFT JOIN vib v
          ON v.device = ? AND g >= v.ts
        LIMIT 5
    """, [device, device]).fetchall()
    con.close()
    return [{"grid": str(g), "ts": str(t), "vib": round(v, 3)} for g, t, v in rows]


if __name__ == "__main__":
    seed()
    import json
    print(json.dumps(window_feats("PUMP-03"), ensure_ascii=False))
    print(json.dumps(asof_grid("PUMP-03")[:2], ensure_ascii=False))
