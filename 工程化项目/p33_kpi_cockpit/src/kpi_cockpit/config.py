# -*- coding: utf-8 -*-
"""配置加载：规则外置（config/rules.yaml），做到"改配置不改代码"。

对应 GB/T 8566 支持过程·配置管理：所有可调阈值/清单集中在 YAML，
代码零硬编码；缺失键走 DEFAULTS 并显式告警，不静默吞掉。
环境无 PyYAML 时自动降级为内置 yaml_lite，保证课堂任意机器可跑。
"""
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

DEFAULTS: Dict[str, Any] = {
    "warn": 80.0, "danger": 95.0, "unit": "c", "seed": 7, "topk": 2,
}

# 缺失即显式告警的必需配置段（工程化要求 1：KPI/阈值/目标全部外置，不许硬编码兜底）
REQUIRED_SECTIONS = ("kpi", "thresholds", "targets", "data", "report",
                     "schedule", "cache")


def _scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
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
    return v.strip(chr(39) + chr(34) + " ")


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
                if ":" in body:
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


@dataclass
class Settings:
    """本项目全部可调参数（YAML 驱动）。"""
    warn: float = 80.0
    danger: float = 95.0
    unit: str = "c"
    seed: int = 7
    topk: int = 2
    items: List[Any] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    missing_sections: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            d = {}
        missing = [s for s in REQUIRED_SECTIONS if s not in d]
        d = dict(DEFAULTS, **d)
        warn, danger = float(d["warn"]), float(d["danger"])
        if warn >= danger:                      # docs/03 异常策略：启动即拒绝
            raise ValueError("阈值顺序颠倒：warn=%.1f 必须小于 danger=%.1f"
                             % (warn, danger))
        items = d.get("items")
        if not items:
            # 数据集键名：优先显式 lines，其次 items，再退化为首个 list 值
            items = d.get("lines")
        if not items:
            for k, v in d.items():
                if isinstance(v, list) and v and isinstance(v[0], (dict, str, int, float)):
                    items = v
                    break
        if not items:
            items = []
        if not isinstance(items, list):
            items = [items]
        return cls(
            warn=warn, danger=danger, unit=str(d["unit"]),
            seed=int(d["seed"]), topk=int(d["topk"]),
            items=items, raw=d, missing_sections=missing,
        )

    # ---- 结构化取数（pipeline/app 统一走这里，杜绝散落硬编码）----
    def section(self, name):
        """取一段配置；缺失 → KeyError（不静默给默认值，防"静默空白"）。"""
        if name not in self.raw:
            raise KeyError("config/rules.yaml 缺少必需段: %s" % name)
        return self.raw[name]

    def path(self, dotted, default=None):
        """按 'a.b.c' 取嵌套值；取不到返回 default（仅供可选键使用）。"""
        cur = self.raw
        for p in dotted.split("."):
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def require(self, dotted):
        """按 'a.b.c' 取嵌套值；取不到抛 KeyError（必需键走这条，避免静默降级）。"""
        sentinel = object()
        out = self.path(dotted, sentinel)
        if out is sentinel:
            raise KeyError("config/rules.yaml 缺少必需键: %s" % dotted)
        return out

    # ---- 常用口径的语义化别名（单一真源：都从 YAML 读）----
    @property
    def temp_max(self):
        return float(self.require("thresholds.temp_max"))

    @property
    def vib_max(self):
        return float(self.require("thresholds.vib_max"))

    @property
    def target_output_per_day(self):
        return float(self.require("targets.output_qty_per_day"))

    @property
    def report_seconds_max(self):
        return float(self.require("targets.report_seconds_max"))

    @property
    def kpi_required(self):
        return list(self.require("kpi.required"))

    @property
    def kpi_extra(self):
        return list(self.section("kpi").get("extra") or [])

    @property
    def unit_symbol(self):
        """config 的 unit 键 → 显示符号（杜绝代码里硬编码 ℃）。"""
        return {"c": "℃", "f": "℉", "k": "K"}.get(str(self.unit).lower(), str(self.unit))

    @property
    def cache_ttl(self):
        return int(self.require("cache.ttl_seconds"))

    @property
    def drill_max_rows(self):
        """联动明细行数上限（工单优秀(B) 钻取；drill.max_rows，缺失即报错不静默给默认）。"""
        return int(self.require("drill.max_rows"))

    @property
    def drill_detail_columns(self):
        """联动明细列清单（工单优秀(B) 钻取；drill.detail_columns）。"""
        return [str(c) for c in self.require("drill.detail_columns")]

    def rules(self):
        """把 YAML 组装成 core.* 统一消费的"扁平规则包"（配置→逻辑唯一通道）。"""
        return {
            "temp_max": self.temp_max, "vib_max": self.vib_max,
            "status_online": self.require("thresholds.status_online"),
            "output_qty_per_day": self.target_output_per_day,
            "warn": self.warn, "danger": self.danger,
            "kpi_required": self.kpi_required, "kpi_extra": self.kpi_extra,
            "unit_symbol": self.unit_symbol,
            "drill_max_rows": self.drill_max_rows,
            "drill_detail_columns": self.drill_detail_columns,
        }


def parse(text):
    """YAML 文本 → dict：有 PyYAML 用之，无则降级内置 yaml_lite（课堂任意机器可跑）。"""
    try:
        import yaml
        data = yaml.safe_load(text)
    except ImportError:
        data = yaml_lite(text)
    return data if isinstance(data, dict) else {}


def load_config(path):
    if not os.path.exists(path):
        raise FileNotFoundError("配置文件不存在: %s" % path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    cfg = Settings.from_dict(parse(text))
    if cfg.missing_sections:                    # 显式告警，不静默吞掉
        import logging
        logging.getLogger("kpi_cockpit").warning(
            "config/rules.yaml 缺少段 %s，相关功能将按 DEFAULTS 运行",
            ",".join(cfg.missing_sections))
    return cfg
