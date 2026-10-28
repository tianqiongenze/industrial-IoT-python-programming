# -*- coding: utf-8 -*-
"""七步清洗管道的领域逻辑（纯函数，零 IO，逐步返回台账）。

管道执行序（B07 清洗顺序：类型→缺失→异常→去重，顺序即依赖）：
    TODO-1 摸底/EDA → TODO-3 类型转换 → TODO-2 缺失处理 → TODO-4 异常检测
    → TODO-5 去重 → 自定义规则(A层) → TODO-6 质量校验 → TODO-7 输出(pipeline 层)
每个函数返回 (df, audit)；audit 含"操作 + 行数变化 + 决策理由"三要素（A 层留痕要求）。
所有阈值/列名/策略来自 Settings（config/rules.yaml），代码内不写死业务数。
"""
import datetime as _dt
import random

import numpy as np
import pandas as pd


class PipelineError(RuntimeError):
    """管道结构性失败（缺列 / 表达式非法）。"""


class QualityError(AssertionError):
    """TODO-6 质量校验未通过（区间越界、时间类型错等）。"""


def _audit(no, name, action, reason, rows_in, rows_out, detail=None):
    """构造一条台账（A 层：操作/行数/理由三要素齐全）。"""
    return {"no": no, "step": name, "action": action, "reason": reason,
            "rows_in": int(rows_in), "rows_out": int(rows_out),
            "removed": int(rows_in - rows_out),
            "detail": list(detail or [])}


# ---------------------------------------------------------------- 脏数据生成
def generate_raw(n=1200, seed=2026):
    """合成与课程 p21_raw.csv 同口径的脏表（缺失/N/A/越界/重复/三种时间格式）。

    用途：①单测夹具；②A 层 100 万行压测数据源。课堂清洗走真实 CSV，不走这里。
    """
    rng = random.Random(seed)
    fmts = ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y%m%d%H%M%S"]
    rows = []
    start = _dt.datetime(2026, 3, 1)
    for i in range(n):
        t = round(rng.uniform(45, 85), 2)
        if i % 37 == 0:
            t = ""
        if i % 53 == 0:
            t = "N/A"
        if i % 89 == 0:
            t = round(rng.uniform(125, 150), 1)
        ts = (start + _dt.timedelta(minutes=i * 30)).strftime(
            fmts[i % 3 == 0 and 0 or (1 if i % 7 == 0 else 2)])
        row = [f"DEV-{i % 4 + 1:02d}", ts, t, round(rng.uniform(.3, .6), 2), "RUN"]
        rows.append(row)
        if i % 211 == 5:                                # 重复采集行
            rows.append(list(row))
    return pd.DataFrame(rows, columns=["device_id", "ts", "temp", "press", "status"])


# --------------------------------------------------------------- TODO-1 摸底
def inspect_schema(df, cfg):
    """TODO-1 摸底/EDA：规模、列类型、逐列缺失率、重复普查、时间格式普查。

    缺必需列直接拒收——"先摸底再动手不盲洗"。
    """
    required = cfg.lst("pipeline.required_columns")
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise PipelineError("输入缺少必需列: %s（现有列: %s）"
                            % (missing_cols, list(df.columns)))
    n = len(df)
    miss_ratio = df.isna().mean()
    detail = [f"规模: {n} 行 × {df.shape[1]} 列",
              f"列类型: " + ", ".join(f"{c}={df[c].dtype}" for c in df.columns),
              f"逐列缺失数: " + ", ".join(f"{c}={int(df[c].isna().sum())}" for c in df.columns),
              f"逐列缺失率: " + ", ".join(f"{c}={miss_ratio[c]:.2%}" for c in df.columns),
              f"整行重复 {int(df.duplicated().sum())} 行；"
              f"语义重复[{','.join(cfg.lst('pipeline.dedupe_subset'))}] "
              f"{int(df.duplicated(subset=cfg.lst('pipeline.dedupe_subset'), keep=False).sum())} 行",
              f"数值列极值: " + ", ".join(
                  f"{c}={pd.to_numeric(df[c], errors='coerce').min():.2f}"
                  f"~{pd.to_numeric(df[c], errors='coerce').max():.2f}"
                  for c in cfg.lst("pipeline.numeric_columns"))]
    fmt_census = ts_format_census(df[cfg.s("pipeline.ts_column")],
                                 cfg.lst("pipeline.ts_formats"))
    detail.append("时间戳格式普查: " + ", ".join(
        f"{f or '其它'}={c}" for f, c in fmt_census.items()))
    top_missing = [(c, float(miss_ratio[c])) for c in
                   miss_ratio.sort_values(ascending=False).head(cfg.topk).index]
    detail.append(f"缺失率 Top{cfg.topk}: " + ", ".join(
        f"{c}={r:.2%}" for c, r in top_missing))
    audit = _audit(1, "TODO-1 摸底", "shape/info/describe/duplicated 四板斧体检 + 格式普查",
                   "先搞清'哪里脏、脏多少、什么型'再定策略，禁止进门就 dropna",
                   n, n, detail)
    return df.copy(), audit


def ts_format_census(series, formats):
    """按配置的时间格式统计各命中条数（摸底用；未命中归入 '(其它)'）。"""
    counts = {}
    rest = series.notna()
    for f in formats:
        parsed = pd.to_datetime(series, format=f, errors="coerce")
        counts[f] = int((parsed.notna() & rest).sum())
        rest = rest & parsed.isna()
    counts["(其它)"] = int(rest.sum())
    return counts


# ------------------------------------------------------------ TODO-3 类型转换
def convert_types(df, cfg):
    """TODO-3：temp/press→数值（errors=coerce），ts→datetime（三格式 combine_first）。

    顺序要点：先转型把 'N/A'/'' 变成 NaN，后续缺失策略才看得见它们。
    """
    n = len(df)
    out = df.copy()
    detail = []
    for col in cfg.lst("pipeline.numeric_columns"):
        if col not in out.columns:
            continue
        bad = int((out[col].astype(str).str.strip().isin(["N/A", "", "nan", "NaN", "None"])).sum())
        out[col] = pd.to_numeric(out[col], errors="coerce")
        detail.append(f"{col}→float64（原非法字面量 {bad} 个转 NaN），"
                      f"有效 {int(out[col].notna().sum())} 值")
    ts_col = cfg.s("pipeline.ts_column")
    formats = cfg.lst("pipeline.ts_formats")
    parts = [pd.to_datetime(out[ts_col], format=f, errors="coerce") for f in formats]
    ts = parts[0]
    for q in parts[1:]:
        ts = ts.combine_first(q)                       # 主解析失败则借下一格式的解
    bad_ts = int(ts.isna().sum())
    out[ts_col] = ts
    detail.append(f"{ts_col}→datetime（{len(formats)} 种格式各解一次后 combine_first 合并），"
                  f"无法解析 {bad_ts} 条")
    id_col = cfg.s("pipeline.id_column")
    if id_col in out.columns:
        before = int((out[id_col].astype(str) != out[id_col].astype(str).str.strip()).sum())
        out[id_col] = out[id_col].astype(str).str.strip()
        detail.append(f"{id_col}→str 并 strip（含空白 {before} 条）；"
                      f"格式[{cfg.s('pipeline.id_pattern')}] 命中 "
                      f"{int(out[id_col].str.match(cfg.s('pipeline.id_pattern')).sum())} 条")
    st_col = cfg.s("pipeline.status_column")
    if st_col in out.columns:
        allowed = cfg.lst("pipeline.status_allowed")
        unknown = int((~out[st_col].astype(str).isin(allowed) & out[st_col].notna()).sum())
        detail.append(f"{st_col} 类别值 {sorted(set(out[st_col].dropna().astype(str)))}，"
                      f"非白名单 {unknown} 条（白名单 {allowed}）")
    audit = _audit(2, "TODO-3 类型转换", "to_numeric(coerce) + to_datetime×N + combine_first",
                   "字符串比不了大小：不先转型，IQR 与区间校验全部失真",
                   n, n, detail)
    return out, audit


# ------------------------------------------------------------- TODO-2 缺失处理
def handle_missing(df, cfg):
    """TODO-2：按列型分策略补缺（插值/中位数/众数），稀疏列整列丢，最后 dropna 兜底。

    决策矩阵写进台账：整列缺失>阈值→丢列 | 时序数值→组内插值 | 类别→众数 | 兜底→dropna。
    """
    n = len(df)
    out = df.copy()
    detail = []
    strat = cfg.get("pipeline.missing_strategy", {})
    ratio_limit = cfg.f("pipeline.drop_column_missing_ratio")
    sparse = [c for c in out.columns if out[c].isna().mean() > ratio_limit]
    if sparse:
        out = out.drop(columns=sparse)
        detail.append(f"整列缺失>{ratio_limit:.0%} → 丢列 {sparse}")
    else:
        detail.append(f"无整列缺失>{ratio_limit:.0%} 的列 → 保留全部列")
    for col in strat.get("interpolate", []):
        if col not in out.columns:
            continue
        hits = int(out[col].isna().sum())
        grp = cfg.s("pipeline.id_column")
        out[col] = out.groupby(grp, sort=False)[col].transform(
            lambda s: s.interpolate(method="linear", limit_direction="both"))
        detail.append(f"{col}←设备组内线性插值：补 {hits - int(out[col].isna().sum())} 个，"
                      f"仍缺 {int(out[col].isna().sum())} 个（组内连续，不断时间轴）")
    for col in strat.get("median", []):
        if col in out.columns:
            hits = int(out[col].isna().sum())
            out[col] = out[col].fillna(out[col].median())
            detail.append(f"{col}←中位数插补 {hits} 个（抗离群，不用均值）")
    for col in strat.get("mode", []):
        if col in out.columns:
            hits = int(out[col].isna().sum())
            mode = out[col].mode(dropna=True)
            fill = mode.iloc[0] if len(mode) else strat.get("unknown_label", "UNKNOWN")
            out[col] = out[col].fillna(fill)
            detail.append(f"{col}←众数/兜底标签 '{fill}' 补 {hits} 个")
    key_cols = [c for c in cfg.lst("pipeline.dropna_columns") if c in out.columns]
    after_fill = len(out)
    out = out.dropna(subset=key_cols)
    detail.append(f"关键列 {key_cols} 仍缺 → dropna: {after_fill}→{len(out)} 行")
    detail.append(f"全表剩余缺失单元格 {int(out.isna().sum().sum())}")
    audit = _audit(3, "TODO-2 缺失处理", "丢稀疏列 + 组内插值 + 中位数 + 众数 + dropna 兜底",
                   "一律 dropna 会切断时间轴：时序数值列插值保样本，缺失本身是信息",
                   n, len(out), detail)
    return out, audit


# ------------------------------------------------------------- TODO-4 异常检测
def detect_anomalies(df, cfg):
    """TODO-4：IQR 统计护栏与业务阈值两条规则**分别计数**，再取并集处置。

    返回 (df, audit, 被剔行副本)——剔掉的行进 audit 表留痕（B06 进阶）。
    """
    n = len(df)
    detail = []
    m_stat = pd.Series(False, index=df.index)
    for col in cfg.lst("pipeline.iqr_columns"):
        if col not in df.columns:
            continue
        k = cfg.f("pipeline.iqr_k")
        q1, q3 = df[col].quantile([.25, .75])
        lo, hi = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
        hit = (df[col] < lo) | (df[col] > hi)
        m_stat |= hit
        detail.append(f"IQR[{col}] Q1={q1:.2f} Q3={q3:.2f} "
                      f"护栏[{lo:.2f},{hi:.2f}] 命中 {int(hit.sum())} 条")
    tmin, tmax = cfg.f("pipeline.temp_min"), cfg.f("pipeline.temp_max")
    pmin, pmax = cfg.f("pipeline.press_min"), cfg.f("pipeline.press_max")
    tcol, pcol = cfg.s("pipeline.temp_column"), cfg.s("pipeline.press_column")
    m_biz = ((df[tcol] < tmin) | (df[tcol] > tmax)
             | (df[pcol] < pmin) | (df[pcol] > pmax))
    detail.append(f"业务阈值 {tcol}∈[{tmin},{tmax}] {pcol}∈[{pmin},{pmax}] "
                  f"命中 {int(m_biz.sum())} 条")
    m_all = m_stat | m_biz
    both = int((m_stat & m_biz).sum())
    detail.append(f"统计嫌疑 {int(m_stat.sum())} ∪ 业务定罪 {int(m_biz.sum())} "
                  f"= 并集 {int(m_all.sum())} 条（双章齐 {both} 条，仅统计嫌疑 "
                  f"{int((m_stat & ~m_biz).sum())} 条，仅业务越界 "
                  f"{int((~m_stat & m_biz).sum())} 条）")
    dropped = df[m_all].copy()
    dropped["hit_stat"] = m_stat[m_all]
    dropped["hit_business"] = m_biz[m_all]
    if cfg.s("pipeline.outlier_action") == "clip":
        out = df.copy()
        out["temp"] = out["temp"].clip(tmin, tmax)
        out["press"] = out["press"].clip(pmin, pmax)
        detail.append("动作=clip：收敛到护栏，保住行数")
        action = "IQR/阈值并集→clip"
    else:
        out = df[~m_all].copy()
        action = "IQR/阈值并集→剔行"
        detail.append("动作=remove：剔行（教师版口径）")
    audit = _audit(4, "TODO-4 异常检测", action,
                   "统计法找嫌疑、业务阈值定罪，两条都过才判异常；"
                   "只用统计法会把真实工艺尖峰当噪声洗掉",
                   n, len(out), detail)
    return out, audit, dropped


# ---------------------------------------------------------------- TODO-5 去重
def dedupe(df, cfg):
    """TODO-5：语义去重（同设备同时刻 = 一次采集的重复上报），非整列去重。"""
    n = len(df)
    subset = cfg.lst("pipeline.dedupe_subset")
    keep = cfg.s("pipeline.dedupe_keep")
    exact = int(df.duplicated().sum())
    out = df.drop_duplicates(subset=subset, keep=keep)
    audit = _audit(5, "TODO-5 去重",
                   f"drop_duplicates(subset={subset}, keep={keep})",
                   f"整列去重只删 {exact} 行；按[{','.join(subset)}]语义去重才能识别"
                   f"'同ID不同写法的时间戳'，且先去重后算统计量才不被重复干扰",
                   n, len(out),
                   [f"整行重复 {exact} 行 → 语义重复共删 {n - len(out)} 行"])
    return out, audit


# --------------------------------------------------- A 层：自定义验证规则（配置）
def apply_custom_rules(df, cfg):
    """A 层拓展：业务侧追加规则，写在 YAML 里（df.query 语法），代码零改动。"""
    n = len(df)
    out = df
    detail = []
    for expr in cfg.lst("pipeline.custom_rules"):
        try:
            mask = out.eval(expr)
        except Exception as exc:                     # 规则写错要明确报出，不静默跳过
            raise PipelineError(f"自定义规则不可执行: {expr!r} → {exc}") from exc
        hit = int((~mask).sum())
        out = out[mask]
        detail.append(f"规则 [{expr}] 剔除 {hit} 行")
    audit = _audit(6, "自定义规则(A层)", "逐条 YAML custom_rules 求值并过滤",
                   "规则外置：新增工艺约束只改 config/rules.yaml",
                   n, len(out), detail)
    return out, audit


# ---------------------------------------------------------------- TODO-6 校验
def validate(df, cfg):
    """TODO-6：范围断言 + 时间类型 + 设备内时间单调 + ID 格式 + 唯一性。"""
    tmin, tmax = cfg.f("pipeline.temp_min"), cfg.f("pipeline.temp_max")
    pmin, pmax = cfg.f("pipeline.press_min"), cfg.f("pipeline.press_max")
    ts_col = cfg.s("pipeline.ts_column")
    id_col = cfg.s("pipeline.id_column")
    tcol = cfg.s("pipeline.temp_column")
    pcol = cfg.s("pipeline.press_column")
    checks = {
        f"{tcol}∈[{tmin},{tmax}]": bool(df[tcol].between(tmin, tmax).all()) if len(df) else True,
        f"{pcol}∈[{pmin},{pmax}]": bool(df[pcol].between(pmin, pmax).all()) if len(df) else True,
        "ts 为 datetime 型": bool(pd.api.types.is_datetime64_any_dtype(df[ts_col])),
        f"{id_col} 匹配 {cfg.s('pipeline.id_pattern')}": bool(
            df[id_col].astype(str).str.match(cfg.s("pipeline.id_pattern")).all()) if len(df) else True,
    }
    dup_rate = 0.0
    if len(df):
        dup_rate = float(df.duplicated(subset=cfg.lst("pipeline.dedupe_subset")).mean())
    checks[f"重复率≤{cfg.f('quality.max_duplicate_rate')}"] = (
        dup_rate <= cfg.f("quality.max_duplicate_rate") + 1e-12)
    if len(df):
        prev = df.groupby(cfg.s("pipeline.id_column"), sort=False)[ts_col].shift(1)
        checks["设备内时间严格递增"] = bool(((df[ts_col] > prev) | prev.isna()).all())
    else:
        checks["设备内时间严格递增"] = True
    failed = [k for k, v in checks.items() if not v]
    detail = [f"校验 {k} = {v}" for k, v in checks.items()]
    detail.append(f"重复率 {dup_rate:.4%}")
    if failed and cfg.get("pipeline.strict_validate", True):
        raise QualityError("质量校验未通过: " + ", ".join(failed))
    if failed:
        detail.append("strict_validate=false → 仅告警不中断")
    audit = _audit(8, "TODO-6 校验", "区间/类型/单调/ID/唯一性 断言",
                   "输出前的最后一道闸：断言失败即中断（strict_validate），"
                   "防止脏数据静默流向下游模型",
                   len(df), len(df), detail)
    return checks, audit, dup_rate


# ------------------------------------------------------- 工艺红线旗标（warn/danger）
def flag_process_limits(df, cfg):
    """warn/danger 工艺红线：只打旗不删行（删与不删是两回事，红线用于报警）。"""
    n = len(df)
    out = df.copy()
    tcol = cfg.s("pipeline.temp_column")
    wcol, dcol = cfg.s("pipeline.warning_column"), cfg.s("pipeline.danger_column")
    w, d = cfg.warn, cfg.danger
    out[wcol] = out[tcol] > w
    out[dcol] = out[tcol] > d
    audit = _audit(7, "工艺红线旗标", f"{tcol}>{w} 打预警旗；{tcol}>{d} 打停机旗",
                   "预警≠异常：红线区间内的统计正常值也要留给看班人员",
                   n, n,
                   [f"预警旗 {int(out[wcol].sum())} 条，"
                    f"停机旗 {int(out[dcol].sum())} 条（单位 {cfg.unit}）"])
    return out, audit


# --------------------------------------------------------------- 质量评分口径
def score(df, cfg):
    """质量分 = 完整性 + 合规性(准确性) + 一致性 + 时间性（权重来自 YAML，合计 100）。

    口径与 Jupyter 教师版 `score()` 一致，便于课堂对分；唯一性单列为硬门禁。
    """
    w = cfg.get("quality.weights")
    tcol = cfg.s("pipeline.temp_column")
    if len(df) == 0:
        return 0.0, {k: 0.0 for k in w}
    tmin, tmax = cfg.f("pipeline.temp_min"), cfg.f("pipeline.temp_max")
    t = pd.to_numeric(df[tcol], errors="coerce")
    comp = float(w["completeness"]) * (1 - float(df.isna().mean().mean()))
    acc = float(w["accuracy"]) * float(t.between(tmin, tmax).mean())
    cons = float(w["consistency"]) * float(
        df[cfg.s("pipeline.id_column")].astype(str)
        .str.match(cfg.s("pipeline.id_pattern")).mean())
    time_ = float(w["timeliness"]) if pd.api.types.is_datetime64_any_dtype(
        df[cfg.s("pipeline.ts_column")]) else 0.0
    parts = {"completeness": round(comp, 2), "accuracy": round(acc, 2),
             "consistency": round(cons, 2), "timeliness": round(time_, 2)}
    return round(comp + acc + cons + time_, 1), parts


def gate(value, cfg):
    """ABCD 门禁判定（及格85/良好88/优秀90 + 唯一性硬门禁）。"""
    g = cfg.get("quality.gates")
    return {"tier_D_pass": bool(value >= float(g["pass"])),
            "tier_C_good": bool(value >= float(g["good"])),
            "tier_B_excellent": bool(value >= float(g["excellent"])),
            "target": float(g["pass"]), "good": float(g["good"]),
            "excellent": float(g["excellent"]), "score": float(value)}


# ------------------------------------------------- 工单 P2.1 四行档位判定（重锚）
EXPECTED_AUDIT_STEPS = 8            # 七步管道台账：摸底→…→校验 共 8 条留痕


def workorder_tiers(score_gates, cfg, evidence):
    """按《P2.1 工单》验收表四行重锚的档位判定（判分仪器就是工单本身）。

    工单原文四行逐字存 `pipeline.WO_ROW`（报告第 15 节行首引用它），本函数只负责
    把每一行落成可测条件：
    D 及格＝管道完整＋质量≥quality.gates.pass＋PEP 8 子集≥pep8_pass_rate；
    C 良好＝质量≥quality.gates.good＋处理日志可复现（同进程二次运行增量一致）；
    B 优秀＝质量≥quality.gates.excellent＋PEP 8 子集≥pep8_pass_rate_high＋
    文档含使用示例（示例本体由 tests 逐字执行，防文案腐烂）；
    A 超优＝B 档达成＋增量重放与全量 clean.csv 逐字节一致＋自定义验证规则
    ＋100 万行压测达标（verdict 取 runtime/bench.json 记录，秒数不进 output/）。
    入参 score_gates 为 gate() 的分数线布尔，evidence 为 pipeline 实测证据；
    返回字典原样镜像进 result.json 的 "tiers"，报告逐档复述同一批数字。
    """
    tiers = dict(score_gates)
    pep8 = evidence["pep8"]
    pep8_score = float(pep8["score"])
    pep8_d = float(cfg.get("pep8_pass_rate", 75.0))
    pep8_b = float(cfg.get("pep8_pass_rate_high", 85.0))
    repro = bool(evidence["reproducible"]["log_reproducible"])
    usage = bool(evidence["usage"]["found"])
    replay = bool(evidence["replay"]["csv_identical"])
    custom_count = int(evidence["custom_rules"]["count"])
    bench = evidence["bench"]                                   # None=本次未压测
    bench_pass = bool(bench and bench["pass"])
    complete = (int(evidence["steps"]) >= EXPECTED_AUDIT_STEPS
                and bool(evidence["pipeline_complete"]))
    tiers.update({
        "pipeline_complete": complete,
        "pipeline_steps": int(evidence["steps"]),
        "pep8_score": pep8_score,
        "pep8_checks": [int(pep8["passed"]), int(pep8["total"])],
        "pep8_min_D": pep8_d,
        "pep8_min_B": pep8_b,
        "pep8_pass_D": bool(pep8_score >= pep8_d),
        "pep8_pass_B": bool(pep8_score >= pep8_b),
        "log_reproducible": repro,
        "log_repro_steps": int(evidence["reproducible"]["steps"]),
        "usage_example": usage,
        "usage_example_ref": evidence["usage"]["ref"],
        "incremental_matches_full": replay,
        "incremental_new_rows": int(evidence["replay"]["new_rows"]),
        "custom_rules_active": bool(custom_count > 0),
        "custom_rules_count": custom_count,
        "custom_rules_removed": int(evidence["custom_rules"]["removed"]),
        "bench_measured": bool(bench is not None),
        "bench_pass": bench_pass,
    })
    tiers["tier_D_pass"] = bool(tiers["tier_D_pass"] and complete
                                and tiers["pep8_pass_D"])
    tiers["tier_C_good"] = bool(tiers["tier_C_good"] and repro)
    tiers["tier_B_excellent"] = bool(tiers["tier_B_excellent"]
                                     and tiers["pep8_pass_B"] and usage)
    tiers["tier_A_super"] = bool(tiers["tier_B_excellent"] and replay
                                 and tiers["custom_rules_active"]
                                 and bench_pass)
    return tiers


# ------------------------------------------------- B 层：文档使用示例定位（纯函数）
USAGE_HEADING_MARK = "使用示例"


def find_usage_example(text, origin="README.md"):
    """在文档文本中定位「使用示例」标题下的 ```python 围栏代码块。

    B 层「文档含使用示例」判据：标题行含「使用示例」且其后（同节内）存在
    python 围栏块。返回 {"found", "ref"(file:line), "code"}；tests 拿同一份
    code 原文对着真实 API 执行——闸门与执行共用抽取逻辑，示例一腐烂测试就红。
    """
    lines = text.splitlines()
    heading = None
    for idx, line in enumerate(lines):
        if line.startswith("#") and USAGE_HEADING_MARK in line:
            heading = idx
            break
    if heading is None:
        return {"found": False, "ref": "", "code": "", "origin": origin}
    fence = None
    for idx in range(heading + 1, len(lines)):
        line = lines[idx]
        if line.startswith("## "):               # 出了本节仍未见围栏
            break
        if fence is None and line.strip() == "```python":
            fence = idx
            continue
        if fence is not None and line.strip() == "```":
            code = "\n".join(lines[fence + 1:idx])
            return {"found": bool(code.strip()), "origin": origin,
                    "ref": "%s:%d" % (origin, fence + 2), "code": code}
    return {"found": False, "ref": "", "code": "", "origin": origin}


# ------------------------------------------------------- A 层：三策略缺失对比
def missing_strategy_comparison(df_typed, cfg):
    """对"转型后待补缺"的表跑三种缺失策略，产出对比表（A 层要求的决策对比）。"""
    id_col = cfg.s("pipeline.id_column")
    keys = [c for c in cfg.lst("pipeline.dropna_columns") if c in df_typed.columns]
    rows = []
    label = {"dropna": "dropna 删行",
             "fillna_median": "fillna 中位数",
             "interpolate_group": "设备组内线性插值（本管道采用）"}
    for how in label:
        d = df_typed.copy()
        if how == "dropna":
            d = d.dropna(subset=keys)
        elif how == "fillna_median":
            for col in cfg.lst("pipeline.missing_strategy.interpolate") + \
                    cfg.lst("pipeline.missing_strategy.median"):
                if col in d.columns:
                    d[col] = d[col].fillna(d[col].median())
            d = d.dropna(subset=keys)
        else:
            for col in cfg.lst("pipeline.missing_strategy.interpolate"):
                if col in d.columns:
                    d[col] = d.groupby(id_col, sort=False)[col].transform(
                        lambda s: s.interpolate(method="linear", limit_direction="both"))
            for col in cfg.lst("pipeline.missing_strategy.median"):
                if col in d.columns:
                    d[col] = d[col].fillna(d[col].median())
            d = d.dropna(subset=keys)
        s, _ = score(d, cfg) if len(d) else (0.0, {})
        rows.append({"策略": label[how], "保留行数": len(d),
                     "信息损失": f"{1 - len(d) / max(len(df_typed), 1):.2%}",
                     "剩余缺失单元格": int(d.isna().sum().sum()) if len(d) else 0,
                     "质量分": s})
    return rows


# --------------------------------------------------------- A 层：增量处理
def build_state(df, cfg):
    """由清洗结果生成增量基线（每设备最大时间戳 + 行数）。"""
    ts_col = cfg.s("pipeline.ts_column")
    id_col = cfg.s("pipeline.id_column")
    last = (df.groupby(id_col)[ts_col].max().sort_index()
            .dt.strftime("%Y-%m-%dT%H:%M:%S").to_dict())
    return {"baseline_rows": int(len(df)), "last_ts_by_device": last}


def incremental_split(df, state, cfg):
    """只保留各设备晚于基线时间戳的增量行；无基线时全量为增量（幂等可重放）。"""
    ts_col = cfg.s("pipeline.ts_column")
    id_col = cfg.s("pipeline.id_column")
    if not state:
        return df.copy(), 0
    marks = pd.to_datetime(pd.Series(state.get("last_ts_by_device", {})))
    if marks.empty:
        return df.copy(), 0
    last = df[id_col].map(marks)
    new = df[df[ts_col] > last]
    return new.copy(), int(len(df) - len(new))


# ---------------------------------------------------------------- 台账渲染
def render_log(audits, rows_in_total, rows_out, clean_rate):
    """把每步 audit 渲染成"操作→行数→理由"三行式文本台账（A 层留痕）。"""
    lines = [f"[管道输入] {rows_in_total} 行（原始 CSV）"]
    for a in audits:
        lines.append("")
        lines.append(f"[{a['no']}/{a['step']}] 操作: {a['action']}")
        lines.append(f"    行数: {a['rows_in']} → {a['rows_out']}（剔除 {a['removed']}）")
        lines.append(f"    理由: {a['reason']}")
        for d in a["detail"]:
            lines.append(f"    - {d}")
    lines.append("")
    lines.append(f"[输出] clean.csv {rows_out} 行｜清洗率 {clean_rate:.2%}｜"
                 f"台账条目 {len(audits)} 步")
    return "\n".join(lines)


def device_summary(df, cfg):
    """设备维度台账（topk 驱动）：每设备行数/时间跨度/均值，写进报告。"""
    id_col = cfg.s("pipeline.id_column")
    ts_col = cfg.s("pipeline.ts_column")
    tcol = cfg.s("pipeline.temp_column")
    g = df.groupby(id_col).agg(rows=(tcol, "size"), temp_mean=(tcol, "mean"),
                               ts_first=(ts_col, "min"), ts_last=(ts_col, "max"))
    g = g.sort_values("rows", ascending=False).head(cfg.topk)
    return [f"{idx}: {int(r['rows'])} 行, {tcol}均值 {r['temp_mean']:.2f}{cfg.unit}, "
            f"{r['ts_first']} → {r['ts_last']}" for idx, r in g.iterrows()]


def as_jsonable(obj):
    """numpy/pandas 标量转原生类型，保证 JSON 可序列化且逐字节稳定。"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, _dt.datetime)):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError("无法序列化类型: %r" % type(obj))
