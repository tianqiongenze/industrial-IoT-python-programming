# -*- coding: utf-8 -*-
"""一题一函数（GB/T 8566 编码要求：主函数只做调用与输出）。

每个 exercise*() 只做"取配置 → 调 core → 组织可核对的文本证据"，
不写文件、不打印；落盘由 pipeline 统一负责，保证可单测与可复现。
"""
from . import core


def _result(number, title, lines, payload):
    """统一结果契约：题号/标题/报告行/结构化数据。"""
    return {"number": number, "title": title, "lines": list(lines),
            "payload": payload}


def exercise1(cfg):
    """题1：温度单位换算器（输入℃，同时输出℉与K + 阈值定级）。"""
    temp_cfg = cfg.temperature
    unit = str(temp_cfg.get("unit", "c"))
    zero = float(temp_cfg.get("absolute_zero_c", core.ABSOLUTE_ZERO_C_DEFAULT))
    warn = float(temp_cfg.get("warn", cfg.warn))
    danger = float(temp_cfg.get("danger", cfg.danger))
    rows, lines = [], []
    for sample in temp_cfg.get("samples") or []:
        fahr, kelvin = core.convert_temperature(sample, unit, zero)
        level = core.temperature_level(sample, warn, danger)
        rows.append({"celsius": float(sample), "fahrenheit": fahr,
                     "kelvin": kelvin, "level": level})
        lines.append("%s℃ → %.2f℉ / %.2fK（判定:%s）"
                     % (sample, fahr, kelvin, level))
    return _result("题1", "温度单位换算器（℃→℉/K）", lines,
                   {"unit": unit, "absolute_zero_c": zero, "rows": rows,
                    "warn": warn, "danger": danger})


def exercise2(cfg):
    """题2：一元二次方程（两实根 / 重根 / 无实根 三分支 + 极值）。"""
    quad = cfg.quadratic
    lines, rows = [], []
    for case in quad.get("cases") or []:
        coef_a = case.get("a", 1)
        coef_b = case.get("b", 0)
        coef_c = case.get("c", 0)
        roots = core.solve_quadratic(coef_a, coef_b, coef_c)
        disc = float(coef_b) ** 2 - 4.0 * float(coef_a) * float(coef_c)
        label = "无实根" if roots is None else "x1=%.6g x2=%.6g" % roots
        rows.append({"a": coef_a, "b": coef_b, "c": coef_c, "delta": disc,
                     "roots": list(roots) if roots else None})
        lines.append("%sx²%+gx%+g → Δ=%.6g → %s"
                     % (coef_a, coef_b, coef_c, disc, label))
    extreme = quad.get("extreme") or {}
    if extreme:
        roots = core.solve_quadratic(extreme.get("a"), extreme.get("b"),
                                     extreme.get("c"))
        rows.append({"extreme": True, "a": extreme.get("a"),
                     "b": extreme.get("b"), "c": extreme.get("c"),
                     "roots": list(roots) if roots else None})
        lines.append("极值系数 %s → 根 %s（韦达定理校验和=%.6g）"
                     % (extreme, roots, -float(extreme["b"]) / float(
                         extreme["a"])))
    return _result("题2", "一元二次方程求解", lines, {"rows": rows})


def exercise3(cfg):
    """题3：设备清单管理（增/查/改/删 全链路，删除真实生效并复核台数）。"""
    dev_cfg = cfg.devices
    reg = core.Registry(dev_cfg.get("id_width", 2),
                        dev_cfg.get("default_status", core.STATUS_STOP))
    rows = cfg.device_rows
    for row in rows:
        reg.add(row["id"], row["name"], row["status"])
    lines = ["初始化 %d 台，键=%s" % (reg.count(), reg.ids())]

    update_id = cfg.device_key(dev_cfg.get("update_id"))
    new_status = str(dev_cfg.get("update_status", core.STATUS_RUN))
    target = reg.get(update_id)
    if target is None:
        raise ValueError("配置 devices.update_id=%r 在清单中不存在"
                         % (dev_cfg.get("update_id"),))
    reg.update(update_id, status=new_status)
    lines.append("改 %s 状态→%s（复核=%s）"
                 % (update_id, new_status, reg.get(update_id).status))

    before = reg.count()
    remove_key = cfg.device_key(dev_cfg.get("remove_id"))
    removed = reg.remove(remove_key)
    after = reg.count()
    if removed is None:
        raise ValueError("配置 devices.remove_id=%r 删除空操作：键 %s 不存在"
                         % (dev_cfg.get("remove_id"), remove_key))
    if after != before - 1:
        raise ValueError("删除未生效：%d → %d" % (before, after))
    lines.append("删 %s：%d 台 → %d 台（键已真正弹出，删除生效）"
                 % (remove_key, before, after,))
    lines.append("按 topk=%d 取前 %d 台：%s"
                 % (cfg.topk, len(reg.top(cfg.topk)),
                    ", ".join("%s/%s" % (r["dev_id"], r["name"])
                              for r in reg.top(cfg.topk))))
    return _result("题3", "设备清单 CRUD（字典实现）", lines,
                   {"before": before, "after": after,
                    "removed": removed.describe(), "keys": reg.ids(),
                    "rows": reg.to_rows(), "updated": target.name})


def exercise4(cfg):
    """题4：Device 基类 + PLC 子类（新增 scan_ms、覆盖 start()、scan 方法）。"""
    plc_cfg = cfg.plc
    scan_ms_max = int(plc_cfg.get("scan_ms_max", 10000))
    plc = core.PLC(cfg.device_key(plc_cfg.get("dev_id")),
                   plc_cfg.get("name", "S7-1200"),
                   plc_cfg.get("scan_ms", 100),
                   scan_ms_max=scan_ms_max)
    base = core.Device("00", "基类对照机")
    lines = ["基类 Device.start() → %s" % base.start(),
             "子类 PLC.start() 覆盖 → %s（status=%s）"
             % (plc.start(), plc.status),
             "isinstance(PLC, Device)=%s；scan_ms=%dms（上限 %dms）"
             % (isinstance(plc, core.Device), plc.scan_ms, scan_ms_max)]
    rounds = int(plc_cfg.get("scan_rounds", 1))
    scans = plc.scan(rounds)
    lines.extend(scans)
    warn_ms = int(plc_cfg.get("scan_warn_ms", 500))
    danger_ms = int(plc_cfg.get("scan_danger_ms", 1000))
    level = (core.LEVEL_DANGER if plc.scan_ms >= danger_ms
             else core.LEVEL_WARN if plc.scan_ms >= warn_ms
             else core.LEVEL_NORMAL)
    lines.append("扫描周期定级（阈值 %d/%dms）：%s" % (warn_ms, danger_ms,
                                                level))
    return _result("题4", "Device 类 + PLC 子类（含 scan）", lines,
                   {"plc": plc.describe(), "base": base.describe(),
                    "scans": scans, "level": level,
                    "scan_warn_ms": warn_ms, "scan_danger_ms": danger_ms})


def exercise5(cfg, files):
    """题5：带异常保护的文件读取器（存在/缺失/坏编码/目录/空路径）。

    参数 files：pipeline 预先把样例文件写进 output/ 后回传的路径字典。
    """
    reader_cfg = cfg.reader
    probes = [("正常", files["sample"], "utf-8"),
              ("缺失", files["missing"], "utf-8"),
              ("坏编码", files["bad"], "utf-8"),
              ("目录", files["dir"], "utf-8"),
              ("空输入", "", "utf-8"),
              ("空输入(None)", None, "utf-8")]
    lines, payload = [], {}
    for label, path, encoding in probes:
        outcome = core.safe_read(path, encoding)
        shown = outcome if len(outcome) <= 24 else outcome[:24] + "…"
        lines.append("%-14s → %s" % (label, shown))
        payload[label] = outcome
    return _result("题5", "异常保护文件读取器", lines,
                   {"probes": payload, "files": {k: v for k, v in
                                                 files.items() if v}})
