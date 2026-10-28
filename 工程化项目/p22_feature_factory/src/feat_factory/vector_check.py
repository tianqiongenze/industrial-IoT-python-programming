# -*- coding: utf-8 -*-
"""向量化静态检查：把 C 层口径「以向量化为主，无逐样本 for 循环」变成可执行证明。

Jupyter 教师版 W04 是用字节码数循环的：

    loops = [nm for nm in TIME15 if any(op.opname == "FOR_ITER"
                                        for op in dis.get_instructions(FEATURES[nm][0]))]
    assert not loops, loops

本模块是它的**源码层等价物**（AST 版），口径一致但覆盖面更大：
  * `ast.For` / `ast.While` / `ast.comprehension`（含列表/字典/生成器推导式）三类
    会产生逐元素迭代的语法都算一次循环，等价于 FOR_ITER；
  * 循环的**迭代对象**决定性质：迭代"特征名注册表"（TIME_FEATS / PRIMARY_FEATS /
    cols / names / np.unique / groupby）= 允许，次数 = 特征数（常数 35），与样本量无关；
    迭代"样本轴"（X / x / y / F / rows / sig）或来路不明的可迭代对象 = 违规；
  * 只扫 config `vectorization.targets` 点名的特征函数（12 个），与教师版"只查 15 个
    时域特征函数"同口径；`zscore_* / corr_matrix / fisher_ratio / near_constant`
    是逐**列**工具函数（列数恒定），不在逐样本口径内，故不列入 targets。

违规判定同时把"这个函数产出哪些特征"列出来（FUNC_FEATS），这样测试失败时点名的是
特征名，不是一句空泛的"存在循环"。
"""
import ast
import os

from . import core

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(ROOT, "src", "feat_factory")

ALL_FEATS = list(core.PRIMARY_FEATS) + list(core.DERIVED_FEATS)

# 函数 → 该函数产出（或直接供养）的特征名：违规时要点名的就是这一串
FUNC_FEATS = {
    "Ctx.__init__": list(core.PRIMARY_FEATS),
    "spectrum": list(core.FREQ_FEATS),
    "_top3": ["dom_freq", "peak2_freq", "peak3_freq",
              "peak1_amp", "peak2_amp", "peak3_amp"],
    "Ctx.amp_at": ["a16", "a16_ratio", "peak1_amp", "d_h2_rel"],
    "Ctx.band_power": ["energy_ratio_low", "energy_ratio_high", "d_energy_tilt"],
    "_time_feats": list(core.TIME_FEATS),
    "_freq_feats": list(core.FREQ_FEATS),
    "_stat_feats": list(core.STAT_FEATS),
    "_stack": ALL_FEATS,
    "extract_primary": list(core.PRIMARY_FEATS),
    "extract_derived": list(core.DERIVED_FEATS),
    "extract": ALL_FEATS,
}

# 工单默认扫描面（config: vectorization.targets，可增删，改配置不改代码）
DEFAULT_TARGETS = [
    "core.Ctx.__init__", "core.spectrum", "core._top3",
    "core.Ctx.amp_at", "core.Ctx.band_power",
    "core._time_feats", "core._freq_feats", "core._stat_feats",
    "core._stack", "core.extract_primary", "core.extract_derived",
    "core.extract",
]
# 注册表迭代 = 允许（次数 = 特征数，与样本量无关）
DEFAULT_REGISTRY = ["TIME_FEATS", "FREQ_FEATS", "STAT_FEATS", "DERIVED_FEATS",
                    "PRIMARY_FEATS", "ALL_FEATS", "META", "cols", "col", "names",
                    "name", "rows", "dict_rows", "keys", "np.unique", "groupby"]
# 样本轴迭代 = 违规
DEFAULT_SAMPLES = ["X", "x", "y", "F", "Z", "sig", "signal", "rows_", "samples",
                   "window", "windows", "batch"]


def _dotted(node):
    """Attribute 链的完整点号名（np.unique / df.groupby），拿不到就返回 None。"""
    parts, cur = [], node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _tokens(node):
    """迭代表达式里出现的所有标识符：全名 + 末段属性名（便于 groupby 命中）。"""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
            d = _dotted(sub)
            if d:
                out.add(d)
    return out


def classify(iter_node, registry, samples):
    """返回 ("registry"|"sample"|"unregistered", 命中的标识符)。"""
    toks = _tokens(iter_node)
    reg = sorted(toks & set(registry))
    if reg:
        return "registry", reg
    bad = sorted(toks & set(samples))
    if bad:
        return "sample", bad
    return "unregistered", sorted(toks)


def _find_func(tree, parts):
    node = tree
    for i, name in enumerate(parts):
        body = getattr(node, "body", None)
        cand = [n for n in (body or []) if getattr(n, "name", None) == name]
        if not cand:
            return None
        node = cand[0]
    return node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None


def _loops(fn_node):
    """一个函数体内所有会产生逐元素迭代的语法点。

    推导式的 `ast.comprehension` 节点本身没有行号（3.12 亦然），所以用外层
    ListComp/SetComp/DictComp/GeneratorExp 的 lineno 定位。
    """
    found = []
    for sub in ast.walk(fn_node):
        if isinstance(sub, ast.For):
            found.append(("for", sub.iter, sub.lineno))
        elif isinstance(sub, ast.While):
            found.append(("while", sub.test, sub.lineno))
        elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp,
                              ast.GeneratorExp)):
            for gen in sub.generators:
                found.append(("comprehension", gen.iter, sub.lineno))
    return found


def func_key(dotted):
    """core.Ctx.__init__ → Ctx.__init__（FUNC_FEATS 的键口径）。"""
    return ".".join(dotted.split(".")[1:])


def scan_text(text, targets, registry=None, samples=None, prefix="core"):
    """纯文本扫描（供测试注入"朴素逐样本写法"验证闸门真的会报警）。

    targets 用 `prefix.dotted.name` 口径；返回与 scan() 同构的结果字典。
    """
    registry = list(registry or DEFAULT_REGISTRY)
    samples = list(samples or DEFAULT_SAMPLES)
    tree = ast.parse(text)
    violations, allowed, missing, scanned = [], [], [], []
    for dotted in targets:
        parts = dotted.split(".")[1:] if dotted.startswith(prefix + ".") \
            else dotted.split(".")
        fn = _find_func(tree, parts)
        if fn is None:
            missing.append(dotted)
            continue
        local = ".".join(parts)
        key = prefix + "." + local
        scanned.append(key)
        for kind, node, lineno in _loops(fn):
            cls, hits = classify(node, registry, samples)
            rec = {"func": key, "line": lineno, "kind": kind,
                   "iterable": ast.unparse(node), "hits": hits}
            if cls == "registry":
                allowed.append(rec)
            else:
                rec["reason"] = "逐样本迭代" if cls == "sample" \
                    else "迭代对象不在特征名注册表内（无法证明与样本量无关）"
                rec["feature_names"] = FUNC_FEATS.get(local, ALL_FEATS)
                violations.append(rec)
    res = {"targets": list(targets), "scanned": scanned,
           "missing_targets": missing, "violations": violations,
           "registry_loops": allowed, "registry_names": registry,
           "sample_names": samples}
    res["n_forbidden"] = len(violations)
    res["n_registry"] = len(allowed)
    res["enabled"] = True
    res["ok"] = not violations and not missing
    res["status"] = "pass" if res["ok"] else \
        ("config_drift" if missing and not violations else "violation")
    return res


def module_file(mod):
    p = os.path.join(SRC_DIR, mod + ".py")
    if not os.path.exists(p):
        raise core.FeatureError("向量化静态检查找不到源码: %s" % p)
    return p


def scan(cfg):
    """按 config 扫描特征函数源码，返回带计数的结果字典（写进报告与 result.json）。"""
    res = {"enabled": bool(cfg.get("vectorization.enabled", True)),
           "targets": [], "scanned": [], "missing_targets": [],
           "violations": [], "registry_loops": [],
           "registry_names": list(cfg.lst("vectorization.registry_names")),
           "sample_names": list(cfg.lst("vectorization.sample_names"))}
    if not res["enabled"]:
        res["status"] = "disabled"
        res["ok"] = False
        res["n_forbidden"] = 0
        res["n_registry"] = 0
        return res
    targets = list(cfg.lst("vectorization.targets"))
    mods = {}
    violations, allowed, missing, scanned = [], [], [], []
    for dotted in targets:
        mod = dotted.split(".")[0]
        if mod not in mods:
            mods[mod] = ast.parse(open(module_file(mod), encoding="utf-8").read())
        parts = dotted.split(".")[1:]
        fn = _find_func(mods[mod], parts)
        if fn is None:
            missing.append(dotted)
            continue
        scanned.append(dotted)
        for kind, node, lineno in _loops(fn):
            cls, hits = classify(node, res["registry_names"], res["sample_names"])
            rec = {"func": dotted, "line": lineno, "kind": kind,
                   "iterable": ast.unparse(node), "hits": hits}
            if cls == "registry":
                allowed.append(rec)
            else:
                rec["reason"] = "逐样本迭代" if cls == "sample" \
                    else "迭代对象不在特征名注册表内（无法证明与样本量无关）"
                rec["feature_names"] = FUNC_FEATS.get(
                    ".".join(parts), ALL_FEATS)
                violations.append(rec)
    res.update({"targets": targets, "scanned": scanned, "missing_targets": missing,
                "violations": violations, "registry_loops": allowed,
                "n_forbidden": len(violations), "n_registry": len(allowed)})
    res["ok"] = not violations and not missing
    res["status"] = "pass" if res["ok"] else \
        ("config_drift" if missing and not violations else "violation")
    return res


def detail_lines(res, limit=None):
    """违规点名行（报告/测试失败信息共用）：函数 + 行号 + 迭代对象 + 特征名清单。"""
    lines = []
    for v in res["violations"]:
        feats = v.get("feature_names") or []
        shown = feats if limit is None else feats[:limit]
        lines.append("%s:%d %s 迭代 %s（%s）涉及特征 %s"
                     % (v["func"], v["line"], v["kind"], v["iterable"],
                        v["reason"], ",".join(shown)))
    for m in res["missing_targets"]:
        lines.append("%s 在源码里找不到（config 与代码漂移，闸门不能空转）" % m)
    return lines


def summary_text(res, verdict=True):
    """报告用的一行结论（无墙钟数值，逐字节可复现）。

    verdict=False 时不结尾判定（供「分层达标」行自己拼接，避免出现两个"→ 达标"）。
    """
    if not res["enabled"]:
        return ("向量化静态检查 : 已关闭（config: vectorization.enabled=false）"
                "⇒ C 层口径无证据，判未达标")
    return ("向量化静态检查 : AST 扫描 %d 个特征函数（targets 共 %d）⇒ 逐样本 "
            "for/while/推导式 %d 处｜特征名注册表级循环 %d 处（%s，次数=特征数 %d、"
            "与样本量无关）｜清单里找不到的目标函数 %d 个%s"
            % (len(res["scanned"]), len(res["targets"]), res["n_forbidden"],
               res["n_registry"],
               " + ".join(sorted({v["func"].split(".")[-1]
                                 for v in res["registry_loops"]})) or "无",
               len(ALL_FEATS), len(res["missing_targets"]),
               " → 达标" if verdict and res["ok"] else
               (" → 未达标" if verdict else "")))
