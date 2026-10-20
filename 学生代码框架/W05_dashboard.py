# -*- coding: utf-8 -*-
# [教学脚手架] 下列导入/变量供 TODO 完成后使用，故标注 noqa 而非删除
"""P3 产线KPI仪表盘+自动日报 —— 框架(Streamlit)
运行: streamlit run W05_dashboard.py
数据: 自动生成模拟产线数据(或替换为P2.1的clean.csv)
"""
import datetime

import numpy as np
import pandas as pd
import plotly.express as px  # noqa: F401
import streamlit as st

rng = np.random.RandomState(2026)


@st.cache_data
def load_data():
    """TODO-0(可选): 改为 pd.read_csv('clean.csv') 使用P2.1产出"""
    n = 2000
    ts = pd.date_range("2026-04-01", periods=n, freq="30min")
    output = rng.poisson(50, n)
    df = pd.DataFrame({
        "ts": ts,
        "device_id": rng.choice(["DEV-01", "DEV-02", "DEV-03", "DEV-04"], n),
        "output": output,
    })
    df["ok_qty"] = (df.output * rng.uniform(0.88, 0.99, n)).astype(int)
    df["yield"] = df.ok_qty / df.output
    df["temp"] = rng.uniform(45, 95, n)
    df["vib"] = rng.uniform(1, 6, n)
    return df


def main():
    st.set_page_config("产线驾驶舱", "📊", layout="wide")
    st.title("🏭 产线KPI实时仪表盘")

    df = load_data()
    # TODO-1 侧栏筛选: 日期范围(date_input) + 设备多选(multiselect)
    # df = df[...]

    c1, c2, c3, c4 = st.columns(4)
    # TODO-2 四个KPI指标卡:
    c1.metric("总产量", f"{int(df.output.sum()):,}")
    # c2: 平均良率 %; c3: 设备在线数(x/4); c4: 今日告警数(振动>4.5)

    # TODO-3 产量趋势: px.line(df, x='ts', y='output') → st.plotly_chart
    # TODO-4 良率仪表/设备状态红绿灯(st.success/warning/error)/告警表格(st.dataframe)
    # TODO-5 效率对标: 进度条 st.progress(实际/目标)


def build_report():
    """P3.2 每日日报(四段式: 概览/分析/异常/附表) — python W05_dashboard.py --report 触发"""
    df = load_data()
    html = f"""<html><body style="font-family:sans-serif">
    <h1>每日生产分析报告 {datetime.date.today()}</h1>
    <h2>1. 生产概览</h2><p>总产量 {int(df.output.sum())}, 平均良率 {df["yield"].mean():.1%}</p>
    <h2>2. 详细分析</h2><!-- TODO: 班次/设备对比表 -->
    <h2>3. 异常识别</h2><!-- TODO: 自动列出 temp>90 或 vib>4.5 记录+建议 -->
    <h2>4. 数据附表</h2><!-- TODO: df.tail(50).to_html() -->
    </body></html>"""
    with open("daily_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("日报已生成 daily_report.html (TODO: reportlab转PDF, 复用02包字体方案)")


if __name__ == "__main__":
    import sys
    if "--report" in sys.argv:
        build_report()
    else:
        main()
