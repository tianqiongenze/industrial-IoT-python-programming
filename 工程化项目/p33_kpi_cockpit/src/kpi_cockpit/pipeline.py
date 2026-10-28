# -*- coding: utf-8 -*-
"""编排层：数据源 → 筛选 → 5+4 KPI → 趋势/仪表/告警/对标 → 四段式日报 → 分层证据报告。

工单 TODO ↔ 本文件（详见 docs/03 §1 的 TODO→file:line 地图）：
  TODO-0 数据源    data_source.load()          （clean.csv 优先，缺失按 seed 合成）
  TODO-1 侧栏筛选  core.filter_records()        （app.py 与 run.py --start/--end/--device 同函数）
  TODO-2 指标卡    core.compute_kpis()           5 个必做 KPI + 4 个补充
  TODO-3 趋势图    core.trend()                  app.py 用 px.line，日报用内联 SVG/PNG
  TODO-4 仪表/灯/表 core.gauge()/device_status()/alarm_rows()
  TODO-5 效率对标  core.efficiency()             app.py 用 st.progress
  P3.2 四段式日报  report.build_context()/render_html()/render_pdf()/verify_pdf()
  异常识别+建议    core.anomalies()/suggest()
  定时/邮件/移动端 schedule.*()（超优(A)）；钻取 core.drill()/core.drill_rows()（优秀(B)）
  分层达标 D/C/B/A _tier_lines()：口径逐条对齐**工单任务书 P3 验收标准**，
  四行原文由本文件的 WO_ROW 单点持有并逐字进报告行首（含线值本身，如
  「5 KPI可用+时间筛选」「日报生成<2分钟」「≥7指标」「优秀+定时…移动端适配」），
  每条给真实可复核数字；跟做示例降级为"保底自检"行，不再借用工单字母。
"""
import datetime
import os
import sys
import time

from . import core, data_source, deps, io_utils, report, schedule

_HEX = "0123456789abcdef"

#: 工单《P3》「验收标准」四行**原文**（逐字），报告「分层达标」每档行首直接引用它。
WO_ROW = {
    "D": "5 KPI可用+时间筛选；日报四部分完整+PDF正确",
    "C": "联动筛选流畅；日报生成<2分钟",
    "B": "≥7指标+钻取交互；异常自动识别；美观度≥4/5",
    "A": "优秀+定时自动生成(mailto/计划任务)+移动端适配",
}
WO_LABEL = {"D": "及格(D)", "C": "良好(C)", "B": "优秀(B)", "A": "超优(A)"}


def _here():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _runtime_dir(out_dir):
    """墙钟/计划任务产物的落点：output/ **之外**的 runtime/（与 p21/p22/p66 同口径），
    output/ 里只留确定性内容，逐字节复现闸门才不被每次刷新的时长打穿。"""
    return os.path.join(os.path.dirname(os.path.abspath(out_dir)), "runtime")


def build_rows(cfg, *, source, csv_path, here):
    """TODO-0：装载数据（返回 Dataset，来源字符串写死进报告）。"""
    return data_source.load(cfg, here, source=source, csv_path=csv_path)


def select_window(cfg, ds, start, end, date, devices):
    """TODO-1：与 app.py 侧栏完全同源的过滤（同一函数，绝不两套逻辑）。"""
    avail = ds.devices
    picked = [d for d in (devices or []) if d] or None
    if picked:
        unknown = [d for d in picked if d not in avail]
        if unknown:
            raise ValueError("筛选设备不存在于数据源: %s（可选：%s）"
                             % (", ".join(unknown), ", ".join(avail)))
    rows = core.filter_records(ds.as_dicts(), start=start, end=end,
                               devices=picked, date=date)
    if not rows:
        raise ValueError("筛选后 0 行：请检查 --start/--end/--device/--date")
    return rows, picked


def run(cfg, out_dir, *, source="auto", csv_path=None, date=None, start=None,
        end=None, devices=None, pdf=True, stamp=False, drill=None, schedule_at=None,
        here=None):
    """完整流水线。返回 (sections, result_dict)。

    pdf=True（默认）时同步生成并校验 daily_report.pdf —— 工单及格(D) 的
    "PDF正确"子条件要求 PDF 是常规产物而非可选项；config report.pdf_enabled=false
    或 reportlab 缺失都会让 D 档当场判未达标（改配置不改代码，可证伪）。
    """
    here = here or _here()
    t0 = time.perf_counter()
    rules = cfg.rules()

    ds = build_rows(cfg, source=source, csv_path=csv_path, here=here)
    rows_all = ds.as_dicts()
    rows, picked = select_window(cfg, ds, start, end, date, devices)
    lo, hi = (start or min(r["ts"][:10] for r in rows),
              end or max(r["ts"][:10] for r in rows))
    days = len({r["ts"][:10] for r in rows})
    rules["days"] = days                       # 效率对标按窗口天数折算
    prev = core.previous_window(rows_all, lo, hi, days)

    kpis = core.compute_kpis(rows, rules, lines=cfg.items, prev=prev)
    km = core.kpi_map(kpis)
    gauge = core.gauge(rows, rules)                       # TODO-4
    status = core.device_status(rows, rules)                      # TODO-4 红绿灯
    alarms = core.alarm_rows(rows, cfg.vib_max)                   # TODO-2 c4 / TODO-4 表
    eff_clip, eff_raw = core.efficiency(rows, cfg.target_output_per_day, days)  # TODO-5
    trend_pts = core.trend(rows, bucket="day" if days > 1 else "hour")   # TODO-3
    analysis = core.by_device(rows, rules)[:int(cfg.require("report.analysis_top"))]
    anom_all = core.anomalies(rows, rules, topk=None)
    anom_top = anom_all[:int(cfg.topk)]
    drill_out = [core.drill(rows_all, d, rules, int(cfg.topk))
                 for d in (drill or [cfg.path("drill.default_device")])]

    # ---- 优秀(B) 钻取证据（CLI 离线复放"点击趋势折线点"的选择事件）----
    # 与 app.py 的 st.plotly_chart(on_select="rerun") 走同一个 core.drill_rows：
    # 选"数据行最多的前 3 个时间桶"作为确定性模拟点击点（n 降序、同 n 按桶名升序）。
    _top_buckets = [str(t["ts"]) for t in
                    sorted(trend_pts, key=lambda t: (-t["n"], str(t["ts"])))[:3]]
    link_pts = [{"x": b} for b in _top_buckets]
    link_det = core.drill_rows(link_pts, rows, rules)
    drill_link = {"selection_points": link_pts, "buckets": _top_buckets,
                  "rows_detail": len(link_det),
                  "cap": int(rules.get("drill_max_rows", 30)),
                  "detail_columns": list(rules.get("drill_detail_columns") or []),
                  "fingerprint": core.drill_fingerprint(link_det)}
    # ---- 良好(C)/及格(D) 筛选探针：同一 core.filter_records 的"联动"程序化实测 ----
    # 时间筛选：缩到窗口首日；设备筛选：只选首台设备，总产量必须同步变小——
    # "筛选→KPI 重算"回路是算出来的，不是肉眼验收出来的（AppTest 无头回归见
    # tests/test_dashboard.py，CLI 复放见 tests/test_tier_gates.py）。
    probe_day = core.filter_records(rows_all, date=lo)
    dev_probe = {}
    if ds.devices:
        d0 = str(ds.devices[0])
        sub = core.filter_records(rows_all, devices=[d0])
        dev_probe = {"device": d0, "rows": len(sub), "rows_all": len(rows_all),
                     "output": core.total_output(sub),
                     "output_all": core.total_output(rows_all)}
    elapsed = time.perf_counter() - t0

    # ---- 依赖与模式：真探测，报告只说实际发生的事 ----
    probes = deps.detect()
    dep_lines = deps.summary(probes)
    dashboard = ("streamlit %s 已安装：`streamlit run app.py` 起真仪表盘；"
                 "离线无头验证入口 `python run.py --app-check`"
                 "（streamlit.testing.v1.AppTest 执行同一份 app.py）"
                 % probes["streamlit"].version
                 ) if probes["streamlit"].installed else \
        "streamlit 未安装：headless 兜底路径（KPI/日报计算与 app.py 共用 core.*，" \
        "文本版报告即为交付物）"

    # ---- 四段式日报（HTML 必出；PDF 默认生成并校验，供及格(D) 判定）----
    renderer = ("Jinja2 %s（StrictUndefined+autoescape）" % probes["jinja2"].version
                if probes["jinja2"].installed else "内置同构渲染器（jinja2 未安装）")
    ctx = report.build_context(cfg, date=date or "%s~%s" % (lo, hi), kpis=kpis,
                               rows_all=rows_all, rows_window=rows,
                               devices=ds.devices, analysis=analysis,
                               anomalies=anom_top, anomalies_total=len(anom_all),
                               trend_points=trend_pts, source=ds.source,
                               provenance=ds.provenance, elapsed=elapsed,
                               deps={"summary": dep_lines, "dashboard": dashboard,
                                     "html_renderer": renderer})
    appendix = core.tail_rows(rows, int(cfg.require("report.tail_rows")))
    ctx["appendix_src"] = appendix               # 附表原行，落 appendix.csv 用
    report.add_appendix(ctx, appendix)
    html_path = os.path.join(out_dir, str(cfg.require("report.html_name")))
    pdf_path = os.path.join(out_dir, str(cfg.require("report.pdf_name")))
    tpl = os.path.join(here, str(cfg.require("report.template")))
    ctx["generated_at"] = (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                           if stamp else "未启用（加 --stamp 写入时间戳）")
    html, got_renderer = report.render_html(ctx, tpl)
    if got_renderer != renderer:      # 自述与实际渲染器不一致 → 立刻失败，杜绝谎报
        raise RuntimeError("渲染器自述不一致：ctx=%r 实际=%r" % (renderer, got_renderer))
    io_utils.write_text(html_path, html)

    pdf_enabled = bool(cfg.require("report.pdf_enabled"))
    pdf_min = int(cfg.require("report.pdf_min_bytes"))
    png_note = "未生成"
    if not pdf_enabled:
        pdf_note = "未生成（config report.pdf_enabled=false）"
        pdf_check = {"file": os.path.basename(pdf_path), "attempted": False,
                     "exists": os.path.exists(pdf_path), "bytes": 0, "pages": 0,
                     "min_bytes": pdf_min, "ok": False,
                     "note": "未生成：config report.pdf_enabled=false（及格(D) 的 PDF "
                             "子条件未达成；学生须开启该键并保证 reportlab 可用）"}
    elif pdf:
        png_path = os.path.join(out_dir, "trend_chart.png")
        made = report.chart_png(trend_pts, png_path)
        png_note = "matplotlib PNG（%s）" % ("已出图" if made else "matplotlib 不可用，跳过")
        ok, why = report.render_pdf(ctx, png_path, pdf_path, cfg, here=here)
        pdf_note = why if ok else "PDF 未生成：" + why
        pdf_check = report.verify_pdf(pdf_path, pdf_min)
        if not ok:   # 渲染失败时盘上即便有旧 PDF 也不采信（防"拿陈货冒充"）
            pdf_check["ok"] = False
            pdf_check["note"] = "reportlab 渲染失败：%s（不采信盘上旧文件）" % why
    else:
        pdf_note = "本次跳过（--no-pdf；及格(D) 需当次产出 PDF，旧文件不采信）"
        pdf_check = report.verify_pdf(pdf_path, pdf_min)
        pdf_check["attempted"] = False
        pdf_check["ok"] = False      # 当次没生成 → 盘上旧 PDF 一律不采信（防陈货冒充）
        pdf_check["note"] = ("本次 --no-pdf 未生成；盘上旧文件实测 %d B / %d 页不采信"
                             % (pdf_check["bytes"], pdf_check["pages"]))
    if elapsed > cfg.report_seconds_max:                 # 工单 P3.2 时限：日报 < 2 分钟
        raise RuntimeError("日报耗时 %.1fs 超过预算 %.0fs（工单 P3.2 时限）"
                           % (elapsed, cfg.report_seconds_max))

    # ---- 超优(A)：定时 + 邮件 + 计划任务产物 + 移动端适配（全部可复核属性）----
    at = schedule_at or str(cfg.require("schedule.at"))
    now_dt = datetime.datetime.now()
    next_at, raw_wait = schedule.next_fire(now_dt, at)
    demo_wait, _ = schedule.wait_seconds(now_dt, at,
                                         cfg.require("schedule.max_wait_seconds"))
    mailto_to = str(cfg.require("schedule.mailto"))
    mailto = schedule.mailto(mailto_to, ctx["date"], ctx["title"],
                             ["%s=%s" % (k["name"], k["text"]) for k in kpis])
    sched_entry = {"project_dir": here, "python": sys.executable,
                   "config": os.path.join(here, "config", "rules.yaml")}
    cron = schedule.crontab_line(cfg, sched_entry, at=at)
    timer = schedule.systemd_timer({"project": str(cfg.require("project")),
                                    **sched_entry}, at)
    h_at, m_at = schedule.parse_at(at)
    launchd = schedule.launchd_plist(sched_entry, "%02d:%02d" % (h_at, m_at))
    next_fire_ok = (isinstance(next_at, datetime.datetime) and next_at > now_dt
                    and (next_at.hour, next_at.minute) == (h_at, m_at))
    crontab_ok = cron.startswith("%d %d * * * " % (m_at, h_at))
    systemd_ok = ("OnCalendar=*-*-* %02d:%02d:00" % (h_at, m_at)) in timer
    launchd_ok = ("<key>Hour</key><integer>%d</integer>" % h_at) in launchd and \
                 ("<key>Minute</key><integer>%d</integer>" % m_at) in launchd
    mail_ok = schedule.mailto_ok(mailto, mailto_to)
    schedule_ok = bool(next_fire_ok and crontab_ok and systemd_ok and launchd_ok
                       and mail_ok)
    # 移动端适配：对生成 HTML 实测 viewport/flex/媒体查询与窄屏断点（不看口号看版式属性）
    mobile = schedule.mobile_note(html)
    narrow = schedule.narrow_width_px(html)
    max_narrow = int(cfg.require("report.mobile.max_narrow_px"))
    mobile_ok = bool(all(mobile.values()) and narrow is not None
                     and narrow <= max_narrow)

    # ---- 落盘：kpi.json / result.json / appendix.csv / report.txt / timing.txt ----
    io_utils.ensure_dir(out_dir)
    # 墙钟与计划任务产物写 output/ 之外的 runtime/（p21/p22/p66 同口径）
    rt_dir = _runtime_dir(out_dir)
    sc_dir = os.path.join(rt_dir, "schedule")
    io_utils.write_text(os.path.join(sc_dir, "crontab.txt"), cron + "\n")
    io_utils.write_text(os.path.join(sc_dir, "p33-daily-report.timer"), timer + "\n")
    io_utils.write_text(os.path.join(sc_dir, "com.p33.kpi-daily-report.plist"), launchd)
    io_utils.write_text(os.path.join(sc_dir, "mailto.txt"), mailto + "\n")
    io_utils.write_text(os.path.join(rt_dir, "schedule_state.txt"),
                        "定时状态：目标 %s｜下次触发 %s｜距此刻 %.0fs｜演示裁剪等待 %.1fs｜"
                        "计划任务产物 runtime/schedule/（crontab/systemd/launchd/mailto 共 4 件）\n"
                        % (at, next_at.strftime("%Y-%m-%d %H:%M:%S"), raw_wait, demo_wait))
    wall_line = ("日报实测耗时 %.3fs｜预算 %.0fs｜%s｜时间戳开关 %s｜"
                 "定时目标 %s（下次触发 %s，距此刻 %.0fs，演示裁剪等待 %.1fs）\n"
                 % (elapsed, cfg.report_seconds_max,
                    "达标(工单P3.2<2分钟)" if elapsed < cfg.report_seconds_max else "超时",
                    "on" if stamp else "off", at,
                    next_at.strftime("%Y-%m-%d %H:%M:%S"), raw_wait, demo_wait))
    io_utils.write_text(os.path.join(rt_dir, "timing.txt"), wall_line)

    ledger = [core.derive(r) for r in cfg.items]                 # 产线台账（保底材料）
    result = {
        "work_order": str(cfg.require("work_order")),
        "project": str(cfg.require("project")),
        "source_mode": ds.mode,
        "source": ds.source, "provenance": ds.provenance,
        "window": {"start": lo, "end": hi, "devices": picked or ds.devices,
                   "rows_all": len(rows_all), "rows_window": len(rows), "days": days},
        "kpis": kpis, "kpi_names": [k["name"] for k in kpis],
        "required_kpis": cfg.kpi_required,
        "ledger": ledger,
        "gauge": gauge, "device_status": status,
        "alarms_total": len(alarms), "efficiency": {"clip": eff_clip, "raw": eff_raw},
        "anomalies_total": len(anom_all), "anomalies_top": anom_top,
        "drill": drill_out,
        "schedule": {"at": at, "mailto": mailto, "crontab": cron,
                     "systemd_timer": timer, "launchd": launchd,
                     "mobile_adapt": mobile,
                     "artifacts_written_to": "runtime/schedule/（output/ 之外）",
                     "wait_reported_in": "timing.txt"},
        "schedule_check": {
            "at": at, "hour": h_at, "minute": m_at,
            "next_fire_is_real_datetime": bool(next_fire_ok),
            "crontab_matches_at": bool(crontab_ok),
            "systemd_matches_at": bool(systemd_ok),
            "launchd_matches_at": bool(launchd_ok),
            "mailto_rendered_ok": bool(mail_ok),
            "artifacts_renders": 4,
            "wall_clock_values_in": "runtime/schedule_state.txt + output/timing.txt",
            "all_ok": schedule_ok},
        "mobile_check": {**mobile, "narrow_px": narrow, "max_narrow_px": max_narrow,
                         "ok": mobile_ok},
        "pdf_check": pdf_check,
        "artifacts": {"html": os.path.basename(html_path), "renderer": renderer,
                      "pdf": pdf_note, "chart": png_note},
        "deps": {k: v.as_dict() for k, v in probes.items()},
        "timing": {"elapsed_bucket": report.bucket(elapsed),   # 稳定档位（可逐字节复现）
                   "budget_seconds": cfg.report_seconds_max,
                   "within_budget": elapsed < cfg.report_seconds_max,
                   "exact_seconds_in": "timing.txt"},
        "stamp": stamp,
    }
    io_utils.write_json(os.path.join(out_dir, "kpi.json"),
                        {"window": result["window"], "kpis": kpis,
                         "source": ds.source, "gauge": gauge, "ledger": ledger,
                         "device_status": status, "efficiency": result["efficiency"]})
    io_utils.write_csv_rows(os.path.join(out_dir, "appendix.csv"),
                            ctx["appendix_src"], list(data_source.CANON))
    # ---- 分层达标：口径逐条对齐**工单任务书 P3 验收标准**（及格D/良好C/优秀B/超优A），
    #      每条都是可对 result.json/产物重算的实测数字；跟做示例降级为"保底自检"行。----
    app_path = os.path.join(here, "app.py")
    app_src = ""
    if os.path.exists(app_path):
        app_src = open(app_path, encoding="utf-8").read()
    artifacts_done = [n for n in (os.path.basename(html_path),
                                  os.path.basename(pdf_path), "kpi.json",
                                  "appendix.csv", "trend_chart.png")
                      if os.path.exists(os.path.join(out_dir, n))]
    rubric = report.ui_rubric(cfg.require("report.ui_rubric"), html, app_src, rules)
    result["ui_rubric"] = rubric

    day_probe_ok = 0 < len(probe_day) < len(rows_all)
    dev_probe_ok = bool(dev_probe) and 0 < dev_probe["rows"] < dev_probe["rows_all"] \
        and 0 < dev_probe["output"] < dev_probe["output_all"]
    required_ok = (len(cfg.kpi_required) >= 5
                   and all(km[n]["value"] is not None for n in cfg.kpi_required))
    sections_in_html = (len(ctx["sections"]) >= 4
                        and all(str(s) in html for s in ctx["sections"]))
    link_ok = drill_link["rows_detail"] > 0
    fingerprint_ok = len(drill_link["fingerprint"]) == 8 and \
        all(c in _HEX for c in drill_link["fingerprint"])
    rerun_ok = bool(app_src) and app_src.count('on_select="rerun"') >= 2 \
        and "core.filter_records" in app_src and "core.drill_rows" in app_src
    drill_keys_ok = 'key="trend_drill"' in app_src and 'key="alarm_table"' in app_src
    tiers = {
        "D": bool(required_ok and day_probe_ok and sections_in_html
                  and pdf_check["ok"]),
        "C": bool(rerun_ok and day_probe_ok and dev_probe_ok and link_ok
                  and fingerprint_ok and elapsed < cfg.report_seconds_max),
        "B": bool(len(kpis) >= 7 and link_ok and fingerprint_ok and drill_keys_ok
                  and len(anom_all) > 0 and rubric["passed"]),
        "A": bool(len(kpis) >= 7 and link_ok and fingerprint_ok and drill_keys_ok
                  and len(anom_all) > 0 and rubric["passed"]
                  and schedule_ok and mobile_ok),
    }
    result["tiers"] = tiers
    result["drill_link"] = drill_link
    result["filter_probe"] = {"date": str(lo), "rows": len(probe_day),
                              "rows_all": len(rows_all), "device": dev_probe,
                              "sections_in_html": bool(sections_in_html)}
    result["report_sections"] = list(ctx["sections"])
    result["artifacts_written"] = artifacts_done
    result["linkage"] = {"app_py_found": bool(app_src),
                         "on_select_rerun": app_src.count('on_select="rerun"'),
                         "trend_drill_key": 'key="trend_drill"' in app_src,
                         "alarm_table_key": 'key="alarm_table"' in app_src,
                         "drill_rows_fn_in_app": "core.drill_rows" in app_src,
                         "shared_filter_fn": "core.filter_records" in app_src}
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    io_utils.write_text(os.path.join(out_dir, "timing.txt"), wall_line)

    sections = [
        ("工单 TODO 覆盖", _todo_lines(result, cfg)),
        ("分层达标（D/C/B/A）", _tier_lines(result, cfg)),
        ("数据源实况（TODO-0）", ["模式：%s" % ds.mode, "来源：%s" % ds.source,
                                  "列级出处：%s" % ", ".join("%s=%s" % kv
                                                          for kv in sorted(ds.provenance.items())),
                                  "行数：全量 %d｜窗口 %d｜设备 %d 台｜覆盖 %d 天"
                                  % (len(rows_all), len(rows), len(ds.devices), days)]),
        ("产线台账（config/lines，保底自检材料）",
         core.render(core.table_rows(ledger)[1:], core.table_rows(ledger)[0]).splitlines()),
        ("KPI 驾驶舱（TODO-2/3/4/5）",
         core.render([(k["name"], k["text"], k["delta"] or "-", k["tone"]) for k in kpis],
                     ("指标", "读数", "环比", "灯态")).splitlines() +
         ["良率仪表读数 %.2f%%（%s）｜告警 %d 条｜效率对标 %.1f%%（截断 %.1f%%）"
          % (gauge["value"], gauge["tone"], len(alarms), eff_raw * 100, eff_clip * 100)] +
         ["趋势采样点 %d（app.py 用 px.line 渲染，日报用内联 SVG/PNG）" % len(trend_pts)]),
        ("异常识别与处置建议（P3.2-3）",
         ["超阈值 %d 条（temp>%.1f 或 vib>%.1f），报告前 %d 条："
          % (len(anom_all), cfg.temp_max, cfg.vib_max, len(anom_top))] +
         (["> %s %s temp=%s vib=%s → %s" % (a["ts"], a["device_id"], a["temp"], a["vib"],
                                           a["suggestion"]) for a in anom_top]
          if anom_top else ["> 本窗口无超阈值记录"])),
        ("四段式日报产物", ["HTML：%s（渲染器：%s）" % (os.path.basename(html_path), renderer),
                          "四段：%s" % " / ".join(ctx["sections"]),
                          "附表行数：%d（config/report.tail_rows）" % len(ctx["appendix"]["rows"]),
                          "PDF：%s｜校验：%s（下限 %d B，实测 %d B / %d 页）"
                          % (pdf_note, pdf_check["note"], pdf_check["min_bytes"],
                             pdf_check["bytes"], pdf_check["pages"]),
                          "趋势图：%s" % png_note]),
        ("依赖探测与运行模式", [dep_lines, dashboard]),
        ("联动钻取证据（优秀(B)·可复核）",
         ["复放选择事件：points=%s（趋势线数据行最多的前 %d 个时间桶，按 n 降序、同 n 按桶名升序）"
          % (drill_link["selection_points"], len(drill_link["buckets"])),
          "core.drill_rows 联动明细 %d 行（上限 drill.max_rows=%d｜列=%s）"
          % (drill_link["rows_detail"], drill_link["cap"],
             ",".join(drill_link["detail_columns"])),
          "明细指纹 crc32=%s（zlib.crc32，跨 PYTHONHASHSEED 稳定；builtin hash() 不可当证据）"
          % drill_link["fingerprint"],
          "app.py 接线：st.plotly_chart(on_select=\"rerun\", key=\"trend_drill\") ＋ "
          "st.dataframe(on_select=\"rerun\", key=\"alarm_table\")，同一 core.drill_rows"]),
        ("定时/邮件/移动端（超优(A)·可复核）",
         ["定时时刻 %s：解析为每日 %02d:%02d，下次触发为真实 datetime——墙钟观测值只写 "
          "runtime/schedule_state.txt 与 output/timing.txt（以保证 output/ 其余文件逐字节可复现）"
          % (at, h_at, m_at),
          "计划任务行：%s" % cron,
          "systemd timer：%s" % timer.replace("\n", " | "),
          "launchd plist：%s" % ("StartCalendarInterval Hour=%d Minute=%d 已渲染"
                                 % (h_at, m_at) if launchd_ok else "渲染异常"),
          "计划任务产物已写 runtime/schedule/（crontab.txt/p33-daily-report.timer/"
          "com.p33.kpi-daily-report.plist/mailto.txt 共 4 件，output/ 之外）",
          "邮件正文链接：%s" % mailto[:120] + "…",
          "移动端适配：viewport=%s flex=%s media=%s 窄屏断点=%spx（config 上限 %dpx）"
          % (mobile["viewport"], mobile["responsive_cards"], mobile["media_query"],
             narrow, max_narrow),
          "钻取：%s" % "; ".join("%s 产量%d 良率%.2f%% 告警%d"
                              % (d["device_id"], d["output"], d["yield_pct"], d["alarms"])
                              for d in drill_out)]),
        ("运行自检", ["日报耗时 %s（预算 %.0fs）→ %s（工单 P3.2 时限）；判定行不含毫秒，"
                    "精确秒数见 output/timing.txt 与 runtime/timing.txt"
                    % (report.bucket(elapsed), cfg.report_seconds_max,
                       "达标" if elapsed < cfg.report_seconds_max else "超时"),
                    "KPI 项数 %d ≥ 7 → %s（工单优秀(B) 佐证，判定见「分层达标」）"
                    % (len(kpis), "达标" if len(kpis) >= 7 else "未达标"),
                    "必做 5 KPI 全部有值：%s" % all(km[n]["value"] is not None
                                                  for n in cfg.kpi_required),
                    "时间戳开关：%s（off 时 output/ 逐字节可复现；timing.txt 除外）"
                    % ("on" if stamp else "off")]),
    ]
    report.save(sections, os.path.join(out_dir, "report.txt"), stamp=stamp)
    return sections, result


def _todo_lines(result, cfg):
    return ["TODO-0 数据源 clean.csv 优先｜本次实际：%s（模式 %s）"
            % (result["source"], result["source_mode"]),
            "TODO-1 侧栏日期范围+设备多选 → app.py 与本 CLI 同用 core.filter_records()",
            "TODO-2 四个 KPI 指标卡 → %s" % " / ".join(result["required_kpis"][:4]),
            "TODO-3 产量趋势 px.line + st.plotly_chart(on_select=\"rerun\") → 点击折线点联动明细",
            "TODO-4 良率仪表 + 设备红绿灯 + 告警表（告警 %d 条，表支持行选择联动钻取）"
            % result["alarms_total"],
            "TODO-5 效率对标 st.progress（%.1f%%）" % (result["efficiency"]["raw"] * 100),
            "P3.2 四段式日报 → %s（%s）" % (result["artifacts"]["html"],
                                          result["artifacts"]["renderer"])]


def _tier_lines(result, cfg):
    """分层达标：逐条对齐**工单任务书 P3 验收标准**（不是 notebook 教师版字母表）：

      及格(D) 5 KPI可用+时间筛选；日报四部分完整+PDF正确
      良好(C) 联动筛选流畅；日报生成<2分钟
      优秀(B) ≥7指标+钻取交互；异常自动识别；美观度≥4/5
      超优(A) 优秀+定时自动生成(mailto/计划任务)+移动端适配
    四行原文由 WO_ROW 单点持有、逐字进报告行首（线值/预算不写进原文，只在箭头后的
    证据段回显，tests/test_workorder_rows.py 直接读课程仓工单文件回归锁定）。
    每条都带可复核实测数字；跟做示例降级为末行"保底自检"，不再借用工单字母。"""
    t = result["tiers"]
    fp = result["filter_probe"]
    dl = result["drill_link"]
    pc = result["pdf_check"]
    sc = result["schedule_check"]
    mc = result["mobile_check"]
    dev = fp.get("device") or {}
    ok = lambda b: "达标" if b else "未达标"  # noqa: E731
    return [
        "%s %s → 必做 KPI %d/%d 全有值；"
        "时间筛选：同一 core.filter_records 缩到单日 %s 命中 %d 行（全量 %d）；"
        "四段 %s 全部见于 %s；PDF %s %s → %s"
        % (WO_LABEL["D"], WO_ROW["D"],
           len(cfg.kpi_required), len(cfg.kpi_required), fp["date"], fp["rows"],
           fp["rows_all"], " / ".join(result["report_sections"]),
           result["artifacts"]["html"], pc["file"], pc["note"], ok(t["D"])),
        "%s %s → 联动程序化验证（同一 core.filter_records）："
        "单日命中 %d/%d 行；仅选 %s 命中 %d 行、总产量 %d＜全量 %d（筛选真的驱动重算）；"
        "app.py on_select=\"rerun\" 接线 %d 处 → core.drill_rows 联动明细 %d 行（回路非空）；"
        "AppTest 无头真执行 app.py 并断言切换单日后命中变小（tests/test_dashboard.py，"
        "非肉眼验收）；日报耗时档位 %s（预算 %.0fs，判定行不含毫秒，精确秒数在 "
        "timing.txt/runtime/）→ %s"
        % (WO_LABEL["C"], WO_ROW["C"],
           fp["rows"], fp["rows_all"], dev.get("device", "-"), dev.get("rows", 0),
           dev.get("output", 0), dev.get("output_all", 0),
           result["linkage"]["on_select_rerun"], dl["rows_detail"],
           result["timing"]["elapsed_bucket"], cfg.report_seconds_max, ok(t["C"])),
        "%s %s → 指标实得 %d 个；"
        "钻取：复放选择事件 x=%s → 联动明细 %d 行（上限 %d）指纹 crc32=%s（跨 PYTHONHASHSEED 稳定）；"
        "异常自动识别命中 %d 条（temp>%.1f 或 vib>%.1f，逐条附处置建议）；%s → %s"
        % (WO_LABEL["B"], WO_ROW["B"],
           len(result["kpis"]), dl["buckets"], dl["rows_detail"], dl["cap"],
           dl["fingerprint"], result["anomalies_total"], cfg.temp_max, cfg.vib_max,
           report.rubric_text(result["ui_rubric"]), ok(t["B"])),
        "%s %s → 继承优秀(B)：%s；"
        "定时：schedule.at=%s 解析为每日 %02d:%02d，下次触发为真实 datetime 且晚于此刻"
        "（墙钟值写 runtime/schedule_state.txt 与 output/timing.txt，不进判定行）；"
        "计划任务 4 件产物已渲染（crontab/systemd/launchd/mailto，写 runtime/schedule/）；"
        "mailto 收件人 %s 且 subject/body 齐；移动端：viewport=%s flex=%s media=%s "
        "窄屏断点 %spx（config 上限 %dpx）→ %s"
        % (WO_LABEL["A"], WO_ROW["A"],
           ok(t["B"]), sc["at"], sc["hour"], sc["minute"],
           str(cfg.require("schedule.mailto")) or "（空）",
           mc["viewport"], mc["responsive_cards"], mc["media_query"],
           mc["narrow_px"], mc["max_narrow_px"], ok(t["A"])),
        "保底自检（不计入工单档位）：跟做示例跑通任务1、程序出结果 → 四段式日报段数 %d、"
        "KPI %d 项、窗口 %d 行、产物落盘 %d/5（daily_report.html+daily_report.pdf+"
        "kpi.json+appendix.csv+trend_chart.png；result.json/report.txt 由本流水线随后写出）→ %s"
        % (len(result["report_sections"]), len(result["kpis"]),
           result["window"]["rows_window"], len(result["artifacts_written"]),
           "通过" if (len(result["report_sections"]) >= 4
                      and result["window"]["rows_window"] > 0
                      and len(result["artifacts_written"]) == 5) else "未通过"),
    ]
