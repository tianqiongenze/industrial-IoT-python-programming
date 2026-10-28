# -*- coding: utf-8 -*-
"""分层达标闸门测试：口径逐条对齐**工单任务书 P3 的验收标准**（不是 notebook 教师版字母表）。

| 工单档位 | 工单验收标准（P3工单-产线KPI仪表盘与自动日报，逐字原文）              |
|----------|------------------------------------------------------------------------|
| 及格(D)  | 5 KPI可用+时间筛选；日报四部分完整+PDF正确                              |
| 良好(C)  | 联动筛选流畅；日报生成<2分钟                                            |
| 优秀(B)  | ≥7指标+钻取交互；异常自动识别；美观度≥4/5                               |
| 超优(A)  | 优秀+定时自动生成(mailto/计划任务)+移动端适配                            |

（原文单点在 pipeline.WO_ROW，逐字对表由 tests/test_workorder_rows.py 直接读工单文件锁定。）

判定行与 result.json 的 tiers 必须一致，且每个子条件都在真实流水线上重算核对
（不用缓存、不看口号）；跟做示例降级为末行「保底自检」，不占工单字母。
红线：四条档位线都能被"只改 config 不改代码"证伪（见 flip_* 系列用例）。
"""
import os
import re
import xml.etree.ElementTree as ET

import pytest

from kpi_cockpit import config as C
from kpi_cockpit import core, pipeline, schedule

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(HERE, "config", "rules.yaml")
PREFIXES = ("及格(D)", "良好(C)", "优秀(B)", "超优(A)", "保底自检")


def _run(cfg, out_dir):
    _sections, data = pipeline.run(cfg, str(out_dir))
    text = open(os.path.join(str(out_dir), "report.txt"), encoding="utf-8").read()
    return data, text


def _flip(tmp_path, **subs):
    """只改配置（不改代码）：把真配置的指定字面量替换后落到 tmp_path。"""
    text = open(CFG, encoding="utf-8").read()
    for old, new in subs.items():
        assert old in text, "翻转目标不存在，用例已失效：%s" % old
        text = text.replace(old, new)
    p = tmp_path / "rules.yaml"
    p.write_text(text, encoding="utf-8")
    return C.load_config(str(p))


def _line(text, prefix):
    hit = [l for l in text.splitlines() if l.startswith(prefix)]
    assert len(hit) == 1, "判定行 %s 应恰好一条，实得 %d 条" % (prefix, len(hit))
    return hit[0]


def _verdict(line):
    return line.rsplit("→", 1)[-1].strip()


# ------------------------------------------------------------------------ 档位线本身
def test_tier_lines_follow_the_work_order(tmp_path):
    """四条工单档位线 + 一条保底自检线；不得再出现 notebook 教师版字母（学徒/师傅）。"""
    _data, text = _run(C.load_config(CFG), tmp_path)
    for p in PREFIXES:
        assert _line(text, p)
    body = "\n".join(_line(text, p) for p in PREFIXES)
    for stale in ("学徒", "操作员", "组长", "师傅"):
        assert stale not in body, "档位字母仍锚在 notebook 教师版表：%s" % stale
    assert "[分层达标（D/C/B/A）]" in text
    for i in range(6):
        assert "TODO-%d" % i in text          # 跟做任务清单不因重锚而丢失
    assert "点击折线点联动明细" in text        # TODO-3 与工单钻取同一口径


def test_tiers_dict_and_report_lines_agree(tmp_path):
    """report.txt 的达标/未达标 ↔ result.json 的 tiers 逐档一致（判定只有一个真源）。"""
    data, text = _run(C.load_config(CFG), tmp_path)
    for letter, prefix in zip(("D", "C", "B", "A"), PREFIXES[:4]):
        assert _verdict(_line(text, prefix)) == (
            "达标" if data["tiers"][letter] else "未达标"), letter
    assert _verdict(_line(text, PREFIXES[4])) in ("通过", "未通过")


# ------------------------------------------------------------------------ 及格(D)
def test_d_gate_kpis_filter_four_sections_and_pdf(tmp_path):
    """及格(D)：必做 5 KPI 有值 + 时间筛选真的缩窗 + 四段齐 + 当次 PDF 字节级合格。"""
    cfg = C.load_config(CFG)
    data, text = _run(cfg, tmp_path)
    assert data["tiers"]["D"] is True
    km = {k["name"]: k for k in data["kpis"]}
    assert len(data["required_kpis"]) == 5
    assert all(km[n]["value"] is not None for n in data["required_kpis"])
    # 时间筛选：独立重算（同一 core.filter_records），不许引用 result 自报数
    fp = data["filter_probe"]
    rows = pipeline.build_rows(cfg, source="auto", csv_path=None, here=HERE).as_dicts()
    assert len(core.filter_records(rows, date=fp["date"])) == fp["rows"]
    assert 0 < fp["rows"] < fp["rows_all"]
    html = open(os.path.join(str(tmp_path), data["artifacts"]["html"]),
                encoding="utf-8").read()
    assert len(data["report_sections"]) == 4
    assert all(s in html for s in data["report_sections"]), "四段式缺段"
    # PDF 正确：对盘上产物重新实测字节/页数，与报告自述必须一致
    pc = data["pdf_check"]
    raw = open(os.path.join(str(tmp_path), pc["file"]), "rb").read()
    assert len(raw) == pc["bytes"] and pc["exists"] and pc["attempted"]
    assert raw[:5] == b"%PDF-" and raw.rstrip().endswith(b"%%EOF")
    assert pc["pages"] >= 1 and pc["bytes"] >= pc["min_bytes"] and pc["ok"] is True
    line = _line(text, "及格(D)")
    assert "%d/%d 全有值" % (len(data["required_kpis"]), len(data["required_kpis"])) in line
    assert "命中 %d 行（全量 %d）" % (fp["rows"], fp["rows_all"]) in line
    assert "%d B / %d 页" % (pc["bytes"], pc["pages"]) in line
    assert _verdict(line) == "达标"


def test_config_only_flip_pdf_disabled_fails_d(tmp_path):
    """只改配置 report.pdf_enabled=false → 及格(D) 当场未达标，其余档位不受牵连。"""
    data, text = _run(_flip(tmp_path, **{"pdf_enabled: true": "pdf_enabled: false"}),
                      tmp_path / "out")
    assert data["tiers"]["D"] is False
    assert data["pdf_check"]["ok"] is False and data["pdf_check"]["attempted"] is False
    assert _verdict(_line(text, "及格(D)")) == "未达标"
    assert "report.pdf_enabled=false" in _line(text, "及格(D)")
    assert data["tiers"]["C"] is True and data["tiers"]["B"] is True


def test_config_only_flip_pdf_min_bytes_fails_d(tmp_path):
    """下限调成不可能的字节数 → pdf_check 实测不过 → 及格(D) 未达标（闸门不是橡皮章）。"""
    data, text = _run(_flip(tmp_path, **{"pdf_min_bytes: 1500": "pdf_min_bytes: 99999999"}),
                      tmp_path / "out")
    assert data["tiers"]["D"] is False
    assert "字节数" in data["pdf_check"]["note"]
    assert _verdict(_line(text, "及格(D)")) == "未达标"


# ------------------------------------------------------------------------ 良好(C)
def test_c_gate_linkage_is_programmatic_not_eyeballed(tmp_path):
    """良好(C)：联动=筛选真驱动重算（单日/单设备探针）＋ on_select 接线＋回路非空；
    日报耗时只以档位进判定行（不含毫秒），精确秒数留在 timing.txt/runtime/。"""
    cfg = C.load_config(CFG)
    data, text = _run(cfg, tmp_path)
    assert data["tiers"]["C"] is True
    rows = pipeline.build_rows(cfg, source="auto", csv_path=None, here=HERE).as_dicts()
    rules = cfg.rules()
    # 1) app/rerun 接线：对 app.py 源码独立计数，不引用 result 自报数
    app_src = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    assert app_src.count('on_select="rerun"') == data["linkage"]["on_select_rerun"] >= 2
    assert data["linkage"]["drill_rows_fn_in_app"] and data["linkage"]["shared_filter_fn"]
    # 2) 时间筛选 + 设备筛选探针：行数和总产量都必须严格变小
    fp = data["filter_probe"]
    dev = fp["device"]
    sub = core.filter_records(rows, devices=[dev["device"]])
    assert len(sub) == dev["rows"] and 0 < len(sub) < len(rows)
    assert core.total_output(sub) == dev["output"] < dev["output_all"] > 0
    # 3) 选择事件 → 明细回路非空（同一 core.drill_rows）
    dl = data["drill_link"]
    assert len(core.drill_rows(dl["selection_points"], rows, rules)) == dl["rows_detail"] > 0
    # 4) 耗时：判定行给档位，不许出现毫秒/小数秒
    line = _line(text, "良好(C)")
    assert "日报耗时档位 %s" % data["timing"]["elapsed_bucket"] in line
    assert not re.search(r"\d+\.\d+", line), "判定行含墙钟小数 → 破坏逐字节复现"
    assert "timing.txt" in line
    timing = open(os.path.join(str(tmp_path), "timing.txt"), encoding="utf-8").read()
    assert re.search(r"\d+\.\d+", timing), "精确秒数应记在 timing.txt"
    assert _verdict(line) == "达标"
    # 5) 无头真执行 app.py 的回归存在（切换单日 → 命中真的变小）
    dash = open(os.path.join(HERE, "tests", "test_dashboard.py"), encoding="utf-8").read()
    assert "AppTest" in dash and "date_input" in dash


def test_config_only_flip_drill_cap_fails_c_and_b(tmp_path):
    """只改配置 drill.max_rows=0 → 联动回路空 → 良好(C)/优秀(B)/超优(A) 同时未达标。"""
    data, text = _run(_flip(tmp_path, **{"max_rows: 30": "max_rows: 0"}),
                      tmp_path / "out")
    assert data["drill_link"]["rows_detail"] == 0
    assert data["tiers"]["C"] is False and data["tiers"]["B"] is False \
        and data["tiers"]["A"] is False
    assert data["tiers"]["D"] is True, "关掉钻取不该牵连及格(D)（档位相互独立）"
    assert "联动明细 0 行（上限 0）" in text
    for p in ("良好(C)", "优秀(B)", "超优(A)"):
        assert _verdict(_line(text, p)) == "未达标"


# ------------------------------------------------------------------------ 优秀(B)
def test_b_gate_metrics_drill_anomalies_rubric(tmp_path):
    """优秀(B)：≥7 指标（报出实得数）+ 钻取（行数/指纹可重算）+ 异常自动识别条数 +
    美观度按 config 确定性清单逐项实测（有得分也有扣分项，不写裸 5/5 自评）。"""
    cfg = C.load_config(CFG)
    data, text = _run(cfg, tmp_path)
    assert data["tiers"]["B"] is True
    assert len(data["kpis"]) >= 7
    rows = pipeline.build_rows(cfg, source="auto", csv_path=None, here=HERE).as_dicts()
    dl = data["drill_link"]
    assert dl["rows_detail"] == dl["cap"] > 0, "满窗数据复放 Top 桶应打满行数上限"
    det = core.drill_rows(dl["selection_points"], rows, cfg.rules())
    assert len(det) == dl["rows_detail"]
    assert core.drill_fingerprint(det) == dl["fingerprint"], "指纹不可复算 = 证据是假的"
    assert re.fullmatch(r"[0-9a-f]{8}", dl["fingerprint"])
    # 异常自动识别条数：独立重算
    assert len(core.anomalies(rows, cfg.rules(), topk=None)) == data["anomalies_total"] > 0
    # 美观度：得分 = 通过项权重之和，判定 = 得分 ≥ 阈值
    rb = data["ui_rubric"]
    assert rb["score"] == sum(i["weight"] for i in rb["items"] if i["passed"])
    assert rb["passed"] is (rb["score"] >= rb["threshold"]) and rb["passed"] is True
    for it in rb["items"]:
        assert it["evidence"], "检查项必须给出可复核证据：%s" % it["name"]
    line = _line(text, "优秀(B)")
    assert "指标实得 %d 个" % len(data["kpis"]) in line
    assert "指纹 crc32=%s" % dl["fingerprint"] in line
    assert "异常自动识别命中 %d 条" % data["anomalies_total"] in line
    assert "美观度 %d/%d（≥%d 达标" % (rb["score"], rb["max"], rb["threshold"]) in line
    assert "扣分项：" in line                      # 逐项得分 + 扣分项都要印出来
    assert 'key="trend_drill"' in text and 'key="alarm_table"' in text
    assert _verdict(line) == "达标"


def test_config_only_flip_thresholds_fails_b_only(tmp_path):
    """阈值放到数据够不到 → 规则命中 0 条异常 → 优秀(B)/超优(A) 未达标（实测条数说话）。"""
    data, text = _run(_flip(tmp_path, **{"temp_max: 90.0": "temp_max: 999.0",
                                         "vib_max: 4.5": "vib_max: 999.0"}),
                      tmp_path / "out")
    assert data["anomalies_total"] == 0
    assert data["tiers"]["B"] is False and data["tiers"]["A"] is False
    assert data["tiers"]["C"] is True
    assert "异常自动识别命中 0 条" in _line(text, "优秀(B)")
    assert _verdict(_line(text, "优秀(B)")) == "未达标"


def test_config_only_flip_rubric_weights_fails_b(tmp_path):
    """清单权重全改 0 → 得分 0 < 阈值 → 优秀(B) 未达标：美观度由 config 决定，不由嘴决定。"""
    data, text = _run(_flip(tmp_path, **{"weight: 1": "weight: 0"}), tmp_path / "out")
    rb = data["ui_rubric"]
    assert rb["max"] == 0 and rb["score"] == 0 and rb["passed"] is False
    assert data["tiers"]["B"] is False and data["tiers"]["A"] is False
    assert data["tiers"]["C"] is True
    assert "美观度 0/0（≥4 达标" in _line(text, "优秀(B)")
    assert _verdict(_line(text, "优秀(B)")) == "未达标"


def test_config_only_flip_rubric_check_name_fails_fast(tmp_path):
    """清单写了未实现的 check → 当场 ValueError（与未知 KPI 名同口径），绝不静默给分。"""
    cfg = _flip(tmp_path, **{"check: heading_levels": "check: subjective_vibe"})
    with pytest.raises(ValueError, match="未实现检查"):
        pipeline.run(cfg, str(tmp_path / "out"))


def test_config_only_flip_fails_d_c_and_b_together(tmp_path):
    """一次配置翻转（PDF 关 + 钻取上限归零）同时打掉 D/C/B：闸门真的会咬人。"""
    data, text = _run(_flip(tmp_path, **{"pdf_enabled: true": "pdf_enabled: false",
                                         "max_rows: 30": "max_rows: 0"}),
                      tmp_path / "out")
    assert data["tiers"]["D"] is False and data["tiers"]["C"] is False \
        and data["tiers"]["B"] is False
    for p in ("及格(D)", "良好(C)", "优秀(B)", "超优(A)"):
        assert _verdict(_line(text, p)) == "未达标"


# ------------------------------------------------------------------------ 超优(A)
def test_a_gate_schedule_artifacts_and_mobile(tmp_path):
    """超优(A)：定时解析出真实下次触发 + 4 件计划任务产物落盘可解析 + mailto 齐 +
    移动端看生成 HTML 的 viewport/窄屏断点属性（不看口号）。"""
    cfg = C.load_config(CFG)
    data, text = _run(cfg, tmp_path)
    assert data["tiers"]["A"] is True and data["tiers"]["B"] is True
    sc = data["schedule_check"]
    assert all(sc[k] for k in ("next_fire_is_real_datetime", "crontab_matches_at",
                               "systemd_matches_at", "launchd_matches_at",
                               "mailto_rendered_ok", "all_ok"))
    h, m = schedule.parse_at(sc["at"])
    assert (sc["hour"], sc["minute"]) == (h, m)
    s = data["schedule"]
    assert s["crontab"].startswith("%d %d * * * " % (m, h))
    assert "OnCalendar=*-*-* %02d:%02d:00" % (h, m) in s["systemd_timer"]
    assert s["mailto"].startswith("mailto:") and "?subject=" in s["mailto"]
    # 计划任务产物：写到 output/ 之外的 runtime/schedule/，内容与 result.json 一致且可解析
    rt = os.path.join(os.path.dirname(str(tmp_path)), "runtime", "schedule")
    for name, expect in (("crontab.txt", s["crontab"]),
                         ("p33-daily-report.timer", s["systemd_timer"]),
                         ("com.p33.kpi-daily-report.plist", s["launchd"]),
                         ("mailto.txt", s["mailto"])):
        got = open(os.path.join(rt, name), encoding="utf-8").read().strip()
        assert got == expect.strip(), name
    plist = ET.fromstring(s["launchd"])
    keys = [k.text for k in plist.find("dict").findall("key")]
    assert {"StartCalendarInterval", "ProgramArguments", "Label"} <= set(keys)
    assert sc["wall_clock_values_in"].startswith("runtime/")
    assert "schedule_state.txt" in os.listdir(os.path.dirname(rt))
    # 移动端：对生成 HTML 实测
    html = open(os.path.join(str(tmp_path), data["artifacts"]["html"]), encoding="utf-8").read()
    mc = data["mobile_check"]
    assert "<meta name=\"viewport\" content=\"width=device-width" in html
    assert schedule.narrow_width_px(html) == mc["narrow_px"] <= mc["max_narrow_px"]
    assert "(max-width:%dpx)" % mc["narrow_px"] in html
    assert all(mc[k] for k in ("viewport", "responsive_cards", "media_query", "ok"))
    line = _line(text, "超优(A)")
    assert "继承优秀(B)：达标" in line
    assert "解析为每日 %02d:%02d" % (h, m) in line
    assert "窄屏断点 %spx（config 上限 %dpx）" % (mc["narrow_px"], mc["max_narrow_px"]) in line
    assert not re.search(r"\d+\.\d+", line), "A 档判定行不得含墙钟小数（下次触发时刻只写 runtime/）"
    assert _verdict(line) == "达标"


def test_config_only_flip_mailto_empty_fails_a_only(tmp_path):
    """收件人改空串 → mailto_ok=False → 只有超优(A) 掉档（B 仍达标）。"""
    data, text = _run(_flip(tmp_path, **{"mailto: line-lead@example.com": 'mailto: ""'}),
                      tmp_path / "out")
    assert data["schedule_check"]["mailto_rendered_ok"] is False
    assert data["schedule_check"]["all_ok"] is False
    assert data["tiers"]["A"] is False and data["tiers"]["B"] is True
    assert _verdict(_line(text, "超优(A)")) == "未达标"


def test_config_only_flip_mobile_cap_fails_a_only(tmp_path):
    """窄屏断点上限改 0 → 版式属性实测不过 → 只有超优(A) 掉档（移动端不是口号）。"""
    data, text = _run(_flip(tmp_path, **{"max_narrow_px: 768": "max_narrow_px: 0"}),
                      tmp_path / "out")
    assert data["mobile_check"]["ok"] is False
    assert data["tiers"]["A"] is False and data["tiers"]["B"] is True
    assert _verdict(_line(text, "超优(A)")) == "未达标"


# ------------------------------------------------------------------------ 保底自检
def test_baseline_self_check_line_is_not_a_work_order_tier(tmp_path):
    """跟做/保底证据保留，但明确标注「不计入工单档位」。"""
    data, text = _run(C.load_config(CFG), tmp_path)
    line = _line(text, "保底自检")
    assert "（不计入工单档位）" in line
    assert "产物落盘 %d/5" % len(data["artifacts_written"]) in line
    assert len(data["artifacts_written"]) == 5
    assert _verdict(line) == "通过"
    assert "产线台账（config/lines，保底自检材料）" in text


# ------------------------------------------------------------------------ 可复现
def test_run_is_reproducible(tmp_path):
    """两次运行：档位判定、钻取证据、PDF/PNG 字节与五条判定行都逐字节一致
    （墙钟行不参与比较，外部 verify_local.py 再用不同 PYTHONHASHSEED 全量比一次）。"""
    a, ta = _run(C.load_config(CFG), tmp_path / "a")
    b, tb = _run(C.load_config(CFG), tmp_path / "b")
    assert a["tiers"] == b["tiers"] == {"D": True, "C": True, "B": True, "A": True}
    assert a["drill_link"] == b["drill_link"]
    assert a["ui_rubric"] == b["ui_rubric"]
    assert a["schedule_check"] == b["schedule_check"]
    assert a["mobile_check"] == b["mobile_check"]
    assert a["pdf_check"] == b["pdf_check"]
    lines_a = [_line(ta, p) for p in PREFIXES]
    lines_b = [_line(tb, p) for p in PREFIXES]
    assert lines_a == lines_b and len(lines_a) == 5
    for name in ("daily_report.pdf", "trend_chart.png", "daily_report.html"):
        pa = os.path.join(str(tmp_path / "a"), name)
        pb = os.path.join(str(tmp_path / "b"), name)
        assert open(pa, "rb").read() == open(pb, "rb").read(), name
