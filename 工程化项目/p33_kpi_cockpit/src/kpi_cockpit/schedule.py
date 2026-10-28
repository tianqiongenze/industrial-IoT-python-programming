# -*- coding: utf-8 -*-
"""超优(A) 层：定时自动生成（计划任务口径）+ 邮件正文（mailto）+ 移动端适配实测。

诚实性说明：本模块计算"何时该跑、跑完发给谁、系统里怎么挂计划任务"，
不冒充已经安装 crontab / 已发送邮件 —— 是否真投递由运行环境决定，报告如实标注。
计划任务三选一（crontab / systemd timer / launchd plist），launchd 面向 macOS 学员。
"""
import re
from datetime import datetime, timedelta


def parse_at(text):
    """'HH:MM' → (时, 分)；非法格式抛 ValueError。"""
    hh, mm = str(text).split(":")
    h, m = int(hh), int(mm)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("schedule.at 需为合法 HH:MM（当前 %s）" % text)
    return h, m


def next_fire(now, at):
    """下一个 HH:MM 时刻（今天未到则今天，已过则明天）。返回 (datetime, 等待秒数)。"""
    h, m = parse_at(at)
    cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if cand <= now:
        cand += timedelta(days=1)
    return cand, max(0.0, (cand - now).total_seconds())


def wait_seconds(now, at, max_wait):
    """演示模式等待秒数：到点等待被裁剪为不超过 max_wait（离线可验证，不真等一天）。"""
    _, secs = next_fire(now, at)
    return min(secs, float(max_wait)), secs


def mailto(to, date, title, kpi_lines):
    """mailto 链接（超优(A) "mailto"提交物）：正文用 KPI 摘要，换行编码为 %0A。"""
    subject = "%s %s" % (title, date)
    # 顺序要紧：% 必须最先编码，否则后面生成的 %20/%0A 会被二次转义成 %2520（审计口径）
    pairs = [("%", "%25"), (" ", "%20"), ("\n", "%0A"), ("@", "%40"),
             ("&", "%26"), ("=", "%3D"), ("?", "%3F"), ("#", "%23")]

    def enc(s):
        for k, v in pairs:
            s = s.replace(k, v)
        return s
    body = enc("\n".join(kpi_lines))
    return "mailto:%s?subject=%s&body=%s" % (enc(str(to)), enc(subject), body)


def mailto_ok(link, to):
    """超优(A) mailto 闸门：非空收件人（含@）+ 合法前缀 + subject/body 参数齐备。"""
    to = str(to or "")
    return bool(link.startswith("mailto:") and "@" in to
                and "?subject=" in link and "&body=" in link)


def crontab_line(cfg, entry, at=None):
    """可粘贴进 crontab 的一行计划任务（工程化：命令与配置显式带全）。

    at=None → 用 config 的 schedule.at；调用方若用 --schedule-at 覆盖了时刻，
    必须把覆盖值传进来，否则会出现"报告里 at=06:15 但 crontab 写 30 7"的自相矛盾。
    行内同时写 --schedule-at，保证触发起生成的那一次与计划时刻口径一致。
    """
    text = at or cfg.require("schedule.at")
    h, m = parse_at(text)
    return "%d %d * * * cd %s && %s run.py --schedule-fire --schedule-at %s " \
           "--config %s >> output/schedule.log 2>&1" % (
        m, h, entry["project_dir"], entry["python"], text, entry["config"])


def systemd_timer(entry, at):
    """systemd timer 单元（与 crontab 二选一的计划任务写法）。

    OnCalendar 用 systemd 合法语法 `*-*-* HH:MM:00`；Persistent=true 保证
    关机错过的班次在下次开机补跑一次（日报场景常见需求）。
    """
    h, m = parse_at(at)
    return ("[Unit]\nDescription=%s 自动日报（P3 超优(A) 层）\n\n"
            "[Timer]\nOnCalendar=*-*-* %02d:%02d:00\nPersistent=true\n\n"
            "[Install]\nWantedBy=timers.target"
            % (entry.get("project", "p33_kpi_cockpit"), h, m))


def launchd_plist(entry, at, label="com.p33.kpi-daily-report"):
    """launchd 日历作业 plist（macOS 计划任务产物，crontab/systemd 的第三种写法）。

    与 crontab_line/systemd_timer 同一诚实口径：这是"可直接装"的渲染产物，
    不代表已 launchctl load。StartCalendarInterval 的 Hour/Minute 由 schedule.at
    解析得到——at 非法时 parse_at 当场抛错，渲染不出"看着对但挂不上"的半成品。
    """
    h, m = parse_at(at)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            '  <key>Label</key><string>%s</string>\n'
            '  <key>WorkingDirectory</key><string>%s</string>\n'
            '  <key>ProgramArguments</key><array>\n'
            '    <string>%s</string>\n'
            '    <string>run.py</string>\n'
            '    <string>--schedule-fire</string>\n'
            '    <string>--schedule-at</string>\n'
            '    <string>%02d:%02d</string>\n'
            '    <string>--quiet</string>\n'
            '  </array>\n'
            '  <key>StartCalendarInterval</key><dict>\n'
            '    <key>Hour</key><integer>%d</integer>\n'
            '    <key>Minute</key><integer>%d</integer>\n'
            '  </dict>\n'
            '  <key>StandardOutPath</key><string>runtime/launchd.log</string>\n'
            '  <key>StandardErrorPath</key><string>runtime/launchd.log</string>\n'
            '</dict>\n</plist>\n'
            % (label, entry["project_dir"], entry["python"], h, m, h, m))


def mobile_note(html_text):
    """超优(A) 移动端适配检查：是否声明 viewport + 是否用 flex 卡片（返回逐条判定）。"""
    return {
        "viewport": "viewport" in html_text and "width=device-width" in html_text,
        "responsive_cards": "flex-wrap" in html_text,
        "media_query": "@media" in html_text,
    }


def narrow_width_px(html_text):
    """从生成 HTML 提取窄屏断点：`@media … (max-width:NNNpx)` → int；没有 → None。

    超优(A) "移动端适配"闸门消费它：断点存在且不大于 config
    report.mobile.max_narrow_px 才算数（拿版式属性判定，不拿口号判定）。
    """
    m = re.search(r"@media[^{]*\(\s*max-width:\s*(\d+)px", html_text)
    return int(m.group(1)) if m else None
