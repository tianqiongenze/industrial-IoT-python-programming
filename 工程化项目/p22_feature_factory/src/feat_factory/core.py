# -*- coding: utf-8 -*-
"""特征工厂：30 主特征（时域10 + 频域15 + 统计5）+ 5 衍生特征，全列式向量化。

工程口径（工单 P2.2 工程化要求）：
  1. **禁 Python 层样本循环**——所有特征函数签名统一 `fn(X, ctx) -> (N,)`，
     X 为 (N, L) 矩阵，一次算完 N 个样本；唯一的循环是"特征清单 × 拼接"，
     次数 = 特征数（常数 35），与样本量无关；
  2. **广播用满**——减均值用 `keepdims`、频率掩码用 `freqs[None,:]`、
     行最大用 `axis=1, keepdims=True`，零逐行拷贝；
  3. **特征字典五列规范**——名称/公式/物理含义/单位/范围（见 FEATURES 注册表）；
  4. **随机种子固定**——信号合成、切分、RF 全部由 config seed 派生，可逐字节复现。

公式版本记录（工单避坑第 2 条）：
  峭度 kurtosis = m4/σ²（**非超额**，正态基线 3）；
  峰度 kurtosis_excess = m4/σ² − 3（超额，正态基线 0）；
  偏度 skewness = m3/σ³（有矩法，非 scipy 无偏修正版）；
  单边幅值谱 amp = |rfft(x − x̄)| · 2/N（去直流 + ×2/N 能量补偿，DC 位置零）。
"""
import numpy as np

EPS = 1e-12

# 特征族与工单《特征清单》一致：时域 10 + 频域 15 + 统计 5 = 30
TIME_FEATS = ["mean", "std", "peak", "ptp", "rms", "var", "abs_mean",
              "crest", "kurtosis", "clearance"]
FREQ_FEATS = ["dom_freq", "peak2_freq", "peak3_freq", "peak1_amp", "peak2_amp",
              "peak3_amp", "a16", "a16_ratio", "spec_energy", "spec_centroid",
              "spec_var", "bandwidth", "spec_flatness", "energy_ratio_low",
              "energy_ratio_high"]
STAT_FEATS = ["skewness", "kurtosis_excess", "cv", "shape_factor", "entropy"]
DERIVED_FEATS = ["d_impact", "d_energy_tilt", "d_severity", "d_h2_rel",
                 "d_ptp_norm"]
PRIMARY_FEATS = TIME_FEATS + FREQ_FEATS + STAT_FEATS

# 名称 → (公式, 物理含义, 单位, 参考量程)：特征字典五列规范的后四列
# （参考量程 = 该类振动信号的工程经验区间；本次运行的实测 min~max 由 pipeline 注入）
META = {
    "mean": ("x.mean()", "直流分量/振动中心位置", "u", "0.48~0.53"),
    "std": ("x.std()", "波动离散程度（交流能量）", "u", "0.16~0.23"),
    "peak": ("max|x|", "峰值：最大振幅，冲击敏感", "u", "0.9~2.0"),
    "ptp": ("max(x)-min(x)", "峰峰值：磨损冲击幅值跨度", "u", "0.9~2.2"),
    "rms": ("sqrt(mean(x²))", "有效值：振动能量代表（烈度）", "u", "0.51~0.58"),
    "var": ("x.var()", "方差：能量二阶矩", "u²", "0.025~0.055"),
    "abs_mean": ("mean(|x|)", "绝对均值：整流后平均幅值", "u", "0.48~0.53"),
    "crest": ("max|x|/rms", "脉冲指标：尖峰密集度（>4 有冲击）", "-", "1.7~3.6（>4 判冲击）"),
    "kurtosis": ("m4/σ⁴", "峭度（非超额，正态=3）：冲击性哨兵", "-", "健康≈3，冲击>4"),
    "clearance": ("max|x|/(mean√|x|)²", "裕度指标：早期点蚀敏感", "-", "1.9~4.1"),
    "dom_freq": ("freqs[argmax(amp)]", "主频率：设备'嗓音音调'", "Hz", "8 或 16（随故障程度跳变）"),
    "peak2_freq": ("freqs[第2大谱线]", "第二峰频率：谐波/松动线索", "Hz", "0.2~50（含噪声底谱线）"),
    "peak3_freq": ("freqs[第3大谱线]", "第三峰频率：振源叠加识别", "Hz", "0.1~50（含噪声底谱线）"),
    "peak1_amp": ("max(amp)", "主峰幅值：最强振源强度", "u", "0.08~0.15"),
    "peak2_amp": ("sorted(amp)[-2]", "第二峰幅值", "u", "0.02~0.10"),
    "peak3_amp": ("sorted(amp)[-3]", "第三峰幅值", "u", "0.02~0.05"),
    "a16": ("amp[f≈2·f0]", "16Hz 二倍频幅值：机械松动/磨损判别指纹（US-02）",
            "u", "0.0004~0.14"),
    "a16_ratio": ("a16/amp[f≈f0]", "二倍频/基频能量比：无量纲松动度", "-", "0.003~7（>1 松动）"),
    "spec_energy": ("sum(amp²)", "频谱总能量：与方差等价（Parseval）", "u²", "0.05~0.11"),
    "spec_centroid": ("sum(f·amp)/sum(amp)", "频域质心：能量重心频率", "Hz", "23~26"),
    "spec_var": ("sum((f-c)²·amp)/sum(amp)", "频域方差：成分分散度", "Hz²", "190~230"),
    "bandwidth": ("f(90%能量)-f(5%能量)", "90% 能量带宽：有效频带宽度", "Hz", "37~44（随机振动主导时接近全带）"),
    "spec_flatness": ("geomean(P)/mean(P)", "频谱平坦度：音调(→0)与噪声(→1)之比",
                      "-", "0.35~0.52（越接近 1 越像噪声）"),
    "energy_ratio_low": ("Σamp²[f<f0×1.5]/Σamp²", "低频能量占比：不平衡/不对中",
                         "-", "0.16~0.50"),
    "energy_ratio_high": ("Σamp²[f>fs/4]/Σamp²", "高频能量占比：磨损/粗糙度",
                          "-", "0.31~0.48"),
    "skewness": ("m3/σ³", "偏度：波形不对称方向", "-", "-0.3~1.3"),
    "kurtosis_excess": ("m4/σ⁴−3", "峰度（超额，正态=0）：冲击拖尾", "-", "-0.5~6.0"),
    "cv": ("std/|mean|", "变异系数：相对离散度（跨设备可比）", "-", "0.32~0.45"),
    "shape_factor": ("rms/mean|x|", "波形因子：波形陡度（≥1）", "-", "1.05~1.10"),
    "entropy": ("−Σpᵢlog pᵢ(幅度直方图)", "信息熵：波形复杂度/无序度", "bit",
                "1.8~2.5（上限 log2(bins)=4）"),
    "d_impact": ("crest×kurtosis_excess", "衍生：冲击复合指标（点蚀预警）", "-", "-1~20"),
    "d_energy_tilt": ("ln(ratio_high/ratio_low)", "衍生：谱倾斜度（高频能量迁移）",
                      "-", "-0.5~1.0"),
    "d_severity": ("rms×spec_centroid", "衍生：振动烈度（能量×重心频率）", "u·Hz",
                   "12~15"),
    "d_h2_rel": ("a16/rms", "衍生：二倍频相对能量（归一化松动度）", "-", "0.001~0.25"),
    "d_ptp_norm": ("ptp/(peak+ε)", "衍生：峰峰值/峰值（上下不对称度）", "-", "0.9~1.3"),
}


class FeatureError(RuntimeError):
    """特征层失败（空输入 / 结果含 NaN / 特征数不达标）。"""


# ------------------------------------------------------------------ 信号合成
# 信号模型（"数据口径"，可被 config 覆盖的量都做成了 make_signals 入参）：
#   0.5 直流偏置 + 确定成分（1×f0 与 2·f0 共享同一份"线谱功率"）+ 高斯随机振动
#   + 磨损类专属的稀疏冲击串。关键设计是 **功率守恒**：
#     looseness u∈[0,1] 决定线谱功率在 1× 与 2× 之间的分配比例，
#     A1=√(2P(1−u))，A2=√(2P·u) ⇒ 两类总能量相同，只有"能量坐在哪条谱线上"不同。
#     这样时域幅值特征（std/rms/var/peak）不再是捷径判别器，模型必须去看频域，
#     a16 才能凭实测坐稳重要性第一名（US-02），而不是被"故障更响"这种假信号抬起来。
NORMAL_U = (0.00, 0.12)         # 正常类 looseness：线谱功率几乎全在 1×
FAULT_U = (0.55, 0.95)          # 磨损类 looseness：功率迁移到 2×（主频会跳变）
FAULT_H3 = 0.02                 # 磨损类 3×f0 分量幅值（不对中伴生，正常类为 0）
IMPACT_FREQ = 33.0              # 冲击包络频率（Hz）：点蚀/剥落的调制载波


def make_signals(n=1000, length=1000, fs=100.0, seed=42, f0=8.0, harmonic=2.0,
                 fault_ratio=0.5, tone_power=0.008, noise_low=0.14, noise_high=0.18,
                 impact_amp=0.9, impact_rate=0.02):
    """向量化合成两类振动信号：正常 / 轴承磨损（判别指纹 = 2·f0=16Hz 的 a16）。

    与 Jupyter 教师版 `make_signals` 同源（0.5 偏置 + 基频正弦 + 白噪 + 冲击），
    工程化改造四处（理由与实测数字见 docs/02「数据口径」）：
      1. 逐样本 for → 整块广播；随机数按固定次序抽取，同种子必得同一矩阵；
      2. 每窗独立 looseness/相位/噪声底——真实机器不会两次采样完全一样。若省略，
         35 列特征会被"类间差异"整体主导，|r|>0.95 的对数虚高，A 层去冗余失真；
      3. 功率守恒（见上）让"频域位移"成为唯一证据链，a16 重要性实测 Top1；
      4. 正常类由随机振动主导 → 峭度中位≈2.9（教科书基线 3）；磨损类叠加稀疏
         冲击 → 峭度中位≈5.4、>4 占比≈95%，B05「峭度哨兵」与 warn/danger
         报警线（4/6）都能落到真实计数上。
    """
    if n < 2 or length < 8:
        raise FeatureError("样本数/窗口长度过小: n=%d length=%d" % (n, length))
    if not 0.0 <= float(fault_ratio) <= 1.0:
        raise FeatureError("fault_ratio 必须在 [0,1]，当前 %s" % fault_ratio)
    if not 0.0 <= float(impact_rate) <= 1.0:
        raise FeatureError("impact_rate 是发生率，需在 [0,1]，当前 %s" % impact_rate)
    if float(tone_power) < 0 or float(noise_low) < 0 or \
            float(noise_high) < float(noise_low):
        raise FeatureError("需 tone_power≥0 且 0≤noise_low≤noise_high，当前 %s/%s/%s"
                           % (tone_power, noise_low, noise_high))
    rng = np.random.default_rng(seed)
    t = (np.arange(length) / float(fs))[None, :]                # (1, L) 供广播
    n = int(n)
    n_fault = int(round(n * float(fault_ratio)))
    labels = np.zeros(n, dtype=int)
    labels[n - n_fault:] = 1                                    # 后半为磨损类
    m = labels[:, None].astype(bool)                            # (N, 1) 行掩码
    # 每窗随机 looseness / 噪声底 / 初相：形状 (N,1) 广播到整行，无逐行循环
    u = np.where(m, rng.uniform(*FAULT_U, (n, 1)),
                 rng.uniform(*NORMAL_U, (n, 1)))
    p = float(tone_power)
    a1 = np.sqrt(2.0 * p * (1.0 - u))                           # 1× 幅值
    a2 = np.sqrt(2.0 * p * u)                                   # 2× 幅值 = a16 指纹
    noise_sd = rng.uniform(float(noise_low), float(noise_high), (n, 1))
    phi = rng.uniform(0.0, 2 * np.pi, (n, 1))
    sig = 0.5 + a1 * np.sin(2 * np.pi * f0 * t + phi) + \
        a2 * np.sin(2 * np.pi * f0 * harmonic * t + phi) + \
        rng.normal(0.0, 1.0, (n, length)) * noise_sd
    sig += np.where(m, FAULT_H3, 0.0) * np.sin(2 * np.pi * 3 * f0 * t + phi)
    hit = rng.binomial(1, np.where(m, float(impact_rate), 0.0), (n, length))
    sig += np.where(m, float(impact_amp), 0.0) * hit * \
        np.abs(np.sin(2 * np.pi * IMPACT_FREQ * t))             # 稀疏冲击串
    return sig, labels


def signals_from_frame(df, cfg):
    """真实数据链：把 P2.1 的 clean.csv 时序按设备切片成窗口（config 驱动）。

    列名/窗口长/步长/故障设备清单全部来自 rules.yaml；标签 = 设备是否在故障清单里。
    """
    idc = cfg.s("io.clean_id_column", "device_id")
    val = cfg.s("io.clean_value_column", "temp")
    tcol = cfg.s("io.clean_time_column", "ts")
    win = cfg.i("signal.window_length")
    stride = max(cfg.i("signal.window_stride"), 1)
    fault = set(cfg.lst("signal.fault_devices"))
    sigs, labels = [], []
    for dev, g in df.sort_values([idc, tcol]).groupby(idc, sort=True):
        x = np.asarray(g[val], dtype=float)
        if len(x) < win:
            continue
        idx = np.arange(0, len(x) - win + 1, stride)
        if idx.size == 0:
            continue
        sigs.append(x[idx[:, None] + np.arange(win)[None, :]])   # 广播切片，无逐窗循环
        labels.append(np.full(idx.size, 1 if dev in fault else 0))
    if not sigs:
        raise FeatureError(
            "clean.csv 无法切出窗口（设备=%s 窗口=%d）——请检查 io.clean_csv 与 signal.*"
            % (sorted(set(df[idc])), win))
    return np.concatenate(sigs), np.concatenate(labels)


# -------------------------------------------------------------------- 频谱
def spectrum(X, fs):
    """单边幅值谱：先去直流，再 |rfft|×2/N，DC 位置零（避坑：rfft 已含共轭对称）。"""
    X = np.atleast_2d(np.asarray(X, dtype=float))
    n = X.shape[1]
    detrend = X - X.mean(axis=1, keepdims=True)              # 广播去直流
    amp = np.abs(np.fft.rfft(detrend, axis=1)) * 2.0 / n
    amp[:, 0] = 0.0
    freqs = np.fft.rfftfreq(n, 1.0 / float(fs))
    return freqs, amp


def _top3(amp, k=3):
    """每行前 k 大谱线的下标（按幅值降序）；argpartition 比全排序省一个量级。"""
    n = amp.shape[0]
    part = np.argpartition(-amp, kth=k - 1, axis=1)[:, :k]
    key = amp[np.arange(n)[:, None], part]
    return np.take_along_axis(part, np.argsort(-key, axis=1), axis=1)


class Ctx:
    """一次 FFT、一份频率轴，供 15 个频域特征共享（避免重复变换）。"""

    def __init__(self, X, fs, f0=8.0, harmonic=2.0, entropy_bins=16):
        self.x = np.atleast_2d(np.asarray(X, dtype=float))
        if self.x.ndim != 2 or self.x.shape[0] == 0 or self.x.shape[1] < 8:
            raise FeatureError(
                "信号矩阵需为 (N≥1, L≥8)，当前 %s" % (self.x.shape,))
        if not np.isfinite(self.x).all():
            raise FeatureError("信号矩阵含 NaN/Inf，请先完成缺失与异常处理")
        self.n, self.length = self.x.shape
        self.fs = float(fs)
        self.f0 = float(f0)
        self.harmonic = float(harmonic)
        self.bins = int(entropy_bins)
        self.freqs, self.amp = spectrum(self.x, self.fs)
        self.power = self.amp * self.amp
        self.f = self.freqs[None, :]                          # (1, B) 广播用
        self.mean = self.x.mean(axis=1)
        dev = self.x - self.mean[:, None]                     # 广播去均值
        d2 = dev * dev                                        # 见"性能"注释：禁用 dev**3/**4
        self.m2 = d2.mean(axis=1)
        self.m3 = (d2 * dev).mean(axis=1)
        self.m4 = (d2 * d2).mean(axis=1)
        self.std = np.sqrt(self.m2)
        self.rms = np.sqrt(self.m2 + self.mean ** 2)          # E[x²]=σ²+μ²，免二次遍历
        ax = np.abs(self.x)
        self.abs_mean = ax.mean(axis=1)
        self.peak = ax.max(axis=1)
        self.root_mean = np.sqrt(ax).mean(axis=1)             # 裕度指标分母
        self.min = self.x.min(axis=1)
        self.ptp = self.x.max(axis=1) - self.min
        self.peak_idx = _top3(self.amp)                       # 前3大谱线下标(降序)

    def amp_at(self, target_hz):
        """取最接近 target_hz 的谱线幅值（频率分辨率 fs/N 内对齐）。"""
        j = int(np.argmin(np.abs(self.freqs - float(target_hz))))
        return self.amp[:, j]

    def band_power(self, lo, hi):
        """(lo, hi] Hz 频段能量占比（分母为全带能量）。"""
        mask = ((self.f > lo) & (self.f <= hi))
        total = self.power.sum(axis=1) + EPS
        return (self.power * mask).sum(axis=1) / total


# ---------------------------------------------------------------- 30 主特征
def _time_feats(c):
    """时域 10 个：全部复用 Ctx 里算好的量（一次遍历原则）。"""
    std = np.where(c.std > EPS, c.std, EPS)
    peak = c.peak
    return [c.mean, c.std, peak, c.ptp, c.rms, c.m2, c.abs_mean,
            peak / (c.rms + EPS),
            c.m4 / std ** 4,                                 # 峭度（非超额，正态=3）
            peak / (c.root_mean * c.root_mean + EPS)]         # 裕度指标


def _freq_feats(c):
    amp, f, power, freqs = c.amp, c.f, c.power, c.freqs
    idx = np.arange(c.n)                                   # 一维行下标：amp[idx, col] 取 (N,)
    top = c.peak_idx
    total = power.sum(axis=1) + EPS
    centroid = (f * amp).sum(axis=1) / (amp.sum(axis=1) + EPS)
    spec_var = (((f - centroid[:, None]) ** 2) * amp).sum(axis=1) / (amp.sum(axis=1) + EPS)
    # 90% 能量带宽：rfftfreq 天然升序，直接按列累计功率，取 5%~90% 主能量带跨度
    cum = np.cumsum(power, axis=1) / total[:, None]
    stop = np.minimum(np.argmax(cum >= 0.90, axis=1), cum.shape[1] - 1)
    start = np.minimum(np.argmax(cum >= 0.05, axis=1), stop)  # 主能量带下界
    bandwidth = freqs[stop] - freqs[start]
    # 频谱平坦度 = 几何均值/算术均值：0→纯音调性，1→白噪声。
    # 工程口径替代说明见 docs/03：离散谱线上 -3dB 半功率带宽退化为主峰单点（恒 0），
    # 故第 13 个频域特征改用平坦度承载"谱形锐/钝"信息。
    flat = np.exp(np.log(power + EPS).mean(axis=1)) / (power.mean(axis=1) + EPS)
    a1 = c.amp_at(c.f0)
    a16 = c.amp_at(c.f0 * c.harmonic)
    return [freqs[top[:, 0]], freqs[top[:, 1]], freqs[top[:, 2]],
            amp[idx, top[:, 0]], amp[idx, top[:, 1]], amp[idx, top[:, 2]],
            a16, a16 / (a1 + EPS),
            total, centroid, spec_var, bandwidth, flat,
            c.band_power(0.0, c.f0 * 1.5), c.band_power(c.fs / 4.0, c.fs / 2.0)]


def _stat_feats(c):
    std = np.where(c.std > EPS, c.std, EPS)
    lo = c.min[:, None]
    span = (c.ptp + EPS)[:, None]
    b = np.clip((c.x - lo) / span * c.bins, 0, c.bins - 1).astype(np.int64)
    # 向量化直方图：全局桶号 + bincount（无 Python 层逐行循环）
    g = (b + np.arange(c.n)[:, None] * c.bins).ravel()
    cnt = np.bincount(g, minlength=c.n * c.bins).reshape(c.n, c.bins)
    p = cnt / cnt.sum(axis=1, keepdims=True)
    entropy = -(p * np.log(p + 1e-12)).sum(axis=1)
    return [c.m3 / std ** 3, c.m4 / std ** 4 - 3.0,
            c.std / (np.abs(c.mean) + EPS), c.rms / (c.abs_mean + EPS), entropy]


def _stack(cols, k):
    """列拼装：预分配 + 逐列写入，比 np.column_stack 快一个量级（1000×35 实测）。"""
    n = len(cols[0])
    if len(cols) != k:
        raise FeatureError("特征列数 %d ≠ 约定 %d" % (len(cols), k))
    M = np.empty((n, k), dtype=float)
    for j, v in enumerate(cols):
        M[:, j] = v
    return M


def extract_primary(X, fs=100.0, f0=8.0, harmonic=2.0, entropy_bins=16):
    """30 维主特征矩阵 (N, 30)——时域10 + 频域15 + 统计5，一次 FFT 共享。

    X 既可以是 (N, L) 信号矩阵，也可以是已建好的 Ctx（供流水线复用同一份 FFT）。
    """
    c = X if isinstance(X, Ctx) else Ctx(X, fs, f0=f0, harmonic=harmonic,
                                         entropy_bins=entropy_bins)
    M = _stack(_time_feats(c) + _freq_feats(c) + _stat_feats(c),
               len(PRIMARY_FEATS))
    _assert_finite(M, "主特征", PRIMARY_FEATS)
    return M


def extract_derived(F):
    """5 维衍生特征（A 层超优口径）：由主特征列组合而成，全程广播无循环。"""
    col = {n: F[:, i] for i, n in enumerate(PRIMARY_FEATS)}
    crest, kx = col["crest"], col["kurtosis_excess"]
    low, high = col["energy_ratio_low"], col["energy_ratio_high"]
    rms, cen = col["rms"], col["spec_centroid"]
    a16, peak, ptp = col["a16"], col["peak"], col["ptp"]
    D = _stack([
        crest * kx,                                          # 冲击复合
        np.log((high + EPS) / (low + EPS)),                  # 谱倾斜
        rms * cen,                                           # 振动烈度
        a16 / (rms + EPS),                                   # 二倍频相对能量
        ptp / (peak + EPS),                                  # 上下不对称度
    ], len(DERIVED_FEATS))
    _assert_finite(D, "衍生特征", DERIVED_FEATS)
    return D


def extract(X, fs=100.0, f0=8.0, harmonic=2.0, entropy_bins=16, with_derived=True):
    """特征矩阵：30 主特征（+5 衍生）；返回 (M, names)。计时口径只含本函数。"""
    c = X if isinstance(X, Ctx) else Ctx(X, fs=fs, f0=f0, harmonic=harmonic,
                                         entropy_bins=entropy_bins)
    F = extract_primary(c)
    names = list(PRIMARY_FEATS)
    if with_derived:
        F = np.hstack([F, extract_derived(F[:, :len(PRIMARY_FEATS)])])
        names = names + list(DERIVED_FEATS)
    return F, names


def _assert_finite(M, tag, names=None):
    """空输入/全零/极端常值序列都可能喂出 NaN——在这里统一拦住并点名坏列。"""
    M = np.asarray(M, dtype=float)
    if M.size == 0 or M.shape[0] == 0:
        raise FeatureError("%s：输入为空矩阵，无法提取特征" % tag)
    if not np.isfinite(M).all():
        cols = names or PRIMARY_FEATS
        bad = [cols[i] if i < len(cols) else "col%d" % i
               for i in np.where(~np.isfinite(M).all(axis=0))[0]]
        raise FeatureError("%s含 NaN/Inf，涉及列: %s" % (tag, bad))


# ------------------------------------------------------------- 标准化（防泄漏）
def zscore_fit(X):
    """只用训练集算 μ/σ（B07 防泄漏军规）；常数列 σ→1 防除零。"""
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd = np.where(sd > EPS, sd, 1.0)
    return mu, sd


def zscore_apply(X, mu, sd):
    """广播标准化：(N,D)-(D,) 直接相减相除。"""
    return (X - mu[None, :]) / sd[None, :]


def train_test_idx(y, test_size=0.3, seed=42):
    """分层切分（同种子同结果）：返回 (train_idx, test_idx)。"""
    rng = np.random.default_rng(seed)
    tr, te = [], []
    for cls in np.unique(y):
        idx = np.flatnonzero(y == cls)
        idx = rng.permutation(idx)
        k = max(int(round(len(idx) * (1.0 - float(test_size)))), 1)
        tr.append(idx[:k])
        te.append(idx[k:])
    return np.sort(np.concatenate(tr)), np.sort(np.concatenate(te))


# ---------------------------------------------------------------- 评价与去冗余
def fisher_ratio(X, y):
    """逐特征 Fisher 判别比 (μ0-μ1)²/(σ0²+σ1²)：类间可分性的实测值。

    分母带"量级地板"：常数列（如主频恒等于 8/16Hz）会让 σ²→0 而爆到 1e14，
    这类特征单独标注，不参与'最强可分特征'排名（见 docs/04）。
    """
    X = np.atleast_2d(np.asarray(X, dtype=float))
    y = np.asarray(y).ravel()
    a, b = X[y == 0], X[y == 1]
    if len(a) == 0 or len(b) == 0:
        return np.zeros(X.shape[1])
    num = (a.mean(axis=0) - b.mean(axis=0)) ** 2
    den = a.var(axis=0) + b.var(axis=0)
    floor = 1e-6 * (X.var(axis=0) + EPS)                      # 相对地板：同列量级的百万分之一
    return num / np.maximum(den, floor)


def near_constant(X, rel=1e-9):
    """类内零方差/近常量特征清单（这类列不能进相关性分析与重要性排名）。"""
    X = np.atleast_2d(np.asarray(X, dtype=float))
    sd = X.std(axis=0)
    scale = np.abs(X.mean(axis=0)) + EPS
    return [i for i in range(X.shape[1]) if sd[i] <= rel * scale[i]]


def corr_matrix(X):
    """相关系数矩阵（向量化标准化后求均值积）；常序列相关记 0。"""
    Z = X - X.mean(axis=0)
    sd = Z.std(axis=0)
    keep = sd > EPS
    Z = Z[:, keep] / sd[keep][None, :]
    R = np.zeros((X.shape[1], X.shape[1]))
    if Z.shape[1]:
        R[np.ix_(keep, keep)] = (Z.T @ Z) / float(Z.shape[0])
    return R


def drop_redundant(R, names, keep_idx, threshold=0.95):
    """A 层去冗余：|r| ≥ 阈值 的特征对只保留优先级更高（排在前面）的那个。

    keep_idx 是**优先级顺序**（工单口径：按 RF 重要性降序），实现严格照这个顺序入场：
      1. 先入场者占位；后来者逐个与"已保留列"比 |r|；
      2. 命中阈值即判冗余，记录被谁挤掉（kept 赢家）与 |r| 数值 ⇒ 可复核的取舍说明；
      3. 与已保留列无关的列正常入场，故传递链（a~b、b~c 而 a~c 弱相关）也能收敛；
      4. 返回值 kept 升序（便于与清单对账），dropped 保持优先级顺序（讲解用）。
    真实坑（原实现）：`sorted(keep_idx, key=pos)` 把调用方给的重要性顺序又按"清单
    位置"重排了一遍 ⇒ 赢家实际是"列号最小"的那个，redundancy.keep 这个配置项形同虚设。
    """
    order, seen = [], set()
    for i in keep_idx:                        # 去重保序：调用方顺序即优先级
        if i in seen:
            continue
        seen.add(i)
        order.append(int(i))
    kept, dropped = [], []
    for i in order:
        winner = None
        for j in kept:
            if abs(R[i, j]) >= threshold:
                winner = j
                break
        if winner is None:
            kept.append(i)
        else:
            dropped.append({"feature": names[i], "kept": names[winner],
                            "abs_r": round(float(abs(R[i, winner])), 4)})
    kept.sort()
    return kept, dropped


# --------------------------------------------------------------- 特征字典导出
def feature_dict_rows(names, measured=None):
    """特征字典（工单五列规范：名称/公式/含义/单位/范围）+ 族别与实测范围两列补充。

    measured: {name: (min, max)}，由真实特征矩阵算出；缺省时只给参考量程。
    """
    fam = {}
    for n in TIME_FEATS:
        fam[n] = "时域"
    for n in FREQ_FEATS:
        fam[n] = "频域"
    for n in STAT_FEATS:
        fam[n] = "统计"
    for n in DERIVED_FEATS:
        fam[n] = "衍生(A层)"
    rows = []
    for name in names:
        formula, meaning, unit, ref = META[name]
        got = ""
        if measured and name in measured:
            lo, hi = measured[name]
            got = "%g ~ %g" % (lo, hi)
        rows.append({"名称": name, "族": fam[name], "公式": formula,
                     "物理含义": meaning, "单位": unit, "参考量程": ref,
                     "实测范围": got})
    return rows


def alarm_counts(F, names, warn, danger):
    """峭度工艺红线（warn/danger 配置项）：健康≈3，破 warn 预警、破 danger 报警。"""
    k = F[:, names.index("kurtosis")]
    return {"warn": float(warn), "danger": float(danger),
            "预警样本": int((k > warn).sum()), "停机样本": int((k > danger).sum()),
            "总样本": int(len(k)), "峭度中位": float(np.median(k))}


# ------------------------------------------------------------ 恒等式对账（分层证据）
# 教师版 W04 用这三条"硬恒等式"证明特征不是各算各的散点，而是同一份矩的不同写法：
#   var = std²（第①个留白的正解）；rms² = mean² + var（E[x²]=σ²+μ²）；
#   kurtosis_excess = kurtosis − 3（超额峭度只是平移）。
# 恒等式两边都由 extract() 真实产出的列算出来 ⇒ 偏差为机器精度级；
# 谁把某一列改成了"另算一遍"的写法，这里立刻露馅（D/A 层判定与测试共用）。
IDENTITY_TOL = 1e-10          # 严格恒等（浮点仅允许机器精度残差）
PARSEVAL_TOL = 5e-3           # Parseval 是谱口径近似，教师版同用 5e-3


def identity_devations(F, names=None):
    """返回 [(口径, 最大绝对偏差, 容差, 是否成立)]——全列式向量化后的自检证据。"""
    names = list(names) if names is not None else list(PRIMARY_FEATS)
    col = {n: i for i, n in enumerate(names)}

    def c(name):
        if name not in col:
            raise FeatureError("恒等式对账缺列: %s（当前 %d 列）" % (name, len(names)))
        return F[:, col[name]]

    checks = [
        ("var=std²", c("var") - c("std") ** 2, IDENTITY_TOL),
        ("rms²=mean²+var", c("rms") ** 2 - (c("mean") ** 2 + c("var")), IDENTITY_TOL),
        ("kurtosis_excess=kurtosis−3",
         c("kurtosis_excess") - (c("kurtosis") - 3.0), IDENTITY_TOL),
        ("crest=peak/rms", c("crest") - c("peak") / (c("rms") + EPS), IDENTITY_TOL),
        ("shape_factor=rms/abs_mean",
         c("shape_factor") - c("rms") / (c("abs_mean") + EPS), IDENTITY_TOL),
        ("cv=std/|mean|", c("cv") - c("std") / (np.abs(c("mean")) + EPS),
         IDENTITY_TOL),
        ("spec_energy≈2·var(Parseval)", c("spec_energy") - 2.0 * c("var"),
         PARSEVAL_TOL),
    ]
    out = []
    for tag, diff, tol in checks:
        dev = float(np.abs(np.asarray(diff, dtype=float)).max())
        out.append((tag, dev, tol, dev < tol))
    return out
