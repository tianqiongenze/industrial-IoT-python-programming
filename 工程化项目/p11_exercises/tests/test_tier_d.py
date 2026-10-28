# -*- coding: utf-8 -*-
"""及格(D) 档 + 保底自检：工单 D 行「≥3题正确运行；PEP 8≥75%；有基础注释」。

锚定说明：课堂 notebook 的"D 学徒跟做"阶梯没有工单对应档位，已降级为
"保底自检（不计入工单档位）"单独留痕；本文件同时验收 D 层闸门本身
（题数/PEP 8 带/基础注释）与 PEP 8 带的可证伪性（脏样例判不过、带宽可改）。
"""
from exercise_five import config, core, exercises, selfcheck, stylecheck

CLEAN_SRC = '"""干净样例。"""\n\n\ndef good_name(value):\n    """说明。"""\n' \
            '    return value\n'
# 故意不规范：无模块 docstring + 非 snake_case 函数名 + 函数缺 docstring
# + 行尾空格，7 个检查项命中 4 项违规（实测 42.9% < 75%）。
DIRTY_SRC = "def Bad_Name(a):\n    return a  \n"


def _full_notes_info(cfg):
    """超优 A 档/保底档证据用的完整笔记实测快照（D 档不消费这些字段）。"""
    return {"verified_entries": 15, "required": 10, "pass": True,
            "explain": "题3", "seed": cfg.seed, "exists": True,
            "questions_covered": 5, "sections_complete": True}


def _gate_with_style(cfg, files, style):
    """用给定规范度量结果跑一遍分层达标线（其余档用真实断言表）。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(cfg), cfg)
    pep8_d = [g for g in gates["gates"]
              if g["tier"] == "D" and "PEP 8" in g["item"]]
    assert len(pep8_d) == 1, pep8_d
    return gates, pep8_d[0]


def _style_from_text(tmp_path, text, name="sample.py"):
    """把一段源码写成文件并实测规范度量（含 score/passed/total）。"""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return stylecheck.check_paths([str(path)])


def test_tier_d_exercise1_runs_and_shows_both_units(cfg):
    """题1 跟做：报告行里同时出现 ℉ 与 K。"""
    run_ = exercises.exercise1(cfg)
    assert any("℉" in line and "K" in line for line in run_["lines"])
    assert run_["payload"]["rows"], "样本为空则无法跟做"


def test_tier_d_exercise2_runs(cfg):
    """题2 跟做：至少一个用例给出根或"无实根"结论。"""
    run_ = exercises.exercise2(cfg)
    assert run_["lines"] and all("Δ" in line or "极值" in line
                                 for line in run_["lines"])


def test_tier_d_change_parameters_changes_output(cfg):
    """改参数再跑：36.6℃ 与 100℃ 必须得到不同结果。"""
    low = core.convert_temperature(36.6)[0]
    high = core.convert_temperature(100.0)[0]
    assert low != high and high > low


def test_tier_d_reference_versus_copy_difference():
    """记录一处差异（C→Python 最容易踩的引用语义）。"""
    a = [1, 2, 3]
    b = a
    b.append(4)
    assert a == [1, 2, 3, 4], "赋值是引用，改 b 会动 a"
    c = list(a)
    c.append(5)
    assert 5 not in a, "真拷贝才互不影响"


def test_tier_d_gate_items_pass(cfg, files):
    """内置断言里 D 标签子集（工单及格线的题数证据）全部为真。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    d_items = [item for item in results if item["tier"] == "D"]
    assert d_items and all(item["ok"] for item in d_items)


def test_tier_d_shipped_lines_match_work_order(cfg):
    """出厂线来自 rules.yaml：及格线 3 题、PEP 8 D 线 75%（工单及格行）。"""
    assert cfg.d_min_correct == 3
    assert cfg.pep8_pass_rate_d == 75.0


def test_tier_d_pep8_clean_sample_scores_100_and_passes_band(cfg, files,
                                                             tmp_path):
    """及格 D 的 PEP 8 带：干净文件实测 100%，达标率 ≥75% 判及格证据项过。"""
    style = _style_from_text(tmp_path, CLEAN_SRC)
    assert style["score"] == 100.0 and style["violations"] == []
    _gates, band = _gate_with_style(cfg, files, style)
    assert band["ok"] is True
    assert "100.0%" in band["item"] and "≥ D 层线 75.0%" in band["item"]


def test_tier_d_pep8_dirty_sample_below_band_fails_gate(cfg, files, tmp_path):
    """及格 D 的 PEP 8 带：故意不规范的样例实测 <75%，闸门必须判 FAIL。"""
    style = _style_from_text(tmp_path, DIRTY_SRC)
    assert style["score"] < 75.0
    assert style["passed"] == 3 and style["total"] == 7
    gates, band = _gate_with_style(cfg, files, style)
    assert band["ok"] is False
    assert "42.9%" in band["item"], band["item"]
    assert "检查项通过 3/7" in band["item"], band["item"]
    assert gates["tier_pass"]["D"] is False


def test_tier_d_pep8_band_boundary_at_exactly_75(cfg, files):
    """边界档：达标率恰为 75.0% 判 PASS（含等号），74.9% 判 FAIL。"""
    base = {"total": 8, "naming_violations": 0, "missing_docstrings": 0}
    hit = dict(base, score=75.0, passed=6)
    miss = dict(base, score=74.9, passed=6)
    assert _gate_with_style(cfg, files, hit)[1]["ok"] is True
    assert _gate_with_style(cfg, files, miss)[1]["ok"] is False


def test_tier_d_pep8_band_threshold_moves_with_config_only(cfg, files,
                                                           tmp_path):
    """改配置不改代码：同一份样例的**真实测出**得分（脏样例实测 42.9%），
    D 线抬到它之上判 FAIL、降到它之下判 PASS——带宽随配置移动这件事不靠手填分数。"""
    style = _style_from_text(tmp_path, DIRTY_SRC)     # 真跑 stylecheck，不构造 dict
    measured = style["score"]
    assert _gate_with_style(cfg, files, style)[1]["ok"] is False   # 出厂线 75
    for line, expected in ((measured + 0.1, False), (measured - 0.1, True)):
        path = tmp_path / ("band_%s.yaml" % round(line, 1))
        path.write_text("warn: 60.0\ndanger: 90.0\npep8_pass_rate_d: %s\n"
                        "pep8_pass_rate_b: 95.0\n" % line,
                        encoding="utf-8")
        moved = config.load_config(str(path))
        assert moved.pep8_pass_rate_d == line
        assert _gate_with_style(moved, files, style)[1]["ok"] is expected


def test_tier_d_shipped_gate_line_prints_measured_counts(cfg, files,
                                                         project_root):
    """出厂口径可证伪：D 层 PEP 8 证据行必须印实测百分比与通过/总数。"""
    style = stylecheck.summarize(project_root)
    gates, band = _gate_with_style(cfg, files, style)
    assert band["ok"] is True
    assert "%.1f%%" % style["score"] in band["item"]
    assert "检查项通过 %d/%d" % (style["passed"], style["total"]) \
        in band["item"]


def test_tier_d_summary_line_carries_real_numbers(cfg, files, project_root):
    """及格(D) 汇总行必须带三项真实数字：题数、PEP 8 达标率、注释计数。"""
    style = stylecheck.summarize(project_root)
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(cfg), cfg)
    text = gates["tiers"]["D"]["summary"]
    assert "D 层 及格" in text and "≥3题正确运行" in text
    assert "正确 5/5 题" in text and "达标率 100.0%" in text
    comments = style["comments"]
    assert "公开函数 %d/%d" % (comments["funcs_documented"],
                             comments["funcs_total"]) in text
    assert gates["tiers"]["D"]["verdict"] == "达标"


def test_tier_d_basic_comments_gate_counts_docstrings(cfg, files,
                                                     project_root):
    """基础注释实测：公开函数/模块 docstring 计数由 check_comments 真数出。"""
    comments = stylecheck.check_comments(
        stylecheck.production_sources(project_root))
    assert comments["funcs_total"] >= 10
    assert comments["modules_total"] >= 11
    style = dict(stylecheck.check_paths([]), comments=comments)
    style["score"] = 100.0
    gates, _band = _gate_with_style(cfg, files, style)
    doc_item = [g for g in gates["gates"]
                if g["tier"] == "D" and "基础注释" in g["item"]][0]
    assert doc_item["ok"] is True
    missing = dict(style, comments={"funcs_total": 10, "funcs_documented": 9,
                                    "modules_total": 12,
                                    "modules_documented": 12})
    gates2, _ = _gate_with_style(cfg, files, missing)
    doc_item2 = [g for g in gates2["gates"]
                 if g["tier"] == "D" and "基础注释" in g["item"]][0]
    assert doc_item2["ok"] is False


def test_floor_selfcheck_passes_but_occupies_no_work_order_tier(cfg, files,
                                                                project_root):
    """保底自检 3 项全过、单独成组，且不占工单字母（不在 tier_pass 内）。"""
    style = stylecheck.summarize(project_root)
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(cfg), cfg)
    assert "保底" not in gates["tier_pass"]
    assert gates["floor_pass"] is True
    floor_items = [g for g in gates["gates"] if g["tier"] == "保底"]
    assert len(floor_items) == 3 and all(g["ok"] for g in floor_items)
    assert "保底自检（不计入工单档位）" in gates["tiers"]["保底"]["summary"]
    assert gates["tiers"]["保底"]["counts_for_work_order"] is False
