# -*- coding: utf-8 -*-
"""特征工厂：13 维时域 + 4 维频域（纯函数，可逐特征断言）。"""
import numpy as np

TIME_FEATS = ["mean", "max", "min", "median", "var", "std", "skew", "q25", "q75",
              "p05", "p95", "iqr", "rms"]


def make_window(kind, size=64, seed=None):
    """生成一个振动窗口：normal（平稳）/ abnormal（叠加冲击+抬升）。"""
    rng = np.random.RandomState(seed)
    x = rng.normal(0, 1, size)
    if kind == "abnormal":
        x[rng.randint(0, size, 5)] += 3.0        # 冲击
        x += 1.5                                  # 整体抬升
    return x


def feats_time(x):
    """13 维时域特征（固定顺序）。"""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        raise ValueError("窗口为空")
    q = np.percentile(x, [5, 25, 50, 75, 95])
    return [
        float(x.mean()), float(x.max()), float(x.min()), float(np.median(x)),
        float(x.var()), float(x.std()), float(((x - x.mean()) ** 3).mean() / (x.std() ** 3 + 1e-12)),
        float(q[1]), float(q[3]), float(q[0]), float(q[4]), float(q[3] - q[1]),
        float(np.sqrt((x ** 2).mean())),
    ]


def feats_freq(x, fs=64.0):
    """4 维频域特征：主频 + 3 个频带能量比。"""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        raise ValueError("窗口为空")
    spec = np.abs(np.fft.rfft(x - x.mean()))
    freqs = np.fft.rfftfreq(x.size, 1 / fs)
    total = spec.sum() + 1e-12
    main_f = float(freqs[np.argmax(spec)])
    bands = [(0, fs / 8), (fs / 8, fs / 4), (fs / 4, fs / 2)]
    return [main_f] + [float(spec[(freqs >= lo) & (freqs < hi)].sum() / total)
                       for lo, hi in bands]


def feature_names():
    return TIME_FEATS + ["main_freq", "band1", "band2", "band3"]
