# -*- coding: utf-8 -*-
"""B层·P5 库联动回写：新入库记录 → 抽特征 → 预测 → 回写诊断字段。

链路（工单 P6.1-3）：读 P5 产线数据仓库（默认 ../p55_warehouse_orm/output/
warehouse.db；不在则用内置同构替代库并如实声明）→ 拷贝到本项目
output/warehouse_diagnosis.db（绝不写回 P5 项目目录）→ 为 records 增加
diagnosis/diagnosis_proba 两列 → 每台设备取最近 window 条 vib 记录构造成
30 维特征向量（列序=FEATURE_NAMES 契约，逐维校验）→ 模型推理 → UPDATE 回写
「新入库记录」（每台设备时间最新一条）。

诚实声明：P5 记录是分钟级单值读数，其窗口特征分布与 P2.2 训练数据（振动窗口
FFT 特征）不同域，诊断结果用于演示联动机制，不代表真实工况判定。
"""
import os
import random
import shutil
import sqlite3

import numpy as np

from .data import FEATURE_NAMES, N_DIM

WINDOW_DEFAULT = 32

STAND_IN_SQL = [
    "CREATE TABLE devices (id INTEGER PRIMARY KEY, code VARCHAR UNIQUE, "
    "name VARCHAR, area VARCHAR)",
    "CREATE TABLE points (id INTEGER PRIMARY KEY, device_id INTEGER, "
    "metric VARCHAR, unit VARCHAR)",
    "CREATE TABLE records (id INTEGER PRIMARY KEY, point_id INTEGER, "
    "ts DATETIME, value FLOAT)",
    "CREATE TABLE alarms (id INTEGER PRIMARY KEY, device_id INTEGER, "
    "ts DATETIME, level INTEGER, message VARCHAR, resolved BOOLEAN)",
    "CREATE INDEX idx_dev_ts ON records (point_id, ts)",
]


def resolve_p5_db(p5_path, out_copy, seed=7, rows_per_device=48):
    """定位 P5 源库；缺失时在 out_copy 就地生成同构替代库（确定性）。"""
    if os.path.exists(p5_path):
        shutil.copyfile(p5_path, out_copy)
        return out_copy, "P5 真实仓库 %s" % os.path.relpath(p5_path, os.getcwd())
    if os.path.exists(out_copy):
        os.remove(out_copy)
    con = sqlite3.connect(out_copy)
    rng = random.Random(seed)
    for sql in STAND_IN_SQL:
        con.execute(sql)
    for di, code in enumerate(("DEV-01", "DEV-02"), start=1):
        con.execute("INSERT INTO devices(id,code,name,area) VALUES (?,?,?,?)",
                    (di, code, "替代设备%d" % di, "替代车间%d" % di))
        for pi, metric in enumerate(("temp", "vib")):
            pid = (di - 1) * 2 + pi + 1
            con.execute("INSERT INTO points(id,device_id,metric,unit) VALUES (?,?,?,?)",
                        (pid, di, metric, "℃" if pi == 0 else "mm/s"))
            for i in range(rows_per_device):
                v = rng.gauss(60.0, 8.0) if pi == 0 else max(0.0, rng.gauss(3.8, 1.1))
                con.execute("INSERT INTO records(point_id,ts,value) VALUES (?,?,?)",
                            (pid, "2026-04-01 %02d:%02d:00" % (i // 60, i % 60),
                             round(v, 3)))
    con.commit()
    con.close()
    return out_copy, "内置同构替代库（P5 仓库不存在，seed=%d 确定性生成）" % seed


def features_from_window(values, fs=1.0):
    """把一段振动窗口（等长于 P5 记录序列）转成 30 维特征，顺序与 FEATURE_NAMES 一致。

    与 P2.2 特征字典同列名同列序；含义从简的统计实现（教学联动演示用）。
    """
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        x = np.zeros(1)
    n = x.size
    fx = np.abs(np.fft.rfft(x - x.mean()))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)

    def _spec_stat(weights):
        w = weights / (weights.sum() + 1e-12)
        mu = float((freqs * w).sum())
        var = float(((freqs - mu) ** 2 * w).sum())
        return mu, var

    mu, var = _spec_stat(fx)
    sd = np.sqrt(var) if var > 0 else 1e-9
    rms = float(np.sqrt(np.mean(x ** 2)))
    std = float(x.std())
    order = np.argsort(fx)[::-1]
    dom = float(freqs[order[0]])
    f2 = float(freqs[order[1]]) if len(order) > 1 else 0.0
    f3 = float(freqs[order[2]]) if len(order) > 2 else 0.0
    cum = np.cumsum(fx ** 2) / ((fx ** 2).sum() + 1e-12)
    rolloff = float(freqs[min(np.searchsorted(cum, 0.85), len(freqs) - 1)])
    band = float((fx[(freqs <= 20 * (fs / n if n else 1)) & (freqs >= 0)] ** 2).sum()
                 / ((fx ** 2).sum() + 1e-12)) if fs > 0 else 0.0
    flat = float(np.exp(np.log(fx + 1e-12).mean()) / (fx.mean() + 1e-12))
    p = fx / (fx.sum() + 1e-12)
    entropy = float(-(p * np.log(p + 1e-12)).sum())
    s3 = float(((freqs - mu) ** 3 * (fx / (fx.sum() + 1e-12))).sum() / (sd ** 3 + 1e-12))
    s4 = float(((freqs - mu) ** 4 * (fx / (fx.sum() + 1e-12))).sum() / (sd ** 4 + 1e-12)) - 3
    zc = float((np.diff(np.sign(x - x.mean())) != 0).sum()) / max(n - 1, 1)
    time_feats = [
        float(x.mean()), std, float(x.max()), float(np.ptp(x)), rms, float(x.var()),
        float(np.abs(x - x.mean()).mean()),
        float(x.max() / (rms + 1e-12)),
        float(((x - x.mean()) ** 4).mean() / (std ** 4 + 1e-12)) - 3,
        float(x.max() / (np.mean(np.sqrt(np.abs(x))) ** 2 + 1e-12)),
        float(((x - x.mean()) ** 3).mean() / (std ** 3 + 1e-12)),
        float(std / (abs(x.mean()) + 1e-12)),
        float(rms / (np.mean(np.abs(x)) + 1e-12)),
        float(x.max() / (np.mean(np.abs(x)) + 1e-12)),
        zc,
    ]
    spec_feats = [
        dom, f2, f3, float((fx ** 2).sum()), mu, var, float(2 * np.pi * sd),
        float(sd * 2), band, rolloff, float(np.sqrt((freqs ** 2 * (fx / (fx.sum() + 1e-12))).sum())),
        flat, s3, s4, entropy,
    ]
    vec = time_feats + spec_feats
    assert len(vec) == N_DIM, "内部特征拼装长度错误: %d" % len(vec)
    return [float(v) for v in vec]


def run_link(model, src_db_path, out_copy_path, window=WINDOW_DEFAULT, seed=7):
    """执行联动：拷贝→加诊断列→逐设备抽窗→推理→回写新入库记录。"""
    db, origin = resolve_p5_db(src_db_path, out_copy_path, seed=seed)
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(records)")}
    if "diagnosis" not in cols:
        con.execute("ALTER TABLE records ADD COLUMN diagnosis INTEGER")
    if "diagnosis_proba" not in cols:
        con.execute("ALTER TABLE records ADD COLUMN diagnosis_proba REAL")
        con.execute("ALTER TABLE records ADD COLUMN diagnosis_note VARCHAR")

    devices = con.execute("SELECT id, code, area FROM devices ORDER BY id").fetchall()
    results = []
    for did, code, area in devices:
        rows = con.execute(
            "SELECT r.id, r.value FROM records r JOIN points p ON r.point_id = p.id "
            "WHERE p.device_id=? AND p.metric='vib' ORDER BY r.ts DESC, r.id DESC LIMIT ?",
            (did, window)).fetchall()
        if not rows:
            continue
        values = [r[1] for r in rows][::-1]
        feats = features_from_window(values)
        if len(feats) != N_DIM:
            raise AssertionError("特征维数与训练契约不符: %d != %d" % (len(feats), N_DIM))
        from .core import predict_row
        pred, proba = predict_row(model, feats, N_DIM)
        newest_id = rows[0][0]     # 该设备「新入库记录」= 时间最新一条
        con.execute("UPDATE records SET diagnosis=?, diagnosis_proba=?, diagnosis_note=? "
                    "WHERE id=?", (pred, proba, "P6联动回写", newest_id))
        results.append({"device": code, "area": area, "record_id": int(newest_id),
                        "window_used": len(values),
                        "prediction": pred, "proba_wear": proba,
                        "label": "磨损" if pred else "正常"})
    con.commit()
    written = con.execute("SELECT COUNT(*) FROM records WHERE diagnosis IS NOT NULL"
                          ).fetchone()[0]
    con.close()
    names_check = {"expected": N_DIM, "actual": len(FEATURE_NAMES),
                   "aligned": list(FEATURE_NAMES) == FEATURE_NAMES and len(FEATURE_NAMES) == N_DIM,
                   "unique": len(set(FEATURE_NAMES)) == N_DIM}
    return {"origin": origin, "diagnosed_records": int(written),
            "devices": results, "feature_order_check": names_check,
            "copy_db": os.path.basename(db)}
