# -*- coding: utf-8 -*-
"""配置加载：规则外置（config/rules.yaml），做到"改配置不改代码"。

对应 GB/T 8566 支持过程·配置管理：五题的全部可调参数（题号样本、
设备清单与 ID 宽度、PLC 扫描周期、告警/停机阈值、题5 样例文件名）
集中在 YAML；代码零硬编码；缺失键走 DEFAULTS 并显式登记告警。
环境无 PyYAML 时自动降级为内置 yaml_lite，保证课堂任意机器可跑。
"""
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

#: 与 config/rules.yaml 一一对应的兜底结构（缺文件缺键也能跑）
DEFAULTS: Dict[str, Any] = {
    "warn": 80.0,
    "danger": 95.0,
    "topk": 3,
    # PEP 8 达标线（内置 stylecheck 子集实测，锚定工单分层表）：
    #   pep8_pass_rate_d = 及格(D) 行：达标率 ≥75%
    #   pep8_pass_rate_b = 优秀(B) 行：达标率 ≥85%
    "pep8_pass_rate_d": 75.0,
    "pep8_pass_rate_b": 85.0,
    # 工单各档"正确题数"线：及格≥3 题 / 良好 4 题（含第 4 题）/ 优秀 5 题；
    # naming_meaningful_rate = 良好(C) 行"命名有意义"达标率线（%）；
    # tests_per_question_min = 超优(A) 行"每题附测试用例"的每题最少条数。
    "d_min_correct": 3,
    "c_min_correct": 4,
    "b_min_correct": 5,
    "naming_meaningful_rate": 90.0,
    "tests_per_question_min": 1,
    "temperature": {
        "unit": "c",
        "absolute_zero_c": -273.15,
        "tolerance": 1e-06,
        "samples": [0.0, 36.6, 100.0, -273.15],
    },
    "quadratic": {
        "cases": [{"a": 1, "b": -3, "c": 2}, {"a": 1, "b": 2, "c": 1},
                  {"a": 1, "b": 0, "c": 1}],
        "extreme": {"a": 1, "b": -1000000, "c": 1},
    },
    "devices": {
        "id_width": 2,
        "remove_id": 2,
        "update_id": 3,
        "update_status": "运行",
        "default_status": "停止",
        "list": [{"id": 1, "name": "注塑机A"}, {"id": 2, "name": "冷却泵B"},
                 {"id": 3, "name": "空压机C"}],
    },
    "plc": {
        "dev_id": 2,
        "name": "S7-1200",
        "scan_ms": 8,
        "scan_rounds": 3,
        "scan_ms_max": 10000,
        "scan_warn_ms": 500,
        "scan_danger_ms": 1000,
    },
    "reader": {
        "sample_name": "sample_utf8.txt",
        "bad_encoding_name": "bad_encoding.bin",
        "missing_name": "no_such_file.txt",
        "sample_text": "设备清单表头：id,name,status",
        "bad_bytes": [255, 254, 65, 66],
    },
    "meta": {"work_order": "P1.1", "seed": 7, "tier": "A"},
}

TIERS = ("D", "C", "B", "A")


def _merge(base, override):
    """深合并（YAML 只写部分键时不丢默认结构）。"""
    if not isinstance(override, dict):
        return override
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


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
    """YAML 子集：嵌套 dict、块状 list（含 dict 元素）、行内 list、标量。

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


def normalize_id(value, width=2):
    """把 YAML 设备 ID 统一成零填充字符串。

    为什么必须做：`id: 01` 经 PyYAML 解析为八进制整数 1，
    `id: 08` 则保持字符串 —— 键类型不一致会让 `remove("02")`
    查不到真实键 `'2'`，删除变成静默空操作（本工单历史缺陷）。
    """
    if value is None or isinstance(value, bool):
        raise ValueError("设备ID非法（空或布尔）: %r" % (value,))
    if not isinstance(value, (int, str)):
        raise ValueError("设备ID类型不支持: %r" % (value,))
    text = str(value).strip()
    if not text:
        raise ValueError("设备ID为空输入")
    width = max(1, int(width))
    if text.isdigit():
        return text.zfill(width)
    return text.upper()


@dataclass
class Settings:
    """本项目全部可调参数（YAML 驱动，五题各自分组）。"""
    warn: float = 80.0
    danger: float = 95.0
    topk: int = 3
    #: 工单分层 PEP 8 达标线（%）：及格(D) 线 pep8_pass_rate_d、优秀(B) 线
    #: pep8_pass_rate_b（课堂"跟做保底"不占工单字母，不设线值）
    pep8_pass_rate_d: float = 75.0
    pep8_pass_rate_b: float = 85.0
    #: 工单各档正确题数线（及格≥3 题 / 良好 4 题且含第 4 题 / 优秀 5 题）
    d_min_correct: int = 3
    c_min_correct: int = 4
    b_min_correct: int = 5
    #: 良好(C)「命名有意义」达标率线（%）与超优(A)「每题附测试用例」最少条数
    naming_meaningful_rate: float = 90.0
    tests_per_question_min: int = 1
    temperature: Dict[str, Any] = field(default_factory=dict)
    quadratic: Dict[str, Any] = field(default_factory=dict)
    devices: Dict[str, Any] = field(default_factory=dict)
    plc: Dict[str, Any] = field(default_factory=dict)
    reader: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    parser: str = "defaults"
    warnings: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d, parser="defaults"):
        merged = _merge(DEFAULTS, d if isinstance(d, dict) else {})
        warnings = []
        if not isinstance(d, dict) or not d:
            warnings.append("配置为空，全部使用内置 DEFAULTS")
        else:
            missing = [k for k in DEFAULTS if k not in d]
            if missing:
                warnings.append("缺失键由默认值补齐: %s" % "/".join(missing))
        unknown = [k for k in (d or {}) if k not in DEFAULTS]
        if unknown:
            warnings.append("忽略未识别的顶层键(死配置): %s" % "/".join(unknown))
        cfg = cls(
            warn=float(merged["warn"]), danger=float(merged["danger"]),
            topk=int(merged["topk"]),
            pep8_pass_rate_d=float(merged["pep8_pass_rate_d"]),
            pep8_pass_rate_b=float(merged["pep8_pass_rate_b"]),
            d_min_correct=int(merged["d_min_correct"]),
            c_min_correct=int(merged["c_min_correct"]),
            b_min_correct=int(merged["b_min_correct"]),
            naming_meaningful_rate=float(merged["naming_meaningful_rate"]),
            tests_per_question_min=int(merged["tests_per_question_min"]),
            temperature=dict(merged["temperature"]),
            quadratic=dict(merged["quadratic"]),
            devices=dict(merged["devices"]),
            plc=dict(merged["plc"]),
            reader=dict(merged["reader"]),
            meta=dict(merged["meta"]),
            parser=parser, warnings=warnings, raw=merged,
        )
        cfg.validate()
        return cfg

    def validate(self):
        """启动即校验：阈值顺序、ID 宽度、分层取值、扫描周期上限、工单达标线。"""
        if self.warn >= self.danger:
            raise ValueError("阈值顺序颠倒: warn=%s >= danger=%s"
                             % (self.warn, self.danger))
        if not 0.0 <= self.pep8_pass_rate_d <= 100.0:
            raise ValueError("pep8_pass_rate_d 必须在 0~100 之间，当前=%s"
                             % self.pep8_pass_rate_d)
        if not 0.0 <= self.pep8_pass_rate_b <= 100.0:
            raise ValueError("pep8_pass_rate_b 必须在 0~100 之间，当前=%s"
                             % self.pep8_pass_rate_b)
        if self.pep8_pass_rate_d > self.pep8_pass_rate_b:
            raise ValueError("PEP 8 分层线顺序颠倒: 及格(D) %s%% > 优秀(B) %s%%"
                             % (self.pep8_pass_rate_d, self.pep8_pass_rate_b))
        if not 0.0 <= self.naming_meaningful_rate <= 100.0:
            raise ValueError("naming_meaningful_rate 必须在 0~100 之间，"
                             "当前=%s" % self.naming_meaningful_rate)
        # 正确题数线允许写到 >5（如 6），供"只改配置即可让闸门判未达标"的
        # 可证伪测试使用；负数/非整数一律拒绝。
        for name, value in (("d_min_correct", self.d_min_correct),
                            ("c_min_correct", self.c_min_correct),
                            ("b_min_correct", self.b_min_correct),
                            ("tests_per_question_min",
                             self.tests_per_question_min)):
            if int(value) < 0:
                raise ValueError("%s 不得为负数，当前=%s" % (name, value))
        if int(self.devices["id_width"]) < 1:
            raise ValueError("devices.id_width 必须 ≥1")
        if int(self.plc["scan_ms_max"]) < 1:
            raise ValueError("plc.scan_ms_max 必须 ≥1")
        if str(self.meta.get("tier", "A")).upper() not in TIERS:
            raise ValueError("meta.tier 只能是 %s，当前=%r"
                             % ("/".join(TIERS), self.meta.get("tier")))
        if self.topk < 1:
            raise ValueError("topk 必须 ≥1")
        return self

    @property
    def seed(self):
        """随机种子：只用于 A 层"挑 1 条向全班讲解"的确定性抽签。"""
        return int(self.meta.get("seed", 7))

    @property
    def device_rows(self):
        """题3 设备清单（键已归一化），供 CRUD 直接消费。"""
        width = int(self.devices["id_width"])
        default_status = str(self.devices["default_status"])
        rows = []
        for idx, item in enumerate(self.devices.get("list") or [], 1):
            if isinstance(item, dict):
                dev_id = item.get("id", idx)
                name = str(item.get("name", "设备%s" % dev_id))
                status = str(item.get("status", default_status))
            else:
                dev_id, name, status = item, "设备%s" % item, default_status
            rows.append({"id": normalize_id(dev_id, width),
                         "name": name, "status": status})
        return rows

    def device_key(self, value):
        """按配置宽度归一化任意来源（YAML/命令行）的设备 ID。"""
        return normalize_id(value, int(self.devices["id_width"]))


def parse_text(text):
    """优先 PyYAML，缺失时降级 yaml_lite；返回 (data, parser 名)。"""
    try:
        import yaml
    except ImportError:
        return yaml_lite(text), "yaml_lite"
    return yaml.safe_load(text), "PyYAML"


def load_config(path):
    """读取 YAML 配置；文件缺失抛 FileNotFoundError（带路径）。"""
    if not os.path.exists(path):
        raise FileNotFoundError("配置文件不存在: %s" % path)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    data, parser = parse_text(text)
    return Settings.from_dict(data, parser=parser)
