# -*- coding: utf-8 -*-
"""超优(A) 档：定时 / 邮件正文（mailto）/ 计划任务产物 / 移动端适配检查。

诚实性红线（审计要求）：本模块只生成"可直接粘贴的计划任务行"，
不冒充 crontab 已安装、邮件已投递 —— 测试也按这个口径断言。
"""
import datetime

import pytest

from kpi_cockpit import schedule as S


NOW = datetime.datetime(2026, 3, 1, 6, 0, 0)


# ----------------------------------------------------------------------- parse_at
def test_parse_at_valid_and_strict():
    assert S.parse_at("07:30") == (7, 30)
    assert S.parse_at("7:5") == (7, 5)


@pytest.mark.parametrize("bad", ["25:00", "07:60", "-1:00", "abc", "07"])
def test_parse_at_rejects_garbage(bad):
    with pytest.raises((ValueError, IndexError)):
        S.parse_at(bad)


# ----------------------------------------------------------------------- next_fire
def test_next_fire_today_when_not_yet():
    nxt, wait = S.next_fire(NOW, "07:30")
    assert nxt == datetime.datetime(2026, 3, 1, 7, 30) and wait == 5400.0


def test_next_fire_rolls_to_tomorrow_when_passed():
    nxt, wait = S.next_fire(datetime.datetime(2026, 3, 1, 23, 0), "07:30")
    assert nxt == datetime.datetime(2026, 3, 2, 7, 30) and wait == 8.5 * 3600.0


def test_next_fire_at_exact_minute_is_not_today():
    """边界：now 正好等于触发时刻 → 排到明天（避免同一分钟重复生成）。"""
    nxt, _ = S.next_fire(datetime.datetime(2026, 3, 1, 7, 30), "07:30")
    assert nxt.date() == datetime.date(2026, 3, 2)


def test_next_fire_invalid_time_raises():
    with pytest.raises(ValueError):
        S.next_fire(NOW, "99:99")


# -------------------------------------------------------------------- wait_seconds
def test_wait_seconds_clips_to_demo_max():
    demo, raw = S.wait_seconds(NOW, "07:30", 5)
    assert raw == 5400.0 and demo == 5.0, "离线演示不许真等一天（审计：可验证）"


def test_wait_seconds_no_clip_when_close():
    demo, raw = S.wait_seconds(datetime.datetime(2026, 3, 1, 7, 29, 58), "07:30", 5)
    assert raw == 2.0 and demo == 2.0


def test_wait_seconds_accepts_string_max():
    demo, _ = S.wait_seconds(NOW, "07:30", "3")
    assert demo == 3.0


# ------------------------------------------------------------------------- mailto
def test_mailto_encodes_at_space_and_newline():
    link = S.mailto("lead@example.com", "2026-03-01", "每日生产分析报告",
                    ["总产量=2,411", "平均良率=93.40%"])
    assert link.startswith("mailto:lead%40example.com?subject=")
    assert "body=%E6%80%BB" not in link          # 不做 URL 百分号编码中文（保持可读）
    assert "%0A" in link                          # 换行编码为 %0A
    assert "%25" in link, "正文里的 % 必须先编码，否则 93.40% 会变成非法转义"


def test_mailto_never_double_encodes():
    """回归：'%' 必须最先编码，否则后续生成的 %20/%0A 会被二次转义成 %2520。"""
    link = S.mailto("a@b.c", "d", "标题 含%和空格", ["良率=95%"])
    assert "%2520" not in link and "%2525" not in link
    assert link.count("%25") == 2, "主题 1 个 % + 正文 1 个 %，各只编码一次"


def test_mailto_empty_body_is_valid_link():
    assert S.mailto("x@y.z", "d", "t", []).endswith("&body=")


# ------------------------------------------------------------ 计划任务产物（A 层）
class _Cfg:
    def require(self, dotted):
        return {"schedule.at": "07:30", "schedule.mailto": "lead@example.com"}[dotted]


def test_crontab_line_is_paste_ready():
    line = S.crontab_line(_Cfg(), {"project_dir": "/srv/p33", "python": "/py",
                                   "config": "/srv/p33/config/rules.yaml"})
    assert line.startswith("30 7 * * * ")
    assert "cd /srv/p33 && /py run.py --schedule-fire" in line
    assert line.endswith(">> output/schedule.log 2>&1")


def test_crontab_line_honours_overridden_time():
    """回归：--schedule-at 覆盖后，crontab 行必须跟着改（曾出现 30 7 与 06:15 自相矛盾）。"""
    line = S.crontab_line(_Cfg(), {"project_dir": "/srv/p33", "python": "/py",
                                   "config": "/c.yaml"}, at="06:15")
    assert line.startswith("15 6 * * * ") and "--schedule-at 06:15" in line


def test_systemd_timer_uses_valid_calendar_syntax():
    text = S.systemd_timer({"project": "p33_kpi_cockpit"}, "07:30")
    assert "OnCalendar=*-*-* 07:30:00" in text, "必须 systemd 合法语法"
    assert "Persistent=true" in text and "WantedBy=timers.target" in text


def test_systemd_timer_rejects_bad_time():
    with pytest.raises(ValueError):
        S.systemd_timer({"project": "p33"}, "07:70")


# ------------------------------------------- launchd plist（macOS 计划任务，超优(A) 产物）
def test_launchd_plist_is_wellformed_and_honours_at():
    import xml.etree.ElementTree as ET
    text = S.launchd_plist({"project_dir": "/srv/p33", "python": "/py"}, "07:30")
    plist = ET.fromstring(text)                    # XML 不合法 → 装不上，当场炸给测试看
    keys = [k.text for k in plist.find("dict").findall("key")]
    assert {"Label", "WorkingDirectory", "ProgramArguments",
            "StartCalendarInterval", "StandardOutPath"} <= set(keys)
    assert "<key>Hour</key><integer>7</integer>" in text
    assert "<key>Minute</key><integer>30</integer>" in text
    assert "<string>07:30</string>" in text and "--schedule-fire" in text


def test_launchd_plist_zero_pads_time_and_takes_custom_label():
    text = S.launchd_plist({"project_dir": "/s", "python": "/p"}, "7:5",
                           label="com.x.y")
    assert "<string>07:05</string>" in text, "ProgramArguments 里的 HH:MM 必须补零"
    assert "<key>Hour</key><integer>7</integer>" in text
    assert "<string>com.x.y</string>" in text


def test_launchd_plist_rejects_bad_time():
    with pytest.raises(ValueError):
        S.launchd_plist({"project_dir": "/s", "python": "/p"}, "25:00")


def test_launchd_plist_does_not_claim_to_be_installed():
    """诚实口径（审计）：只渲染可直接装载的产物，不得自称已 launchctl load。"""
    text = S.launchd_plist({"project_dir": "/s", "python": "/p"}, "07:30")
    assert "launchctl" not in text and "已安装" not in text


# ------------------------------------------------------------------ 移动端适配
def test_mobile_note_all_green_on_real_style_html():
    html = ('<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>.cards{display:flex;flex-wrap:wrap}@media(max-width:600px){}</style>')
    assert S.mobile_note(html) == {"viewport": True, "responsive_cards": True,
                                   "media_query": True}


def test_mobile_note_reports_missing_pieces():
    assert S.mobile_note("<html></html>") == {"viewport": False,
                                             "responsive_cards": False,
                                             "media_query": False}


def test_mobile_note_partial_html():
    n = S.mobile_note('<meta name="viewport" content="width=device-width">')
    assert n["viewport"] is True and n["media_query"] is False


def test_narrow_width_px_reads_the_real_breakpoint():
    """超优(A) 的"移动端适配"取数口：从 CSS 实测窄屏断点，不认 min-width、不认口号。"""
    assert S.narrow_width_px("@media (max-width:600px){body{margin:10px}}") == 600
    assert S.narrow_width_px("@media screen and (max-width: 768px){}") == 768
    assert S.narrow_width_px("@media (min-width:600px){}") is None
    assert S.narrow_width_px("没有任何媒体查询") is None


# ---------------------------------------------------------------- 收件人闸门检查
def test_mailto_ok_requires_recipient_and_both_params():
    """mailto_ok：收件人非空含 @ + subject/body 参数齐，缺一即 A 档闸门关。"""
    good = S.mailto("lead@example.com", "2026-03-01", "每日生产分析报告", ["总产量=1"])
    assert S.mailto_ok(good, "lead@example.com") is True
    assert S.mailto_ok(good, "") is False, "config 收件人清空 → 不得算达标"
    assert S.mailto_ok("mailto:lead@example.com", "lead@example.com") is False
    assert S.mailto_ok("https://x?subject=a&body=b", "a@b.c") is False
    assert S.mailto_ok("", "a@b.c") is False
