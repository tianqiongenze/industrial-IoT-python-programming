# -*- coding: utf-8 -*-
"""报告渲染：文本过程报告 + 四段式 HTML 日报（Jinja2）+ PDF（reportlab）。

工程化要求 3（模板与数据分离）：HTML 骨架在 templates/daily_report.html.j2，
本模块只准备数据与调度；jinja2 缺失时走内置同构渲染器，并在报告中如实标注。
四段式口径与工单 P3.2 一致：生产概览 / 详细分析 / 异常识别 / 数据附表。
"""
import datetime
import html as _html
import os
import re as _re

from . import data_source, io_utils


# ---------------------------------------------------------------------------
# 文本过程报告（既有 D 层证据链，保持向后兼容）
# ---------------------------------------------------------------------------
def render(sections, stamp=False):
    """sections: [(标题, [行, ...]), ...] -> 文本。

    stamp=False（默认）：不写时间戳 —— 保证 output/report.txt 逐字节可复现（NF-1）；
    stamp=True：写入墙钟时间戳（人类可读交付版），此时文件不再逐字节一致，已在 docs/05 声明。
    """
    out = ["=" * 64]
    if stamp:
        out.append("生成时间: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    else:
        out.append("生成时间: 未启用（加 --stamp 写入墙钟时间戳；"
                   "耗时/定时等墙钟观测值见 output/timing.txt）")
    out.append("=" * 64)
    for title, lines in sections:
        out.append("")
        out.append("[%s]" % title)
        out.append("-" * 64)
        out.extend(str(x) for x in lines)
    out.append("")
    return "\n".join(out)


def save(sections, path, stamp=False):
    text = render(sections, stamp=stamp)
    io_utils.write_text(path, text)
    return text


# ---------------------------------------------------------------------------
# 上下文组装（日报的唯一数据面；app.py 亦复用，保证"同源双输出"）
# ---------------------------------------------------------------------------
BUCKETS = (1, 2, 5, 15, 60, 120)


def bucket(elapsed):
    """把实测耗时归档到稳定档位（NF-1 逐字节可复现的关键：
    0.055s 与 0.081s 同归 "<1s"，精确值只写进 output/timing.txt 这一份可变态文件）。"""
    for b in BUCKETS:
        if float(elapsed) < b:
            return "<%ds" % b
    return ">=120s"


def trend_svg(points, width=720, height=120):
    """纯 Python 折线 SVG（日报图文混排用，零依赖、可离线、可复现）。"""
    vals = [float(p.get("output", 0) or 0) for p in points]
    if len(vals) < 2:
        return '<svg width="%d" height="%d"><text x="8" y="20">数据点不足</text></svg>' % (
            width, height)
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = width / (len(vals) - 1)
    path = " ".join("%.1f,%.1f" % (i * step, height - 10 - (v - lo) * (height - 20) / span)
                   for i, v in enumerate(vals))
    return ('<svg width="%d" height="%d" xmlns="http://www.w3.org/2000/svg">'
            '<polyline fill="none" stroke="#2b6cb0" stroke-width="2" points="%s"/></svg>'
            % (width, height, path))


def build_context(cfg, *, date, kpis, rows_all, rows_window, devices, analysis,
                  anomalies, trend_points, source, provenance, deps, elapsed,
                  anomalies_total=None):
    """四段式日报的数据包（模板只读它，不读 cfg，确保版式/数据分离）。"""
    km = {k["name"]: k for k in kpis}
    total_out = sum(int(r["output"]) for r in rows_window)
    total_ok = sum(int(r["ok_qty"]) for r in rows_window)
    return {
        "title": str(cfg.require("report.title")),
        "date": date,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": list(cfg.require("report.sections")),
        "source": source,
        "provenance": sorted(provenance.items()),
        "deps": deps,
        "elapsed_text": bucket(elapsed),
        "within_budget": float(elapsed) < cfg.report_seconds_max,
        "budget_seconds": cfg.report_seconds_max,
        "kpi_names": [k["name"] for k in kpis],
        "kpis": kpis,
        "overview": {
            "rows_total": len(rows_all), "rows_window": len(rows_window),
            "devices": len(devices), "output": total_out, "good": total_ok,
            "yield_pct": (100.0 * total_ok / total_out) if total_out else 0.0,
            "efficiency": km.get("效率对标", {}).get("text", "-"),
            "alarms": km.get("今日告警数", {}).get("value", 0),
            "online": km.get("设备在线数", {}).get("text", "-"),
        },
        "analysis": analysis,
        "anomalies": anomalies,
        "thresholds_display": {"temp_max": cfg.temp_max, "vib_max": cfg.vib_max},
        "appendix_total": len(rows_window),
        "anomalies_total": int(len(anomalies) if anomalies_total is None
                               else anomalies_total),
        "trend_points": len(trend_points),
        "trend_svg": trend_svg(trend_points),
    }


APPENDIX_COLS = tuple(data_source.CANON)   # 单一真源：附表列 = 规范列，不重复定义


def add_appendix(ctx, rows):
    ctx["appendix"] = {"columns": list(APPENDIX_COLS),
                       "rows": [[r.get(c, "") for c in APPENDIX_COLS] for r in rows]}
    return ctx


# ---------------------------------------------------------------------------
# HTML 渲染：Jinja2 优先，缺失降级（并记录到底用了哪条路径）
# ---------------------------------------------------------------------------
def _fallback_html(ctx):
    """内置同构渲染器：与 .j2 模板同段落同占位，仅供 jinja2 缺失时兜底。"""
    esc = lambda v: _html.escape(str(v))  # noqa: E731
    s = ctx["sections"]
    out = ["<!doctype html><html lang=zh><head><meta charset=utf-8>",
           "<title>%s %s</title></head><body style='font-family:sans-serif'>" %
           (esc(ctx["title"]), esc(ctx["date"])),
           "<h1>%s ｜ %s</h1><p>生成时间 %s ｜ 数据源：%s</p>" %
           (esc(ctx["title"]), esc(ctx["date"]), esc(ctx["generated_at"]), esc(ctx["source"])),
           "<h2>1. %s</h2><ul>" % esc(s[0])]
    for k in ctx["kpis"]:
        out.append("<li><b>%s</b> %s（%s）</li>" % (esc(k["name"]), esc(k["text"]),
                                                   esc(k["tone"])))
    out.append("</ul><h2>2. %s</h2><table border=1 cellspacing=0><tr><th>设备</th>"
               "<th>产线</th><th>产量</th><th>合格</th><th>良率%%</th><th>告警</th>"
               "<th>灯态</th></tr>" % esc(s[1]))
    for r in ctx["analysis"]:
        out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(r.get(c, "")) for c in
                                           ("device_id", "line", "output", "ok_qty",
                                            "yield_pct", "alarms", "light")))
    out.append("</table>%s<h2>3. %s</h2><table border=1 cellspacing=0><tr><th>时间</th>"
               "<th>设备</th><th>温度</th><th>振动</th><th>原因</th><th>处置建议</th></tr>%s"
               % (ctx["trend_svg"], esc(s[2]), ""))
    for a in ctx["anomalies"]:
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % tuple(_html.escape(str(a.get(k, ""))) for k in
                           ("ts", "device_id", "temp", "vib", "reasons", "suggestion")))
    out.append("</table><h2>4. %s</h2><table border=1 cellspacing=0><tr>%s</tr>%s</table>"
               "<p>渲染路径：%s ｜ 日报耗时档位 %s（预算 %.0fs）｜耗时精确值见 timing.txt</p>"
               "</body></html>"
               % (esc(s[3]),
                  "".join("<th>%s</th>" % esc(c) for c in ctx["appendix"]["columns"]),
                  "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in row)
                          for row in ctx["appendix"]["rows"]),
                  esc(ctx["deps"]["html_renderer"]), esc(ctx["elapsed_text"]),
                  ctx["budget_seconds"]))
    return "".join(out)


def render_html(ctx, template_path):
    """返回 (html 文本, 渲染器标识)。Jinja2 不可用 → 内置同构渲染器。"""
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined, \
            select_autoescape
    except ImportError:
        return _fallback_html(ctx), "内置同构渲染器（jinja2 未安装）"
    env = Environment(loader=FileSystemLoader(os.path.dirname(template_path)),
                      # 注意：模板文件名是 *.html.j2，扩展名是 .j2 ——
                      # 若只写 select_autoescape(["html","xml"]) 会自动判定"非 HTML"而关闭转义，
                      # 数据源等外部字符串将原样进页面（XSS/版式破坏）。故把 .j2 显式列入。
                      autoescape=select_autoescape(["html", "htm", "xml", "j2"],
                                                   default_for_string=True, default=False),
                      undefined=StrictUndefined)   # 变量名错配 → 当场报错而非静默空白
    tpl = env.get_template(os.path.basename(template_path))
    return tpl.render(**ctx), "Jinja2 %s（StrictUndefined+autoescape）" % _ver("jinja2")


def _ver(name):
    try:
        import importlib.metadata as md
        return md.version(name)
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# PDF（reportlab，图文混排；中文用内置 CID 字体，字体文件不可用时如实降级）
# ---------------------------------------------------------------------------
def chart_png(points, path):
    """matplotlib 出趋势图 PNG 供 PDF 图文混排。

    为什么不用 plotly 静态导出：需要 kaleido，本机 pp03 环境未安装（报告如实标注）。
    图内文字用 ASCII，避免 matplotlib 默认字体无中文字形导致方框。
    """
    vals = [float(p.get("output", 0) or 0) for p in points]
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 2.4), dpi=120)
    ax.plot(range(len(vals)), vals, color="#2b6cb0", linewidth=1.4)
    ax.set_title("output trend (n=%d buckets)" % len(vals))
    ax.set_xlabel("sequence")
    ax.set_ylabel("output")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def render_pdf(ctx, png_path, out_path, cfg, here=None):
    """reportlab 生成四段式 PDF（图文混排）；返回 (是否成功, 说明)。"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                        Table, TableStyle)
        from reportlab import rl_config
    except ImportError as exc:
        return False, "reportlab 未安装（%s）：本次仅出 HTML" % exc
    # 默认 PDF 参与 output/ 逐字节复现闸门：必须钉死 /CreationDate 与 /ID
    # （invariant=1 → 固定时间戳 + 内容哈希 ID；否则每次运行 PDF 字节都漂移）
    rl_config.invariant = 1
    font, note = _pick_font(cfg, pdfmetrics, TTFont, UnicodeCIDFont, here=here)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("cn", parent=ss["Normal"], fontName=font, fontSize=8,
                          leading=11)
    head = ParagraphStyle("cnh", parent=ss["Heading2"], fontName=font, fontSize=13,
                          leading=17)
    doc = SimpleDocTemplate(out_path, title=ctx["title"], author="p33_kpi_cockpit",
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    avail = doc.width

    def tbl(rows):
        return _table(rows, avail, Paragraph, body, Table, TableStyle, colors)

    st = [Paragraph("%s ｜ %s" % (_esc(ctx["title"]), _esc(ctx["date"])), head),
          Paragraph("数据源：%s" % _esc(ctx["source"]), body),
          Paragraph("生成时间：%s ｜ 耗时 %s（预算 %.0fs）｜ 中文字体：%s"
                    % (_esc(ctx["generated_at"]), _esc(ctx["elapsed_text"]),
                       ctx["budget_seconds"], _esc(note)), body),
          Spacer(1, 3 * mm),
          Paragraph("一、%s" % _esc(ctx["sections"][0]), head)]
    krows = [["指标", "读数", "环比", "灯态"]] + [
        [k["name"], k["text"], k["delta"] or "-", k["tone"]] for k in ctx["kpis"]]
    krows.append(["覆盖设备", str(ctx["overview"]["devices"]),
                  "窗口行数", str(ctx["overview"]["rows_window"])])
    st.append(tbl(krows))
    st.append(Paragraph("二、%s" % _esc(ctx["sections"][1]), head))
    arows = [["设备", "产线", "产量", "合格", "良率%", "告警", "灯态"]] + [
        [r["device_id"], r["line"], r["output"], r["ok_qty"], r["yield_pct"],
         r["alarms"], r["light"]] for r in ctx["analysis"]]
    st.append(tbl(arows))
    if png_path and os.path.exists(png_path):
        st.append(Spacer(1, 4 * mm))
        st.append(Image(png_path, width=min(avail, 170 * mm), height=58 * mm))
    st.append(Paragraph("三、%s（超阈值 %d 条，列前 %d 条）"
                        % (_esc(ctx["sections"][2]), ctx["anomalies_total"],
                           len(ctx["anomalies"])), head))
    mrows = [["时间", "设备", "温度", "振动", "原因", "处置建议"]] + [
        [a["ts"], a["device_id"], a["temp"], a["vib"], a["reasons"], a["suggestion"]]
        for a in ctx["anomalies"]]
    st.append(tbl(mrows))
    st.append(Paragraph("四、%s（末 %d 行）"
                        % (_esc(ctx["sections"][3]), len(ctx["appendix"]["rows"])), head))
    drows = [list(ctx["appendix"]["columns"])] + [
        [str(c) for c in row] for row in ctx["appendix"]["rows"]]
    st.append(tbl(drows))
    doc.build(st)
    return True, "reportlab PDF（中文字体 %s）" % note


def _esc(v):
    return _html.escape(str(v), quote=False)


def _pick_font(cfg, pdfmetrics, TTFont, UnicodeCIDFont, here=None):
    """中文字体：候选 TTF/TTC 依次试，全失败用 reportlab 内置 CID（免字体文件）。"""
    base = here or os.getcwd()
    for rel in cfg.require("report.fonts") or []:
        p = os.path.normpath(os.path.join(base, rel))
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont("cnfile", p))
                return "cnfile", "字体文件 %s" % os.path.basename(p)
            except Exception:
                continue
    name = str(cfg.require("report.cid_font"))
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        return name, ("内置 CID %s；仓库 OTF 为 CFF 轮廓，reportlab TTFont 不支持故未采用"
                      % name)
    except Exception:                                  # pragma: no cover - 极端环境
        return "Helvetica", "Helvetica（中文可能显示为方框）"


def _table(rows, avail, Paragraph, body, Table, TableStyle, colors):
    """等分列宽 + 单元格 Paragraph 化：长文本自动换行，杜绝跨页溢出。"""
    ncol = max(len(r) for r in rows)
    norm = [[str(c) for c in (list(r) + [""] * (ncol - len(r)))] for r in rows]
    cells = [[Paragraph(s, body) for s in row] for row in norm]
    widths = [avail / ncol] * ncol
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6ecf5")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# ---------------------------------------------------------------------------
# 及格(D)"PDF 正确"：对产出 PDF 做字节级实测校验（存在/头尾/大小/页数）
# ---------------------------------------------------------------------------
def verify_pdf(path, min_bytes=1500):
    """校验 PDF 产物并返回可证伪数字：bytes、页数（/Type /Page 对象计数）、逐项判定。

    口径：%PDF- 头与 %%EOF 尾齐、字节数 ≥ config report.pdf_min_bytes、
    页对象 ≥1 才算 ok；任何一项不过都写进 note，报告如实引用，不做美化。
    """
    out = {"file": os.path.basename(str(path)), "attempted": True, "exists": False,
           "bytes": 0, "pages": 0, "min_bytes": int(min_bytes), "ok": False,
           "note": ""}
    if not path or not os.path.exists(path):
        out["note"] = "PDF 文件不存在（日报只有 HTML，及格(D) 的 PDF 子条件未达成）"
        return out
    with open(path, "rb") as fh:
        raw = fh.read()
    out["exists"] = True
    out["bytes"] = len(raw)
    out["pages"] = len(_re.findall(rb"/Type\s*/Page\b(?!s)", raw))
    bad = []
    if raw[:5] != b"%PDF-":
        bad.append("缺 %PDF- 文件头")
    if not raw.rstrip().endswith(b"%%EOF"):
        bad.append("缺 %%EOF 文件尾")
    if out["bytes"] < int(min_bytes):
        bad.append("字节数 %d < 下限 %d" % (out["bytes"], int(min_bytes)))
    if out["pages"] < 1:
        bad.append("页对象数为 0（未检索到 /Type /Page）")
    out["ok"] = not bad
    out["note"] = ("校验通过：" + "%d B / %d 页" % (out["bytes"], out["pages"])
                   + "，%PDF- 头与 %%EOF 尾齐") if not bad \
        else "校验失败：" + "、".join(bad)
    return out


# ---------------------------------------------------------------------------
# 优秀(B)"美观度 ≥4/5"：确定性检查清单（config report.ui_rubric 定义项与分值，
# 代码只提供可对真实产物复核的 check 函数——杜绝"5/5"裸自评）
# ---------------------------------------------------------------------------
def _rubric_heading(bundle):
    html = bundle["html"]
    n_h1, n_h2 = html.count("<h1"), html.count("<h2>")
    return n_h1 >= 1 and n_h2 >= 4, "h1=%d h2=%d（要求 h1≥1 且 h2≥4 段）" % (n_h1, n_h2)


def _rubric_units(bundle):
    html, unit = bundle["html"], str(bundle["rules"].get("unit_symbol", "℃"))
    missing = [tok for tok in ("%", unit, "mm/s") if tok not in html]
    return not missing, ("标注齐全 %%/%s/mm/s" % unit) if not missing \
        else "缺单位：%s" % "、".join(missing)


def _rubric_colors(bundle):
    html = bundle["html"]
    css = all(tok in html for tok in (".ok{", ".warn{", ".error{"))
    used = any(tok in html for tok in ("pill ok", "pill warn", "pill error"))
    return css and used, "三色 CSS=%s 使用=%s（红绿灯/告警上色）" % (css, used)


def _rubric_legend(bundle):
    app_src, html = bundle["app_src"], bundle["html"]
    ok = "px.line" in app_src and "labels=" in app_src and "<svg" in html
    return ok, "app.py px.line 轴例 labels=%s｜日报趋势 SVG=%s" % (
        "labels=" in app_src, "<svg" in html)


def _rubric_responsive(bundle):
    html = bundle["html"]
    toks = ("width=device-width", "flex-wrap", "@media")
    missing = [t for t in toks if t not in html]
    return not missing, ("viewport+flex+media 齐" if not missing
                         else "缺：%s" % "、".join(missing))


RUBRIC_CHECKS = {
    "heading_levels": _rubric_heading,
    "unit_labels": _rubric_units,
    "tone_colors": _rubric_colors,
    "chart_legend": _rubric_legend,
    "responsive_layout": _rubric_responsive,
}


def ui_rubric(rubric_cfg, html, app_src, rules):
    """按 config 清单逐项实测生成产物，返回 {items, score, max, threshold, passed}。

    红线：check 名写错 → ValueError（与 compute_kpis 对未知 KPI 名同口径）；
    清单为空/权重全 0 → score 上不去，优秀(B) 当场判未达标（改配置不改代码）。
    """
    bundle = {"html": html, "app_src": app_src, "rules": rules}
    threshold = int(rubric_cfg.get("threshold"))
    items = list(rubric_cfg.get("items") or [])
    score = total = 0
    rows = []
    for it in items:
        name, check = str(it.get("name")), str(it.get("check"))
        if check not in RUBRIC_CHECKS:
            raise ValueError("config report.ui_rubric 含未实现检查: %s（请同步 "
                             "report.RUBRIC_CHECKS）" % check)
        weight = int(it.get("weight", 1))
        passed, evidence = RUBRIC_CHECKS[check](bundle)
        score += weight if passed else 0
        total += weight
        rows.append({"name": name, "check": check, "weight": weight,
                     "passed": bool(passed), "evidence": evidence})
    return {"items": rows, "score": score, "max": total, "threshold": threshold,
            "passed": bool(items) and score >= threshold}


def rubric_text(rubric):
    """把检查表压成一行：逐项 名称 得分/权重；随后列出扣分项与证据（可复核）。"""
    detail = "、".join("%s %d/%d" % (it["name"], it["weight"] if it["passed"] else 0,
                                     it["weight"]) for it in rubric["items"]) or "清单为空"
    deducts = "、".join("%s(%s)" % (it["name"], it["evidence"])
                        for it in rubric["items"] if not it["passed"]) or "无"
    return "美观度 %d/%d（≥%d 达标；%s；扣分项：%s）" % (
        rubric["score"], rubric["max"], rubric["threshold"], detail, deducts)
