# -*- coding: utf-8 -*-
"""内置断言表 + 工单分层达标线（及格D/良好C/优秀B/超优A + 课堂保底组）。

为什么不用 pytest 代替：run.py 要在课堂白板一键出结果（工单验收
证据链），所以断言以**数据表**形式内置在 src/ 里，pytest 只是把同一
张表再跑一遍（tests/test_selfcheck.py），两处共用一套口径不重复实现。
"""
import os

from . import core

BOUNDARY_KINDS = ("空输入", "极值", "异常")
TIER_ORDER = ("D", "C", "B", "A")
#: 工单 P1.1 分层表字母 ↔ 档位名（定档唯一权威；课堂阶梯仅留作保底）
TIER_NAMES = {"D": "及格", "C": "良好", "B": "优秀", "A": "超优"}
#: 课堂"D 学徒跟做"保底自检组：保留证据，但不占工单字母、不计入定档
FLOOR = "保底"


def _raises(callable_, exc=core.ExerciseError):
    """callable_ 必须抛出 exc 才算通过（异常路径断言）。"""
    try:
        callable_()
    except exc:
        return True
    except Exception:                          # noqa: BLE001 其它异常=不达标
        return False
    return False


def _case(number, tier, kind, label, fn):
    return {"number": number, "tier": tier, "kind": kind, "label": label,
            "fn": fn}


def build_cases(cfg, files):
    """按配置构造全部断言用例（阈值/样本/设备清单都来自 rules.yaml）。"""
    temp = cfg.temperature
    zero = float(temp.get("absolute_zero_c", core.ABSOLUTE_ZERO_C_DEFAULT))
    tol = float(temp.get("tolerance", 1e-06))
    unit = str(temp.get("unit", "c"))
    quad = cfg.quadratic
    extreme = quad.get("extreme") or {"a": 1, "b": -1000000, "c": 1}
    rows = cfg.device_rows
    width = int(cfg.devices.get("id_width", 2))
    plc_cfg = cfg.plc
    scan_max = int(plc_cfg.get("scan_ms_max", 10000))
    cases = []

    # ---------- 题1 ----------
    cases.append(_case("题1", "D", "正常", "100℃ → 212℉/373.15K（华氏+开尔文都在）",
                       lambda: core.convert_temperature(100, unit, zero)
                       == (212.0, 373.15)))
    cases.append(_case("题1", "D", "正常", "0℃ → 32℉/273.15K",
                       lambda: core.convert_temperature(0, unit, zero)
                       == (32.0, 273.15)))
    cases.append(_case("题1", "B", "正常", "配置样本全部同时返回 ℉ 与 K",
                       lambda: all(
                           len(core.convert_temperature(v, unit, zero)) == 2
                           for v in (temp.get("samples") or []))))
    cases.append(_case("题1", "A", "空输入", "None → ExerciseError",
                       lambda: _raises(lambda: core.convert_temperature(
                           None, unit, zero))))
    cases.append(_case("题1", "A", "空输入", "空字符串 → ExerciseError",
                       lambda: _raises(lambda: core.convert_temperature(
                           "  ", unit, zero))))
    cases.append(_case("题1", "A", "极值", "绝对零度 %.2f℃ → 0K（误差<%g）"
                       % (zero, tol),
                       lambda: abs(core.convert_temperature(zero, unit, zero)
                                   [1] - 0.0) < tol))
    cases.append(_case("题1", "A", "极值", "极大值 1e6℃ 线性关系成立",
                       lambda: abs(core.convert_temperature(1000000, unit,
                                                             zero)[0]
                                   - (1000000 * 9.0 / 5.0 + 32.0)) < tol))
    cases.append(_case("题1", "A", "异常", "低于绝对零度 → ExerciseError",
                       lambda: _raises(lambda: core.convert_temperature(
                           zero - 1, unit, zero))))
    cases.append(_case("题1", "A", "异常", "非数字输入 'abc' → ExerciseError",
                       lambda: _raises(lambda: core.convert_temperature(
                           "abc", unit, zero))))
    cases.append(_case("题1", "A", "异常", "输入单位非 ℃ → ExerciseError",
                       lambda: _raises(lambda: core.convert_temperature(
                           100, "f", zero))))

    # ---------- 题2 ----------
    cases.append(_case("题2", "D", "正常", "x²-3x+2 → (2.0, 1.0)",
                       lambda: _roots_equal(core.solve_quadratic(1, -3, 2),
                                            (2.0, 1.0), tol)))
    cases.append(_case("题2", "C", "正常", "Δ<0 无实根 → None",
                       lambda: core.solve_quadratic(1, 0, 1) is None))
    cases.append(_case("题2", "B", "正常", "Δ=0 重根 → (-1.0, -1.0)",
                       lambda: _roots_equal(core.solve_quadratic(1, 2, 1),
                                            (-1.0, -1.0), tol)))
    cases.append(_case("题2", "A", "空输入", "a=None → ExerciseError",
                       lambda: _raises(lambda: core.solve_quadratic(
                           None, 1, 1))))
    cases.append(_case("题2", "A", "空输入", "b='' → ExerciseError",
                       lambda: _raises(lambda: core.solve_quadratic(
                           1, "", 1))))
    cases.append(_case("题2", "A", "极值", "极值系数：两根代回原方程残差达标"
                       "（韦达和校验）", lambda: _vieta(extreme, tol)))
    cases.append(_case("题2", "A", "极值", "a 极小 1e-6 仍返回有限根",
                       lambda: all(abs(r) < 1e18 for r in
                                   core.solve_quadratic(1e-6, 1.0, 1.0))))
    cases.append(_case("题2", "A", "异常", "a=0 退化 → ExerciseError",
                       lambda: _raises(lambda: core.solve_quadratic(0, 1, 1))))
    cases.append(_case("题2", "A", "异常", "系数 'x' → ExerciseError",
                       lambda: _raises(lambda: core.solve_quadratic(
                           1, "x", 1))))

    # ---------- 题3 ----------
    def crud_full_cycle():
        reg = core.Registry(width, core.STATUS_STOP)
        for row in rows:
            reg.add(row["id"], row["name"], row["status"])
        if reg.count() != len(rows):
            return False
        removed = reg.remove(cfg.device_key(cfg.devices["remove_id"]))
        return removed is not None and reg.count() == len(rows) - 1

    cases.append(_case("题3", "C", "正常", "配置清单全入库后删除真正生效(-1台)",
                       crud_full_cycle))
    first_id = rows[0]["id"] if rows else "（清单为空）"
    cases.append(_case("题3", "B", "正常",
                       "YAML 的 01 归一化为 %s" % first_id,
                       lambda: bool(rows) and rows[0]["id"] ==
                       core.normalize_id(rows[0]["id"], width)))
    cases.append(_case("题3", "B", "正常", "改状态后复核生效",
                       lambda: _update_ok(cfg)))
    cases.append(_case("题3", "A", "空输入", "add(None) → ExerciseError",
                       lambda: _raises(lambda: core.Registry().add(
                           None, "无名机"))))
    cases.append(_case("题3", "A", "空输入", "add('') → ExerciseError",
                       lambda: _raises(lambda: core.Registry().add(
                           "  ", "无名机"))))
    cases.append(_case("题3", "A", "极值", "500 台批量增删后计数自洽",
                       lambda: _bulk(500)))
    cases.append(_case("题3", "A", "极值", "宽度 3 的 ID 零填充为 '007'",
                       lambda: core.normalize_id(7, 3) == "007"))
    cases.append(_case("题3", "A", "异常", "重复 ID 新增 → ExerciseError",
                       lambda: _raises(lambda: _dup())))
    cases.append(_case("题3", "A", "异常", "删不存在的键 → None（非假装删除）",
                       lambda: core.Registry().remove("99") is None))
    cases.append(_case("题3", "A", "异常", "改不存在的设备 → ExerciseError",
                       lambda: _raises(lambda: core.Registry().update(
                           "88", status="运行"))))

    # ---------- 题4 ----------
    def plc_ok():
        dev = core.PLC(cfg.device_key(plc_cfg.get("dev_id")),
                       plc_cfg.get("name", "S7-1200"),
                       plc_cfg.get("scan_ms", 100), scan_ms_max=scan_max)
        base_status = dev.status
        message = dev.start()
        scans = dev.scan(int(plc_cfg.get("scan_rounds", 1)))
        return (isinstance(dev, core.Device)
                and base_status == core.STATUS_STOP
                and dev.status == core.STATUS_RUN
                and message.endswith("扫描%dms" % dev.scan_ms)
                and len(scans) == int(plc_cfg.get("scan_rounds", 1)))

    cases.append(_case("题4", "B", "正常", "PLC 继承 Device+覆盖 start()+scan()",
                       plc_ok))
    cases.append(_case("题4", "B", "正常", "基类 start() 与子类文案不同",
                       lambda: core.Device("09", "机").start()
                       != core.PLC("09", "机", 10, scan_ms_max=scan_max)
                       .start()))
    cases.append(_case("题4", "A", "空输入", "dev_id=None → ExerciseError",
                       lambda: _raises(lambda: core.PLC(None, "机", 10))))
    cases.append(_case("题4", "A", "空输入", "name='' → ExerciseError",
                       lambda: _raises(lambda: core.PLC("01", "   ", 10))))
    cases.append(_case("题4", "A", "空输入", "scan_ms=None → ExerciseError",
                       lambda: _raises(lambda: core.PLC("01", "机", None))))
    cases.append(_case("题4", "A", "极值", "scan_ms 取上限 %dms 合法" % scan_max,
                       lambda: core.PLC("01", "机", scan_max,
                                         scan_ms_max=scan_max).scan_ms
                       == scan_max))
    cases.append(_case("题4", "A", "极值", "scan(1000) 返回 1000 轮",
                       lambda: len(_started_plc(scan_max).scan(1000)) == 1000))
    cases.append(_case("题4", "A", "极值", "scan(0) 返回空列表（零轮合法）",
                       lambda: _started_plc(scan_max).scan(0) == []))
    cases.append(_case("题4", "A", "异常", "scan_ms=0 → ExerciseError",
                       lambda: _raises(lambda: core.PLC(
                           "01", "机", 0, scan_ms_max=scan_max))))
    cases.append(_case("题4", "A", "异常", "scan_ms 超上限 → ExerciseError",
                       lambda: _raises(lambda: core.PLC(
                           "01", "机", scan_max + 1, scan_ms_max=scan_max))))
    cases.append(_case("题4", "A", "异常", "未启动就 scan() → ExerciseError",
                       lambda: _raises(lambda: core.PLC("01", "机", 10).scan(
                           1))))
    cases.append(_case("题4", "A", "异常", "轮次为负 → ExerciseError",
                       lambda: _raises(lambda: _started_plc(scan_max).scan(
                           -1))))

    # ---------- 题5 ----------
    cases.append(_case("题5", "B", "正常", "正常文件读回内容",
                       lambda: core.safe_read(files["sample"]) ==
                       str(cfg.reader.get("sample_text", ""))))
    cases.append(_case("题5", "B", "正常", "缺失文件 → FILE_NOT_FOUND",
                       lambda: core.safe_read(files["missing"])
                       == core.FILE_NOT_FOUND))
    cases.append(_case("题5", "A", "空输入", "path='' → EMPTY_PATH",
                       lambda: core.safe_read("") == core.EMPTY_PATH))
    cases.append(_case("题5", "A", "空输入", "path=None → EMPTY_PATH",
                       lambda: core.safe_read(None) == core.EMPTY_PATH))
    cases.append(_case("题5", "A", "极值", "空文件 → 空字符串（不报错）",
                       lambda: core.safe_read(files["empty"]) == ""))
    cases.append(_case("题5", "A", "极值", "多行大文件行数正确",
                       lambda: len(core.safe_read(files["large"]).splitlines())
                       == int(files["large_lines"])))
    cases.append(_case("题5", "A", "异常", "非 UTF-8 字节 → BAD_ENCODING",
                       lambda: core.safe_read(files["bad"])
                       == core.BAD_ENCODING))
    cases.append(_case("题5", "A", "异常", "传目录 → IS_DIRECTORY",
                       lambda: core.safe_read(files["dir"])
                       == core.IS_DIRECTORY))
    cases.append(_case("题5", "A", "异常", "深层不存在路径 → FILE_NOT_FOUND",
                       lambda: core.safe_read(os.path.join(files["dir"], "a",
                                                            "b.txt"))
                       == core.FILE_NOT_FOUND))
    return cases


def _roots_equal(got, expected, tol):
    """根比较（浮点容差）。"""
    if got is None or expected is None:
        return got is expected
    return all(abs(a - b) <= tol for a, b in zip(got, expected))


def _vieta(extreme, tol):
    """极值系数的真实校验：两根代回原方程残差 + 韦达和（x1+x2=-b/a）。

    为什么不用"根的乘积"直接比：b=-1e6、c=1 时小根由减法抵消产生，
    乘积校验会因浮点损失而误判失败；代回残差用相对量级容差才站得住。
    """
    a = float(extreme["a"])
    b = float(extreme["b"])
    c = float(extreme["c"])
    roots = core.solve_quadratic(a, b, c)
    if roots is None:
        return False
    for root in roots:
        scale = max(abs(a * root * root), abs(b * root), abs(c), 1.0)
        if abs(a * root * root + b * root + c) > max(tol, 1e-9 * scale):
            return False
    return abs(sum(roots) + b / a) <= max(tol, abs(b / a) * 1e-9)


def _update_ok(cfg):
    reg = core.Registry(int(cfg.devices["id_width"]), core.STATUS_STOP)
    for row in cfg.device_rows:
        reg.add(row["id"], row["name"], row["status"])
    key = cfg.device_key(cfg.devices["update_id"])
    reg.update(key, status=str(cfg.devices["update_status"]))
    return reg.get(key).status == str(cfg.devices["update_status"])


def _bulk(count):
    reg = core.Registry(4, core.STATUS_STOP)
    for idx in range(count):
        reg.add(idx, "设备%d" % idx)
    if reg.count() != count:
        return False
    reg.remove(0)
    reg.remove(count - 1)
    return reg.count() == count - 2


def _dup():
    reg = core.Registry()
    reg.add("01", "A")
    reg.add(1, "B")                       # 归一化后与 '01' 冲突 → 必须报错


def _started_plc(scan_max):
    dev = core.PLC("01", "机", 10, scan_ms_max=scan_max)
    dev.start()
    return dev


def run_cases(cases):
    """执行断言表，返回带 ok 标记的明细（异常视为失败并记录原因）。"""
    results = []
    for case in cases:
        try:
            ok = bool(case["fn"]())
            detail = "" if ok else "返回 False"
        except Exception as exc:                    # noqa: BLE001
            ok = False
            detail = "%s: %s" % (type(exc).__name__, exc)
        results.append(dict(case, ok=ok, detail=detail))
    return results


def summarise(results):
    """按题号汇总：总数/通过数/边界(空+极值+异常)通过数/失败明细。"""
    summary = {}
    for item in results:
        bucket = summary.setdefault(item["number"], {
            "total": 0, "passed": 0, "boundary_total": 0, "boundary_passed": 0,
            "failed": []})
        bucket["total"] += 1
        bucket["passed"] += 1 if item["ok"] else 0
        if item["kind"] in BOUNDARY_KINDS:
            bucket["boundary_total"] += 1
            bucket["boundary_passed"] += 1 if item["ok"] else 0
        if not item["ok"]:
            bucket["failed"].append("%s[%s] %s %s"
                                     % (item["label"], item["tier"],
                                        item["kind"], item["detail"]))
    for bucket in summary.values():
        bucket["pass"] = bucket["total"] == bucket["passed"]
        # A 层口径：边界断言既要"够 3 条"，也要"全过"
        bucket["boundary_enough"] = (bucket["boundary_passed"] >= 3
                                     and bucket["boundary_passed"]
                                     == bucket["boundary_total"])
    return summary


def tier_gate(results, summary, style, notes_info, cfg=None):
    """工单分层达标线：D 及格 / C 良好 / B 优秀 / A 超优，逐条实测判定。

    锚定口径 = 工单 P1.1 「验收标准」四行原文（逐字复述，见 `_tier_criterion`；
    课堂"跟做阶梯"字母上移一档，不作为定档依据）：
      及格(D) ≥3题正确运行；PEP 8≥75%；有基础注释
      良好(C) 4题；命名有意义
      优秀(B) 5题全对；PEP 8≥85%；结构清晰
      超优(A) 优秀+每题附测试用例与《迁移笔记》
    线值全部来自 config/rules.yaml（pep8_pass_rate_d / pep8_pass_rate_b /
    d_min_correct / c_min_correct / b_min_correct / naming_meaningful_rate /
    tests_per_question_min），实测数字来自 summary（内置断言）、style
    （stylecheck + testmap 真计数）与 notes_info（笔记文本实测），绝不编造。
    原文里的百分比写的是 75%/85%（不带小数），实跑用的线值（可能是 75.0%，
    也可能被 rules.yaml 抬起）只写在证据段，不去改写工单原文——
    `tests/test_pipeline_cli.py::test_workorder_rows_are_quoted_verbatim` 锁住这一点。
    课堂"D 学徒跟做保底"保留为独立"保底"组，不计入工单档位。
    """
    by_tier = {}
    for item in results:
        by_tier.setdefault(item["tier"], []).append(item)

    def tier_pass(tier):
        items = by_tier.get(tier, [])
        return bool(items) and all(i["ok"] for i in items)

    numbers = sorted(summary)
    correct = sum(1 for n in numbers if summary.get(n, {}).get("pass"))
    d_min = int(getattr(cfg, "d_min_correct", 3))
    c_min = int(getattr(cfg, "c_min_correct", 4))
    b_min = int(getattr(cfg, "b_min_correct", 5))
    d_line = float(getattr(cfg, "pep8_pass_rate_d", 75.0))
    b_line = float(getattr(cfg, "pep8_pass_rate_b", 85.0))
    name_line = float(getattr(cfg, "naming_meaningful_rate", 90.0))
    tests_min = int(getattr(cfg, "tests_per_question_min", 1))

    score = float(style.get("score", 0.0))
    passed = int(style.get("passed", 0))
    total = int(style.get("total", 0))
    comments = style.get("comments") or {}
    funcs_total = int(comments.get("funcs_total", 0))
    funcs_doc = int(comments.get("funcs_documented", 0))
    mods_total = int(comments.get("modules_total", 0))
    mods_doc = int(comments.get("modules_documented", 0))
    naming_checked = int(style.get("naming_checked", 0))
    naming_passed = int(style.get("naming_passed", 0))
    naming_rate = float(style.get("naming_rate", 0.0))
    structure = style.get("structure") or {}
    parts = int(structure.get("parts_present", 0))
    parts_total = int(structure.get("parts_total", 4))
    ex_fns = int(structure.get("exercise_functions", 0))
    ex_fns_doc = int(structure.get("exercise_functions_documented", 0))
    src_mods = int(structure.get("src_modules_total", 0))
    src_mods_doc = int(structure.get("src_modules_documented", 0))
    qtests = style.get("question_tests") or {}
    gates = []

    # ---------- 及格(D)：≥3题正确 + PEP 8≥75% + 基础注释 ----------
    gates.append(("D", "正确 %d/5 题（及格线 ≥%d 题）" % (correct, d_min),
                  correct >= d_min))
    gates.append(("D", "PEP 8（内置子集）达标率 %.1f%%（检查项通过 %d/%d）"
                  " ≥ D 层线 %.1f%%" % (score, passed, total, d_line),
                  score >= d_line))
    gates.append(("D", "有基础注释：有 docstring 的公开函数 %d/%d、模块 %d/%d"
                  % (funcs_doc, funcs_total, mods_doc, mods_total),
                  funcs_total > 0 and funcs_doc == funcs_total
                  and mods_total > 0 and mods_doc == mods_total))

    # ---------- 良好(C)：第4题正确（4题）+ 命名有意义 ----------
    q4_ok = bool(summary.get("题4", {}).get("pass"))
    gates.append(("C", "第4题正确=%s（正确 %d/5 题 ≥ 良好线 %d 题）"
                  % ("是" if q4_ok else "否", correct, c_min),
                  q4_ok and correct >= c_min))
    gates.append(("C", "命名有意义达标率 %.1f%%（公开函数/方法名合格 %d/%d）"
                  " ≥ 命名线 %.1f%%" % (naming_rate, naming_passed,
                                        naming_checked, name_line),
                  naming_checked > 0 and naming_rate >= name_line))

    # ---------- 优秀(B)：5题全对 + PEP 8≥85% + 结构清晰 ----------
    gates.append(("B", "题1-5 全部通过（五题全对，正确 %d/5 ≥ 优秀线 %d 题）"
                  % (correct, b_min),
                  bool(numbers) and correct >= b_min
                  and correct == len(numbers)))
    gates.append(("B", "内置断言 B 层子集全过", tier_pass("B")))
    gates.append(("B", "命名规范检查：snake_case/PascalCase 违规数=%d"
                  % style.get("naming_violations", 0),
                  style.get("naming_violations", 0) == 0))
    gates.append(("B", "PEP 8（内置子集）达标率 %.1f%%（检查项通过 %d/%d）"
                  " ≥ B 层线 %.1f%%" % (score, passed, total, b_line),
                  score >= b_line))
    gates.append(("B", "结构清晰：工程四件套 %d/%d｜一题一函数 %d/5（均含 "
                  "docstring %d/5）｜src 模块有 docstring %d/%d"
                  % (parts, parts_total, ex_fns, ex_fns_doc,
                     src_mods_doc, src_mods),
                  parts == parts_total and ex_fns == 5 and ex_fns_doc == 5
                  and src_mods > 0 and src_mods_doc == src_mods))
    b_ok = all(g[2] for g in gates if g[0] == "B")

    # ---------- 超优(A)：优秀+每题附测试用例与《迁移笔记》 ----------
    counts = [int(qtests.get(n, 0)) for n in ("题1", "题2", "题3", "题4",
                                              "题5")]
    gates.append(("A", "优秀(B)层达标（超优=优秀+附加项）", b_ok))
    gates.append(("A", "每题附测试用例：pytest 命名用例 题1 %d｜题2 %d｜"
                  "题3 %d｜题4 %d｜题5 %d（每题线 ≥%d）"
                  % (counts[0], counts[1], counts[2], counts[3], counts[4],
                     tests_min),
                  all(c >= tests_min for c in counts)
                  and sum(counts) > 0))
    boundary_ok = all(summary.get(n, {}).get("boundary_enough")
                      for n in numbers) if numbers else False
    gates.append(("A", "每题 ≥3 条边界断言（空输入/极值/异常）全过",
                  boundary_ok))
    notes_measured = int(notes_info.get("verified_entries", 0))
    notes_required = int(notes_info.get("required", 10))
    questions_cov = int(notes_info.get("questions_covered", 0))
    sections_ok = bool(notes_info.get("sections_complete", False))
    notes_exists = bool(notes_info.get("exists", False))
    gates.append(("A", "迁移笔记《C→Python》：文件存在=%s｜正文实测 %d 条"
                  "（要求 ≥%d）｜逐题常见错误覆盖 %d/5｜P1.2 布局映射等"
                  "必备章节齐全=%s"
                  % ("是" if notes_exists else "否", notes_measured,
                     notes_required, questions_cov,
                     "是" if sections_ok else "否"),
                  notes_exists and notes_measured >= notes_required
                  and questions_cov == 5 and sections_ok))
    gates.append(("A", "ℹ pytest 全绿不在此代跑：由 `python -m pytest -q "
                  "-p no:cacheprovider` 现场复核", None))
    gates.append(("A", "讲解抽签：%s（seed=%s，确定性，可复现）"
                  % (notes_info.get("explain") or "未生成",
                     notes_info.get("seed", "?")),
                  bool(notes_info.get("explain"))))

    # ---------- 保底自检（课堂跟做，不计入工单档位） ----------
    gates.append((FLOOR, "跟做题1/2（能运行出结果）",
                  all(summary.get(n, {}).get("pass") for n in ("题1", "题2"))))
    gates.append((FLOOR, "改参数再跑：36.6℃ 与 100℃ 输出不同",
                  _diff_when_params_change()))
    gates.append((FLOOR, "记录一处差异（迁移笔记「引用语义」条目 + "
                  "tests/test_tier_d.py 差异断言）",
                  notes_info.get("verified_entries", 0) >= 1))

    scored = [{"tier": t, "item": item, "ok": ok} for t, item, ok in gates]
    tier_pass_result = {
        t: all(g["ok"] for g in scored
               if g["tier"] == t and g["ok"] is not None)
        for t in TIER_ORDER}
    data = {
        "correct": correct, "score": score, "passed": passed,
        "total": total, "d_line": d_line, "b_line": b_line,
        "d_min": d_min, "c_min": c_min, "b_min": b_min,
        "funcs_doc": funcs_doc, "funcs_total": funcs_total,
        "mods_doc": mods_doc, "mods_total": mods_total,
        "q4": "正确" if q4_ok else "未过", "name_rate": naming_rate,
        "name_passed": naming_passed, "name_checked": naming_checked,
        "name_line": name_line, "parts": parts, "parts_total": parts_total,
        "ex_fns": ex_fns, "ex_fns_doc": ex_fns_doc, "src_mods": src_mods,
        "src_mods_doc": src_mods_doc, "tests_min": tests_min,
        "counts": counts,
        "notes_exists": "是" if notes_exists else "否",
        "notes_entries": notes_measured, "notes_required": notes_required,
        "questions_cov": questions_cov,
        "sections": "是" if sections_ok else "否",
    }
    tiers = {}
    for t in TIER_ORDER:
        verdict = "达标" if tier_pass_result[t] else "未达标"
        tiers[t] = {
            "name": TIER_NAMES[t],
            "criterion": _tier_criterion(t),
            "summary": _tier_summary(t, data, verdict),
            "verdict": verdict,
        }
    floor_ok = all(g["ok"] for g in scored
                   if g["tier"] == FLOOR and g["ok"] is not None)
    floor_items = [g for g in gates if g[0] == FLOOR]
    tiers[FLOOR] = {
        "name": "保底自检（不计入工单档位）",
        "counts_for_work_order": False,
        "criterion": "课堂跟做保底：题1/2 跑通 + 改参数再跑 + 记录一处差异",
        "summary": "保底自检（不计入工单档位）: %d/%d 项通过 → %s（仅课堂"
                   "跟做留痕，不参与工单定档）"
                   % (sum(1 for g in floor_items if g[2]), len(floor_items),
                      "达标" if floor_ok else "未达标"),
        "verdict": "达标" if floor_ok else "未达标",
    }
    return {"gates": scored, "tier_pass": tier_pass_result,
            "tiers": tiers, "floor_pass": floor_ok}


def _tier_criterion(tier):
    """工单《P1.1》「验收标准」四行原文，逐字复述。

    这里刻意**不**把 rules.yaml 的线值插进原文：工单写的是 `PEP 8≥75%`，
    而实跑线值可能带小数（75.0%）甚至被抬起，改写原文就等于冒充工单口径。
    真实判线一律在证据段回显（`_tier_summary` 的 `≥ %.1f%%`）。
    """
    return {
        "D": "≥3题正确运行；PEP 8≥75%；有基础注释",
        "C": "4题；命名有意义",
        "B": "5题全对；PEP 8≥85%；结构清晰",
        "A": "优秀+每题附测试用例与《迁移笔记》",
    }[tier]


def _tier_summary(tier, data, verdict):
    """每档一行汇总证据：工单要求 + 真实测量数字 + 判定，报告/JSON 同源。"""
    crit = _tier_criterion(tier)
    if tier == "D":
        return ("D 层 及格（%s）: 正确 %d/5 题｜PEP 8 子集达标率 %.1f%%"
                "（检查项通过 %d/%d）≥ %.1f%%｜有 docstring 的公开函数"
                " %d/%d、模块 %d/%d → %s"
                % (crit, data["correct"], data["score"], data["passed"],
                   data["total"], data["d_line"], data["funcs_doc"],
                   data["funcs_total"], data["mods_doc"], data["mods_total"],
                   verdict))
    if tier == "C":
        return ("C 层 良好（%s）: 第4题 %s、正确 %d/5（线 ≥%d）"
                "｜命名有意义达标率 %.1f%%（合格 %d/%d）≥ %.1f%% → %s"
                % (crit, data["q4"], data["correct"], data["c_min"],
                   data["name_rate"], data["name_passed"],
                   data["name_checked"], data["name_line"], verdict))
    if tier == "B":
        return ("B 层 优秀（%s）: 正确 %d/5｜PEP 8 子集达标率 %.1f%%"
                "（检查项通过 %d/%d）≥ %.1f%%｜结构：四件套 %d/%d、"
                "一题一函数 %d/5、src 模块 docstring %d/%d → %s"
                % (crit, data["correct"], data["score"], data["passed"],
                   data["total"], data["b_line"], data["parts"],
                   data["parts_total"], data["ex_fns"], data["src_mods_doc"],
                   data["src_mods"], verdict))
    c = data["counts"]
    return ("A 层 超优（%s）: 每题 pytest 用例 题1 %d｜题2 %d｜题3 %d｜"
            "题4 %d｜题5 %d（线 ≥%d）｜迁移笔记 存在=%s 正文 %d 条"
            "（≥%d）逐题易错点 %d/5 必备章节=%s → %s"
            % (crit, c[0], c[1], c[2], c[3], c[4], data["tests_min"],
               data["notes_exists"], data["notes_entries"],
               data["notes_required"], data["questions_cov"],
               data["sections"], verdict))


def _diff_when_params_change():
    """D 层"改参数再跑"证据：同函数不同入参必须给出不同结果。"""
    return (core.convert_temperature(36.6)[0]
            != core.convert_temperature(100)[0])
