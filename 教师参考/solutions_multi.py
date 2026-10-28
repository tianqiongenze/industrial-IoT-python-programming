# -*- coding: utf-8 -*-
"""PP课程教师版·多解法参考（每题2-3解，全部可运行、结果互验）
运行: cd 03-Python程序设计-项目实战 && /usr/local/bin/python3.11 教师参考/solutions_multi.py
     （沙箱环境用 /opt/anaconda3/bin/python）→ 22 项全部 ✓ 才算数；退出码非 0 即有解法不一致。
教学用法: 课堂上先展示解A(直白)再展示解B/C(工程化/新语法)，
         让学生说"什么场景选哪个"——这就是六步法'决策'环节的素材。
P6服务两解(方案A http.server / 方案B Litestar+Granian)见 学生代码框架/W08_ml_service.py；
P7多模存储两解(Redis / diskcache)见 教师参考/p77_smart_ops/stores/kv.py。
"""
import math
import random
import sqlite3
import sys

RESULTS = []


def check(name, fn, expect):
    got = fn()
    ok = got == expect
    RESULTS.append((name, ok))
    print(("✓" if ok else "✗"), name, "→", got)


# ================= P1.1-EX1 温度转换 =================
def ex1_a(c):            # 解A：基础算术（第一周直白写法）
    f = c * 9 / 5 + 32
    k = c + 273.15
    return round(f, 2), round(k, 2)


def ex1_b(c):            # 解B：lambda查表（批量转换/可配置场景）
    conv = {"F": lambda x: round(x * 9 / 5 + 32, 2),
            "K": lambda x: round(x + 273.15, 2)}
    return conv["F"](c), conv["K"](c)


# ================= P1.1-EX2 一元二次 =================
def ex2_a(a, b, c):      # 解A：if-elif 分支
    d = b * b - 4 * a * c
    if d < 0:
        return None
    r = math.sqrt(d)
    x1, x2 = (-b + r) / (2 * a), (-b - r) / (2 * a)
    return (x1, x2) if x1 <= x2 else (x2, x1)


def ex2_b(a, b, c):      # 解B：match结构模式匹配(3.10+新语法)+复数域兜底
    d = b * b - 4 * a * c
    match d:
        case _ if d > 1e-12:
            r = math.sqrt(d)
            return tuple(sorted(((-b + r) / (2 * a), (-b - r) / (2 * a))))
        case _ if abs(d) <= 1e-12:
            return ((-b / (2 * a)), (-b / (2 * a)))
        case _:
            return None                  # 工程口径：负根返回None交上层决策


# ================= P1.1-EX5 安全读取 =================
def ex5_a(path):         # 解A：try-except 逐异常处理
    try:
        with open(path, encoding="utf8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def ex5_b(path):         # 解B：contextlib.suppress（吞掉指定异常的声明式写法）
    from contextlib import suppress
    with suppress(FileNotFoundError):
        with open(path, encoding="utf8") as f:
            return f.read().strip()
    return ""


# ================= P2.1 数据清洗：两解 =================
_RAW = [("PUMP-03", " 4.2 ", ""), ("FAN-02", "3.1", "99"), ("PUMP-03", "4.5", "8")]


def W03_a():             # 解A：pandas 链式（大数据/后续要聚合分析）
    import pandas as pd
    df = (pd.DataFrame(_RAW, columns=["dev", "vib", "temp"])
          .replace("", None).bfill().ffill())
    df["vib"] = df["vib"].astype(float)
    df["dev"] = df["dev"].str.strip()
    return df.groupby("dev")["vib"].mean().round(2).to_dict()


def W03_b():             # 解B：纯Python字典归并（无pandas环境/嵌入式网关）
    last = {}
    out = {}
    for dev, vib, temp in _RAW:
        dev = dev.strip()
        v = float(vib) if vib else last.get(dev)   # 空值取该设备上一条
        if v is None:
            continue
        last[dev] = v
        out.setdefault(dev, []).append(v)
    return {k: round(sum(v) / len(v), 2) for k, v in out.items()}


# ================= P2.2 特征提取：两解 =================
_X = [1.0, 2.0, 3.0, 4.0, 5.0]


def W04_a():             # 解A：NumPy向量化（P2.2主线：100ms内30维）
    import numpy as np
    x = np.array(_X)
    return [float(np.mean(x)), float(np.std(x)), float(np.ptp(x))]


def W04_b():             # 解B：statistics标准库（小样本/零依赖演示）
    import statistics as st
    return [round(st.mean(_X), 6), round(st.pstdev(_X), 6),
            round(max(_X) - min(_X), 6)]


# ================= P5 查询：三解（共用一个内存库） =================
def _mkdb():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE devices(code TEXT, line TEXT, vib REAL)")
    con.executemany("INSERT INTO devices VALUES (?,?,?)",
                    [("PUMP-03", "A2", 4.6), ("FAN-02", "B1", 3.1), ("PUMP-04", "A2", 4.4)])
    con.commit()
    return con


def p5_a():              # 解A：原生SQL（DBA视角/复杂报表）
    con = _mkdb()
    rows = con.execute(
        "SELECT line, ROUND(AVG(vib),2) FROM devices GROUP BY line ORDER BY 1").fetchall()
    con.close()
    return dict(rows)


def p5_b():              # 解B：SQLAlchemy ORM（类型安全/可迁移PostgreSQL）
    """同一句分组聚合，2.0 与 1.3 两代声明式口径都能跑（requirements.lock=2.0，老环境=1.3）。"""
    from sqlalchemy import create_engine, func

    try:                                            # ── SQLAlchemy 2.0 口径 ──
        from sqlalchemy import select
        from sqlalchemy.orm import (DeclarativeBase, Mapped,  # noqa: F401
                                    mapped_column, Session)

        class Base(DeclarativeBase):
            pass

        class Dev(Base):
            __tablename__ = "devices"
            code: Mapped[str] = mapped_column(primary_key=True)
            line: Mapped[str]
            vib: Mapped[float]

        def agg(engine):
            with Session(engine) as s:
                return dict(s.execute(
                    select(Dev.line, func.round(func.avg(Dev.vib), 2))
                    .group_by(Dev.line)).all())

        style = "2.0 DeclarativeBase+select"
    except ImportError:                           # ── SQLAlchemy 1.3 口径 ──
        from sqlalchemy import Column, Float, String
        from sqlalchemy.ext.declarative import declarative_base

        Base = declarative_base()

        class Dev(Base):
            __tablename__ = "devices"
            code = Column(String, primary_key=True)
            line = Column(String)
            vib = Column(Float)

        def agg(engine):
            from sqlalchemy.orm import sessionmaker
            s = sessionmaker(bind=engine)()
            try:
                return dict(s.query(Dev.line, func.round(func.avg(Dev.vib), 2))
                            .group_by(Dev.line).all())
            finally:
                s.close()

        style = "1.3 declarative_base+Query"

    print(f"    [ORM口径] {style}")
    return agg(create_engine("sqlite://", creator=_mkdb))


def p5_c():              # 解C：pandas.read_sql（要接着做可视化/透视）
    import pandas as pd
    con = _mkdb()
    df = pd.read_sql("SELECT line, vib FROM devices", con).groupby("line")["vib"].mean().round(2)
    con.close()
    return df.to_dict()


# ================= P1.2 模板：两解 =================
def W02_a():             # 解A：单文件 main+顶部常量（小项目/快速交付）
    spec = {"entry": "main()", "config": "顶部常量", "log": "print"}
    return spec


def W02_b():             # 解B：config/logger/main 三件套包结构（可测试/可替换）
    spec = {"entry": "app.main:main", "config": "config.yaml+dataclass",
            "log": "logging RotatingHandler"}
    return spec


# ================= P3 日报：两解 =================
def W05_a():             # 解A：Streamlit实时仪表盘数据层（st.cache_data+px.line）
    import pandas as pd
    rng = random.Random(2026)
    n = 500
    df = pd.DataFrame({
        "ts": pd.date_range("2026-04-01", periods=n, freq="30min"),
        "device_id": [rng.choice(["DEV-01", "DEV-02", "DEV-03", "DEV-04"]) for _ in range(n)],
        "output": [max(0, int(rng.gauss(50, 8))) for _ in range(n)]})
    return df.groupby(df.ts.dt.date).output.sum().tail(3).to_dict()


def W05_b():             # 解B：静态HTML日报（离线导出+cron定时，同数据层）
    return W05_a()       # 数据口径一致；差异在呈现层（浏览器实时 vs 邮件/文件推送）


# ================= P4.1 采集：两解（逻辑同构烟测, 不连PLC） =================
def W06_a():             # 解A：三线程+Queue（教材主线, 阻塞IO直观）
    regs = [563, 45, 12, 1480, 1]
    names = ["temp", "press", "vib", "rpm", "status"]
    return {n: (v / 10 if n != "status" else v) for n, v in zip(names, regs)}


def W06_b():             # 解B：asyncio异步协程（高并发IO密集, C10K扩展路径）
    import asyncio
    regs = [563, 45, 12, 1480, 1]
    names = ["temp", "press", "vib", "rpm", "status"]

    async def _read():
        return regs
    regs_b = asyncio.run(_read())
    return {n: (v / 10 if n != "status" else v) for n, v in zip(names, regs_b)}


# ================= P6 部署：两解 =================
def W08_a():             # 解A：模型落盘→API在线推理（W08_ml_service.py即此路线）
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    rng = np.random.RandomState(7)
    X = rng.normal(0, 1, (400, 30))
    y = rng.binomial(1, .5, 400)
    X[y == 1, 2:8] += rng.uniform(.8, 1.6)
    Xtr, Xte, ytr, yte = train_test_split(X, y, stratify=y, random_state=42)
    m = RandomForestClassifier(random_state=42).fit(Xtr, ytr)
    joblib.dump(m, "/tmp/_W08_model.joblib", compress=3)
    m2 = joblib.load("/tmp/_W08_model.joblib")
    return m2.predict(Xte[:5]).tolist()


def W08_b():             # 解B：离线批推理（无服务, 定时预测写回——网关侧常用）
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    rng = np.random.RandomState(7)
    X = rng.normal(0, 1, (400, 30))
    y = rng.binomial(1, .5, 400)
    X[y == 1, 2:8] += rng.uniform(.8, 1.6)
    Xtr, Xte, ytr, yte = train_test_split(X, y, stratify=y, random_state=42)
    m = RandomForestClassifier(random_state=42).fit(Xtr, ytr)
    return m.predict(Xte[:5]).tolist()


if __name__ == "__main__":
    check("P1.1-1 温度 解A(基础)", lambda: ex1_a(25), (77.0, 298.15))
    check("P1.1-1 温度 解B(查表)", lambda: ex1_b(25), (77.0, 298.15))
    check("P1.1-2 求根 解A(分支)", lambda: ex2_a(1, -3, 2), (1.0, 2.0))
    check("P1.1-2 求根 解B(match)", lambda: ex2_b(1, -3, 2), (1.0, 2.0))
    check("P1.1-2 负根两解一致", lambda: (ex2_a(1, 0, 1), ex2_b(1, 0, 1)), (None, None))
    check("P1.1-5 读取 解A(try)", lambda: ex5_a("/tmp/__no__.txt"), "")
    check("P1.1-5 读取 解B(suppress)", lambda: ex5_b("/tmp/__no__.txt"), "")
    check("P2.1 清洗 解A(pandas)", W03_a, {"FAN-02": 3.1, "PUMP-03": 4.35})
    check("P2.1 清洗 解B(纯Py)", W03_b, {"PUMP-03": 4.35, "FAN-02": 3.1})
    check("P2.2 特征 解A(NumPy)", W04_a, [3.0, 1.4142135623730951, 4.0])
    check("P2.2 特征 解B(stats)", W04_b, [3.0, 1.414214, 4.0])
    check("P5 查询 解A(SQL)", p5_a, {"A2": 4.5, "B1": 3.1})
    check("P5 查询 解B(ORM)", p5_b, {"A2": 4.5, "B1": 3.1})
    check("P5 查询 解C(pandas)", p5_c, {"A2": 4.5, "B1": 3.1})
    check("P1.2 模板 解A(单文件)", W02_a, {"entry": "main()", "config": "顶部常量", "log": "print"})
    check("P1.2 模板 解B(三件套)", lambda: sorted(W02_b().values()),
          ["app.main:main", "config.yaml+dataclass", "logging RotatingHandler"])
    check("P3 日报 解A(Streamlit数据层)", lambda: len(W05_a()), 3)
    check("P3 日报 解A=B(数据口径一致)", lambda: W05_a() == W05_b(), True)
    check("P4.1 采集 解A(线程)", W06_a, {"temp": 56.3, "press": 4.5, "vib": 1.2, "rpm": 148.0, "status": 1})
    check("P4.1 采集 A=B同构", lambda: W06_a() == W06_b(), True)
    check("P6 部署 解A(API在线)", lambda: len(W08_a()), 5)
    check("P6 部署 A=B预测一致", lambda: W08_a() == W08_b(), True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS)}项解法互验：{'ALL PASS ✅' if not bad else 'FAIL ❌ ' + str(bad)}")
    sys.exit(1 if bad else 0)                         # 供自检/阅卷脚本判定退出码
