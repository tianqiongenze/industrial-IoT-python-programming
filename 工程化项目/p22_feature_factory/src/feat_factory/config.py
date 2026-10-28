# -*- coding: utf-8 -*-
"""配置加载：特征/性能/落盘口径全部外置（config/rules.yaml），改口径不改代码。

对应 GB/T 8566 支持过程·配置管理；无 PyYAML 时降级内置 yaml_lite（与 P2.1 同一实现）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

import os

DEFAULTS: Dict[str, Any] = {
    "seed": 42,
    "topk": 6,
    "warn": 4.0,          # 峭度预警线（工单 B05：健康≈3，破 4 预警）
    "danger": 6.0,        # 峭度停机线（冲击密集，需停机检查）
    "unit": "mm/s",
    "io": {
        # 真实数据链：默认吃 P2.1 的干净输出；source=generator 时用合成信号
        "clean_csv": "../p21_pandas_clean/output/clean.csv",
        "clean_id_column": "device_id",
        "clean_value_column": "temp",
        "clean_time_column": "ts",
        "out_features_csv": "features.csv",
        "out_features_npy": "features.npy",
        "out_labels_npy": "labels.npy",
        "out_scaler_json": "scaler.json",
        "out_feature_dict_csv": "feature_dict.csv",
        "out_feature_dict_md": "feature_dict.md",
        "out_result_json": "result.json",
        "out_report": "report.txt",
        "out_boxplot": "boxplot.png",
        "out_corr_heatmap": "corr_heatmap.png",
        "out_timing_json": "../runtime/timing.json",   # 易变计时不落 output/
    },
    "signal": {
        "source": "generator",       # generator | clean（P2.1 输出切窗）
        "samples": 1000,
        "length": 1000,
        "fs": 100.0,
        "f0": 8.0,
        "harmonic": 2.0,
        "fault_ratio": 0.5,
        "tone_power": 0.008,         # 1×/2× 共享的线谱功率（功率守恒设计）
        "noise_low": 0.14,           # 随机振动标准差下限
        "noise_high": 0.18,          # 随机振动标准差上限
        "impact_amp": 0.9,           # 磨损类冲击幅值
        "impact_rate": 0.02,         # 冲击发生率（每采样点命中概率）
        "window_length": 64,         # source=clean 时的切窗长度
        "window_stride": 32,         # 切窗步长
        "fault_devices": ["DEV-03", "DEV-04"],   # 标签=设备是否在此清单
    },
    "features": {"primary": 30, "derived": 5, "entropy_bins": 16,
                 "peak_orders": 3},
    "model": {"estimators": 200, "min_samples_leaf": 2, "test_size": 0.3,
              "cv_folds": 5},
    "perf": {"target_ms": 100.0, "excellent_ms": 50.0, "repeats": 5},
    "redundancy": {"corr_threshold": 0.95, "keep": "importance"},
    # C 层向量化静态检查（AST）：口径与 vector_check.py 的默认值一致
    "vectorization": {
        "enabled": True,
        "targets": ["core.Ctx.__init__", "core.spectrum", "core._top3",
                    "core.Ctx.amp_at", "core.Ctx.band_power",
                    "core._time_feats", "core._freq_feats", "core._stat_feats",
                    "core._stack", "core.extract_primary",
                    "core.extract_derived", "core.extract"],
        "registry_names": ["TIME_FEATS", "FREQ_FEATS", "STAT_FEATS",
                           "DERIVED_FEATS", "PRIMARY_FEATS", "ALL_FEATS", "META",
                           "cols", "col", "names", "name", "rows", "dict_rows",
                           "keys", "np.unique", "groupby"],
        "sample_names": ["X", "x", "y", "F", "Z", "sig", "signal", "rows_",
                         "samples", "window", "windows", "batch"],
    },
}


def _merge(base, override):
    if not isinstance(override, dict):
        return override
    out = dict(base)
    for k, v in override.items():
        out[k] = _merge(base.get(k, {}), v) if isinstance(v, dict) else v
    return out


def _scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~", ""):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _quoted(s):
    return s[:1] in ("\"", "'")


def _fill_kv(d, s):
    k, _, v = s.partition(":")
    k, v = k.strip(), v.strip()
    if k:
        d[k] = _scalar(v)


def yaml_lite(text):
    """YAML 子集解析（嵌套 dict / 块状 list / 行内 list / 标量 / 注释）。"""
    root = {}
    stack = [(-1, root, None)]
    lines = [(len(r) - len(r.lstrip(" ")), r.strip())
             for r in text.splitlines()
             if r.strip() and not r.strip().startswith("#")]
    i = 0
    while i < len(lines):
        indent, line = lines[i]
        if line.startswith("- "):
            if len(stack) > 1 and stack[-1][2] is None:
                stack.pop()
            owner, key = stack[-1][1], stack[-1][2]
            if isinstance(owner, dict) and key is not None:
                if not isinstance(owner[key], list):
                    owner[key] = []
                body = line[2:]
                if ":" in body and not _quoted(body):
                    item = {}
                    _fill_kv(item, body)
                    owner[key].append(item)
                    i += 1
                    while i < len(lines) and lines[i][0] > indent \
                            and not lines[i][1].startswith("- "):
                        _fill_kv(item, lines[i][1])
                        i += 1
                    continue
                owner[key].append(_scalar(body))
            i += 1
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        owner = stack[-1][1]
        if not isinstance(owner, dict):
            i += 1
            continue
        key, _, v = line.partition(":")
        key, v = key.strip(), v.strip()
        if v == "":
            child = {}
            owner[key] = child
            stack.append((indent, owner, key))
            stack.append((indent + 0.5, child, None))
        else:
            owner[key] = _scalar(v)
            stack[-1] = (stack[-1][0], owner, key)
        i += 1
    return root


class ConfigError(ValueError):
    """配置非法（阈值顺序颠倒 / 口径越界）——启动即拒绝。"""


@dataclass
class Settings:
    """特征工厂的全部可调参数（YAML 驱动，点号路径访问）。"""
    raw: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def get(self, dotted, default=None):
        cur = self.raw
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def f(self, dotted, default=None):
        return float(self.get(dotted, default))

    def i(self, dotted, default=None):
        return int(self.get(dotted, default))

    def s(self, dotted, default=""):
        return str(self.get(dotted, default))

    def lst(self, dotted, default=None):
        v = self.get(dotted, default)
        if v is None:
            return []
        return list(v) if isinstance(v, (list, tuple)) else [v]

    @property
    def seed(self):
        return self.i("seed")

    @property
    def topk(self):
        return self.i("topk")

    @property
    def warn(self):
        return self.f("warn")

    @property
    def danger(self):
        return self.f("danger")

    @property
    def unit(self):
        return self.s("unit")

    def _validate(self):
        if self.warn >= self.danger:
            raise ConfigError("峭度报警线顺序颠倒: warn(%s) >= danger(%s)"
                              % (self.warn, self.danger))
        if self.warn <= 0:
            raise ConfigError("warn 需为正数（峭度健康基线≈3）")
        if self.f("signal.fs") <= 0:
            raise ConfigError("signal.fs 必须为正数")
        if self.f("signal.f0") * self.f("signal.harmonic") >= self.f("signal.fs") / 2:
            raise ConfigError("二倍频 %.1fHz 超过奈奎斯特 %.1fHz，请降 f0 或 fs"
                              % (self.f("signal.f0") * self.f("signal.harmonic"),
                                 self.f("signal.fs") / 2))
        if not 0 < self.f("redundancy.corr_threshold") < 1:
            raise ConfigError("redundancy.corr_threshold 必须在 (0,1)")
        if self.s("redundancy.keep") not in ("importance", "rank"):
            raise ConfigError("redundancy.keep 只能是 importance/rank，当前 %s"
                              % self.s("redundancy.keep"))
        if self.f("perf.excellent_ms") >= self.f("perf.target_ms"):
            raise ConfigError("perf.excellent_ms 必须小于 perf.target_ms")
        if self.f("perf.target_ms") <= 0 or self.i("perf.repeats") < 1:
            raise ConfigError("perf.target_ms 需为正且 perf.repeats ≥ 1")
        if self.i("features.primary") <= 0 or self.i("features.derived") < 0:
            raise ConfigError("features.primary 必须为正、derived 不能为负")
        if self.i("features.entropy_bins") < 2:
            raise ConfigError("features.entropy_bins 需 ≥ 2")
        vec_targets = self.lst("vectorization.targets")
        if self.get("vectorization.enabled", True) and not vec_targets:
            raise ConfigError("vectorization.enabled=true 时 targets 不能为空"
                              "（闸门不能空转）")
        for t in vec_targets:
            if len(str(t).split(".")) < 2:
                raise ConfigError("vectorization.targets 需是 模块.函数 口径，"
                                  "当前 %s" % t)
        clash = (set(self.lst("vectorization.registry_names"))
                 & set(self.lst("vectorization.sample_names")))
        if clash:
            raise ConfigError("vectorization 注册表与样本轴名单冲突: %s"
                              % sorted(clash))
        if self.i("features.peak_orders") < 3:
            raise ConfigError("features.peak_orders 需 ≥ 3（前 3 峰是频域特征的基础）")
        if self.i("signal.samples") <= 1 or self.i("signal.length") <= 8:
            raise ConfigError("signal.samples 需 >1 且 signal.length 需 >8")
        if self.f("signal.tone_power") < 0:
            raise ConfigError("signal.tone_power 不能为负")
        if self.f("signal.noise_low") < 0 or \
                self.f("signal.noise_high") < self.f("signal.noise_low"):
            raise ConfigError("需 0 ≤ signal.noise_low ≤ signal.noise_high")
        if not 0 <= self.f("signal.impact_rate") <= 1:
            raise ConfigError("signal.impact_rate 是发生率，需在 [0,1]")
        if self.f("signal.impact_amp") < 0:
            raise ConfigError("signal.impact_amp 不能为负")
        if not 0 <= self.f("signal.fault_ratio") <= 1:
            raise ConfigError("signal.fault_ratio 需在 [0,1]")
        if self.i("signal.window_length") < 8:
            raise ConfigError("signal.window_length 需 ≥ 8（否则无法做 FFT/矩）")
        if self.i("signal.window_stride") < 1:
            raise ConfigError("signal.window_stride 需 ≥ 1")
        if self.i("model.estimators") < 1 or self.i("model.cv_folds") < 2:
            raise ConfigError("model.estimators 需 ≥1 且 cv_folds 需 ≥2")
        if not 0 < self.f("model.test_size") < 1:
            raise ConfigError("model.test_size 必须在 (0,1)")
        if self.i("topk") < 1:
            raise ConfigError("topk 需 ≥ 1")
        if self.seed < 0:
            raise ConfigError("seed 需为非负整数")
        if self.s("signal.source") not in ("generator", "clean"):
            raise ConfigError("signal.source 只能是 generator/clean，当前 %s"
                              % self.s("signal.source"))
        if not self.i("features.primary") >= self.i("features.peak_orders"):
            raise ConfigError("features.primary 需覆盖 peak_orders")
        for key in ("out_features_csv", "out_features_npy", "out_labels_npy",
                    "out_scaler_json", "out_feature_dict_csv", "out_feature_dict_md",
                    "out_result_json", "out_report", "out_boxplot",
                    "out_corr_heatmap"):
            if not str(self.get("io." + key, "")).strip():
                raise ConfigError("io.%s 不能为空" % key)
        if self.i("signal.length") < self.i("features.peak_orders"):
            raise ConfigError("signal.length 过短")

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            d = {}
        st = cls(raw=_merge(DEFAULTS, d))
        unknown = [k for k in d if k not in DEFAULTS]
        if unknown:
            st.warnings.append("配置含未识别顶层键（已忽略）: %s" % ",".join(unknown))
        st._validate()
        return st


def load_config(path):
    if not os.path.exists(path):
        raise FileNotFoundError("配置文件不存在: %s" % path)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml
        data = yaml.safe_load(text)
    except ImportError:
        data = yaml_lite(text)
    return Settings.from_dict(data)
