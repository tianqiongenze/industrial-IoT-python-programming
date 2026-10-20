# -*- coding: utf-8 -*-
"""数据加载层：只负责'读进来'，不掺清洗逻辑（单一职责）"""
import random
import pandas as pd


def make_raw(path: str = "W03_raw.csv", n: int = 1200, seed: int = 2026) -> str:
    """生成演示用原始数据（种子固定可复现）；真实场景替换为 read_csv 即可"""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        dev = f"PUMP-{rng.randint(1, 8):02d}"
        temp = round(rng.uniform(55, 92), 1)
        if rng.random() < 0.04:
            temp = round(rng.uniform(120, 160), 1)      # 注入离群
        vib = round(rng.uniform(1.0, 6.0), 2)
        shift = rng.choice(["白班", "夜班", "中班"])
        ts = f"2026-09-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00"
        rows.append([ts, dev, temp, vib, shift])
        if rng.random() < 0.05:
            rows.append(rows[-1])                        # 注入重复
    df = pd.DataFrame(rows, columns=["ts", "dev", "temp", "vib", "shift"])
    df.to_csv(path, index=False, encoding="utf-8")
    return path


def load(path: str) -> pd.DataFrame:
    return pd.read_csv(path)
