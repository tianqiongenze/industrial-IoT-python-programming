# -*- coding: utf-8 -*-
"""特征工厂流水线：取数 → 30+5 维特征 → 防泄漏标准化 → 可分性与重要性 → 落盘。

对应工单 P2.2 教师版 cell-0 的四级达标要求（**口径以该表为准**，
每条都能在 output/report.txt 的「分层达标」段指到实测数字）：
  D 学徒·跟做保底：跟做示例跑通第①个留白(var)，程序出结果（§8 D 行 + §2/§4）
  C 操作员·基础完成：30 特征正确 + 向量化为主（§8 C 行 + §2/§3 静态检查行）
  B 组长·标准达成：<100ms + 特征字典含物理含义（§8 B 行 + §3/§2）
  A 师傅·进阶拓展：相关系数矩阵热力图，剔除 |r|>0.95 的冗余特征并说明取舍；
                    示范讲解（§8 A 行 + §9 去冗余明细与取舍说明）
  注：perf.excellent_ms（50ms）是内部加速参考线，**不是**工单等级；
      工单只给了 B 层的 100ms 这条硬线，等级判定按 D→C→B→A 逐级取证。

确定性口径（NF-1）：output/ 里每个文件都由「配置 + 输入」唯一决定——
  墙钟计时（实测 ms）**只**写在 runtime/timing.json（output/ 之外），
  report.txt / result.json 只写阈值与判定文字，一个墙钟数值都不出现；
  产物清单不写 report.txt / result.json 自身字节数（避免自指抖动），
  runtime/timing.json 的字节数也不写（它随每次实测刷新，会让清单漂移）。
  于是连续两次 `python run.py`（不同 PYTHONHASHSEED）后 `output/` 逐字节一致
  （docs/06 有验证命令，tests/test_tier_gates.py 有墙钟红线用例）。
"""
import os
import time

import numpy as np

from . import config as cfg_mod
from . import core, io_utils, report, vector_check

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SELF = ("io.out_report", "io.out_result_json")     # 大小不写进清单的两个自指文件

# 工单 P2.2 教师版 cell-0 的四级达标要求（**逐字引用该表**，报告/文档/测试都以此为准）
TIER_NAME = {"D": "D 学徒·跟做保底", "C": "C 操作员·基础完成",
             "B": "B 组长·标准达成", "A": "A 师傅·进阶拓展"}
TIER_REQ = {"D": "跟做示例跑通第①个留白(var), 程序出结果",
            "C": "30特征正确+向量化为主",
            "B": "<100ms+特征字典含物理含义",
            "A": "相关系数矩阵热力图：剔除|r|>%.2f的冗余特征并说明取舍；示范讲解"}

# 工单《P2.2 特征工程工厂 · 验收标准》四档原文（逐字照抄，作为对照节的单一口径来源）：
# 注意它与上面 TIER_REQ 的字母错一档——课堂 C≈工单及格，课堂 B≈工单良好，
# 工单优秀(B)『<50ms…』只有下面的 wo_lines 一节取证。
WO_ROW = {"D": "30特征计算正确；向量化为主；标准化正确；PEP 8≥75%",
          "C": "1000样本<100ms；特征字典含物理含义",
          "B": "<50ms；广播运用充分；箱线图输出；文档完整",
          "A": "优秀+衍生特征5个+相关性特征选择(去冗余)"}


def _rel(path):
    """把机器相关的绝对路径收敛成项目内相对路径（保证报告逐字节可复现）。"""
    ap = os.path.abspath(path)
    rp = os.path.relpath(ap, ROOT)
    return rp if not rp.startswith("..") else os.path.basename(ap)


def _path(cfg, key, out_dir):
    return os.path.join(out_dir, cfg.s(key))


def _timing_display(cfg):
    """墙钟文件的稳定展示名：不泄露机器绝对路径，且看得出它在 output/ 之外的 runtime/。"""
    raw = cfg.s("io.out_timing_json")
    if os.path.isabs(raw):
        return "%s/%s" % (os.path.basename(os.path.dirname(raw)),
                          os.path.basename(raw))
    return raw


def _resolve_path(cfg, key):
    """io.* 允许相对路径：以本项目目录为基准解析。"""
    raw = cfg.s(key)
    return raw if os.path.isabs(raw) else os.path.normpath(os.path.join(ROOT, raw))


# ------------------------------------------------------------------ 取数（流水线第 1 步）
def load_signals(cfg, input_override=None):
    """返回 (X, y, meta)：source=generator 用故障发生器；clean 走 P2.1 真实数据链。"""
    src = "clean" if input_override else cfg.s("signal.source")
    meta = {"source": src}
    if src == "generator":
        X, y = core.make_signals(
            n=cfg.i("signal.samples"), length=cfg.i("signal.length"),
            fs=cfg.f("signal.fs"), seed=cfg.seed, f0=cfg.f("signal.f0"),
            harmonic=cfg.f("signal.harmonic"),
            fault_ratio=cfg.f("signal.fault_ratio"),
            tone_power=cfg.f("signal.tone_power"),
            noise_low=cfg.f("signal.noise_low"), noise_high=cfg.f("signal.noise_high"),
            impact_amp=cfg.f("signal.impact_amp"),
            impact_rate=cfg.f("signal.impact_rate"))
        meta.update(length=int(X.shape[1]), windows=None)
        return X, y, meta
    path = input_override or _resolve_path(cfg, "io.clean_csv")
    if not os.path.exists(path):
        raise core.FeatureError(
            "真实数据链输入不存在: %s（请先运行 P2.1，或把 signal.source 改回 generator）"
            % _rel(path))
    rows = io_utils.read_csv_rows(path)          # 物理行数，与 pandas 逻辑行数对账
    import pandas as pd
    df = pd.read_csv(path)
    meta.update(input=_rel(path), input_sha=io_utils.sha256_short(path),
                columns=list(df.columns), physical_rows=len(rows),
                logical_rows=int(len(df)),
                length=cfg.i("signal.window_length"))
    if len(rows) != int(len(df)):
        meta["row_mismatch"] = len(rows) - int(len(df))
    X, y = core.signals_from_frame(df, cfg)
    meta.update(windows="窗口 %d 步长 %d｜故障设备 %s"
                % (cfg.i("signal.window_length"), cfg.i("signal.window_stride"),
                   ",".join(sorted(set(cfg.lst("signal.fault_devices"))))))
    return X, y, meta


# ------------------------------------------------------------------ 计时（性能验收）
def measure(fn, X, fs, repeats, **kw):
    """只计时特征计算（工单避坑第 3 条：不含数据生成/落盘/训练）。

    返回 (最小值ms, 全部ms)。取最小值的口径：机器噪声只会让结果偏慢，
    最小值是对"算法成本"最诚实的估计（取舍说明见 docs/04）。
    """
    out = []
    for _ in range(max(int(repeats), 1)):
        t0 = time.perf_counter()
        fn(X, fs, **kw)
        out.append((time.perf_counter() - t0) * 1000.0)
    return min(out), out


# ------------------------------------------------------------------ 图表（箱线图 / 热力图）
CJK_FONT_CANDIDATES = ["PingFang SC", "Heiti SC", "Arial Unicode MS",
                       "Noto Sans CJK SC", "Source Han Sans SC",
                       "Microsoft YaHei", "SimHei", "WenQuanYi Zen Hei"]


def use_cjk(plt):
    """机器上有中文字体才写中文标签，否则图上全是豆腐块（DejaVu 无 CJK 字形）。

    返回 bool：调用方据此选中/英文标签，保证图在任何机器都可读。
    """
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for cand in CJK_FONT_CANDIDATES:
        if cand in installed:
            plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


def plot_boxplot(path, F, y, top_feats, names):
    """B 层箱线图：重要性 Top 特征 × 两类并排，直观呈现类间分离。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    cn = use_cjk(plt)
    ticks = ["正常", "磨损"] if cn else ["normal", "wear"]
    k = min(len(top_feats), 6)
    if k == 0:
        return None
    fig, axes = plt.subplots(1, k, figsize=(2.2 * k, 3.0))
    for ax, feat in zip(np.atleast_1d(axes), top_feats[:k]):
        j = names.index(feat)
        ax.boxplot([F[y == 0, j], F[y == 1, j]], tick_labels=ticks,
                   patch_artist=True)
        ax.set_title(feat, fontsize=9)
        ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_corr_heatmap(path, R, names, threshold):
    """A 层相关系数热力图：去冗余决策的证据图。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    cn = use_cjk(plt)
    title = ("|r| 相关系数矩阵（阈值 %.2f 以上判冗余）" % threshold if cn
             else "|r| correlation matrix (redundant above %.2f)" % threshold)
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    im = ax.imshow(np.abs(R), vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, fontsize=5)
    ax.set_yticklabels(names, fontsize=5)
    ax.set_title(title, fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


# ------------------------------------------------------------------ 模型（重要性证明）
def fit_model(Z, y, cfg):
    """分层切分 + 训练段拟合 Z-score + 随机森林 → (重要性, 诊断, 切分, μσ, W)。

    防泄漏军规（B07）：μ/σ 只用训练段估计，测试段仅做变换。
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score, silhouette_score
    tr, te = core.train_test_idx(y, cfg.f("model.test_size"), cfg.seed)
    mu, sd = core.zscore_fit(Z[tr])
    W = core.zscore_apply(Z, mu, sd)
    clf = RandomForestClassifier(n_estimators=cfg.i("model.estimators"),
                                 min_samples_leaf=cfg.i("model.min_samples_leaf"),
                                 random_state=cfg.seed, n_jobs=1)
    clf.fit(W[tr], y[tr])
    pred = clf.predict(W[te])
    diag = {"train_rows": int(len(tr)), "test_rows": int(len(te)),
            "accuracy": float(accuracy_score(y[te], pred)),
            "f1": float(f1_score(y[te], pred, zero_division=0)),
            "silhouette": float(silhouette_score(W, y)),
            "leak_guard": "μ/σ 仅由训练段 %d 行估计，测试段 %d 行只做变换"
                          % (len(tr), len(te))}
    return clf.feature_importances_, diag, (tr, te), (mu, sd), W


# ------------------------------------------------------------------ 主流程
def build(cfg=None, out_dir=None, input_path=None, with_plot=True):
    """跑完整链路，返回实测 bundle（run() 与 tests 共用，测试即走真代码）。"""
    cfg = cfg or cfg_mod.load_config(os.path.join(ROOT, "config/rules.yaml"))
    out_dir = out_dir or os.path.join(ROOT, "output")
    io_utils.ensure_dir(out_dir)

    X, y, meta = load_signals(cfg, input_path)
    fs = cfg.f("signal.fs")
    kw = dict(f0=cfg.f("signal.f0"), harmonic=cfg.f("signal.harmonic"),
              entropy_bins=cfg.i("features.entropy_bins"))
    t0 = time.perf_counter()
    F, names = core.extract(X, fs=fs, **kw)
    load_ms = (time.perf_counter() - t0) * 1000.0
    best_ms, all_ms = measure(core.extract, X, fs, cfg.i("perf.repeats"), **kw)

    primary_n = cfg.i("features.primary")
    if primary_n != len(core.PRIMARY_FEATS):
        raise core.FeatureError("features.primary=%d 与 core 主特征数 %d 不一致，"
                                "请改 config 或补特征"
                                % (primary_n, len(core.PRIMARY_FEATS)))
    Z = F[:, :primary_n]                    # features.npy 契约：30 维主特征原始量纲
    imp, diag, (tr, te), (mu, sd), W = fit_model(Z, y, cfg)
    order = np.argsort(-imp)
    top_names = [names[i] for i in order[:cfg.topk]]

    R = core.corr_matrix(F)
    thr = cfg.f("redundancy.corr_threshold")
    prio = (list(order) if cfg.s("redundancy.keep") == "importance"
            else list(range(len(names))))
    kept, dropped = core.drop_redundant(R, names, prio, thr)
    # 冗余对数（上三角 |r| ≥ 阈值的特征对）：主特征域 30×30 与全矩阵 35×35 两个口径，
    # 外加"严格恒等对"（|r|=1，如 kurtosis ↔ kurtosis_excess）作为可证伪的锚点。
    pr = primary_n
    iu_p, iu_all = np.triu_indices(pr, 1), np.triu_indices(len(names), 1)
    abs_p = np.abs(R[:pr, :pr][iu_p])
    red_pairs = {"primary": int((abs_p >= thr).sum()),
                 "all": int((np.abs(R[iu_all]) >= thr).sum()),
                 "exact_one": int((abs_p >= 1.0 - 1e-12).sum()),
                 "total_pairs": int(len(abs_p))}
    identities = core.identity_devations(F, names)
    vec = vector_check.scan(cfg)

    a16 = names.index("a16")
    a16_rank = int(np.where(order == a16)[0][0]) + 1
    us02 = "达成：a16 重要性第 %d 名（Top1/2 口径）" % a16_rank if a16_rank <= 2 else \
           "未达成：a16 第 %d 名，Top1=%s" % (a16_rank, names[int(order[0])])

    alarms = core.alarm_counts(F, names, cfg.warn, cfg.danger)
    fisher = core.fisher_ratio(F, y)
    ftop = np.argsort(-fisher)[:3]
    meas = {n: (float(F[:, i].min()), float(F[:, i].max()))
            for i, n in enumerate(names)}
    dict_rows = core.feature_dict_rows(names, meas)

    timing = {"target_ms": cfg.f("perf.target_ms"),
              "excellent_ms": cfg.f("perf.excellent_ms"),
              "best_ms": round(best_ms, 3), "all_ms": [round(v, 3) for v in all_ms],
              "load_ms": round(load_ms, 3), "samples": int(F.shape[0]),
              "note": "墙钟实测值（best_ms/all_ms/load_ms）只写本文件，"
                      "且本文件在 output/ 之外 ⇒ output/ 逐字节可复现"}
    return {"cfg": cfg, "out_dir": out_dir, "meta": meta, "y": y, "F": F,
            "names": names, "Z": Z, "imp": imp, "order": order,
            "top_names": top_names, "R": R, "kept": kept, "dropped": dropped,
            "a16": a16, "a16_rank": a16_rank, "us02": us02, "alarms": alarms,
            "fisher": fisher, "ftop": ftop, "meas": meas, "dict_rows": dict_rows,
            "diag": diag, "mu": mu, "sd": sd, "primary_n": primary_n,
            "best_ms": best_ms, "all_ms": all_ms, "load_ms": load_ms,
            "with_plot": with_plot, "timing": timing, "fs": fs, "kw": kw,
            "thr": thr, "red_pairs": red_pairs, "identities": identities,
            "vec": vec, "plots": {}}


def write_outputs(b):
    """把 build() 的实测结果落盘：output/ 内全部确定性，墙钟写 runtime/。"""
    cfg, out_dir = b["cfg"], b["out_dir"]
    io_utils.ensure_dir(out_dir)
    names, F, y = b["names"], b["F"], b["y"]
    rows = []
    for r in range(F.shape[0]):
        d = {n: round(float(F[r, i]), 6) for i, n in enumerate(names)}
        d["label"] = int(y[r])
        rows.append(d)
    io_utils.write_csv_rows(_path(cfg, "io.out_features_csv", out_dir), rows,
                            fields=list(names) + ["label"])
    np.save(_path(cfg, "io.out_features_npy", out_dir), b["Z"])
    np.save(_path(cfg, "io.out_labels_npy", out_dir), y.astype(np.int64))
    io_utils.write_json(_path(cfg, "io.out_scaler_json", out_dir), {
        "kind": "zscore",
        "fit_on": "train %d 行（分层切分，seed=%d）"
                  % (b["diag"]["train_rows"], cfg.seed),
        "leak_guard": b["diag"]["leak_guard"],
        "features": names[:b["primary_n"]],
        "mean": [round(float(v), 8) for v in b["mu"]],
        "std": [round(float(v), 8) for v in b["sd"]]})
    io_utils.write_csv_rows(_path(cfg, "io.out_feature_dict_csv", out_dir),
                            b["dict_rows"],
                            fields=["名称", "族", "公式", "物理含义", "单位",
                                    "参考量程", "实测范围"])
    io_utils.write_text(_path(cfg, "io.out_feature_dict_md", out_dir),
                        markdown_dict(b["dict_rows"]))
    if b["with_plot"]:
        p = plot_boxplot(_path(cfg, "io.out_boxplot", out_dir), F, y,
                         b["top_names"], names)
        if p:
            b["plots"]["boxplot"] = _rel(p)
        p = plot_corr_heatmap(_path(cfg, "io.out_corr_heatmap", out_dir), b["R"],
                              names, cfg.f("redundancy.corr_threshold"))
        if p:
            b["plots"]["corr_heatmap"] = _rel(p)
    return b["plots"]


def _fmt(v, nd=4):
    return "NA" if v is None else ("%." + str(nd) + "f") % float(v)


def markdown_dict(rows):
    """特征字典 Markdown（工单五列规范 + 族别 + 本次运行实测范围）。"""
    head = ["名称", "族", "公式", "物理含义", "单位", "参考量程", "实测范围"]
    out = ["# 特征字典（P2.2 · 30 主特征 + 5 衍生特征）", "",
           "> 工单工程要求第 2 条「五列规范」= 名称/公式/含义/单位/范围；",
           "> 本表另附「族」与「实测范围」两列，实测值取自本次运行的真实特征矩阵。",
           "",
           "| " + " | ".join(head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r[h]).replace("|", "\\|") for h in head) + " |")
    return "\n".join(out) + "\n"


def outputs_list(b):
    """产物清单（名字 + 字节数）；自指的 report.txt / result.json 不写大小。

    自指两格无条件列出：它们正是本次运行要写出的文件，若按"磁盘上是否已存在"决定
    列不列，第一次运行（报告尚未生成）与第二次运行（上一份还在）的清单长度就会不同，
    等于把"二次运行逐字节一致"这条闸门锁死在第二次以后——先删后跑也会漂。
    """
    cfg, out_dir = b["cfg"], b["out_dir"]
    keys = ["io.out_features_csv", "io.out_features_npy", "io.out_labels_npy",
            "io.out_scaler_json", "io.out_feature_dict_csv",
            "io.out_feature_dict_md", "io.out_boxplot", "io.out_corr_heatmap",
            "io.out_result_json", "io.out_report"]
    lines = []
    for k in keys:
        p = _path(cfg, k, out_dir)
        if k in _SELF:
            lines.append("%-42s （本文件，不写自身字节数）" % _rel(p))
            continue
        if not os.path.exists(p):
            continue
        lines.append("%-42s %9d B" % (_rel(p), os.path.getsize(p)))
    tp = _resolve_path(cfg, "io.out_timing_json")
    if os.path.exists(tp):
        # 只列路径不列字节数：timing.json 每次实测都会刷新，写大小会让 output/ 报告漂移
        lines.append("%-42s %s"
                     % (_timing_display(cfg),
                        "墙钟时长在此（output/ 之外，字节数不计入本清单）"))
    return lines


# ------------------------------------------------------------------ 分层台账（报告行）
def ledger(b):
    """把 build() 的实测数字整理成报告行——无一行是手写常量。"""
    cfg, meta, names, F, y = b["cfg"], b["meta"], b["names"], b["F"], b["y"]
    a16, imp, order = b["a16"], b["imp"], b["order"]
    alarms, diag = b["alarms"], b["diag"]
    target, excellent = cfg.f("perf.target_ms"), cfg.f("perf.excellent_ms")
    best = b["best_ms"]
    verdict = "达标" if best <= target else "未达标"
    n = int(F.shape[0])
    kurt = names.index("kurtosis")
    has0, has1 = int((y == 0).sum()), int((y == 1).sum())
    kn = float(np.median(F[y == 0, kurt])) if has0 else None
    kf = float(np.median(F[y == 1, kurt])) if has1 else None
    a16n = float(np.median(F[y == 0, a16])) if has0 else None
    a16f = float(np.median(F[y == 1, a16])) if has1 else None
    ratio = (_fmt(a16f / max(a16n, 1e-12), 2) if (has0 and has1) else "NA")
    red = float(np.abs(b["R"] - np.diag(np.diag(b["R"]))).max())
    fam = (len(core.TIME_FEATS), len(core.FREQ_FEATS), len(core.STAT_FEATS),
           len(core.DERIVED_FEATS))
    thr = b["thr"]
    vec = b["vec"]
    rp = b["red_pairs"]
    timing_rel = _timing_display(cfg)

    # ---- 分层达标证据（工单 cell-0 的 ABCD 四级；每条都是可证伪的真实数字）
    exact_ids = [x for x in b["identities"] if x[2] == core.IDENTITY_TOL]
    parseval = [x for x in b["identities"] if x[2] == core.PARSEVAL_TOL][0]
    id_dev = max(x[1] for x in exact_ids)
    id_ok = all(x[3] for x in exact_ids) and parseval[3]
    dup = len(names) - len(set(names))
    waveform = fam[0] + fam[2]           # 工单口径的"时域 15" = 时域 10 + 统计 5
    meaning_blank = sum(1 for r in b["dict_rows"] if not str(r["物理含义"]).strip())
    heat, boxp = b["plots"].get("corr_heatmap"), b["plots"].get("boxplot")
    partition_ok = len(b["kept"]) + len(b["dropped"]) == b["primary_n"]
    explain_ok = bool(b["dropped"]) and all(
        {"feature", "kept", "abs_r"} <= set(d) and float(d["abs_r"]) >= thr - 5e-5
        for d in b["dropped"])
    tiers = {"D": bool(id_ok and np.isfinite(F).all() and n > 0),
             "C": bool(len(core.PRIMARY_FEATS) == b["primary_n"] and dup == 0
                       and len(core.FREQ_FEATS) == fam[1] and vec["ok"]),
             "B": bool(best <= target and meaning_blank == 0
                       and len(b["dict_rows"]) == len(names)),
             "A": bool(heat and partition_ok and explain_ok
                       and rp["primary"] >= len(b["dropped"])
                       and (rp["primary"] == 0 or len(b["dropped"]) > 0))}
    passed = [k for k in "DCBA" if tiers[k]]
    unmet = [k for k in "DCBA" if not tiers[k]]
    if not vec["enabled"]:
        vec_clause = ("向量化：静态检查已被关闭（config: vectorization.enabled=false）"
                      "⇒ C 层口径无证据")
    else:
        vec_clause = ("向量化：AST 扫描 %d 个特征函数（config: vectorization.targets 共 %d）"
                      "⇒ 逐样本 for/while/推导式 %d 处｜特征名注册表级循环 %d 处（%s，"
                      "次数=特征数 %d、与样本量无关）｜清单里找不到的目标函数 %d 个"
                      % (len(vec["scanned"]), len(vec["targets"]),
                         vec["n_forbidden"], vec["n_registry"],
                         " + ".join(sorted({v["func"].split(".")[-1]
                                           for v in vec["registry_loops"]})) or "无",
                         len(core.PRIMARY_FEATS) + len(core.DERIVED_FEATS),
                         len(vec["missing_targets"])))
    if not passed:
        grade = "未达 D 线（学徒保底项即未通过）"
    elif not unmet:
        grade = "%s（四级全达标）" % TIER_NAME[passed[-1]]
    else:
        grade = "%s（未达标：%s）" % (TIER_NAME[passed[-1]], "/".join(unmet))

    input_lines = [
        "数据来源 : %s（config: signal.source）" % meta["source"],
        "样本矩阵 : %d 个窗口 × %d 采样点" % (n, meta["length"]),
        "采样率   : %g Hz｜奈奎斯特 %g Hz｜频率分辨率 %g Hz"
        % (cfg.f("signal.fs"), cfg.f("signal.fs") / 2.0,
           cfg.f("signal.fs") / meta["length"]),
        "基频 f0  : %g Hz｜二倍频 2·f0 = %g Hz（US-02 要找的磨损指纹就落在这条谱线上）"
        % (cfg.f("signal.f0"), cfg.f("signal.f0") * cfg.f("signal.harmonic")),
        "类别构成 : 正常 %d 窗 / 磨损 %d 窗（signal.fault_ratio=%g）"
        % (has0, has1, cfg.f("signal.fault_ratio")),
        "信号口径 : 功率守恒（1× 与 2× 共享线谱功率 %g）；随机振动 σ∈[%g,%g]；"
        "冲击幅值 %g × 发生率 %g——理由见 docs/02"
        % (cfg.f("signal.tone_power"), cfg.f("signal.noise_low"),
           cfg.f("signal.noise_high"), cfg.f("signal.impact_amp"),
           cfg.f("signal.impact_rate")),
    ]
    if meta.get("input"):
        input_lines.append("真实链输入 : %s｜sha256 %s｜物理行 %d vs pandas 逻辑行 %d"
                           % (meta["input"], meta.get("input_sha", "-"),
                              meta.get("physical_rows", -1),
                              meta.get("logical_rows", -1)))
        input_lines.append("切窗口径 : %s｜列名 %s"
                           % (meta.get("windows", "-"), ",".join(meta["columns"])))

    feature_lines = [
        "特征总数 : %d 维 = 时域 %d + 频域 %d + 统计 %d + 衍生 %d（A 层）"
        % (len(names), fam[0], fam[1], fam[2], fam[3]),
        "主特征   : %d 维，与工单《特征清单》30 维一致（config: features.primary）"
        % b["primary_n"],
        "分组口径   : 教师版 cell-0 的『时域 15 + 频域 15 = 30』= 波形域 15"
        "（时域 %d + 统计 %d，全部只吃波形）+ 频域 %d（全部吃同一次 rfft）；"
        "名单重名 %d 个" % (fam[0], fam[2], fam[1], len(names) - len(set(names))),
        "工单点名补齐项 : 峭度 kurtosis=第%s列｜脉冲指标 crest=第%s列｜"
        "裕度 clearance=第%s列｜峰峰值 ptp=第%s列｜绝对均值 abs_mean=第%s列"
        % (names.index("kurtosis"), names.index("crest"), names.index("clearance"),
           names.index("ptp"), names.index("abs_mean")),
        "公式版本 : 峭度 m4/σ⁴（非超额，正态基线 3）；峰度 = 峭度 − 3；偏度 m3/σ³；"
        "单边幅值谱 |rfft(x−x̄)|·2/N 且 DC 置零（工单避坑第 2 条）",
        "特征字典 : %d 条 × 7 列（名称/族/公式/物理含义/单位/参考量程/实测范围）→ %s"
        % (len(b["dict_rows"]), cfg.s("io.out_feature_dict_md")),
        "信息熵   : 直方图桶数 %d（上限 log2=%s bit），实测 %s ~ %s"
        % (cfg.i("features.entropy_bins"),
           _fmt(np.log2(cfg.i("features.entropy_bins")), 2),
           _fmt(b["meas"]["entropy"][0], 3), _fmt(b["meas"]["entropy"][1], 3)),
    ]

    perf_lines = [
        "计时口径 : 只计 core.extract（数据生成/落盘/训练不计，工单避坑第 3 条）；"
        "重复 %d 次取最小值" % cfg.i("perf.repeats"),
        "计算规模 : %d 窗 × %d 采样点 × %d 特征" % (n, meta["length"], len(names)),
        "验收判定 : B 层线（=工单良好(C)『1000样本<100ms』）%g ms → %s；工单优秀(B)"
        "『<50ms』档线 %g ms（perf.excellent_ms，取证见下方工单四档对照节）→ %s"
        % (target, verdict, excellent, "更快" if best <= excellent else "未更快"),
        "墙钟去向 : 时长数值（本轮各次 / 最小值 / 含取数合计）只写 %s"
        "（config: io.out_timing_json，在 output/ 之外）"
        "⇒ report.txt 与 result.json 内无任何时长数值" % timing_rel,
        "复现口径 : 无墙钟数值 ⇒ 换 PYTHONHASHSEED 重跑，output/ 逐字节一致"
        "（verify_local.py 的 repeat 闸门）",
        vector_check.summary_text(b["vec"]),
        "广播运用 : keepdims 去均值/去直流、(N,1) 行掩码、(1,B) 频率掩码、"
        "argpartition 取前 %d 大谱线（免全排序）；一次 FFT 由 Ctx 供 %d 个频域特征共享；"
        "特征列拼装用预分配 _stack"
        % (cfg.i("features.peak_orders"), len(core.FREQ_FEATS)),
    ]

    scale_lines = [
        "标准化   : Z-score 手写实现 core.zscore_fit / zscore_apply（不依赖 StandardScaler）",
        "防泄漏   : %s" % diag["leak_guard"],
        "μ 范围   : %s ~ %s｜σ 范围 : %s ~ %s（常数列 σ→1 防除零）"
        % (_fmt(float(np.min(b["mu"])), 5), _fmt(float(np.max(b["mu"])), 5),
           _fmt(float(np.min(b["sd"])), 5), _fmt(float(np.max(b["sd"])), 5)),
        "落盘口径 : features.npy = 主特征 %d×%d（原始量纲，p66 侧再标准化）；"
        "labels.npy = %d 个 int64 标签；scaler.json 存 μ/σ"
        % (n, b["primary_n"], n),
        "契约校验 : features.npy 行数 == labels.npy 长度 → %s"
        % (b["Z"].shape[0] == len(y)),
    ]

    sep_lines = [
        "轮廓系数 : %s（标准化主特征实测；>0.4 即两类清晰可分）"
        % _fmt(diag["silhouette"], 4),
        "RF 指标  : accuracy=%s｜f1=%s（分层切分 训练 %d / 测试 %d，seed=%d）"
        % (_fmt(diag["accuracy"], 4), _fmt(diag["f1"], 4), diag["train_rows"],
           diag["test_rows"], cfg.seed),
        "Fisher Top3 : " + "｜".join("%s=%s" % (names[i], _fmt(float(b["fisher"][i]), 2))
                                     for i in b["ftop"]),
        "峭度中位 : 正常 %s｜磨损 %s（B05「哨兵指标」实测，健康基线≈3）"
        % (_fmt(kn, 3), _fmt(kf, 3)),
        "a16 中位 : 正常 %s｜磨损 %s（二倍频能量迁移约 %s 倍）"
        % (_fmt(a16n, 4), _fmt(a16f, 4), ratio),
    ]

    imp_lines = ["Top%d 特征重要性（RandomForest %d 树，min_samples_leaf=%d，"
                 "输入=标准化后的 30 维主特征）："
                 % (cfg.topk, cfg.i("model.estimators"),
                    cfg.i("model.min_samples_leaf"))]
    for k in range(min(cfg.topk, len(order))):
        i = int(order[k])
        imp_lines.append("  %d. %-16s = %.4f%s"
                         % (k + 1, names[i], float(imp[i]),
                            "   ← US-02 判别指纹" if i == a16 else ""))
    imp_lines.append("US-02 判定 : %s" % b["us02"])

    alarm_lines = [
        "预警线   : 峭度 > %g → %d/%d 样本（%s%%）"
        % (alarms["warn"], alarms["预警样本"], alarms["总样本"],
           _fmt(100.0 * alarms["预警样本"] / max(alarms["总样本"], 1), 1)),
        "停机线   : 峭度 > %g → %d/%d 样本（%s%%）"
        % (alarms["danger"], alarms["停机样本"], alarms["总样本"],
           _fmt(100.0 * alarms["停机样本"] / max(alarms["总样本"], 1), 1)),
        "峭度实测 : min %s｜median %s｜max %s"
        % (_fmt(float(F[:, kurt].min()), 3), _fmt(float(np.median(F[:, kurt])), 3),
           _fmt(float(F[:, kurt].max()), 3)),
        "口径来源 : config/rules.yaml 的 warn/danger（改阈值不改代码，重跑即生效）",
    ]

    tier_lines = [
        "D层 学徒·跟做保底（%s）: 第①个留白 var 已落地为第 %d 列（二阶中心矩 m2），"
        "硬恒等式 var=std²、rms²=mean²+var、峰度=峭度−3、crest=peak/rms、"
        "shape=rms/abs_mean、cv=std/|mean| 在 %d 窗实测上的最大偏差 %.1e < %g%s；"
        "程序出结果：%d 窗 × %d 列全有限、features.csv/npy + labels.npy 已落盘 → %s"
        % (TIER_REQ["D"], names.index("var") + 1, n, id_dev, core.IDENTITY_TOL,
           "（Parseval 谱能量≈2·var 偏差 %.1e < %g）" % (parseval[1], parseval[2])
           if parseval[3] else "（Parseval 口径超差）",
           n, len(names), "达标" if tiers["D"] else "未达标"),
        "C层 操作员·基础完成（%s）: 主特征 %d = 波形域 %d（时域 %d + 统计 %d）+ 频域 %d"
        " = 工单『时域 15 + 频域 15 = 30』口径，名单重名 %d、缺列 %d；加衍生 %d 列后"
        "全表 %d 列；%s → %s"
        % (TIER_REQ["C"], b["primary_n"], waveform, fam[0], fam[2], fam[1],
           dup, len(core.PRIMARY_FEATS) - b["primary_n"], fam[3], len(names),
           vec_clause, "达标" if tiers["C"] else "未达标"),
        "B层 组长·标准达成（%s）: 特征计算 %d 窗 %s B 层线 %g ms（config: perf.target_ms）"
        "→ %s；墙钟实测 ms 只写 %s，output/ 内 report.txt/result.json 零墙钟数值；"
        "特征字典 %d 条 × 7 列，物理含义非空 %d 条（空白 %d）→ %s"
        % (TIER_REQ["B"], n, "≤" if best <= target else "＞", target, verdict,
           timing_rel, len(b["dict_rows"]), len(b["dict_rows"]) - meaning_blank,
           meaning_blank, "达标" if tiers["B"] else "未达标"),
        "A层 师傅·进阶拓展（%s）: 相关系数矩阵 %d×%d 热力图 %s；主特征域 %d 列两两共 %d 对，"
        "其中 |r|≥%.2f 的冗余对 %d 对（全表 35×35 口径 %d 对）⇒ 剔除 %d 个、保留 %d 个"
        "（保留+剔除=%d，参与去冗余的是主特征，衍生 %d 列由主特征组合故不再剔）；"
        "取舍口径=%s（config: redundancy.keep），每个剔除项都带 kept 赢家与 |r| 证据"
        "（严格恒等 |r|=1 的对 %d 对，如 kurtosis↔kurtosis_excess）→ %s"
        % (TIER_REQ["A"] % thr, len(names), len(names), heat or "未生成（--no-plot）",
           b["primary_n"], rp["total_pairs"], thr, rp["primary"], rp["all"],
           len(b["dropped"]), len(b["kept"]), b["primary_n"], fam[3],
           "RF 重要性降序优先保留" if cfg.s("redundancy.keep") == "importance"
           else "清单顺序优先保留", rp["exact_one"],
           "达标" if tiers["A"] else "未达标"),
        "等级判定 : %s" % grade,
    ]

    # ---- 工单 P2.2 验收表逐档对照（及格/良好/优秀/超优）：本节只判测得到的，测不到的点名说明
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _docs = os.path.join(_root, "docs")
    docs_n = len([f for f in os.listdir(_docs) if f.endswith(".md")]) \
        if os.path.isdir(_docs) else 0
    wo_b = bool(best <= excellent and boxp and docs_n >= 8)
    wo = {
        "D": bool(b["primary_n"] == len(core.PRIMARY_FEATS) and dup == 0 and vec["ok"]),
        "C": bool(best <= target and meaning_blank == 0),
        "B": wo_b,
        # 工单超优行原文是"优秀+…"，所以 B 档的实测项是 A 档的前置条件：
        # 只把 <50ms 这条线挪一挪，就会同时翻掉优秀与超优两档。
        "A": bool(wo_b and partition_ok and explain_ok
                  and len(core.DERIVED_FEATS) == fam[3]),
    }
    wo_ext = {
        "D": ["标准化正确（μ/σ 仅训练段估计，见 fit_model 与 docs/03 §2.4）",
              "PEP 8≥75%（本项目未内置 PEP 8 子集检查，由教师/CI 侧 lint 取证）"],
        "C": [],
        "B": ["广播运用充分（AST 向量化闸门证明无逐样本循环，但广播写法本身不属该闸门）"],
        "A": ["优秀档的前置项（与 B 档同源，见上一行）"],
    }
    wo_lines = [
        "工单及格(D)「%s」: 主特征 %d/%d、重名 %d、缺列 %d｜向量化 AST 扫描 %d 个特征"
        "函数逐样本循环 %d 处 → 本节实测项 %s｜未实测项：%s"
        % (WO_ROW["D"], b["primary_n"], len(core.PRIMARY_FEATS), dup,
           len(core.PRIMARY_FEATS) - b["primary_n"], len(vec["scanned"]),
           vec["n_forbidden"], "通过" if wo["D"] else "未通过",
           "；".join(wo_ext["D"])),
        "工单良好(C)「%s」: %d 窗 %s C 档线 %g ms"
        "（config: perf.target_ms，实测毫秒只写 runtime/timing.json 以免破坏 output/ 逐字节复现）"
        "｜特征字典 %d 条物理含义空白 %d 条 → %s"
        % (WO_ROW["C"], n, "≤" if best <= target else "＞", target,
           len(b["dict_rows"]), meaning_blank, "达标" if wo["C"] else "未达标"),
        "工单优秀(B)「%s」: 实测 %s B 档线 %g ms"
        "（config: perf.excellent_ms）｜箱线图 %s｜docs/ 过程文档 %d 篇 → 本节实测项 %s"
        "｜未实测项：%s"
        % (WO_ROW["B"], "≤" if best <= excellent else "＞", excellent,
           boxp or "未生成（--no-plot）", docs_n,
           "通过" if wo["B"] else "未通过", "；".join(wo_ext["B"])),
        "工单超优(A)「%s」: 前置优秀档=%s｜衍生 %d/%d 列｜"
        "去冗余 保留 %d + 剔除 %d = 主特征 %d（分区完整=%s）｜剔除项均带 kept 赢家与 |r| 证据"
        "=%s → 本节实测项 %s｜未实测项：%s"
        % (WO_ROW["A"], "达标" if wo["B"] else "未达标",
           fam[3], len(core.DERIVED_FEATS), len(b["kept"]),
           len(b["dropped"]), b["primary_n"], partition_ok, explain_ok,
           "通过" if wo["A"] else "未通过", "；".join(wo_ext["A"])),
        "档位口径说明 : 课堂阶梯（D 跟做保底 / C 基础完成 / B 标准达成 / A 进阶拓展）与工单"
        "四档（及格/良好/优秀/超优）字母不同源——课堂 C 层≈工单及格、课堂 B 层≈工单良好，"
        "工单优秀档只在本节取证；本节的「%s」按实测项判定，未实测项一律点名而不下结论。"
        % ("四档实测项全部通过" if all(wo.values()) else "部分实测项未通过"),
    ]

    red_lines = [
        "去冗余明细 : %s" % ("；".join("%s↔%s |r|=%s"
                                  % (d["feature"], d["kept"], d["abs_r"])
                                  for d in b["dropped"][:cfg.topk]) or "无冗余对"),
        "剔除全清单 : %s" % ("、".join(d["feature"] for d in b["dropped"]) or "无"),
        "保留全清单 : %s" % ("、".join(names[i] for i in b["kept"])),
        "阈值口径   : |r| ≥ %g 即判冗余（含等号，config: redundancy.corr_threshold）；"
        "矩阵最大非对角 |r|=%s" % (thr, _fmt(red, 16)),
        "相关热力图 : %s" % (heat or "未生成（--no-plot 或无 matplotlib）"),
        "讲解要点   : 恒等式对（|r|=1，如 kurtosis↔kurtosis_excess）至多留一个"
        "（后入场者必被判冗余）；高相关但不恒等的对（如 ptp↔peak）按优先级取舍，"
        "redundancy.keep=importance 时重要性低的一方出局、=rank 时列号大的一方出局",
    ]
    return {"input": input_lines, "features": feature_lines, "perf": perf_lines,
            "scale": scale_lines, "separation": sep_lines,
            "importance": imp_lines, "alarm": alarm_lines, "tier": tier_lines,
            "workorder": wo_lines, "workorder_tiers": {k: bool(wo[k]) for k in "DCBA"},
            "workorder_docs": docs_n, "workorder_dict_blank": meaning_blank,
            "workorder_unmeasured": wo_ext,
            "redundancy": red_lines, "tiers": tiers,
            "verdict": verdict, "grade": grade, "best": best, "target": target,
            "excellent": excellent, "us02": b["us02"], "a16_rank": b["a16_rank"],
            "dropped": len(b["dropped"]), "kept": len(b["kept"]),
            "red_pairs": rp, "vectorization": vec, "identities": exact_ids,
            "parseval": parseval,
            "alarms": alarms, "n": n, "red": red}


def sections(b, bx=None):
    bx = bx or ledger(b)
    return [
        ("1 输入与信号口径", bx["input"]),
        ("2 特征清单对账（时域10 + 频域15 + 统计5 + 衍生5）", bx["features"]),
        ("3 性能与向量化口径（只计特征计算，墙钟数值不入 output/）", bx["perf"]),
        ("4 标准化与防泄漏（B07）", bx["scale"]),
        ("5 类间可分性实测", bx["separation"]),
        ("6 特征重要性 Top%d 与 US-02 判定" % b["cfg"].topk, bx["importance"]),
        ("7 峭度工艺红线（warn/danger）", bx["alarm"]),
        ("8 分层达标（工单 P2.2 学徒/操作员/组长/师傅四级，逐条可证伪）", bx["tier"]),
        ("8.5 工单验收四档对照（及格/良好/优秀/超优）", bx["workorder"]),
        ("9 A 层去冗余明细与取舍说明", bx["redundancy"]),
        ("10 输出清单", outputs_list(b)),
        ("11 结论与建议", conclusion(bx)),
    ]


def conclusion(bx):
    vec = bx["vectorization"]
    return [
        "1) 特征设计决定模型上限：%s；把 a16 做成看板指标可直接支撑松动/磨损预警。"
        % bx["us02"],
        "2) 性能判定：特征计算落在 B 层线 %g ms 以内 → %s，等级 %s；"
        "具体时长只写 runtime/timing.json（output/ 之外），本报告不出现任何墙钟数值。"
        % (bx["target"], bx["verdict"], bx["grade"]),
        "3) 去冗余剔除 %d 个高相关特征、保留 %d 个（|r|≥阈值的主特征对 %d 对）："
        "建模阶段改用保留集可同时降低共线性与训练成本。"
        % (bx["dropped"], bx["kept"], bx["red_pairs"]["primary"]),
        "4) 工艺红线：峭度预警 %d 个 / 停机 %d 个样本（共 %d），可作为在线监测触发条件。"
        % (bx["alarms"]["预警样本"], bx["alarms"]["停机样本"], bx["n"]),
        "5) C 层向量化口径已被静态检查证明（非文案）：AST 扫描 %d 个特征函数、"
        "逐样本 for/while/推导式 %d 处、注册表级循环 %d 处 ⇒ %s。"
        % (len(vec["scanned"]), vec["n_forbidden"], vec["n_registry"],
           "达标" if vec["ok"] else "未达标"),
    ]


def result_json(b, bx=None):
    cfg = b["cfg"]
    bx = bx or ledger(b)
    vec = bx["vectorization"]
    thr = cfg.f("redundancy.corr_threshold")
    return {
        "input": b["meta"], "samples": int(b["F"].shape[0]),
        "signal_length": int(b["meta"]["length"]),
        "features": {"primary": b["primary_n"], "derived": cfg.i("features.derived"),
                     "total": len(b["names"]),
                     "families": {"time": list(core.TIME_FEATS),
                                  "freq": list(core.FREQ_FEATS),
                                  "stat": list(core.STAT_FEATS),
                                  "derived": list(core.DERIVED_FEATS)},
                     "names": b["names"],
                     "measured_range": {k: [round(v[0], 6), round(v[1], 6)]
                                        for k, v in b["meas"].items()}},
        # 墙钟红线：本段只有阈值与判定，实测 ms 一律留在 runtime/timing.json
        "perf": {"target_ms": cfg.f("perf.target_ms"),
                 "excellent_ms": cfg.f("perf.excellent_ms"),
                 "repeats": cfg.i("perf.repeats"),
                 "samples": int(b["F"].shape[0]),
                 "feature_cols": len(b["names"]),
                 "verdict": bx["verdict"],
                 "within_target": bool(b["best_ms"] <= cfg.f("perf.target_ms")),
                 "timing_json": _timing_display(cfg),
                 "note": "墙钟时长（本轮各次、最小值、含取数合计）只写 "
                         "io.out_timing_json 指向的 runtime/timing.json；"
                         "本文件与 report.txt 不含任何时长数值"},
        "tiers": bx["tiers"], "grade": bx["grade"],
        "workorder_tiers": bx["workorder_tiers"],
        "workorder_rows": dict(WO_ROW),
        "workorder_evidence": {"docs_md": bx["workorder_docs"],
                               "derived": int(cfg.i("features.derived")),
                               "primary": b["primary_n"],
                               "dict_blank_meaning": bx["workorder_dict_blank"]},
        "workorder_unmeasured": bx["workorder_unmeasured"],
        "tier_requirements": {k: (TIER_REQ[k] % thr if k == "A" else TIER_REQ[k])
                              for k in "DCBA"},
        "identities": [{"check": t, "max_abs_dev": d, "tol": tol, "ok": ok}
                       for t, d, tol, ok in b["identities"]],
        "vectorization": {
            "enabled": vec["enabled"], "ok": vec["ok"], "status": vec["status"],
            "n_targets": len(vec["targets"]), "n_scanned": len(vec["scanned"]),
            "n_forbidden": vec["n_forbidden"], "n_registry": vec["n_registry"],
            "missing_targets": vec["missing_targets"],
            "violations": [{k: v[k] for k in ("func", "line", "kind", "iterable",
                                              "reason", "feature_names")}
                           for v in vec["violations"]],
            "registry_loops": [{k: v[k] for k in ("func", "line", "kind",
                                                  "iterable", "hits")}
                               for v in vec["registry_loops"]],
            "summary": vector_check.summary_text(vec)},
        "model": b["diag"],
        "separation": {"silhouette": round(b["diag"]["silhouette"], 4),
                       "accuracy": round(b["diag"]["accuracy"], 4),
                       "f1": round(b["diag"]["f1"], 4),
                       "fisher_top3": [(b["names"][int(i)],
                                        round(float(b["fisher"][int(i)]), 3))
                                       for i in b["ftop"]]},
        "importance_top": [(b["names"][int(i)], round(float(b["imp"][int(i)]), 4))
                           for i in b["order"][:cfg.topk]],
        "us02_a16": {"rank": b["a16_rank"],
                     "importance": round(float(b["imp"][b["a16"]]), 4),
                     "verdict": b["us02"]},
        "redundancy": {"threshold": thr,
                       "keep_rule": cfg.s("redundancy.keep"),
                       "scope": "主特征 %d 列参与（衍生 %d 列由主特征组合，不重复剔）"
                                % (b["primary_n"], len(core.DERIVED_FEATS)),
                       "pair_counts": bx["red_pairs"],
                       "kept": [b["names"][i] for i in b["kept"]],
                       "dropped": b["dropped"],
                       "max_offdiag_abs_r": round(bx["red"], 16)},
        "kurtosis_alarm": b["alarms"], "outputs": outputs_list(b),
    }


def run(cfg=None, out_dir=None, input_path=None, with_plot=True, quiet=False,
        stamp=None):
    cfg = cfg or cfg_mod.load_config(os.path.join(ROOT, "config/rules.yaml"))
    b = build(cfg, out_dir=out_dir, input_path=input_path, with_plot=with_plot)
    write_outputs(b)                       # 先落盘，plots 路径才能进台账与清单
    # 墙钟文件必须在 result.json / report.txt 之前落盘：§10 产物清单按"文件是否存在"
    # 列出它，先写就能保证"第一次运行"与"第二次运行"的清单逐字节一致（否则首次少一行）
    io_utils.write_json(_resolve_path(cfg, "io.out_timing_json"), b["timing"])
    bx = ledger(b)                         # 台账（分层达标判定）只算一次
    io_utils.write_json(_path(cfg, "io.out_result_json", b["out_dir"]),
                        result_json(b, bx))
    secs = sections(b, bx)
    text = report.save(secs, _path(cfg, "io.out_report", b["out_dir"]), stamp=stamp)
    return {"sections": secs, "text": text, "ledger": bx, "build": b,
            "report_path": _path(cfg, "io.out_report", b["out_dir"]),
            "outputs": outputs_list(b)}


def formula_demo(cfg=None, limit=None):
    """课前导学单第 3 条：打印「公式 → NumPy 一行」翻译表（starter 示例实现的可读版）。

    数据全部来自 core.META 注册表——它与 extract_* 的实现同源，所以打印的就是
    真正跑的那套公式，不会出现"文档一套、代码一套"。
    """
    cfg = cfg or cfg_mod.load_config(os.path.join(ROOT, "config/rules.yaml"))
    names = list(core.PRIMARY_FEATS) + list(core.DERIVED_FEATS)
    if limit:
        names = names[:limit]
    out = ["公式 → NumPy 一行（共 %d 条，本次打印 %d 条；禁 Python 层逐样本循环）："
           % (len(names), len(names))]
    for n in names:
        formula, meaning, unit, ref = core.META[n]
        out.append("  %-16s %-28s 单位%-4s %s" % (n, formula, unit, meaning))
    out.append("决策矩阵：纯向量化(禁循环)=快/风险低 → 采用；apply 逐样本=慢/索引易错 → 弃用")
    return "\n".join(out)


def peek(cfg=None, lines=16):
    """只读输入并打印口径速览（C 层「先看清数据再动手」），不写任何文件。"""
    cfg = cfg or cfg_mod.load_config(os.path.join(ROOT, "config/rules.yaml"))
    X, y, meta = load_signals(cfg, None)
    F, names = core.extract(X, fs=cfg.f("signal.fs"), f0=cfg.f("signal.f0"),
                            harmonic=cfg.f("signal.harmonic"),
                            entropy_bins=cfg.i("features.entropy_bins"))
    out = ["输入 : %s｜矩阵 %d × %d｜正常 %d 窗 / 磨损 %d 窗"
           % (meta["source"], X.shape[0], X.shape[1],
              int((y == 0).sum()), int((y == 1).sum()))]
    if meta.get("input"):
        out.append("文件 : %s｜sha256 %s｜列 %s"
                   % (meta["input"], meta.get("input_sha"),
                      ",".join(meta["columns"])))
        out.append("切窗 : %s" % meta.get("windows"))
    out.append("采样口径 : fs=%g Hz｜分辨率 %g Hz｜f0=%g｜2·f0=%g"
               % (cfg.f("signal.fs"), cfg.f("signal.fs") / meta["length"],
                  cfg.f("signal.f0"),
                  cfg.f("signal.f0") * cfg.f("signal.harmonic")))
    out.append("首窗前 6 个采样点 : %s" % " ".join(_fmt(v, 4) for v in X[0, :6]))
    out.append("末窗前 6 个采样点 : %s" % " ".join(_fmt(v, 4) for v in X[-1, :6]))
    out.append("特征 : %d 维（主 %d + 衍生 %d）；全为有限值 = %s"
               % (len(names), cfg.i("features.primary"), len(core.DERIVED_FEATS),
                  bool(np.isfinite(F).all())))
    std_rank = np.argsort(-F.std(axis=0))[:cfg.topk]
    out.append("离散度 Top%d（预览，正式排名见 §6 RF 重要性）: %s"
               % (cfg.topk, ", ".join("%s=%s" % (names[i], _fmt(F[:, i].std(), 4))
                                      for i in std_rank)))
    out.append("峭度中位 %s｜a16 中位 %s｜信息熵中位 %s"
               % (_fmt(float(np.median(F[:, names.index("kurtosis")])), 3),
                  _fmt(float(np.median(F[:, names.index("a16")])), 4),
                  _fmt(float(np.median(F[:, names.index("entropy")])), 3)))
    out.append("(peek 只读不写：不生成 output/ 下任何文件)")
    return "\n".join(out[:lines])
