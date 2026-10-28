# -*- coding: utf-8 -*-
"""端到端 + 筛选/报告完整性 + 钻取/定时：从 pipeline.run() 走真产物。

档位口径 = 工单任务书 P3 验收标准（及格D/良好C/优秀B/超优A），专项判定见
tests/test_tier_gates.py；本文件只管"交付物本身"：
  * output/ 八个产物齐不齐（含 daily_report.pdf / trend_chart.png）、四段式有没有空洞；
  * 数字是否真由 config 阈值算出来（改阈值 → 结论变，证明非硬编码）；
  * 连跑两次逐字节一致（NF-1，timing.txt 除外）。
"""
import copy
import filecmp
import json
import os

import pytest

from kpi_cockpit import config as C
from kpi_cockpit import deps, pipeline, report

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(HERE, "config", "rules.yaml")
ARTIFACTS = ("daily_report.html", "daily_report.pdf", "kpi.json", "result.json",
             "appendix.csv", "report.txt", "timing.txt", "trend_chart.png")


def _cfg(**over):
    """真配置深拷贝 + 定点覆盖：证明"改配置即改结论"，代码里没有第二套阈值。"""
    base = copy.deepcopy(C.load_config(REAL).raw)
    for k, v in over.items():
        if "." in k:
            head, tail = k.split(".", 1)
            base[head][tail] = v
        else:
            base[k] = v
    return C.Settings.from_dict(base)


@pytest.fixture(scope="module")
def run_once(tmp_path_factory):
    out = tmp_path_factory.mktemp("p33run")
    cfg = _cfg()
    sections, result = pipeline.run(cfg, str(out), source="synth", here=HERE)
    return str(out), cfg, sections, result


# ------------------------------------------------ 产物齐备（工单及格(D) 的材料面）
def test_all_eight_artifacts_written(run_once):
    out, _, _, _ = run_once
    for name in ARTIFACTS:
        p = os.path.join(out, name)
        assert os.path.isfile(p) and os.path.getsize(p) > 0, "%s 缺失或为空" % name


def test_kpi_json_has_required_five_plus_extra(run_once):
    _, _, _, result = run_once
    data = json.load(open(os.path.join(_out(run_once), "kpi.json"), encoding="utf-8"))
    names = [k["name"] for k in data["kpis"]]
    assert names[:5] == ["总产量", "平均良率", "设备在线数", "今日告警数", "效率对标"]
    assert len(names) >= 7, "工单要求 ≥7 指标（优秀(B) 判定项），实得 %d" % len(names)
    assert all(k["value"] is not None for k in data["kpis"])
    assert set(["window", "source", "gauge", "ledger", "device_status",
                "efficiency"]) <= set(data)


def _out(run_once):
    return run_once[0]


def test_result_json_records_source_and_deps(run_once):
    out, _, _, result = run_once
    data = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
    assert data["work_order"] == "P3" and data["project"] == "p33_kpi_cockpit"
    assert data["source_mode"] == "synth" and "seed=2026" in data["source"]
    assert data["stamp"] is False, "默认不得开时间戳（否则破坏复现）"
    assert set(data["deps"]) == set(deps.OPTIONAL)
    assert all(d["mode"] == ("native" if d["installed"] else "fallback")
               for d in data["deps"].values()), "自述模式必须与探测结果一致"
    assert data["timing"]["exact_seconds_in"] == "timing.txt"
    assert data["timing"]["within_budget"] is True


def test_appendix_csv_matches_tail_rows(run_once):
    out, _, _, result = run_once
    lines = open(os.path.join(out, "appendix.csv"), encoding="utf-8").read().splitlines()
    assert lines[0] == "ts,device_id,line,output,ok_qty,yield_pct,temp,vib,status"
    assert len(lines) - 1 == min(result["window"]["rows_window"], 50)


def test_report_txt_covers_every_tier_and_todo(run_once):
    out, _, sections, _ = run_once
    text = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    for t in ("TODO-0", "TODO-1", "TODO-2", "TODO-3", "TODO-4", "TODO-5"):
        assert t in text, "%s 未见于过程报告" % t
    for tier in ("及格(D)", "良好(C)", "优秀(B)", "超优(A)", "保底自检"):
        assert tier in text
    assert "已安装(原生启用)" in text and "缺失(降级兜底)" in text
    assert [s[0] for s in sections] and "工单 TODO 覆盖" in [s[0] for s in sections]


def test_report_txt_has_no_unfilled_placeholder(run_once):
    text = open(os.path.join(_out(run_once), "report.txt"), encoding="utf-8").read()
    assert "%s" not in text and "%d" not in text, "格式化残留 = 有分支没跑通"
    assert "你的代码" not in text and "TODO-0 待实现" not in text
    assert "NotImplemented" not in text


# ----------------------------------------------------------- 日报四段式（工单及格(D)）
def test_daily_html_four_sections_complete(run_once):
    out, _, _, result = run_once
    html = open(os.path.join(out, result["artifacts"]["html"]), encoding="utf-8").read()
    for h in ("一、生产概览", "二、详细分析", "三、异常识别", "四、数据附表"):
        assert h in html, "四段式缺段：%s" % h
    assert html.count("<h2>") >= 4
    assert "{{" not in html and "{%" not in html
    assert "每日生产分析报告" in html


def test_daily_html_names_the_actual_source_and_renderer(run_once):
    out, _, _, result = run_once
    html = open(os.path.join(out, "daily_report.html"), encoding="utf-8").read()
    assert "seed=2026" in html, "来源必须写死为真实使用的那条路径"
    assert result["artifacts"]["renderer"].split("（")[0] in html


def test_daily_html_shows_disposal_suggestions(run_once):
    """工单 P3.2-3：异常识别必须带处置建议，不是只列告警。"""
    out, _, _, result = run_once
    html = open(os.path.join(out, "daily_report.html"), encoding="utf-8").read()
    assert "建议" in html
    assert any("建议" in a["suggestion"] for a in result["anomalies_top"])


# ------------------------------------------------------------------ 阈值由配置驱动
def _run(cfg, out, **kw):
    """pipeline.run 返回 (sections, result)：测试只关心结果字典。"""
    return pipeline.run(cfg, out, source=kw.pop("source", "synth"), here=HERE, **kw)[1]


def test_raising_vib_threshold_reduces_alarms(tmp_path):
    ra = _run(_cfg(), str(tmp_path / "a"))
    rb = _run(_cfg(**{"thresholds.vib_max": 5.9}), str(tmp_path / "b"))
    assert rb["alarms_total"] < ra["alarms_total"], "阈值放宽后告警必须减少"
    assert rb["gauge"]["tone"] == ra["gauge"]["tone"]


def test_dropping_danger_line_flips_gauge_tone(tmp_path):
    r_lo = _run(_cfg(warn=97.0, danger=99.0), str(tmp_path / "lo"))
    r_hi = _run(_cfg(warn=20.0, danger=50.0), str(tmp_path / "hi"))
    assert r_lo["gauge"]["tone"] == "error" and r_hi["gauge"]["tone"] == "ok"


def test_target_change_moves_efficiency(tmp_path):
    r1 = _run(_cfg(), str(tmp_path / "1"))
    r2 = _run(_cfg(**{"targets.output_qty_per_day": 9999.0}), str(tmp_path / "2"))
    assert r2["efficiency"]["raw"] < r1["efficiency"]["raw"]
    assert r2["efficiency"]["clip"] == pytest.approx(max(
        0.0, min(1.0, r2["efficiency"]["raw"])), abs=1e-9)


def test_budget_violation_raises_rather_than_passing_quietly(tmp_path):
    cfg = _cfg(**{"targets.report_seconds_max": -1.0})
    with pytest.raises(RuntimeError, match="超过预算"):
        pipeline.run(cfg, str(tmp_path / "x"), source="synth", here=HERE)


# ------------------------------------------------------- 时间/设备筛选（工单及格(D)/良好(C)）
def test_date_filter_narrows_window(tmp_path):
    cfg = _cfg()
    full = _run(cfg, str(tmp_path / "full"))
    day = full["window"]["start"]
    one = _run(cfg, str(tmp_path / "one"), date=day)
    assert one["window"]["rows_window"] < full["window"]["rows_window"]
    assert one["window"]["start"] == one["window"]["end"] == day
    assert one["window"]["days"] == 1


def test_device_filter_keeps_only_picked_devices(tmp_path):
    r = _run(_cfg(), str(tmp_path / "d"), devices=["DEV-01", "DEV-02"])
    assert r["window"]["devices"] == ["DEV-01", "DEV-02"]
    assert {d["device_id"] for d in r["device_status"]} == {"DEV-01", "DEV-02"}


def test_unknown_device_raises_with_candidates(tmp_path):
    with pytest.raises(ValueError, match="不存在于数据源"):
        _run(_cfg(), str(tmp_path / "bad"), devices=["DEV-99"])


def test_empty_window_raises(tmp_path):
    with pytest.raises(ValueError, match="筛选后 0 行"):
        _run(_cfg(), str(tmp_path / "e"), date="1999-01-01")


def test_range_filter_endpoints_inclusive(tmp_path):
    r = _run(_cfg(), str(tmp_path / "rg"), start="2026-04-01", end="2026-04-02")
    assert r["window"]["start"] == "2026-04-01" and r["window"]["end"] == "2026-04-02"
    assert r["window"]["days"] == 2


# --------------------------------------------- 钻取/定时/移动端（工单优秀(B)/超优(A)）
def test_drill_defaults_and_explicit_devices(tmp_path):
    r = _run(_cfg(), str(tmp_path / "dr"))
    assert [d["device_id"] for d in r["drill"]] == ["DEV-01"], "默认钻取=config/drill"
    r2 = _run(_cfg(), str(tmp_path / "dr2"), drill=["DEV-03", "DEV-04"])
    assert [d["device_id"] for d in r2["drill"]] == ["DEV-03", "DEV-04"]
    for d in r2["drill"]:
        assert d["n"] > 0 and set(["yield_pct", "max_vib", "alarms",
                                  "top_anomalies"]) <= set(d)


def test_schedule_block_is_paste_ready(tmp_path):
    r = _run(_cfg(), str(tmp_path / "sc"), schedule_at="06:15")
    s = r["schedule"]
    assert s["at"] == "06:15"
    assert s["crontab"].startswith("15 6 * * * ")
    assert "OnCalendar=*-*-* 06:15:00" in s["systemd_timer"]
    assert s["mailto"].startswith("mailto:line-lead%40example.com")
    assert all(s["mobile_adapt"].values())
    assert s["wait_reported_in"] == "timing.txt"


def test_timing_txt_is_the_only_volatile_wall_clock_file(tmp_path):
    d = str(tmp_path / "tt")
    r = _run(_cfg(), d)
    text = open(os.path.join(d, "timing.txt"), encoding="utf-8").read()
    assert "日报实测耗时" in text and "达标" in text
    assert r["timing"]["elapsed_bucket"] == report.bucket(0.001)
    # 墙钟值只允许出现在 timing.txt 与 output/ 之外的 runtime/（其余产物必须逐字节可复现，
    # 由 test_two_runs_are_byte_identical_except_timing 守住；runtime/ 每次刷新）
    rt = os.path.join(os.path.dirname(d), "runtime")
    assert open(os.path.join(rt, "timing.txt"), encoding="utf-8").read() == text
    assert os.path.isfile(os.path.join(rt, "schedule_state.txt"))


# ------------------------------------------------------------------ 时间戳开关
def test_stamp_flag_adds_timestamp_and_is_off_by_default(tmp_path):
    r1 = _run(_cfg(), str(tmp_path / "n"))
    r2 = _run(_cfg(), str(tmp_path / "y"), stamp=True)
    assert r1["stamp"] is False and r2["stamp"] is True
    t1 = open(os.path.join(str(tmp_path / "n"), "report.txt"), encoding="utf-8").read()
    t2 = open(os.path.join(str(tmp_path / "y"), "report.txt"), encoding="utf-8").read()
    assert "生成时间: 未启用" in t1 and "生成时间: 20" in t2


# ------------------------------------------------------------------ 可复现（NF-1）
def test_two_runs_are_byte_identical_except_timing(tmp_path):
    d1, d2 = str(tmp_path / "1"), str(tmp_path / "2")
    _run(_cfg(), d1)
    _run(_cfg(), d2)
    names = sorted(n for n in os.listdir(d1) if n != "timing.txt")
    assert set(names) == set(ARTIFACTS) - {"timing.txt"}
    diffs = [n for n in names if not filecmp.cmp(os.path.join(d1, n),
                                                 os.path.join(d2, n), shallow=False)]
    assert diffs == [], "逐字节复现失败：%s" % diffs


def test_clean_source_path_end_to_end(tmp_path):
    """TODO-0 主路径：喂外部 CSV → 报告写"外部 CSV"，列级出处随之改变。"""
    p = tmp_path / "clean.csv"
    p.write_text("ts,device_id,output,ok_qty,temp,vib,status\n"
                 "2026-03-01 08:00:00,DEV-01,100,98,60.0,2.0,RUN\n"
                 "2026-03-01 08:30:00,DEV-02,100,80,95.0,5.0,RUN\n", encoding="utf-8")
    r = _run(_cfg(), str(tmp_path / "o"), source="csv", csv_path=str(p))
    assert r["source_mode"] == "clean" and "外部 CSV" in r["source"]
    assert r["provenance"]["ts"] == "文件原始"
    assert r["provenance"]["line"].startswith("派生")
    assert r["alarms_total"] == 1 and r["anomalies_total"] == 1


def test_pdf_flag_writes_pdf_and_records_font(tmp_path):
    """PDF 是默认产物（工单及格(D) 的"PDF正确"要当次实测）：字体/图注如实自述。"""
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    d = str(tmp_path / "pdf")
    r = _run(_cfg(), d)                          # 不传 pdf 参数 = 默认路径
    assert (tmp_path / "pdf" / "daily_report.pdf").stat().st_size > 2000
    assert (tmp_path / "pdf" / "trend_chart.png").stat().st_size > 500
    assert "STSong-Light" in r["artifacts"]["pdf"]
    assert "matplotlib" in r["artifacts"]["chart"]
    assert r["pdf_check"]["ok"] is True and r["pdf_check"]["pages"] >= 1


def test_no_pdf_run_does_not_trust_stale_pdf(tmp_path):
    """pdf=False（run.py --no-pdf）：盘上旧 PDF 一律不采信，及格(D) 当场未达标。"""
    pytest.importorskip("reportlab")
    d = str(tmp_path / "np")
    _run(_cfg(), d)                              # 先出一次真 PDF
    r = _run(_cfg(), d, pdf=False)               # 再跳过生成 → 陈货不得冒充
    assert r["pdf_check"]["attempted"] is False and r["pdf_check"]["ok"] is False
    assert r["pdf_check"]["bytes"] > 0, "旧文件确实在盘上，但不得计入达标证据"
    assert r["tiers"]["D"] is False


def test_ledger_and_trend_reach_the_report(run_once):
    _, _, sections, result = run_once
    titles = [t for t, _ in sections]
    assert "产线台账（config/lines，保底自检材料）" in titles
    assert "KPI 驾驶舱（TODO-2/3/4/5）" in titles
    body = "\n".join("\n".join(lines) for _, lines in sections)
    assert "一号产线" in body and "趋势采样点" in body
    assert result["ledger"][0]["good_rate"] == pytest.approx(0.9825, abs=1e-4)
