# -*- coding: utf-8 -*-
"""配置加载：规则外置（config/rules.yaml），做到"改规则不改代码"。

对应 GB/T 8566 支持过程·配置管理：所有阈值/列名/策略/输出路径集中在 YAML，
代码零硬编码；缺失键走 DEFAULTS 并显式校验（temp_min>=temp_max 之类直接拒绝启动，
不静默吞掉）。环境无 PyYAML 时自动降级为内置 yaml_lite，保证课堂任意机器可跑。
"""
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

# 与 config/rules.yaml 一一对应的内置兜底（改 YAML 即可覆盖，键名不可拼错——
# _validate() 会检查未知键并告警）
DEFAULTS: Dict[str, Any] = {
    "warn": 80.0,
    "danger": 95.0,
    "unit": "c",
    "seed": 7,
    "topk": 3,
    # PEP 8 内置子集分层线（与 p11_exercises 同一口径）：D 层 / B 层，单位 %
    "pep8_pass_rate": 75.0,
    "pep8_pass_rate_high": 85.0,
    "io": {
        "input": "../../p21_raw.csv",
        "input_fallback": "../../W03_raw.csv",
        "out_clean_csv": "clean.csv",
        "out_log": "clean_log.txt",
        "out_result_json": "result.json",
        "out_report": "report.txt",
        "out_strategies": "missing_strategies.csv",
        "out_state": "state.json",
        "out_anomalies": "anomalies.csv",
    },
    "pipeline": {
        "required_columns": ["device_id", "ts", "temp", "press", "status"],
        "numeric_columns": ["temp", "press"],
        "temp_column": "temp",
        "press_column": "press",
        "id_column": "device_id",
        "id_pattern": r"DEV-\d{2}",
        "ts_column": "ts",
        "status_column": "status",
        "status_allowed": ["RUN", "IDLE", "FAULT", "MAINT"],
        "ts_formats": ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y%m%d%H%M%S"],
        "drop_column_missing_ratio": 0.30,
        "missing_strategy": {
            "interpolate": ["temp"],
            "median": ["press"],
            "mode": ["status"],
            "unknown_label": "UNKNOWN",
        },
        "dropna_columns": ["temp", "ts", "press"],
        "iqr_columns": ["temp"],
        "iqr_k": 1.5,
        "temp_min": 20.0,
        "temp_max": 120.0,
        "press_min": 0.1,
        "press_max": 1.0,
        "outlier_action": "remove",
        "warning_column": "temp_warning",
        "danger_column": "temp_danger",
        "dedupe_subset": ["device_id", "ts"],
        "dedupe_keep": "first",
        "strict_validate": True,
        "custom_rules": [],
    },
    "quality": {
        "weights": {"completeness": 40, "accuracy": 30,
                    "consistency": 20, "timeliness": 10},
        "max_duplicate_rate": 0.0,
        "gates": {"pass": 85, "good": 88, "excellent": 90},
    },
    "perf": {"bench_rows": 1000000, "bench_budget_seconds": 300},
}


def _merge(base, override):
    """深合并：YAML 里只写部分键时，其余仍取 DEFAULTS（不丢默认）。"""
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
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:      # 引号标量：原样取值
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
    """把 "k: v" 填入 dict d。"""
    k, _, v = s.partition(":")
    k, v = k.strip(), v.strip()
    if k:
        d[k] = _scalar(v)


def yaml_lite(text):
    """YAML 子集：嵌套 dict、块状 list（含 dict 元素）、行内 list、标量、注释。

    实现要点：`key:` 空值时同时压入两帧——
      ① "列表父级帧"(缩进, 父dict, key)  —— 供 `- item` 归入
      ② "子字典帧"(缩进+.5, 子dict, None) —— 供更深层 `k: v` 归入
    遇到 `- ` 时若栈顶是"子字典帧"则先弹出，回到列表父级帧。
    引号包裹的列表项（如 `- "%m/%d/%Y %H:%M"`）按标量处理，避免把引号内的
    冒号误判成键值分隔。
    """
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
                stack.pop()                       # 弹掉子字典帧，回到列表父级帧
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
    """配置非法（阈值顺序颠倒 / 键缺失 / 类型错）——启动即拒绝。"""


@dataclass
class Settings:
    """本项目全部可调参数（YAML 驱动，点号路径访问）。"""
    raw: Dict[str, Any] = field(default_factory=dict)
    used_keys: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # ---------- 访问 ----------
    def get(self, dotted, default=None):
        """按 "pipeline.temp_max" 形式取值；缺失返回 default。"""
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

    # ---------- 常用别属性（报告/台账高频取用） ----------
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

    # ---------- 校验 ----------
    def _validate(self):
        p = self.raw["pipeline"]
        for lo, hi in (("temp_min", "temp_max"), ("press_min", "press_max")):
            if float(p[lo]) >= float(p[hi]):
                raise ConfigError("区间阈值非法: %s(%s) >= %s(%s)"
                                  % (lo, p[lo], hi, p[hi]))
        if self.warn > self.danger:
            raise ConfigError("预警/停机线顺序颠倒: warn(%s) > danger(%s)"
                              % (self.warn, self.danger))
        if self.f("pipeline.iqr_k") <= 0:
            raise ConfigError("iqr_k 必须为正数, 当前 %s" % self.f("pipeline.iqr_k"))
        if self.f("pipeline.drop_column_missing_ratio") <= 0 or \
                self.f("pipeline.drop_column_missing_ratio") >= 1:
            raise ConfigError("drop_column_missing_ratio 必须在 (0,1) 区间")
        if self.f("perf.bench_budget_seconds") <= 0:
            raise ConfigError("perf.bench_budget_seconds 必须为正数")
        if not isinstance(self.get("quality.weights", {}), dict):
            raise ConfigError("缺少 quality.weights 评分口径")
        total = sum(float(v) for v in self.raw["quality"]["weights"].values())
        if abs(total - 100.0) > 1e-6:
            raise ConfigError("质量评分权重之和必须为 100, 当前 %s" % total)
        for gate_key in ("pass", "good", "excellent"):
            if not 0 <= float(self.raw["quality"]["gates"][gate_key]) <= 100:
                raise ConfigError("门禁线 quality.gates.%s 必须在 0~100" % gate_key)
        for pep8_key in ("pep8_pass_rate", "pep8_pass_rate_high"):
            v = float(self.get(pep8_key))
            if not 0 < v <= 100:
                raise ConfigError("PEP 8 达标线 %s 必须在 (0,100]" % pep8_key)
        if self.f("pep8_pass_rate") > self.f("pep8_pass_rate_high"):
            raise ConfigError("PEP 8 分层线顺序颠倒: D 线(%s) > B 线(%s)"
                              % (self.f("pep8_pass_rate"),
                                 self.f("pep8_pass_rate_high")))
        if self.s("pipeline.outlier_action") not in ("remove", "clip"):
            raise ConfigError("pipeline.outlier_action 只能是 remove/clip")
        if self.i("seed") < 0:
            raise ConfigError("seed 必须 >= 0")
        if self.i("topk") <= 0:
            raise ConfigError("topk 必须 >= 1")

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            d = {}
        merged = _merge(DEFAULTS, d)
        st = cls(raw=merged)
        unknown = [k for k in d if k not in DEFAULTS]
        if unknown:
            st.warnings.append("配置含未识别顶层键（已忽略）: %s" % ",".join(unknown))
        st._validate()
        st.used_keys = sorted(merged)
        return st


def load_config(path):
    """读取 YAML 配置；文件缺失抛 FileNotFoundError（带路径），非法抛 ConfigError。"""
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
