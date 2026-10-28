# -*- coding: utf-8 -*-
"""良好(C) 档：工单 C 行「4题；命名有意义」（落地把「4题」钉成「第4题必须正确 + 总正确数 ≥4」）。

此前 C 行从未被任何闸门把住（PEP 8≥75% 实为工单及格(D) 行，已移去
test_tier_d.py）。本文件验收两条真实可测的 C 档证据：
第 4 题正确 + 公开函数/方法命名有意义（snake_case、≥2 字符、可读、
非占位符）的达标率闸门，线值外置 rules.yaml 的 naming_meaningful_rate。
"""
from exercise_five import core, exercises, selfcheck, stylecheck

DIRTY_NAMES = ('"""坏命名样例。"""\n\n\ndef BadName(value):\n'
               '    """说明。"""\n    return value\n\n\n'
               'def foo():\n    """占位符名。"""\n\n\n'
               'def qv():\n    """无元音。"""\n')
CLEAN_NAMES = '"""好命名样例。"""\n\n\ndef list_devices():\n' \
              '    """说明。"""\n\n\ndef run():\n    """说明。"""\n'


def _full_notes_info(cfg):
    return {"verified_entries": 15, "required": 10, "pass": True,
            "explain": "题3", "seed": cfg.seed, "exists": True,
            "questions_covered": 5, "sections_complete": True}


def _gates_for(cfg, files, style=None):
    """跑真实断言表 + 指定规范度量，返回达标线结果（默认出厂实测）。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    if style is None:
        style = {}
    return selfcheck.tier_gate(results, summary, style,
                               _full_notes_info(cfg), cfg), summary, results


def _naming_item(gates):
    items = [g for g in gates["gates"]
             if g["tier"] == "C" and "命名有意义" in g["item"]]
    assert len(items) == 1, items
    return items[0]


def _question_item(gates):
    items = [g for g in gates["gates"]
             if g["tier"] == "C" and "第4题" in g["item"]]
    assert len(items) == 1, items
    return items[0]


def test_tier_c_exercise1_temperature(cfg):
    """题1：配置样本逐条换算，华氏与开尔文成对出现。"""
    run_ = exercises.exercise1(cfg)
    rows = run_["payload"]["rows"]
    assert len(rows) == len(cfg.temperature["samples"])
    assert all({"fahrenheit", "kelvin"} <= set(row) for row in rows)


def test_tier_c_exercise2_branches(cfg):
    """题2：配置用例覆盖 Δ>0 / Δ=0 / Δ<0 三种分支。"""
    run_ = exercises.exercise2(cfg)
    rows = [row for row in run_["payload"]["rows"] if "delta" in row]
    deltas = [row["delta"] for row in rows]
    assert any(d > 0 for d in deltas) and any(d == 0 for d in deltas)
    assert any(d < 0 for d in deltas)
    assert [row for row in rows if row["delta"] < 0][0]["roots"] is None


def test_tier_c_exercise3_delete_is_effective(cfg):
    """题3（历史缺陷回归）：删除必须真正生效且台数可复核。"""
    run_ = exercises.exercise3(cfg)
    payload = run_["payload"]
    assert payload["after"] == payload["before"] - 1
    assert payload["removed"]["dev_id"] == cfg.device_key(
        cfg.devices["remove_id"])
    assert payload["removed"]["dev_id"] not in payload["keys"]


def test_tier_c_exercise3_update_is_effective(cfg):
    """题3：改状态后回读必须一致（不是只写不回读）。"""
    run_ = exercises.exercise3(cfg)
    target = cfg.device_key(cfg.devices["update_id"])
    rows = run_["payload"]["rows"]
    row = [item for item in rows if item["dev_id"] == target]
    assert row and row[0]["status"] == str(cfg.devices["update_status"])


def test_tier_c_registry_accepts_dict_from_config(cfg):
    """题3：字典容器选型正确——按 ID 查 O(1)，键归一化后可查。"""
    reg = core.Registry(cfg.devices["id_width"])
    for row in cfg.device_rows:
        reg.add(row["id"], row["name"], row["status"])
    first = cfg.device_rows[0]["id"]
    assert reg.get(first).name == cfg.device_rows[0]["name"]
    assert reg.get("99") is None


def test_tier_c_docstrings_present_in_shipped_sources(project_root):
    """注释补全（及格 D 证据在 C 档用例里同样锁定）：src 缺失数为 0。"""
    result = stylecheck.summarize(project_root)
    src_missing = [item for item in result["violations"]
                   if item[1] in ("C0116", "C0114")
                   and item[0].startswith("exercise_five/")]
    assert src_missing == []


def test_tier_c_exercise4_gate_passes_on_shipped_run(cfg, files):
    """良好(C) 第 1 项：第 4 题正确且正确数 ≥4（出厂实测 5/5）。"""
    gates, summary, _results = _gates_for(cfg, files)
    assert summary["题4"]["pass"] is True
    item = _question_item(gates)
    assert item["ok"] is True
    assert "第4题正确=是" in item["item"] and "正确 5/5 题" in item["item"]


def test_tier_c_gate_fails_when_question4_fails(cfg, files):
    """可证伪：把题4 断言改成必假，C 档"第4题正确"项必须翻 FAIL。"""
    cases = selfcheck.build_cases(cfg, files)
    broken = [dict(case, fn=(lambda: False)) if case["number"] == "题4"
              and case["tier"] == "B" else case for case in cases]
    results = selfcheck.run_cases(broken)
    summary = selfcheck.summarise(results)
    assert summary["题4"]["pass"] is False
    gates = selfcheck.tier_gate(results, summary, {}, _full_notes_info(cfg),
                                cfg)
    assert _question_item(gates)["ok"] is False
    assert gates["tier_pass"]["C"] is False


def test_tier_c_gate_shipped_lines_from_config(cfg):
    """出厂 C 档线来自 rules.yaml：良好线 4 题、命名有意义线 90%。"""
    assert cfg.c_min_correct == 4
    assert cfg.naming_meaningful_rate == 90.0


def test_tier_c_naming_metrics_are_measured(project_root):
    """命名有意义是"真计数"：对出厂生产码实测，合格率 100% 且分母>0。"""
    result = stylecheck.check_naming_meaningful(
        stylecheck.production_sources(project_root))
    assert result["naming_checked"] >= 30
    assert result["naming_passed"] == result["naming_checked"]
    assert result["naming_rate"] == 100.0
    assert result["naming_meaning_violations"] == []


def test_tier_c_naming_gate_fails_on_dirty_sample(cfg, files, tmp_path):
    """可证伪：坏命名样例（BadName/foo/qv）实测合格率 0%，闸门判 FAIL。"""
    path = tmp_path / "bad_names.py"
    path.write_text(DIRTY_NAMES, encoding="utf-8")
    naming = stylecheck.check_naming_meaningful([str(path)])
    assert naming["naming_checked"] == 3
    assert naming["naming_rate"] == 0.0
    reasons = {item[3] for item in naming["naming_meaning_violations"]}
    assert "非 snake_case" in reasons and "占位符名(tmp/foo/data1 风格)" \
        in reasons and "无元音、不可读缩写" in reasons
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, dict(naming),
                                _full_notes_info(cfg), cfg)
    item = _naming_item(gates)
    assert item["ok"] is False
    assert "达标率 0.0%" in item["item"] and "≥ 命名线 90.0%" in item["item"]
    assert gates["tier_pass"]["C"] is False


def test_tier_c_naming_gate_passes_on_clean_sample(cfg, files, tmp_path):
    """干净命名样例：合格率 100% ≥ 90%，C 档命名证据项判 PASS。"""
    path = tmp_path / "good_names.py"
    path.write_text(CLEAN_NAMES, encoding="utf-8")
    naming = stylecheck.check_naming_meaningful([str(path)])
    assert naming["naming_checked"] == 2 and naming["naming_rate"] == 100.0
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, dict(naming),
                                _full_notes_info(cfg), cfg)
    assert _naming_item(gates)["ok"] is True
    assert gates["tier_pass"]["C"] is True


def test_tier_c_naming_line_is_config_only(cfg, files, tmp_path):
    """改配置不改代码：命名线抬到 100% 时，实测 95% 的中间带必须判不过。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    style = {"naming_checked": 20, "naming_passed": 19, "naming_rate": 95.0}
    base_path = tmp_path / "naming_line.yaml"
    base_path.write_text("warn: 60.0\ndanger: 90.0\n"
                         "naming_meaningful_rate: 100.0\n", encoding="utf-8")
    strict = _load(base_path)
    assert strict.naming_meaningful_rate == 100.0
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(strict), strict)
    assert _naming_item(gates)["ok"] is False
    loose_path = tmp_path / "naming_loose.yaml"
    loose_path.write_text("warn: 60.0\ndanger: 90.0\n"
                          "naming_meaningful_rate: 94.0\n",
                          encoding="utf-8")
    loose = _load(loose_path)
    gates2 = selfcheck.tier_gate(results, summary, style,
                                 _full_notes_info(loose), loose)
    assert _naming_item(gates2)["ok"] is True


def _load(path):
    """延迟导入 config，避免测试模块在收集期依赖加载顺序。"""
    from exercise_five import config
    return config.load_config(str(path))


def test_tier_c_summary_line_mirrors_measurements(cfg, files, project_root):
    """良好(C) 汇总行：第4题、题数、命名达标率与分母全部印真实数字。"""
    style = stylecheck.summarize(project_root)
    gates, summary, _results = _gates_for(cfg, files, style)
    text = gates["tiers"]["C"]["summary"]
    assert "C 层 良好" in text and "命名有意义" in text
    assert "第4题 正确" in text and "正确 5/5" in text
    assert "达标率 %.1f%%" % style["naming_rate"] in text
    assert "合格 %d/%d" % (style["naming_passed"], style["naming_checked"]) \
        in text
    assert gates["tiers"]["C"]["verdict"] == "达标"
