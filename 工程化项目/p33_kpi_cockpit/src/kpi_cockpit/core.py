# -*- coding: utf-8 -*-
"""KPI 驾驶舱领域逻辑（纯函数，零 IO —— 工程化要求 1：KPI 计算与图表渲染分离）。

对外契约（与 docs/01 §4、工单 P3.1 一一对应）：
  filter_records   → TODO-1 侧栏日期范围 + 设备多选
  compute_kpis     → TODO-2 五个 KPI（总产量/平均良率/设备在线数/今日告警数/效率对标）
                     + 4 个补充指标（共 9 个，满足工单"≥7 指标"，B 层佐证）
  trend            → TODO-3 产量趋势（供 px.line）
  gauge / device_status / alarm_rows → TODO-4 良率仪表·红绿灯·告警表
  efficiency       → TODO-5 效率对标（供 st.progress）
  anomalies/suggest→ 工单 P3.2-3 异常识别 + 处置建议
  drill            → A 层单设备汇总榜（CLI --drill）
  drill_rows       → A 层"点击折线点/表格行 → 联动明细"（app.py on_select 与
                     CLI 证据行共用这一个纯函数）
  drill_fingerprint→ 明细稳定指纹（zlib.crc32，跨 PYTHONHASHSEED 可复现）
"""
import math

STATUS_TONE = {"ok": "绿灯", "warn": "黄灯", "error": "红灯"}


def derive(k):
    """产线台账行 → 派生指标（保留：D 层台账表与 tests/test_core.py 依赖）。"""
    produced, planned, good = float(k["produced"]), float(k["planned"]), float(k["good"])
    return {"line": str(k["line"]), "planned": int(planned), "produced": int(produced),
            "good": int(good), "oee": float(k["oee"]),
            "good_rate": round(good / produced, 4) if produced else 0.0,
            "plan_rate": round(produced / planned, 4) if planned else 0.0}


def w(s):
    """显示宽度：CJK=2，其它=1。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def render(rows, headers):
    """等宽文本表（中文对齐）。

    程序化发现：推导式/生成器的循环变量不得与函数后续变量同名
    （Python 闭包作用域会抛 NameError: cannot access free variable）。
    """
    cols = [list(headers)] + [[str(c) for c in row] for row in rows]
    widths = [max(w(row[i]) for row in cols) for i in range(len(headers))]

    def pad(s, n):
        s = str(s)
        return s + " " * (n - w(s))

    def line(row):
        return "  ".join(pad(row[i], widths[i]) for i in range(len(headers)))

    out = [line(cols[0]), "  ".join("-" * x for x in widths)]
    out += [line(row) for row in cols[1:]]
    return chr(10).join(out)


def table_rows(rows):
    hdr = ("产线", "计划", "产出", "合格", "合格率", "达成率", "OEE%")
    body = [(r["line"], str(r["planned"]), str(r["produced"]), str(r["good"]),
             "%.2f%%" % (r["good_rate"] * 100), "%.2f%%" % (r["plan_rate"] * 100),
             "%.1f%%" % r["oee"]) for r in rows]
    return [hdr] + body


# ---------------------------------------------------------------------------
# TODO-1 侧栏筛选：日期范围 + 设备多选（app.py 与 run.py --start/--end/--device 共用）
# ---------------------------------------------------------------------------
def filter_records(records, start=None, end=None, devices=None, date=None):
    """按日期区间/单日/设备清单过滤。

    参数：start/end 'YYYY-MM-DD'（闭区间，含端点）；devices 可迭代设备名；
          date 单日（与 start/end 互斥，优先 date）。
    返回：过滤后的 list[dict]（保持原顺序，不排序 —— 趋势图要求时序原样）。
    """
    if date:
        start = end = date
    keep = None
    if devices:
        keep = {str(d) for d in devices if str(d)}
    out = []
    for r in records:
        day = str(r.get("ts", ""))[:10]
        if not day:
            continue                            # 无日期的脏行直接剔除（边界）
        if start and day < str(start):
            continue
        if end and day > str(end):
            continue
        if keep is not None and str(r.get("device_id")) not in keep:
            continue
        out.append(r)
    return out


def previous_window(records, start, end, days):
    """上一等长窗口（st.metric 的环比 delta 取数用）。"""
    from datetime import date as _d, timedelta

    def _shift(s, n):
        y, m, dd = (int(x) for x in str(s).split("-"))
        return (_d(y, m, dd) - timedelta(days=n)).strftime("%Y-%m-%d")

    if not start or not end or days <= 0:
        return []
    return filter_records(records, _shift(start, days), _shift(end, days))


# ---------------------------------------------------------------------------
# TODO-2 / TODO-4 / TODO-5 单项指标（每个都可独立单测，边界见 tests/test_kpi.py）
# ---------------------------------------------------------------------------
def total_output(records):
    return int(sum(int(r.get("output", 0) or 0) for r in records))


def total_good(records):
    return int(sum(int(r.get("ok_qty", 0) or 0) for r in records))


def avg_yield_pct(records):
    """平均良率（加权口径：合格总量/总产量，比"逐行均值"抗小样本噪声）。"""
    out = total_output(records)
    return round(100.0 * total_good(records) / out, 2) if out else 0.0


def alarm_rows(records, vib_max):
    """告警明细：振动超阈值（TODO-2 的 c4 计数与 TODO-4 的告警表同一真源）。"""
    return [r for r in records if _num(r.get("vib")) > float(vib_max)]


def online_devices(records, status_online):
    """设备在线数：每台设备"最后一条记录"的状态为在线 → 计在线。返回 (在线, 总数)。"""
    last = {}
    for r in records:
        dev = str(r.get("device_id"))
        last[dev] = str(r.get("status"))          # 时序原样，后写覆盖前写
    if not last:
        return 0, 0
    return sum(1 for v in last.values() if v == str(status_online)), len(last)


def efficiency(records, target_per_day, days=1):
    """效率对标 = 实际产量 / (单日目标 × 窗口天数)，上限截断到 1.0（st.progress 只收 0..1）。

    工单 TODO-5 的"实际/目标"：目标口径必须是同时间窗的目标，否则跨月窗口会
    算出 5000% 这类无意义数（审计发现之一）。days<1 视为 1（单日/空窗兜底）。
    """
    tgt = float(target_per_day) * max(1, int(days))
    if tgt <= 0:
        raise ValueError("targets.output_qty_per_day 必须为正（当前 %.3f）" % tgt)
    raw = total_output(records) / tgt
    return min(1.0, round(raw, 4)), round(raw, 4)


def mean_temp(records):
    vals = [_num(r.get("temp")) for r in records]
    vals = [v for v in vals if v == v]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def max_vib(records):
    vals = [_num(r.get("vib")) for r in records]
    return round(max(vals), 3) if vals else 0.0


def oee_mean(lines):
    """台账 OEE 均值（无台账 → None，报告如实标"不适用"）。"""
    vals = [float(r["oee"]) for r in (lines or []) if "oee" in r]
    return round(sum(vals) / len(vals), 2) if vals else None


def plan_rate(lines):
    """计划达成率 = 台账产出合计 / 计划合计。"""
    produced = sum(float(r["produced"]) for r in (lines or []))
    planned = sum(float(r["planned"]) for r in (lines or []))
    return round(100.0 * produced / planned, 2) if planned else 0.0


def _num(v):
    """宽松取数：非数字/None → nan（供过滤与统计统一忽略）。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def tone(value, rules):
    """红绿灯口径（阈值全部来自 config）：≥danger 绿，≥warn 黄，否则红。"""
    if value >= float(rules["danger"]):
        return "ok"
    if value >= float(rules["warn"]):
        return "warn"
    return "error"


# ---------------------------------------------------------------------------
# 五 KPI 汇总（名称与顺序由 config/rules.yaml 的 kpi.required/kpi.extra 决定）
#
# rules 是一个"扁平规则包"，由 pipeline 从 YAML 组装（单一真源，见 build_rules）：
#   temp_max / vib_max / status_online / output_qty_per_day / warn / danger
#   days（窗口天数，效率对标折算用，由调用方注入）
#   + kpi_required / kpi_extra
# ---------------------------------------------------------------------------
def compute_kpis(records, rules, lines=None, prev=None):
    """返回有序 KPI 列表：每项 {name,value,text,delta,tone,raw,total}。"""
    on, tot = online_devices(records, rules["status_online"])
    eff_clip, eff_raw = efficiency(records, rules["output_qty_per_day"],
                                   rules.get("days", 1))
    ay = avg_yield_pct(records)
    alar = len(alarm_rows(records, rules["vib_max"]))
    out = total_output(records)
    om, pr = oee_mean(lines), plan_rate(lines)
    base = {
        "总产量": dict(value=out, text="{:,}".format(out), raw=out, total=None),
        "平均良率": dict(value=ay, text="%.2f%%" % ay, raw=ay, total=None),
        "设备在线数": dict(value=on, text="%d/%d" % (on, tot), raw=on, total=tot),
        "今日告警数": dict(value=alar, text=str(alar), raw=alar, total=None),
        "效率对标": dict(value=eff_raw, text="%.1f%%" % (eff_raw * 100),
                       raw=eff_clip, total=None),
        "OEE均值": dict(value=om, text="%.2f%%" % om if om is not None else "不适用",
                       raw=om, total=None),
        "计划达成率": dict(value=pr, text="%.2f%%" % pr if pr is not None else "不适用",
                        raw=pr, total=None),
        "平均温度": dict(value=mean_temp(records),
                       text="%s %s" % ("%.2f" % mean_temp(records),
                                       rules.get("unit_symbol", "℃")),
                       raw=mean_temp(records), total=None),
        "最高振动": dict(value=max_vib(records),
                       text="%.3f mm/s" % max_vib(records),
                       raw=max_vib(records), total=None),
    }
    prev_k = {k["name"]: k for k in compute_kpis(prev, rules)} if prev else {}
    names = list(rules.get("kpi_required") or []) + list(rules.get("kpi_extra") or [])
    names = names or list(base)
    unknown = [n for n in names if n not in base]
    if unknown:                               # 配置写了代码不认识的 KPI 名 → 立刻失败
        raise ValueError("config kpi 列表含未实现指标: %s（请同步 core.compute_kpis）"
                         % ", ".join(unknown))
    res = []
    for n in names:
        item = dict(base[n])
        item["name"] = n
        item["delta"] = _delta(item, prev_k.get(n))
        item["tone"] = _item_tone(n, item, rules)
        res.append(item)
    return res


def _item_tone(name, item, rules):
    """指标卡配色：告警类"越高越坏"，良率类"越高越好"（避免 delta 正负想当然）。"""
    val = item["value"]
    if val is None:
        return "ok"
    if name == "平均良率":
        return tone(val, rules)
    if name == "今日告警数":
        return "error" if val > 0 else "ok"
    if name == "设备在线数":
        tot = item.get("total") or 0
        if tot == 0:
            return "warn"
        return "ok" if val == tot else ("warn" if val * 2 >= tot else "error")
    if name == "效率对标":
        return "ok" if val >= 1.0 else ("warn" if val >= 0.8 else "error")
    if name == "最高振动":
        return "error" if val > float(rules["vib_max"]) else "ok"
    if name == "平均温度":
        return "error" if val > float(rules["temp_max"]) else "ok"
    return "ok"


def _delta(item, prev_item):
    """环比文本（st.metric 的 delta）；无上一窗口 → 空串（不谎报涨跌）。"""
    if prev_item is None or item.get("value") is None:
        return ""
    pv = prev_item.get("value")
    if pv is None:
        return ""
    d = item["value"] - pv
    return "%+.2f" % d if abs(d) >= 0.005 else "0.00"


def kpi_map(kpis):
    """KPI 列表 → {名称: 项}，模板/断言都好用。"""
    return {k["name"]: k for k in kpis}


# ---------------------------------------------------------------------------
# TODO-3 趋势 / TODO-4 仪表与红绿灯 / 详细分析 / 附表
# ---------------------------------------------------------------------------
def trend(records, bucket="hour"):
    """产量趋势聚合：bucket=hour 按时间戳原样，day 按日汇总（px.line 的数据面）。"""
    agg, order = {}, []
    for r in records:
        key = str(r.get("ts")) if bucket == "hour" else str(r.get("ts"))[:10]
        if key not in agg:
            agg[key] = {"ts": key, "output": 0, "ok_qty": 0, "n": 0}
            order.append(key)
        agg[key]["output"] += int(r.get("output", 0) or 0)
        agg[key]["ok_qty"] += int(r.get("ok_qty", 0) or 0)
        agg[key]["n"] += 1
    return [agg[k] for k in order]


def gauge(records, rules):
    """良率仪表盘读数（TODO-4）：delta 相对 config 的良率达标线（danger）。"""
    ay = avg_yield_pct(records)
    return {"value": ay, "delta": round(ay - float(rules["danger"]), 2),
            "tone": tone(ay, rules)}


def device_status(records, rules):
    """设备状态红绿灯（TODO-4）：按设备末条状态 + 该设备超阈值次数综合定级。"""
    vib_max, temp_max = float(rules["vib_max"]), float(rules["temp_max"])
    online = str(rules["status_online"])
    info = {}
    for r in records:
        dev = str(r.get("device_id"))
        d = info.setdefault(dev, {"device_id": dev, "status": "", "alarms": 0,
                                  "over_temp": 0, "n": 0})
        d["status"] = str(r.get("status"))
        d["n"] += 1
        if _num(r.get("vib")) > vib_max:
            d["alarms"] += 1
        if _num(r.get("temp")) > temp_max:
            d["over_temp"] += 1
    for dev, d in info.items():
        if d["status"] != online or d["alarms"] > 2 or d["over_temp"] > 0:
            d["tone"] = "error"
        elif d["alarms"] > 0:
            d["tone"] = "warn"
        else:
            d["tone"] = "ok"
        d["light"] = STATUS_TONE[d["tone"]]
    return [info[k] for k in sorted(info)]


def by_device(records, rules):
    """详细分析用的设备对比表（日报第二段 / B 层对比）。"""
    rows = []
    for d in device_status(records, rules):
        recs = [r for r in records if str(r.get("device_id")) == d["device_id"]]
        rows.append({"device_id": d["device_id"], "line": recs[0].get("line", "") if recs else "",
                     "output": total_output(recs), "ok_qty": total_good(recs),
                     "yield_pct": avg_yield_pct(recs), "alarms": d["alarms"],
                     "tone": d["tone"], "light": d["light"]})
    return sorted(rows, key=lambda r: (-r["output"], r["device_id"]))


def tail_rows(records, n):
    """数据附表：末 n 行（越界自动截断，n<=0 → 空表）。"""
    if n <= 0:
        return []
    return records[-int(n):]


# ---------------------------------------------------------------------------
# 工单 P3.2-3 异常识别 + 处置建议（B/A 层）
# ---------------------------------------------------------------------------
SUGGESTIONS = {
    "temp": "温度 %.1f{U} > 限值 %.1f{U}：疑似散热不良/过载。建议：①核查冷却风机与滤网；"
            "②降载 10%% 观察 30min；③若持续爬升，报设备组停机点检。",
    "vib": "振动 %.3f mm/s > 限值 %.3f mm/s：疑似不平衡/轴承磨损/地脚松动。"
           "建议：①复检地脚螺栓扭矩；②安排动平衡；③连续 3 点超标即换轴承并录台账。",
    "yield": "良率 %.2f%% < 目标 %.2f%%：建议首件复确认、检查上料批次与刀具寿命。",
    "offline": "设备状态 %s（非在线）：建议核对供电/通信链路，确认是否为计划内停机。",
}


def suggest(row, rules):
    """单条记录 → 处置建议列表（可能同时命中温度+振动，按严重度排序）。"""
    th, tv = float(rules["temp_max"]), float(rules["vib_max"])
    out = []
    temp, vib = _num(row.get("temp")), _num(row.get("vib"))
    if temp > th:
        out.append(("temp", SUGGESTIONS["temp"].replace(
            "{U}", str(rules.get("unit_symbol", "℃"))) % (temp, th)))
    if vib > tv:
        out.append(("vib", SUGGESTIONS["vib"] % (vib, tv)))
    if str(row.get("status")) != str(rules["status_online"]):
        out.append(("offline", SUGGESTIONS["offline"] % row.get("status")))
    return out


def anomalies(records, rules, topk=5):
    """异常清单：temp>限值 或 vib>限值 或 非在线状态，逐条附原因与建议。"""
    th, tv = float(rules["temp_max"]), float(rules["vib_max"])
    rows = []
    for r in records:
        if _num(r.get("temp")) > th or _num(r.get("vib")) > tv:
            hits = suggest(r, rules)
            rows.append({
                "ts": r.get("ts"), "device_id": r.get("device_id"),
                "temp": r.get("temp"), "vib": r.get("vib"),
                "status": r.get("status"),
                "reasons": ",".join(h[0] for h in hits) or "over_limit",
                "suggestion": "；".join(h[1] for h in hits) or "超阈值，建议现场复核。",
            })
    rows.sort(key=lambda x: (-_safe(x["vib"]), -_safe(x["temp"]), str(x["ts"])))
    return rows if topk is None else rows[:int(topk)]


def _safe(v):
    return v if isinstance(v, (int, float)) and not math.isnan(v) else 0.0


def drill(records, device, rules, topk=5):
    """A 层钻取：单设备明细 + 该机告警榜（仪表盘点击下钻的等价数据面）。"""
    sub = [r for r in records if str(r.get("device_id")) == str(device)]
    return {"device_id": str(device), "n": len(sub),
            "output": total_output(sub), "ok_qty": total_good(sub),
            "yield_pct": avg_yield_pct(sub), "mean_temp": mean_temp(sub),
            "max_vib": max_vib(sub),
            "alarms": len(alarm_rows(sub, rules["vib_max"])),
            "top_anomalies": anomalies(sub, rules, topk)}


# ---------------------------------------------------------------------------
# A 层：图表选择事件 → 联动明细（工单"点击折线点弹出该时段明细表"）
# 纯函数：app.py 的 st.plotly_chart(on_select="rerun") / st.dataframe 选择、
# run.py CLI 的"复放选择事件"证据行，全部走这一个函数（绝不两套逻辑）。
# ---------------------------------------------------------------------------
def drill_rows(selection_points, rows, rules):
    """把选择事件里的数据点翻译成明细行。

    参数：selection_points —— 前端回送的点列表，每个点可以是——
            {"x"/"ts": 时间桶}                 → 命中 str(ts) 以该桶为前缀的行
            {"x": 桶, "device_id": 设备}       → 时间桶 + 设备双条件
            {"row"/"row_index": i} 或裸整数 i  → 取 rows[i] 并展开为"该设备该日"
        rows —— 当前窗口的记录列表（保持原时序）。
        rules —— 扁平规则包（config.Settings.rules()），消费两个可调键：
            drill_max_rows（默认 30，<=0 → 空表，改配置即可关掉钻取）
            drill_detail_columns（明细列裁剪，缺列自动忽略）。
    返回：按 rows 原顺序去重后的明细 list[dict]，行数截到 drill_max_rows。
    防御性：非 dict 点、缺桶点、越界/非数字行号一律忽略，绝不抛异常
    （前端选择格式随版本漂移时，仪表盘不能白屏）。
    确定性：只按输入顺序遍历 + 整数下标去重，不使用 dict/set 迭代序，
    也不使用 builtin hash()（PYTHONHASHSEED 随机化），结果逐字节可复现。
    """
    try:
        cap = int(rules.get("drill_max_rows", 30))
    except (TypeError, ValueError):
        cap = 30
    if cap <= 0:
        return []
    cols = [str(c) for c in (rules.get("drill_detail_columns") or [])]

    want, rowidx = [], set()
    for p in (selection_points or []):
        if isinstance(p, bool):
            continue
        if isinstance(p, (int, float)):
            if 0 <= int(p) < len(rows):
                rowidx.add(int(p))
            continue
        if not isinstance(p, dict):
            continue
        bucket = p.get("x", p.get("ts"))
        if bucket is not None and str(bucket):
            dev = str(p["device_id"]) if p.get("device_id") is not None else None
            want.append((str(bucket), dev))
            continue
        idx = p.get("row", p.get("row_index"))
        if isinstance(idx, bool) or not isinstance(idx, (int, float)):
            continue
        idx = int(idx)
        if 0 <= idx < len(rows):
            rowidx.add(idx)
    # 表格行号选择：展开成"该设备该日"的整段明细（工单：点击行弹出该时段明细）。
    # 行本身已在 rowidx 保底命中；无 ts 的脏行不展开，避免空前缀误伤全表。
    for i in sorted(rowidx):
        ts = str(rows[i].get("ts", ""))
        if ts:
            want.append((ts[:10], str(rows[i].get("device_id"))))
    uniq, dedup = [], set()
    for pair in want:
        if pair not in dedup:
            dedup.add(pair)
            uniq.append(pair)

    keep = set()
    for pos, r in enumerate(rows):
        if pos in rowidx:
            keep.add(pos)
            continue
        ts = str(r.get("ts", ""))
        if not ts:
            continue
        dev = str(r.get("device_id"))
        for bucket, bdev in uniq:
            if ts.startswith(bucket) and (bdev is None or dev == bdev):
                keep.add(pos)
                break
    out = []
    for pos in sorted(keep):
        r = rows[pos]
        picked = {k: r[k] for k in cols if k in r} if cols else dict(r)
        if not picked:
            picked = dict(r)
        out.append(picked)
        if len(out) >= cap:
            break
    return out


def drill_fingerprint(det):
    """明细列表的稳定指纹（zlib.crc32 而非 builtin hash()，跨 PYTHONHASHSEED 不变）。

    序列化口径：按键名排序 + 值转字符串，保证同一份明细永远得到同一个 8 位十六进制串，
    可直接写进 output/report.txt 供人复核（可证伪证据）。
    """
    import json
    import zlib
    canon = json.dumps([[[k, str(v)] for k, v in sorted(r.items())] for r in det],
                       ensure_ascii=False, separators=(",", ":"))
    return "%08x" % zlib.crc32(canon.encode("utf-8"))
