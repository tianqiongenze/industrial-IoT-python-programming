# -*- coding: utf-8 -*-
"""P2.2 NumPy 30维故障特征提取 —— 骨架先行(特征字典+5个示例已给)
运行: python W04_features.py          # 生成特征+箱线图+计时
数据: 自动合成振动信号(正常/磨损两类, 100Hz采样)
"""
import time

import numpy as np

rng = np.random.RandomState(42)


def make_signals(n=200, length=1000, fs=100):
    """合成两类信号: 正常(低幅+白噪) / 轴承磨损(冲击+高频成分)"""
    t = np.arange(length) / fs
    sigs, labels = [], []
    for i in range(n):
        base = 0.5 + 0.1 * np.sin(2 * np.pi * 8 * t)
        s = base + rng.normal(0, 0.05, length)
        if i >= n // 2:                      # 磨损: 加冲击与高频
            s += 1.2 * np.abs(np.sin(2 * np.pi * 33 * t)) * rng.binomial(1, 0.08, length)
            s += 0.4 * np.sin(2 * np.pi * 60 * t)
        sigs.append(s)
        labels.append(0 if i < n // 2 else 1)
    return np.array(sigs), np.array(labels), fs


# ============ 特征字典(补齐空实现; 每个特征: 函数+物理含义) ============
FEATURES = {}


def feature(name, meaning):
    def deco(fn):
        FEATURES[name] = (fn, meaning)
        return fn
    return deco


# ---- 示例1-5(已给, 照此补齐其余) ----
@feature("mean", "均值: 振动能量平均水平")
def f_mean(x):
    return x.mean()


@feature("std", "标准差: 波动离散程度")
def f_std(x):
    return x.std()


@feature("max", "峰值: 最大振幅, 冲击敏感")
def f_max(x):
    return np.abs(x).max()


@feature("ptp", "峰峰值: max-min, 磨损冲击幅值")
def f_ptp(x):
    return np.ptp(x)


@feature("rms", "均方根: 有效值, 能量代表")
def f_rms(x):
    return np.sqrt((x ** 2).mean())


# ---- 时域5个(TODO) ----
@feature("var", "方差")
def f_var(x):
    # === 你的代码 ===
    return 0.0


@feature("abs_mean", "绝对均值")
def f_abs_mean(x):
    return 0.0


@feature("crest", "脉冲指标: peak/rms")
def f_crest(x):
    # === 你的代码 ===
    return 0.0


@feature("kurtosis", "峭度: 冲击性(四阶矩)")
def f_kurtosis(x):
    # 提示: ((x-x.mean())**4).mean() / std**4 - 3
    return 0.0


@feature("clearance", "裕度指标: peak/半波平方均值^2")
def f_clearance(x):
    return 0.0


# ---- 频域15个(TODO, 先完成fft_help) ----
def spectrum(x, fs):
    """返回 freqs, amp: 单边幅值谱(已归一化)"""
    n = len(x)
    amp = np.abs(np.fft.rfft(x)) * 2 / n
    freqs = np.fft.rfftfreq(n, 1 / fs)
    return freqs, amp


@feature("dom_freq", "主频率: 最大幅值对应频率")
def f_dom_freq(x, fs=100):
    freqs, amp = spectrum(x, fs)
    # === 你的代码 ===
    return 0.0


@feature("spec_energy", "频谱总能量")
def f_spec_energy(x, fs=100):
    # === 你的代码 ===
    return 0.0


@feature("spec_centroid", "频域质心")
def f_centroid(x, fs=100):
    return 0.0


# ... TODO: 再补12个频域/统计特征, 例如:
#  f2/f3(第2、3峰频率), bandwidth(带宽), spec_var(频域方差),
#  half_power_bw(半功率带宽), energy_ratio_0_20hz(低频能量占比),
#  skewness(偏度), cv(变异系数), shape_factor(波形因子), entropy(信息熵) ...


def extract(signals, fs=100):
    """对每条信号计算全部特征 → 特征矩阵(N×30) + 名称列表"""
    names = list(FEATURES)[:30]
    t0 = time.time()
    X = np.array([[FEATURES[n][0](s, fs) if FEATURES[n][0].__code__.co_argcount > 1
                   else FEATURES[n][0](s) for n in names] for s in signals])
    ms = (time.time() - t0) * 1000
    return X, names, ms


def main():
    sigs, labels, fs = make_signals()
    X, names, ms = extract(sigs, fs)
    print(f"特征矩阵: {X.shape}  计算耗时: {ms:.0f}ms (及格<100, 优秀<50)")
    # TODO: Z-score标准化 → 保存 features.npy + labels.npy
    # TODO: 箱线图(matplotlib, 每类对比前6个特征)
    # TODO: (超优)相关系数矩阵去冗余特征
    return X, labels


if __name__ == "__main__":
    main()
