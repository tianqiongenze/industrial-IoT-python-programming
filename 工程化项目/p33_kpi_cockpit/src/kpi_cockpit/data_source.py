# -*- coding: utf-8 -*-
"""TODO-0：数据源装载 —— 优先消费 P2.1 的清洁产出 clean.csv，缺失才按种子合成。

诚实性设计（审计要求"说清用了哪个源"）：
  * Dataset.source 记录实际选中的文件（含相对路径与 sha256 前 12 位）；
  * Dataset.provenance 逐列标注 real(文件原始)/derived(由已有列推导)/synth(纯合成)；
  * 全部随机走 random.Random(seed)，不用内置 hash()（后者受 PYTHONHASHSEED 随机化，
    跨进程不可复现 —— 这正是 P4.1 曾经踩过的坑）。
"""
import csv
import hashlib
import os
import random
from datetime import datetime, timedelta

#: 本项目仪表盘/日报需要的规范列（工单点名的字段口径）
CANON = ("ts", "device_id", "line", "output", "ok_qty", "yield_pct",
         "temp", "vib", "status")
_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def sha12(path):
    """文件指纹（写进报告，便于上游数据变动时追责）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def parse_ts(text):
    """宽松时间解析；解析失败抛 ValueError（由候选筛选器捕获后跳过该文件）。"""
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(str(text).strip(), fmt)
        except ValueError:
            continue
    raise ValueError("无法解析时间: %r" % (text,))


def poisson(rng, lam):
    """Knuth 采样：stdlib 无泊松，自实现以保证跨机可复现（不依赖 numpy）。"""
    import math
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return max(0, k - 1)


class Dataset:
    """一次装载的结果：记录 + 来源 + 列级出处 + 可用设备/日期清单。"""

    def __init__(self, records, source, provenance, mode):
        self.records = records
        self.source = source
        self.provenance = provenance
        self.mode = mode                      # clean | synth
        if not records:
            raise ValueError("数据源为空（0 行），无法计算 KPI")

    @property
    def devices(self):
        seen = []
        for r in self.records:
            if r["device_id"] not in seen:
                seen.append(r["device_id"])
        return sorted(seen)

    @property
    def dates(self):
        return sorted({r["ts"][:10] for r in self.records})

    def as_dicts(self):
        return list(self.records)

    def as_df(self):
        """给 app.py/plotly 用的 pandas.DataFrame（pandas 缺失时抛 ImportError）。"""
        import pandas as pd
        df = pd.DataFrame(self.records)
        df["ts"] = pd.to_datetime(df["ts"])
        return df


def _to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def read_csv_rows(path):
    """用 stdlib csv 读（零依赖），首行表头；返回 list[dict]。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _candidate_paths(cfg, here):
    """按 config 的 data.candidates 顺序展开为绝对路径（相对项目根解析）。"""
    out = []
    for rel in cfg.section("data").get("candidates") or []:
        out.append(os.path.normpath(os.path.join(here, rel)))
    return out


def _usable(path, cfg):
    """文件存在且含 require_columns 全部列、且首行时间可解析 → 可用。"""
    if not os.path.isfile(path):
        return None
    need = list(cfg.section("data").get("require_columns") or ["ts"])
    try:
        rows = read_csv_rows(path)
    except (OSError, csv.Error):
        return None
    if not rows or not all(c in rows[0] for c in need):
        return None
    try:
        parse_ts(rows[0][need[0]])
    except (ValueError, KeyError):
        return None
    return rows


def synth_records(cfg):
    """兜底合成（参数全部来自 config/data/synth，种子 = config.seed）。"""
    s = cfg.section("data")["synth"]
    rng = random.Random(int(cfg.seed))
    n, devices = int(s["rows"]), list(s["devices"])
    start, freq = parse_ts(s["start"]), str(s["freq"])
    step = timedelta(minutes=30 if freq.endswith("min") else 60 * 24)
    recs, lines = [], cfg.items or []
    for i in range(n):
        dev = devices[i % len(devices)]
        output = poisson(rng, float(s["output_lambda"])) + 1
        ok = int(output * rng.uniform(float(s["yield_low"]), float(s["yield_high"])))
        recs.append({
            "ts": (start + step * i).strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": dev,
            "line": _line_of(dev, lines),
            "output": output,
            "ok_qty": min(ok, output),
            "yield_pct": round(100.0 * min(ok, output) / output, 2),
            "temp": round(rng.uniform(float(s["temp_low"]), float(s["temp_high"])), 2),
            "vib": round(rng.uniform(float(s["vib_low"]), float(s["vib_high"])), 3),
            "status": rng.choice(["RUN", "RUN", "RUN", "IDLE", "DOWN"]),
        })
    return recs


def _line_of(dev, lines):
    """设备 → 产线名的确定性映射（台账不足时按序号取名，保证可复现）。"""
    idx = int(dev.rsplit("-", 1)[-1]) - 1 if dev.rsplit("-", 1)[-1].isdigit() else 0
    if lines and idx < len(lines):
        return str(lines[idx].get("line"))
    return "N%d号产线" % (idx + 1)


def from_clean(path, rows, cfg):
    """把任意 schema 的 clean.csv 归一到 CANON：已有列照收，缺失列按 seed 派生。"""
    s = cfg.section("data")["synth"]
    rng = random.Random(int(cfg.seed))
    devices = list(s["devices"])
    lines = cfg.items or []
    online = str(cfg.require("thresholds.status_online"))
    prov = {}
    recs = []
    for i, raw in enumerate(rows):
        raw = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        ts = parse_ts(raw.get("ts"))
        dev = raw.get("device_id") or devices[i % len(devices)]
        temp, vib = _to_float(raw.get("temp")), _to_float(raw.get("vib"))
        output = _to_float(raw.get("output"))
        out_synth = output is None
        if out_synth:
            output = poisson(rng, float(s["output_lambda"])) + 1
        ok = _to_float(raw.get("ok_qty"))
        if ok is None:
            ok = int(output * rng.uniform(float(s["yield_low"]), float(s["yield_high"])))
        ok = min(ok, output)
        if vib is None:
            vib = round(rng.uniform(float(s["vib_low"]), float(s["vib_high"])), 3)
        if temp is None:
            temp = round(rng.uniform(float(s["temp_low"]), float(s["temp_high"])), 2)
        status = raw.get("status") or (online if temp < cfg.temp_max else "WARN")
        recs.append({
            "ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": str(dev),
            "line": raw.get("line") or _line_of(str(dev), lines),
            "output": int(output),
            "ok_qty": int(ok),
            "yield_pct": round(100.0 * ok / output, 2) if output else 0.0,
            "temp": round(temp, 2),
            "vib": round(vib, 3),
            "status": str(status),
        })
    have = set(rows[0])
    derived_rule = {
        "line": "派生·产线台账",
        "yield_pct": "派生·ok_qty/output",
        "device_id": "派生·按行序轮询设备表",
        "status": "派生·阈值判定",
    }
    prov = {}
    for col in CANON:
        if col in have:
            prov[col] = "文件原始"
        elif col in derived_rule:
            prov[col] = derived_rule[col]
        else:
            prov[col] = "合成·seed=%d" % cfg.seed
    return recs, prov


def load(cfg, here, source="auto", csv_path=None):
    """入口：source ∈ auto|clean|synth|csv。返回 Dataset（来源写死在 .source）。"""
    if source == "csv":
        if not csv_path:
            raise ValueError("--source csv 必须配 --csv 指定文件")
        rows = _usable(csv_path, cfg)
        if rows is None:
            raise ValueError("CSV 不可用（缺列或时间不可解析）: %s" % csv_path)
        recs, prov = from_clean(csv_path, rows, cfg)
        return Dataset(recs, "外部 CSV: %s (sha256=%s)" % (csv_path, sha12(csv_path)),
                       prov, "clean")
    if source in ("auto", "clean"):
        tried = []
        pool = [csv_path] if csv_path else _candidate_paths(cfg, here)
        for p in pool:
            if not p:
                continue
            tried.append(p)
            rows = _usable(p, cfg)
            if rows is not None:
                recs, prov = from_clean(p, rows, cfg)
                rel = os.path.relpath(p, here)
                return Dataset(recs, "P2.1 清洁产出 %s (sha256=%s, %d 行)"
                               % (rel, sha12(p), len(recs)), prov, "clean")
        if source == "clean":
            raise FileNotFoundError("未找到可用 %s，已依次尝试: %s"
                                    % (cfg.require("data.prefer"), ", ".join(tried)))
    prov = {c: "合成·seed=%d" % cfg.seed for c in CANON}
    return Dataset(synth_records(cfg),
                   "内置合成数据（未找到 %s，已尝试 %d 个候选路径；seed=%d，"
                   "参数见 config/data/synth）" % (cfg.require("data.prefer"),
                                              len(cfg.section("data").get("candidates") or []),
                                              cfg.seed), prov, "synth")
