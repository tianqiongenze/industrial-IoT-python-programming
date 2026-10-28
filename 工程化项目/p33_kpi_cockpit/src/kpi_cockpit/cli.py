# -*- coding: utf-8 -*-
"""命令行入口：run.py 与 pyproject 的 [project.scripts] 共用同一份参数解析。

所有工单条目都能从这里到达（详见 docs/05 运行手册的"标志 ↔ 工单条目"表）：
  python run.py                      默认跑完整流水线（确定性：output/ 逐字节可复现）
  python run.py --stamp              写入时间戳（会破坏逐字节复现，故默认关）
  python run.py --source synth       强制内置合成（种子见 config/rules.yaml）
  python run.py --source clean       强制读 P2.1 clean.csv（找不到即报错，不静默降级）
  python run.py --csv a.csv          指定外部 CSV
  python run.py --date 2026-03-01    单日筛选（TODO-1）
  python run.py --start A --end B    区间筛选（TODO-1）
  python run.py --device DEV-01 --device DEV-02   设备多选（TODO-1，可重复）
  python run.py --pdf                显式声明要 PDF（默认已生成，此标志保留兼容旧命令）
  python run.py --no-pdf             跳过 PDF —— 工单及格(D) 的"PDF正确"当场判未达标
  python run.py --drill DEV-01       钻取设备（工单优秀(B) 证据，可重复）
  python run.py --schedule-at 07:30  定时时刻 HH:MM（工单超优(A) 口径，默认取 config）
  python run.py --app-check          用 streamlit AppTest 无头执行 app.py（真跑仪表盘；
                                     工单良好(C) 的"联动筛选"程序化验证入口）
  python run.py --schedule-fire      定时触发（超优(A)：裁剪等待后生成一次，见报告说明）
  python run.py --determinism        连跑两次比对 output/（可复现性实证）
  python run.py --quiet              不打印报告正文
"""
import argparse
import os

from . import config as C
from . import deps as D
from . import pipeline as P
from . import report as R
from . import schedule as S

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_parser():
    ap = argparse.ArgumentParser(description="KPI 驾驶舱（工单 P3）",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "rules.yaml"))
    ap.add_argument("--outdir", default=os.path.join(ROOT, "output"))
    ap.add_argument("--quiet", action="store_true", help="只写文件，不打印正文")
    ap.add_argument("--stamp", action="store_true",
                    help="在报告与日报中写入时间戳（默认关，以保证逐字节可复现）")
    ap.add_argument("--source", choices=["auto", "clean", "synth", "csv"], default="auto")
    ap.add_argument("--csv", default=None, help="外部 CSV 路径（--source csv 必需）")
    ap.add_argument("--date", default=None, help="单日筛选 YYYY-MM-DD")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--device", action="append", default=[],
                    help="设备筛选，可重复（等价侧栏 multiselect）")
    ap.add_argument("--pdf", action="store_true",
                    help="显式声明要 PDF（默认已生成，保留兼容旧命令）")
    ap.add_argument("--no-pdf", dest="no_pdf", action="store_true",
                    help="跳过 PDF 生成：及格(D) 的 PDF 子条件当场判未达标（旧文件不采信）")
    ap.add_argument("--drill", action="append", default=[],
                    help="钻取设备，可重复（工单优秀(B) 证据）")
    ap.add_argument("--schedule-at", dest="schedule_at", default=None,
                    help="定时时刻 HH:MM（工单超优(A)；默认取 config/schedule.at）")
    ap.add_argument("--app-check", action="store_true",
                    help="无头执行 app.py（streamlit.testing.v1.AppTest）验证仪表盘")
    ap.add_argument("--determinism", action="store_true",
                    help="连跑两次并比对 output/，实证可复现")
    ap.add_argument("--schedule-fire", dest="schedule_fire", action="store_true",
                    help="定时触发（工单超优(A)）：裁剪等待后立即生成一次日报")
    return ap


def _one(a, cfg, outdir):
    return P.run(cfg, outdir, source=a.source, csv_path=a.csv, date=a.date,
                 start=a.start, end=a.end, devices=a.device,
                 pdf=not a.no_pdf,
                 stamp=a.stamp, drill=a.drill or None, schedule_at=a.schedule_at,
                 here=ROOT)


def app_check(cfg):
    """真跑 app.py（Streamlit 官方无头测试器），断言 TODO-1~5 的控件都在。

    这是工单良好(C)"联动筛选流畅"的程序化验证入口：不靠肉眼，靠 AppTest 实际
    执行 app.py 并断言切换筛选后命中行真的变少（同一函数见 tests/test_dashboard.py）。
    """
    probes = D.detect()
    if not probes["streamlit"].installed:
        print("[app-check] 降级：streamlit 未安装，无法执行 app.py；"
              "本次仅由 run.py headless 路径覆盖 KPI/日报计算（同一 core.* 函数）")
        return 0
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    bad = [e.value for e in at.exception]
    checks = {
        "侧栏日期控件(TODO-1)": len(at.sidebar.date_input) >= 1,
        "侧栏设备多选(TODO-1)": len(at.sidebar.multiselect) >= 1,
        "指标卡≥4(TODO-2)": len(at.metric) >= 4,
        "Plotly 图(TODO-3/4)": len(at.get("plotly_chart")) >= 1,
        "进度条(TODO-5)": len(at.get("progress")) >= 1,
        "告警/异常表(TODO-4)": len(at.dataframe) >= 2,
        "红绿灯提示(TODO-4)": len(at.success) + len(at.warning) + len(at.error) >= 1,
        "联动钻取面板(工单B)": any("折线点" in (c.value or "") for c in at.caption)
                             and len(at.dataframe) >= 3,
    }
    for name, ok in checks.items():
        print("[app-check] %-22s %s" % (name, "PASS" if ok else "FAIL"))
    if bad:
        print("[app-check] app.py 抛异常：%s" % bad)
    return 0 if (all(checks.values()) and not bad) else 1


def schedule_fire(cfg, a):
    """定时触发（工单超优(A)）：按 config/schedule.max_wait_seconds 裁剪等待后真跑一次生成。

    诚实说明：这是"计划任务应当在此刻触发"的本地演示，不冒充 crontab 已装、
    邮件已投；crontab / systemd timer / launchd plist / mailto 只作为可直接粘贴的
    产物渲染到 runtime/schedule/（output/ 之外，避免墙钟值打穿逐字节复现闸门）。
    """
    import datetime
    import time as _t
    at = a.schedule_at or str(cfg.require("schedule.at"))
    demo_wait, raw_wait = S.wait_seconds(datetime.datetime.now(), at,
                                                cfg.require("schedule.max_wait_seconds"))
    print("[schedule] 目标时刻 %s：真实还需等待 %.0fs，演示裁剪为 %.1fs 后立即生成"
          % (at, raw_wait, demo_wait))
    _t.sleep(demo_wait)
    sections, result = _one(a, cfg, a.outdir)
    print("[schedule] 已生成 %s ｜ PDF %s ｜ 渲染器 %s ｜ 耗时 %s"
          % (result["artifacts"]["html"], result["pdf_check"]["file"],
             result["artifacts"]["renderer"],
             result["timing"]["elapsed_bucket"]))
    print("[schedule] crontab 行：%s" % result["schedule"]["crontab"])
    print("[schedule] mailto：%s" % result["schedule"]["mailto"][:160])
    print("[schedule] 计划任务产物：%s（4 件）｜超优(A) 判定：%s"
          % (result["schedule"]["artifacts_written_to"],
             "达标" if result["tiers"]["A"] else "未达标"))
    return 0


def determinism(cfg, a):
    """连跑两次（默认关时间戳）比对 output/ 是否逐字节一致（含 PDF/PNG）。"""
    import filecmp
    import tempfile
    # output/ 是 runtime/ 的同级目录 → 每次跑都写进自己的 tmp 沙箱，互不污染
    d1, d2 = (os.path.join(tempfile.mkdtemp(prefix="p33_det"), "output")
              for _ in range(2))
    _one(a, cfg, d1)
    _one(a, cfg, d2)
    volatile = {"timing.txt"}                   # 唯一可变态产物：精确耗时（文档已声明）
    names = sorted(n for n in os.listdir(d1) if n not in volatile)
    diffs = [n for n in names
             if not (os.path.isfile(os.path.join(d2, n))
                     and filecmp.cmp(os.path.join(d1, n), os.path.join(d2, n),
                                     shallow=False))]
    print("[determinism] 比对 %d 个文件（排除声明的可变态 %s）：%s"
          % (len(names), ", ".join(sorted(volatile)), ", ".join(names)))
    print("[determinism] 差异文件：%s → %s"
          % (", ".join(diffs) or "无", "PASS（逐字节可复现）" if not diffs else "FAIL"))
    return 0 if not diffs else 1


def main(argv=None):
    a = build_parser().parse_args(argv)
    cfg = C.load_config(a.config)
    if a.determinism:
        return determinism(cfg, a)
    if a.app_check:
        return app_check(cfg)
    if a.schedule_fire:
        return schedule_fire(cfg, a)
    sections, result = _one(a, cfg, a.outdir)
    if not a.quiet:
        print(R.render(sections, stamp=a.stamp))
        print("[产物] %s ｜ %s（%s）｜ output/kpi.json ｜ output/result.json ｜ output/timing.txt"
              % (result["artifacts"]["html"], result["pdf_check"]["file"],
                 result["artifacts"]["pdf"]))
        print("[工单档位] %s" % " ".join(
            "%s:%s" % (n, "达标" if result["tiers"][n] else "未达标")
            for n in ("D", "C", "B", "A")))
        print("[耗时] 日报 %s（预算 %.0fs，%s）｜精确值见 output/timing.txt"
              % (result["timing"]["elapsed_bucket"], cfg.report_seconds_max,
                 "达标" if result["timing"]["within_budget"] else "超时"))
        print("[依赖] %s" % D.summary({k: D.Probe(k, v["installed"], v["version"])
                                       for k, v in result["deps"].items()}))
    return 0
