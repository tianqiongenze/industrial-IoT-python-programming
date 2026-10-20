# -*- coding: utf-8 -*-
"""P2.1 Pandas数据清洗管道 —— 框架(内置脏数据生成+质量评分)
运行: python W03_pipeline.py --peek   # 预览数据
     python W03_pipeline.py           # 执行管道并评分
"""
import random
import sys

random.seed(2026)


def make_raw(path="W03_raw.csv", n=1200):
    """生成脏数据(勿改): 缺失/类型错/越界/重复/时间戳混乱"""
    import csv
    import datetime
    fmts = ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y%m%d%H%M%S"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["device_id", "ts", "temp", "press", "status"])
        for i in range(n):
            t = round(random.uniform(45, 85), 2)
            if i % 37 == 0:
                t = ""
            if i % 53 == 0:
                t = "N/A"
            if i % 89 == 0:
                t = round(random.uniform(125, 150), 1)
            ts = (datetime.datetime(2026, 3, 1) +
                  datetime.timedelta(minutes=i * 30)).strftime(
                fmts[i % 3 == 0 and 0 or (1 if i % 7 == 0 else 2)])
            row = [f"DEV-{i % 4 + 1:02d}", ts, t,
                   round(random.uniform(.3, .6), 2), "RUN"]
            w.writerow(row)
            if i % 211 == 5:                   # 重复行
                w.writerow(row)
    return path


def pipeline(path):
    import pandas as pd
    df = pd.read_csv(path)
    log = []

    # ---- 步骤1 检查 ----
    log.append(f"加载 {len(df)} 行, 缺失统计: {df.temp.isna().sum()}")

    # TODO-2 缺失处理(决策: dropna/fillna/interpolate——写矩阵后选定)

    # TODO-3 类型转换: temp→float(错误值→NaN); ts→datetime(三种格式统一!)

    # 提示: pd.to_datetime(series, format=..., errors='coerce') 分格式转换后 combine_first
    # TODO-4 异常检测: IQR法 与 业务阈值(>120) 的AND结果(决策记录理由)

    # TODO-5 去重: subset=['device_id','ts']

    # TODO-6 验证: temp范围[20,120], press[0.1,1.0]

    # TODO-7 输出: clean.csv + 处理日志

    return df, log


def score(df):
    """质量评分(勿改): 完整性40+准确性30+一致性20+时间性10"""
    import pandas as pd
    s = 0
    s += 40 * (1 - df.isna().mean().mean())
    t = pd.to_numeric(df.temp, errors="coerce")
    s += 30 * ((t.between(20, 120)).mean())
    s += 20 * (df.device_id.str.match(r"DEV-\d{2}").mean())
    s += 10 if "ts" in df and pd.api.types.is_datetime64_any_dtype(df.ts) else 0
    return round(s, 1)


if __name__ == "__main__":
    path = make_raw() if "--peek" not in sys.argv else make_raw()
    if "--peek" in sys.argv:
        import pandas as pd
        print(pd.read_csv(path).head(10))
        print("temp异常值预览:\n", pd.read_csv(path).query("temp in ['','N/A']").head())
    else:
        df, log = pipeline(path)
        print("\n".join(log))
        print("质量评分:", score(df), "(及格线85, 优秀90)")
