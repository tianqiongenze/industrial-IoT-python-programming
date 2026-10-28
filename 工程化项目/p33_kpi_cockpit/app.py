# -*- coding: utf-8 -*-
"""P3.1 产线 KPI 仪表盘 —— 真正的 Streamlit 应用（工单 TODO-0~TODO-5 全在此实现）。

运行：
    conda activate pp03
    streamlit run app.py
离线无头验证（不启浏览器也能证明本文件真的能跑）：
    python -m pytest tests/test_dashboard.py -q     # 用 streamlit.testing.v1.AppTest
计算逻辑一律走 `kpi_cockpit.core`，与 run.py 的 headless 报告同源（工程化要求 1）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))           # src 布局：未 pip install 也可跑

import pandas as pd                     # noqa: E402
import plotly.express as px             # noqa: E402
import plotly.graph_objects as go       # noqa: E402
import streamlit as st                  # noqa: E402

from kpi_cockpit import config as C     # noqa: E402
from kpi_cockpit import core, data_source, deps, pipeline  # noqa: E402

CFG = C.load_config(os.path.join(HERE, "config", "rules.yaml"))
PROBES = deps.detect()


# ---------------------------------------------------------------- TODO-0 装载
@st.cache_data(ttl=CFG.cache_ttl, show_spinner="读取数据源…")
def load_data(source, csv_path):
    """@st.cache_data + ttl（工程化要求 2：缓存加 TTL 保数据新鲜）。

    返回 (DataFrame, 来源说明, 列级出处)，来源说明直接来自 data_source（不谎报）。
    """
    ds = pipeline.build_rows(CFG, source=source, csv_path=csv_path, here=HERE)
    return ds.as_df(), ds.source, ds.provenance, ds.mode


# -------------------------------------------------------------------- 页面
st.set_page_config("产线驾驶舱", "📊", layout="wide")
st.title("🏭 产线KPI实时仪表盘")

_source_sel = st.sidebar.selectbox("数据源（TODO-0）", ["auto", "clean", "synth", "csv"],
                                   index=0,
                                   help="auto：优先读 P2.1 的 clean.csv，缺失才按 seed 合成")
_csv_path = (st.sidebar.text_input("clean.csv 路径（仅 source=csv）", "")
             if _source_sel == "csv" else None)
try:
    df, SRC, PROV, MODE = load_data(_source_sel, _csv_path or None)
except (ValueError, FileNotFoundError) as exc:          # 配置/数据不合法 → 显式告知
    st.error("数据源不可用：%s" % exc)
    st.stop()
st.caption("数据源：%s ｜ 列级出处：%s ｜ streamlit=%s plotly=%s"
           % (SRC, ", ".join("%s→%s" % kv for kv in sorted(PROV.items())),
              PROBES["streamlit"].version, PROBES["plotly"].version))

# -------------------------------------------------- TODO-1 侧栏：日期范围 + 设备多选
_dmin, _dmax = df["ts"].min().date(), df["ts"].max().date()
_mode = st.sidebar.radio("筛选方式", ["日期范围", "单日"], index=0)
_date = st.sidebar.date_input("报告日期（单日）", _dmax, min_value=_dmin, max_value=_dmax,
                              disabled=_mode != "单日")
_rng = st.sidebar.date_input("日期范围", (_dmin, _dmax), min_value=_dmin, max_value=_dmax,
                             disabled=_mode != "日期范围")
_devs_all = sorted(df["device_id"].unique())
_devs = st.sidebar.multiselect("设备多选", _devs_all, default=_devs_all)
_lines = st.sidebar.multiselect("产线多选", sorted(df["line"].unique()),
                                default=sorted(df["line"].unique()))
if not _devs:
    st.warning("未选设备：已回退到全部设备（避免空仪表盘）")
    _devs = _devs_all

_start, _end = (_dmin, _dmax)
if _mode == "单日":
    _start = _end = _date
elif isinstance(_rng, tuple) and len(_rng) == 2:
    _start, _end = _rng
# 交互口径：与 run.py --start/--end/--date/--device 走同一个 core.filter_records（一份逻辑两处用）
_rows = core.filter_records(df.to_dict("records"), start=_start, end=_end, devices=_devs)
if _lines:
    _rows = [r for r in _rows if r["line"] in _lines]
if not _rows:
    st.error("筛选后 0 行，请放宽日期或设备条件")
    st.stop()
_view = pd.DataFrame(_rows)
st.caption("筛选口径：%s ｜ 设备 %d/%d 台 ｜ 命中 %d 行"
           % (("单日 %s" % _date) if _date else "区间 %s~%s" % (_start, _end),
              len(_devs), len(_devs_all), len(_view)))

# ------------------------------------------------------------ TODO-2 四个指标卡
RULES = CFG.rules()
RULES["days"] = int(_view["ts"].dt.normalize().nunique())      # 效率对标折算窗口
KPIS = core.compute_kpis(_rows, RULES, lines=CFG.items)
KM = core.kpi_map(KPIS)
c1, c2, c3, c4 = st.columns(4)
c1.metric("总产量", KM["总产量"]["text"], KM["总产量"]["delta"] or None)
c2.metric("平均良率", KM["平均良率"]["text"], KM["平均良率"]["delta"] or None)
c3.metric("设备在线数", KM["设备在线数"]["text"], KM["设备在线数"]["delta"] or None,
          delta_color="inverse" if KM["设备在线数"]["tone"] == "error" else "normal")
# 告警是"越高越坏"，delta 用 inverse 让上升显示为红（工单避坑：delta 正负好坏别想当然）
c4.metric("今日告警数", KM["今日告警数"]["text"], KM["今日告警数"]["delta"] or None,
          delta_color="inverse")

# 工单"≥7 指标"（B 层佐证）：required 5 + extra 4 的补充指标行
_extra = KPIS[5:] if len(KPIS) > 5 else []
if _extra:
    e_cols = st.columns(len(_extra))
    for col, k in zip(e_cols, _extra):
        col.metric(k["name"], k["text"], k["delta"] or None)

# ------------------------------------------------- TODO-3 产量趋势（px.line 交互图）
_tr = pd.DataFrame(core.trend(_rows, bucket="day" if _view["ts"].dt.date.nunique() > 1
                              else "hour"))
fig_line = px.line(_tr, x="ts", y="output", title="产量趋势", markers=True,
                   labels={"output": "产量", "ts": "时间"})
fig_line.update_layout(xaxis_type="category")   # 类目轴：选择事件回传的 x 就是桶名本身
_ev_tr = st.plotly_chart(fig_line, use_container_width=True,
                         on_select="rerun", key="trend_drill",
                         selection_mode="points")

# ------------------------------------------ TODO-4 良率仪表 / 红绿灯 / 告警表
_g = core.gauge(_rows, RULES)
fig_g = go.Figure(go.Indicator(
    mode="gauge+number+delta", value=_g["value"],
    number={"suffix": "%"}, delta={"reference": CFG.danger},
    title={"text": "平均良率"},
    gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2b6cb0"},
          "steps": [{"range": [0, CFG.warn], "color": "#fed7d7"},
                    {"range": [CFG.warn, CFG.danger], "color": "#fefcbf"},
                    {"range": [CFG.danger, 100], "color": "#c6f6d5"}]}))
gcol1, gcol2 = st.columns(2)
gcol1.plotly_chart(fig_g, use_container_width=True)

_st = core.device_status(_rows, RULES)
for d in _st:                                    # 设备状态红绿灯
    msg = "%s ｜ 产线 %s ｜ 采样 %d ｜ 振动超阈 %d ｜ 温度超阈 %d" % (
        d["device_id"], next((r["line"] for r in _rows if r["device_id"] == d["device_id"]), ""),
        d["n"], d["alarms"], d["over_temp"])
    {"ok": st.success, "warn": st.warning, "error": st.error}[d["tone"]](msg)

_alarm = pd.DataFrame(core.alarm_rows(_rows, CFG.vib_max))
st.subheader("今日告警明细（振动 > %.1f mm/s）" % CFG.vib_max)
_ev_al = st.dataframe(_alarm if not _alarm.empty else pd.DataFrame([{"提示": "本窗口无告警"}]),
                      use_container_width=True, hide_index=True,
                      on_select="rerun", key="alarm_table",
                      selection_mode="multi-row")

# ------------------------------------------------------------- TODO-5 效率对标
_clip, _raw = core.efficiency(_rows, CFG.target_output_per_day, RULES["days"])
st.progress(_clip, text="效率对标：%.1f%%（单日目标 %d × %d 天 = %d，实际 %d）"
           % (_raw * 100, CFG.target_output_per_day, RULES["days"],
              CFG.target_output_per_day * RULES["days"], core.total_output(_rows)))
if not PROBES["reportlab"].installed:
    st.info("reportlab 未安装：PDF 日报降级为仅 HTML（本次运行实况，非模板话术）")

# ------------------------------------------------- B/A 层：异常清单 + 联动钻取 + 日报
_an = pd.DataFrame(core.anomalies(_rows, RULES, int(CFG.topk)))
st.subheader("异常识别与处置建议（temp>%.1f 或 vib>%.1f）" % (CFG.temp_max, CFG.vib_max))
st.dataframe(_an if not _an.empty else pd.DataFrame([{"提示": "无超阈值记录"}]),
             use_container_width=True, hide_index=True)

with st.expander("A 层：点击趋势折线点 / 选中告警行 → 联动明细（on_select=rerun 真选择事件）",
                 expanded=True):
    # 选择事件 → 数据点清单：趋势图点自带 x（时间桶）；告警表行先换算成"该设备该日"点位。
    # 过滤逻辑一律走 core.drill_rows —— 与 run.py CLI 证据行同一函数，绝不写第二套。
    _pts = [dict(p) for p in ((_ev_tr.selection.get("points") or [])
                              if _ev_tr is not None else []) if isinstance(p, dict)]
    _al_rows = ((_ev_al.selection.get("rows") or []) if _ev_al is not None else [])
    for _i in _al_rows:
        if isinstance(_i, int) and not isinstance(_i, bool) and 0 <= _i < len(_alarm):
            _pts.append({"x": str(_alarm.iloc[_i]["ts"])[:10],
                         "device_id": str(_alarm.iloc[_i]["device_id"])})
    _det = core.drill_rows(_pts, _rows, RULES)
    if _pts and _det:
        st.caption("已选 %d 个点位 → 联动明细 %d 行（上限 drill.max_rows=%d｜指纹 crc32=%s）"
                   % (len(_pts), len(_det), RULES.get("drill_max_rows", 30),
                      core.drill_fingerprint(_det)))
        st.dataframe(pd.DataFrame(_det), use_container_width=True, hide_index=True)
    elif _pts:
        st.caption("已选 %d 个点位，但没有命中记录（桶越界或筛选窗口外）——core.drill_rows 已防御性忽略。"
                   % len(_pts))
    else:
        st.caption("尚无选择：点击上方趋势图的折线点、或在告警明细表选中一行，"
                   "本表会随选择事件（on_select=\"rerun\"）自动联动刷新；"
                   "离线等价复放见 `python run.py` 报告的「联动钻取证据」行。")
        st.dataframe(pd.DataFrame([{"提示": "等待图表选择事件（点击折线点/告警行）"}]),
                     use_container_width=True, hide_index=True)
    _d = st.selectbox("（对照）单设备汇总榜", _devs_all,
                      index=_devs_all.index(_devs[0]) if _devs[0] in _devs_all else 0)
    _dr = core.drill(df.to_dict("records"), _d, RULES, int(CFG.topk))
    st.json(_dr)
    st.plotly_chart(px.line(pd.DataFrame(_dr["top_anomalies"]), x="ts", y="vib",
                            title="%s 告警振动钻取" % _d), use_container_width=True)

with st.expander("一键生成四段式日报（HTML/PDF）"):
    if st.button("生成到 output/"):
        secs, res = pipeline.run(CFG, os.path.join(HERE, "output"),
                                 source=_source_sel, date=str(_date),
                                 devices=_devs, pdf=True, stamp=True)
        st.success("已生成 %s ｜ 渲染器 %s ｜ 耗时档位 %s（精确值见 output/timing.txt）"
                   % (res["artifacts"]["html"], res["artifacts"]["renderer"],
                      res["timing"]["elapsed_bucket"]))
        st.download_button("下载日报 HTML",
                           data=open(os.path.join(HERE, "output",
                                                   res["artifacts"]["html"]),
                                     encoding="utf-8").read(),
                           file_name=res["artifacts"]["html"], mime="text/html")
