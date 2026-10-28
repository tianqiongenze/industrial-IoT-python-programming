# -*- coding: utf-8 -*-
"""四段式日报产物完整性 + 渲染路径真实性（Jinja2 主路径 / 内置兜底路径）
+ 工单及格(D) 的 PDF 实测校验 + 工单优秀(B) 的美观度确定性检查清单。

审计红线：报告文案不得谎报渲染器。这里用 monkeypatch 把 jinja2 真的"变没"，
验证兜底分支确实跑得到、跑得对，且 render_html 返回的自述与实际一致。
"""
import os
import sys

import pytest

from kpi_cockpit import config as C
from kpi_cockpit import core, report, schedule

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(HERE, "config", "rules.yaml")
TPL = os.path.join(HERE, "templates", "daily_report.html.j2")

ROWS = [
    {"ts": "2026-03-01 08:00:00", "device_id": "DEV-01", "line": "一号产线",
     "output": 60, "ok_qty": 57, "yield_pct": 95.0, "temp": 70.0, "vib": 3.0,
     "status": "RUN"},
    {"ts": "2026-03-01 08:30:00", "device_id": "DEV-02", "line": "二号产线",
     "output": 40, "ok_qty": 30, "yield_pct": 75.0, "temp": 91.5, "vib": 5.2,
     "status": "DOWN"},
]


@pytest.fixture(scope="module")
def cfg():
    return C.load_config(REAL)


@pytest.fixture(scope="module")
def ctx(cfg):
    rules = cfg.rules()
    rules["days"] = 1
    kpis = core.compute_kpis(ROWS, rules, lines=cfg.items)
    c = report.build_context(
        cfg, date="2026-03-01", kpis=kpis, rows_all=ROWS, rows_window=ROWS,
        devices=["DEV-01", "DEV-02"], analysis=core.by_device(ROWS, rules),
        anomalies=core.anomalies(ROWS, rules, cfg.topk), trend_points=core.trend(ROWS, "hour"),
        source="测试数据（内存）", provenance={"ts": "文件原始", "output": "文件原始"},
        deps={"summary": "已安装(原生启用): 全部 ｜ 缺失(降级兜底): 无",
              "dashboard": "streamlit 1.65.0 已安装", "html_renderer": "Jinja2 测试"},
        elapsed=0.42)
    c["generated_at"] = "2026-03-01 07:30:00"
    report.add_appendix(c, core.tail_rows(ROWS, cfg.require("report.tail_rows")))
    return c


# ------------------------------------------------------------------- 耗时归档（NF-1）
@pytest.mark.parametrize("secs,expected", [
    (0.0, "<1s"), (0.999, "<1s"), (1.0, "<2s"), (2.0, "<5s"),
    (59.0, "<60s"), (119.9, "<120s"), (120.0, ">=120s"), (9e9, ">=120s")])
def test_bucket_boundaries(secs, expected):
    assert report.bucket(secs) == expected


def test_bucket_accepts_string_number():
    assert report.bucket("0.1") == "<1s"


# ------------------------------------------------------------------ 文本过程报告
def test_render_omits_wall_clock_by_default():
    text = report.render([("甲", ["1"])])
    assert "生成时间: 未启用" in text and "--stamp" in text


def test_render_with_stamp_has_timestamp():
    text = report.render([("甲", ["1"])], stamp=True)
    assert "生成时间: 20" in text


def test_render_keeps_section_order_and_lines():
    text = report.render([("A", ["a1", "a2"]), ("B", ["b1"])])
    assert text.index("[A]") < text.index("[B]")
    assert text.index("a1") < text.index("a2") < text.index("b1")


def test_render_coerces_non_string_lines():
    assert "42" in report.render([("n", [42])])


# --------------------------------------------------------------------- 上下文
def test_context_overview_sums_window_only(cfg, ctx):
    assert ctx["overview"]["output"] == 100 and ctx["overview"]["good"] == 87
    assert ctx["overview"]["yield_pct"] == pytest.approx(87.0)
    assert ctx["overview"]["devices"] == 2


def test_context_thresholds_come_from_config(cfg, ctx):
    assert ctx["thresholds_display"] == {"temp_max": cfg.temp_max, "vib_max": cfg.vib_max}
    assert ctx["elapsed_text"] == "<1s" and ctx["within_budget"] is True
    assert ctx["budget_seconds"] == cfg.report_seconds_max


def test_context_anomalies_total_falls_back_to_list_len(cfg, ctx):
    assert ctx["anomalies_total"] == len(ctx["anomalies"])


def test_context_anomalies_total_honours_explicit_count(cfg, ctx):
    rules = cfg.rules()
    rules["days"] = 1
    kpis = core.compute_kpis(ROWS, rules, lines=cfg.items)
    big = report.build_context(
        cfg, date="d", kpis=kpis, rows_all=ROWS, rows_window=ROWS, devices=["DEV-01"],
        analysis=core.by_device(ROWS, rules),
        anomalies=core.anomalies(ROWS, rules, topk=1),
        trend_points=[], source="s", provenance={"ts": "文件原始"},
        deps={"summary": "x", "dashboard": "y", "html_renderer": "z"},
        elapsed=0.1, anomalies_total=77)
    assert big["anomalies_total"] == 77 and len(big["anomalies"]) == 1


def test_context_appendix_columns_are_canon(ctx):
    from kpi_cockpit import data_source
    assert ctx["appendix"]["columns"] == list(data_source.CANON)
    assert len(ctx["appendix"]["rows"]) == 2


# --------------------------------------------------------------------- SVG
def test_trend_svg_normal_and_degenerate():
    svg = report.trend_svg([{"output": 10}, {"output": 20}, {"output": 15}])
    assert svg.startswith("<svg") and svg.count(",") == 3 and "polyline" in svg
    assert "数据点不足" in report.trend_svg([{"output": 1}])
    flat = report.trend_svg([{"output": 5}, {"output": 5}])   # span=0 → 不除零
    assert "数据点不足" not in flat and flat.count(",") == 2


def test_trend_svg_is_reproducible():
    pts = [{"output": 3}, {"output": 9}, {"output": 6}]
    assert report.trend_svg(pts) == report.trend_svg(pts)


# --------------------------------------------------------------------- HTML 渲染
def test_html_jinja_path_has_four_sections_and_no_holes(ctx, cfg):
    html, label = report.render_html(ctx, TPL)
    assert label.startswith("Jinja2"), label
    for s in cfg.require("report.sections"):
        assert s in html, "四段式标题必须齐全"
    assert "{{" not in html and "{%" not in html, "不得留下未填充占位符"
    assert "None" not in html.replace("None-", ""), "占位符不得渲染成 None"


def test_html_escapes_untrusted_source_string(ctx):
    evil = dict(ctx)
    evil["source"] = "<script>alert(1)</script>"
    html, _ = report.render_html(evil, TPL)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html, "autoescape 必须生效（工单避坑：XSS/静默）"


def test_jinja_strictundefined_raises_on_missing_key(tmp_path):
    """工单避坑：模板变量与 Python 命名不一致 → 必须当场报错，而非静默空白。"""
    tpl = tmp_path / "t.j2"
    tpl.write_text("值={{ not_provided }}", encoding="utf-8")
    with pytest.raises(Exception) as e:
        report.render_html({"title": "x"}, str(tpl))
    assert "not_provided" in str(e.value)


def test_fallback_renderer_path_runs_and_says_so(monkeypatch, ctx):
    """把 jinja2 真的伪装成未安装 → 走内置同构渲染器，且自述必须与实际一致。"""
    for m in [k for k in list(sys.modules) if k == "jinja2" or k.startswith("jinja2.")]:
        monkeypatch.delitem(sys.modules, m, raising=False)
    monkeypatch.setitem(sys.modules, "jinja2", None)
    html, label = report.render_html(ctx, TPL)
    assert label == "内置同构渲染器（jinja2 未安装）"
    assert "渲染路径：%s" % ctx["deps"]["html_renderer"] in html
    assert "日报耗时档位" in html and "预算 120s" in html
    for s in ctx["sections"]:
        assert s in html
    assert "<h2>1. " in html and "<h2>4. " in html
    assert "良率%" in html, "表头百分号不得被当成格式符（历史 TypeError 回归）"


def test_fallback_and_jinja_paths_agree_on_sections(monkeypatch, ctx):
    j_html, _ = report.render_html(ctx, TPL)
    for m in [k for k in list(sys.modules) if k == "jinja2" or k.startswith("jinja2.")]:
        monkeypatch.delitem(sys.modules, m, raising=False)
    monkeypatch.setitem(sys.modules, "jinja2", None)
    f_html, _ = report.render_html(ctx, TPL)
    for dev in ("DEV-01", "DEV-02"):
        assert (dev in j_html) == (dev in f_html)


# --------------------------------------------------------------------- PDF / PNG
def test_chart_png_writes_file_when_matplotlib_present(tmp_path):
    pytest.importorskip("matplotlib")
    p = str(tmp_path / "t.png")
    assert report.chart_png([{"output": 1}, {"output": 2}], p) == p
    assert os.path.getsize(p) > 500


def test_chart_png_returns_none_without_matplotlib(monkeypatch):
    for m in [k for k in list(sys.modules) if k.startswith("matplotlib")]:
        monkeypatch.delitem(sys.modules, m, raising=False)
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    assert report.chart_png([{"output": 1}], "/tmp/should-not-exist.png") is None


def test_render_pdf_end_to_end(ctx, cfg, tmp_path):
    pytest.importorskip("reportlab")
    ok, note = report.render_pdf(ctx, None, str(tmp_path / "r.pdf"), cfg, here=HERE)
    assert ok is True, note
    assert (tmp_path / "r.pdf").stat().st_size > 1500
    assert "STSong-Light" in note, "中文走内置 CID 字体（OTF 为 CFF 轮廓不可用）"
    assert (tmp_path / "r.pdf").read_bytes()[:5] == b"%PDF-"


def test_render_pdf_reports_missing_reportlab_honestly(monkeypatch, ctx, cfg):
    for m in [k for k in list(sys.modules) if k.startswith("reportlab")]:
        monkeypatch.delitem(sys.modules, m, raising=False)
    monkeypatch.setitem(sys.modules, "reportlab", None)
    ok, note = report.render_pdf(ctx, None, "/tmp/x.pdf", cfg, here=HERE)
    assert ok is False and "reportlab 未安装" in note


def test_pick_font_falls_back_to_helvetica(cfg):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    import copy as _copy
    bad = C.Settings.from_dict(_copy.deepcopy(cfg.raw))
    bad.raw["report"]["cid_font"] = "NoSuchCIDFont"
    font, note = report._pick_font(bad, pdfmetrics, TTFont, UnicodeCIDFont, here=HERE)
    assert font == "Helvetica" and "方框" in note


def test_pick_font_skips_unusable_file_then_uses_cid(cfg):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    import copy as _copy
    c = C.Settings.from_dict(_copy.deepcopy(cfg.raw))
    c.raw["report"]["fonts"] = ["../../../fonts/SourceHanSansCN-Regular.otf"]
    font, note = report._pick_font(c, pdfmetrics, TTFont, UnicodeCIDFont, here=HERE)
    assert font == str(cfg.require("report.cid_font"))
    assert "CFF" in note, "必须说明为何弃用仓库 OTF（审计：不许含糊）"


# ---------------------------------------------------------- 移动端适配（工单超优(A)）
def test_real_html_is_mobile_adapted(ctx):
    html, _ = report.render_html(ctx, TPL)
    assert all(schedule.mobile_note(html).values()), "日报需 viewport+flex+media"


def test_daily_html_embeds_the_trend_chart_not_escaped_markup(ctx):
    """图文混排的真图：trend_svg 由本模块自生成，模板必须 | safe 渲染成 <svg>；
    被 autoescape 转义成 &lt;svg 时页面只会显示一行 markup 文本（原缺陷，此处守住）。"""
    html, _ = report.render_html(ctx, TPL)
    assert "<svg" in html and "&lt;svg" not in html
    assert "polyline" in html


# --------------------------------------------------- PDF 校验（工单及格(D)"PDF正确"）
def test_verify_pdf_accepts_a_real_rendered_pdf(ctx, cfg, tmp_path):
    pytest.importorskip("reportlab")
    p = str(tmp_path / "v.pdf")
    ok, note = report.render_pdf(ctx, None, p, cfg, here=HERE)
    assert ok is True, note
    chk = report.verify_pdf(p, 1500)
    assert chk["ok"] is True and chk["exists"] is True and chk["attempted"] is True
    assert chk["bytes"] == os.path.getsize(p) and chk["pages"] >= 1
    assert "校验通过" in chk["note"]


def test_verify_pdf_missing_file_is_not_ok(tmp_path):
    chk = report.verify_pdf(str(tmp_path / "nope.pdf"), 10)
    assert chk["ok"] is False and chk["exists"] is False and chk["bytes"] == 0
    assert "不存在" in chk["note"]


@pytest.mark.parametrize("body", [b"not a pdf at all",
                                  b"%PDF-1.4\ntruncated middle",
                                  b"%PDF-1.4\nno page objects here\n%%EOF\n"])
def test_verify_pdf_rejects_garbage_and_truncation(tmp_path, body):
    """坏文件一律不采信：缺头/缺尾/页对象为 0 都要具体写进 note（不许"存在即达标"）。"""
    p = tmp_path / "g.pdf"
    p.write_bytes(body)
    chk = report.verify_pdf(str(p), 1)
    assert chk["ok"] is False
    bad = chk["note"]
    assert ("头" in bad or "尾" in bad or "页对象" in bad), bad
    if b"/Type /Page" not in body:
        assert chk["pages"] == 0


def test_verify_pdf_enforces_min_bytes(tmp_path):
    p = tmp_path / "small.pdf"
    p.write_bytes(b"%PDF-1.4\n<< /Type /Page >>\n" + b"x" * 40 + b"\n%%EOF\n")
    chk = report.verify_pdf(str(p), 5000)
    assert chk["ok"] is False and "字节数" in chk["note"]
    assert chk["min_bytes"] == 5000 and chk["bytes"] == len(p.read_bytes())


def test_verify_pdf_counts_pages_not_pages_object(tmp_path):
    p = tmp_path / "pages.pdf"
    p.write_bytes(b"%PDF-1.4\n<< /Type /Pages >>\n<< /Type /Page >>\n"
                  b"<< /Type /Page >>\n%%EOF\n")
    chk = report.verify_pdf(str(p), 1)
    assert chk["pages"] == 2, "/Type /Pages 容器不得被当成一页"


# ----------------------------- 美观度检查清单（工单优秀(B)"≥4/5"，逐项实测、零主观）
def test_ui_rubric_scores_the_real_generated_html(ctx, cfg):
    html, _ = report.render_html(ctx, TPL)
    app_src = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    rb = report.ui_rubric(cfg.require("report.ui_rubric"), html, app_src, cfg.rules())
    assert len(rb["items"]) == rb["max"] == 5
    assert rb["score"] == sum(i["weight"] for i in rb["items"] if i["passed"])
    assert rb["score"] >= rb["threshold"] and rb["passed"] is True
    assert all(i["evidence"] for i in rb["items"]), "每项都要留可复核证据"
    assert "美观度 %d/%d（≥%d 达标" % (rb["score"], rb["max"], rb["threshold"]) \
        in report.rubric_text(rb)


def test_ui_rubric_deducts_a_bare_html_without_styling(ctx, cfg):
    """裸 HTML（无 CSS/无媒体查询/无图例）→ 五项全扣分、score=0 → 优秀(B) 判定不通过。"""
    rb = report.ui_rubric(cfg.require("report.ui_rubric"), "<h1>日报</h1>", "",
                          cfg.rules())
    assert rb["score"] == 0 and rb["passed"] is False
    assert {i["name"] for i in rb["items"] if not i["passed"]} == \
        {i["name"] for i in rb["items"]}
    assert "扣分项：" in report.rubric_text(rb)


def test_ui_rubric_rejects_unimplemented_check(cfg):
    """check 名写错 → 当场 ValueError（与未知 KPI 名同口径），绝不静默给分。"""
    with pytest.raises(ValueError, match="未实现检查"):
        report.ui_rubric({"threshold": 4,
                          "items": [{"name": "玄学", "check": "vibes", "weight": 1}]},
                         "", "", cfg.rules())


def test_ui_rubric_empty_items_cannot_pass(cfg):
    """清单为空 → 无从实测 → passed=False（不得用"默认满分"蒙过优秀(B) 闸门）。"""
    rb = report.ui_rubric({"threshold": 4, "items": []}, "", "", cfg.rules())
    assert rb["score"] == rb["max"] == 0 and rb["passed"] is False


def test_rubric_text_lists_per_item_scores_and_deductions():
    rb = {"items": [{"name": "甲", "weight": 1, "passed": True, "evidence": "e1"},
                    {"name": "乙", "weight": 1, "passed": False, "evidence": "缺X"}],
          "score": 1, "max": 2, "threshold": 2, "passed": False}
    txt = report.rubric_text(rb)
    assert "美观度 1/2（≥2 达标" in txt and "甲 1/1" in txt and "乙 0/1" in txt
    assert "扣分项：乙(缺X)" in txt
