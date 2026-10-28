# -*- coding: utf-8 -*-
"""编排层：真实脏 CSV → 七步管道 → 质量分/工单档位门禁 → 台账 + 报告 + 落盘。

档位口径（docs/03 §2.6）：一切判定以《P2.1工单》「验收标准」四行**原文**为准
（逐字复述见 `WO_ROW`，由 `tests/test_workorder_tiers.py::test_workorder_rows_are_quoted_verbatim`
直接对表 `../../../工单任务书/P2.1工单-*.md` 锁定；线值只出现在证据段，不改写原文）：
  D 及格「管道完整；质量≥85%；PEP 8≥75%」
  C 良好「质量≥88%；处理日志可复现」
  B 优秀「质量≥90%；PEP 8≥85%；文档含使用示例」
  A 超优「优秀+增量处理/自定义验证规则/100万行<5分钟」
落地把"管道完整"钉成七步台账齐、"日志可复现"钉成同进程二次运行逐步增量一致、
"文档含使用示例"钉成 tests 逐字执行 README 的那段示例。
模式（run.py 转发）：
  full（默认）  七步管道 + 全程留痕 + 工单四行证据实测
  peek          只摸底预览，不写业务产物（课前导学单第 3 条）
  incremental   按 output/state.json 基线只处理增量并追加 clean.csv

可复现口径：output/ 内所有文件**不含墙钟**；压测与计时的精确秒数写 runtime/bench.json
（波动指标），报告只记录由预算判定的档位结论，保证二次运行逐字节一致。
"""
import datetime as _dt
import os
import tempfile
import time

import pandas as pd

from . import core, io_utils, report, stylecheck

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: 《P2.1工单》「验收标准」四行**原文**（逐字），报告第 15 节每档行首直接引用它。
#: 线值（85/88/90、75%/85%）在 rules.yaml 里可能被抬起，抬起后的实际线只写进证据段，
#: 绝不允许回填进这四行——否则报告里的"工单原文"就成了自创口径。
WO_ROW = {
    "D": "管道完整；质量≥85%；PEP 8≥75%",
    "C": "质量≥88%；处理日志可复现",
    "B": "质量≥90%；PEP 8≥85%；文档含使用示例",
    "A": "优秀+增量处理/自定义验证规则/100万行<5分钟",
}


def _rel(path):
    """相对项目根的显示路径：去掉机器相关的绝对前缀，保证跨机逐字节可复现。

    超出课程包范围（3 层 ../ 以上）的路径只留文件名，避免把用户名写进产物。
    """
    try:
        r = os.path.relpath(path, ROOT)
    except ValueError:
        return os.path.basename(path)
    return r if r.count("..") <= 2 else os.path.basename(path)


def resolve_input(cfg, override=None):
    """解析输入 CSV：--input 优先 → 配置 io.input → 配置 io.input_fallback。"""
    candidates = []
    if override:
        candidates.append(os.path.abspath(override))
    for key in ("io.input", "io.input_fallback"):
        v = cfg.s(key)
        if v:
            candidates.append(os.path.abspath(os.path.join(ROOT, v)))
    for p in candidates:
        if os.path.isfile(p):
            return p, candidates
    raise FileNotFoundError(
        "找不到输入 CSV。候选: %s（可用 --input 指定，或改 config/rules.yaml 的 io.input）"
        % candidates)


def load_raw(path, cfg):
    """读取真实脏数据：read_csv_rows 核对物理行/表头，pandas 解析成表。"""
    rows = io_utils.read_csv_rows(path)                 # 原始文本口径（含 N/A 字面量）
    df = pd.read_csv(path)
    if len(rows) != len(df):
        raise core.PipelineError(
            "物理行 %d ≠ 解析行 %d：存在换行/引号类脏格式" % (len(rows), len(df)))
    na_literal = sum(1 for r in rows
                     if str(r.get(cfg.s("pipeline.temp_column"), "")).strip()
                     in ("N/A", ""))
    return df, {"physical_rows": len(rows),
                "header": list(rows[0].keys()) if rows else [],
                "na_literal_rows": na_literal,
                "sha256": io_utils.sha256_short(path),
                "bytes": os.path.getsize(path)}


def run_pipeline(df, cfg):
    """七步管道：每步 (df, audit)，返回结果字典（台账、被剔行、评分、校验）。"""
    audits = []
    df, a_check = core.inspect_schema(df, cfg)
    audits.append(a_check)
    df, a_type = core.convert_types(df, cfg)
    audits.append(a_type)
    typed = df.copy()                                   # 缺失处理前快照（三策略对比用）
    df, a_miss = core.handle_missing(df, cfg)
    audits.append(a_miss)
    df, a_out, dropped = core.detect_anomalies(df, cfg)
    audits.append(a_out)
    df, a_dup = core.dedupe(df, cfg)
    audits.append(a_dup)
    df, a_rule = core.apply_custom_rules(df, cfg)
    audits.append(a_rule)
    df, a_flag = core.flag_process_limits(df, cfg)
    audits.append(a_flag)
    checks, a_val, dup_rate = core.validate(df, cfg)
    audits.append(a_val)
    clean = (df.sort_values([cfg.s("pipeline.id_column"), cfg.s("pipeline.ts_column")])
             .reset_index(drop=True))
    flag_cols = [cfg.s("pipeline.warning_column"), cfg.s("pipeline.danger_column")]
    value, parts = core.score(clean.drop(columns=flag_cols), cfg)
    tiers = core.gate(value, cfg)
    tiers["uniqueness_pass"] = bool(
        dup_rate <= cfg.f("quality.max_duplicate_rate") + 1e-12)
    return {"raw_rows": a_check["rows_in"], "clean": clean, "audits": audits,
            "typed": typed, "dropped": dropped, "checks": checks, "score": value,
            "score_parts": parts, "tiers": tiers, "dup_rate": dup_rate}


def write_outputs(res, cfg, out_dir, path, meta):
    """TODO-7 输出：clean.csv + 每步行数台账 + 留痕副产物 + result.json + 基线。"""
    io_utils.ensure_dir(out_dir)
    cols = cfg.lst("pipeline.required_columns")
    clean = res["clean"]
    clean_path = os.path.join(out_dir, cfg.s("io.out_clean_csv", "clean.csv"))
    clean[cols].to_csv(clean_path, index=False)
    rate = 1 - len(clean) / max(res["raw_rows"], 1)
    log_text = core.render_log(res["audits"], res["raw_rows"], len(clean), rate)
    log_path = os.path.join(out_dir, cfg.s("io.out_log", "clean_log.txt"))
    io_utils.write_text(log_path, log_text + "\n")

    strat = core.missing_strategy_comparison(res["typed"], cfg)
    strat_path = os.path.join(out_dir, cfg.s("io.out_strategies", "missing_strategies.csv"))
    io_utils.write_csv_rows(strat_path, strat, fields=list(strat[0].keys()))

    anom = res["dropped"]
    anom_cols = cols + [c for c in ("hit_stat", "hit_business") if c in anom.columns]
    anom_path = os.path.join(out_dir, cfg.s("io.out_anomalies", "anomalies.csv"))
    io_utils.write_csv_rows(anom_path, [{k: r[k] for k in anom_cols}
                                        for r in anom.to_dict("records")],
                            fields=anom_cols)

    state_path = os.path.join(out_dir, cfg.s("io.out_state", "state.json"))
    io_utils.write_json(state_path, core.build_state(clean, cfg))

    result = {
        "input": {"path": _rel(path), "sha256": meta["sha256"],
                  "physical_rows": meta["physical_rows"],
                  "na_literal_rows": meta["na_literal_rows"], "bytes": meta["bytes"]},
        "rows_in": res["raw_rows"], "rows_out": len(clean),
        "removed": res["raw_rows"] - len(clean), "clean_rate": round(rate, 6),
        "quality_score": res["score"], "score_parts": res["score_parts"],
        "duplicate_rate": round(res["dup_rate"], 6),
        "tiers": res["tiers"], "validation": res["checks"],
        "step_ledger": [{"step": a["step"], "rows_in": a["rows_in"],
                         "rows_out": a["rows_out"], "removed": a["removed"]}
                        for a in res["audits"]],
        "config": {"seed": cfg.seed, "topk": cfg.topk, "unit": cfg.unit,
                   "warn": cfg.warn, "danger": cfg.danger,
                   "temp_range": [cfg.f("pipeline.temp_min"), cfg.f("pipeline.temp_max")],
                   "press_range": [cfg.f("pipeline.press_min"), cfg.f("pipeline.press_max")],
                   "iqr_k": cfg.f("pipeline.iqr_k"),
                   "outlier_action": cfg.s("pipeline.outlier_action"),
                   "custom_rules": cfg.lst("pipeline.custom_rules")},
    }
    io_utils.write_json(os.path.join(out_dir, cfg.s("io.out_result_json", "result.json")),
                        result, default=core.as_jsonable)
    return {"clean_path": _rel(clean_path), "log_path": _rel(log_path),
            "strat": strat, "strat_path": _rel(strat_path),
            "anom_path": _rel(anom_path),
            "anom_rows": len(anom), "state_path": _rel(state_path),
            "clean_rate": rate}


def _step_table(res):
    rows = [(a["no"], a["step"], "%d → %d" % (a["rows_in"], a["rows_out"]), a["removed"])
            for a in res["audits"]]
    return io_utils.fmt_table(rows, ["步", "操作(步骤名)", "行数变化", "剔除"]).splitlines()


def _strat_table(strat):
    head = list(strat[0].keys())
    return io_utils.fmt_table([[r[h] for h in head] for r in strat], head).splitlines()


# ---------------------------------------------------- 工单四行档位的实测证据采集
def reproducibility_check(res, cfg, input_path):
    """C 层「处理日志可复现」硬断言（同进程二次运行，无墙钟、无落盘）。

    同一输入重跑七步：逐步行数增量 (rows_in→rows_out/removed) 与渲染出的
    clean_log 文本必须逐字节一致——台账里没有任何时间戳，任何非确定性
    （排序不稳、分组顺序漂移、插值方向依赖哈希序）都会在这里暴露。
    """
    df2, _ = load_raw(input_path, cfg)
    res2 = run_pipeline(df2, cfg)

    def deltas(r):
        return [(a["step"], a["rows_in"], a["rows_out"], a["removed"])
                for a in r["audits"]]

    rate1 = 1 - len(res["clean"]) / max(res["raw_rows"], 1)
    rate2 = 1 - len(res2["clean"]) / max(res2["raw_rows"], 1)
    log1 = core.render_log(res["audits"], res["raw_rows"], len(res["clean"]), rate1)
    log2 = core.render_log(res2["audits"], res2["raw_rows"], len(res2["clean"]), rate2)
    same_delta = deltas(res) == deltas(res2)
    return {"steps": len(deltas(res)), "deltas_equal": same_delta,
            "log_identical": log1 == log2,
            "log_reproducible": bool(same_delta and log1 == log2)}


def usage_evidence():
    """B 层「文档含使用示例」：从 README.md 定位可执行示例块（file:line）。"""
    try:
        text = io_utils.read_text(os.path.join(ROOT, "README.md"))
    except OSError:
        return {"found": False, "ref": "", "code": "", "origin": "README.md"}
    return core.find_usage_example(text, "README.md")


def incremental_replay_check(res, cfg, input_path):
    """A 层「增量处理」硬断言：全量结果落基线后重放同一输入——

    增量必须为 0 行，且 clean.csv 与全量运行**逐字节一致**（幂等且无损；
    任何一行漏进或被改写，字节比较立即翻红）。在临时目录里跑，output/
    只有本次全量产物，二次运行仍逐字节复现。
    """
    cols = cfg.lst("pipeline.required_columns")
    expected = res["clean"][cols].to_csv(index=False)
    with tempfile.TemporaryDirectory() as tmp:
        clean_path = os.path.join(tmp, cfg.s("io.out_clean_csv", "clean.csv"))
        res["clean"][cols].to_csv(clean_path, index=False)
        io_utils.write_json(
            os.path.join(tmp, cfg.s("io.out_state", "state.json")),
            core.build_state(res["clean"], cfg))
        _sections, info = run_incremental(cfg, tmp, input_path)
        actual = io_utils.read_text(clean_path)
    return {"csv_identical": bool(actual == expected),
            "new_rows": int(info["new_rows"]),
            "clean_rows": int(info["clean_after"])}


def collect_evidence(res, cfg, input_path, bench=True):
    """汇总工单 D/C/B/A 四行判定所需的全部实测证据（数字，不是文案）。"""
    custom = next(a for a in res["audits"] if a["step"] == "自定义规则(A层)")
    bench_lines, bench_info = bench_evidence(cfg) if bench else ([], None)
    return {
        "pep8": stylecheck.summarize(ROOT),
        "steps": len(res["audits"]),
        # 走到这里＝八条台账全部执行且无异常中断（任何一步抛错都到不了本行）
        "pipeline_complete": True,
        "reproducible": reproducibility_check(res, cfg, input_path),
        "usage": usage_evidence(),
        "replay": incremental_replay_check(res, cfg, input_path),
        "custom_rules": {"count": len(cfg.lst("pipeline.custom_rules")),
                         "removed": int(custom["removed"]),
                         "detail": custom["detail"]},
        "bench": bench_info,
        "bench_lines": bench_lines,
    }


def build_sections(cfg, res, meta, path, artifacts, evidence, inc_lines):
    """报告分节：工单 D/C/B/A 四行证据全部来自实测数字，无写死文案。"""
    a = {x["step"]: x for x in res["audits"]}
    k_check = "TODO-1 摸底"
    t = res["tiers"]
    p = res["score_parts"]
    pep8 = evidence["pep8"]
    repro = evidence["reproducible"]
    usage = evidence["usage"]
    replay = evidence["replay"]
    bench = evidence["bench"]
    s_input = [
        "输入文件: %s（相对项目根）" % _rel(path),
        "输入指纹 sha256: %s（报告不含墙钟 → 二次运行逐字节一致）" % meta["sha256"],
        "物理行 %d｜pandas 解析行 %d｜temp 非法字面量(N/A/空) %d 行｜文件 %d B"
        % (meta["physical_rows"], res["raw_rows"], meta["na_literal_rows"], meta["bytes"]),
        "表头: %s" % meta["header"],
        "规则口径(YAML 驱动): temp∈[%.1f, %.1f] press∈[%.2f, %.2f] %s｜iqr_k=%.1f"
        "｜预警线 %.1f%s 停机线 %.1f%s"
        % (cfg.f("pipeline.temp_min"), cfg.f("pipeline.temp_max"),
           cfg.f("pipeline.press_min"), cfg.f("pipeline.press_max"), cfg.unit,
           cfg.f("pipeline.iqr_k"), cfg.warn, cfg.unit, cfg.danger, cfg.unit),
        "动作口径: outlier_action=%s｜去重 subset=%s keep=%s｜关键列 dropna=%s"
        % (cfg.s("pipeline.outlier_action"), cfg.lst("pipeline.dedupe_subset"),
           cfg.s("pipeline.dedupe_keep"), cfg.lst("pipeline.dropna_columns")),
        "时间格式: %s｜seed=%d｜topk=%d｜strict_validate=%s"
        % (cfg.lst("pipeline.ts_formats"), cfg.seed, cfg.topk,
           cfg.get("pipeline.strict_validate"))]
    s_ledger = _step_table(res) + ["",
                                   "合计 %d → %d 行｜剔除 %d 行｜清洗率 %.2f%%"
                                   % (res["raw_rows"], len(res["clean"]),
                                      res["raw_rows"] - len(res["clean"]),
                                      artifacts["clean_rate"] * 100)]
    log_lines = len(core.render_log(
        res["audits"], res["raw_rows"], len(res["clean"]),
        artifacts["clean_rate"]).splitlines())
    s_quality = [
        "质量总分 %.1f/100 ＝ 完整性 %.1f + 合规性 %.1f + 一致性 %.1f + 时间性 %.1f"
        % (res["score"], p["completeness"], p["accuracy"], p["consistency"],
           p["timeliness"]),
        "重复率 %.4f%%（唯一性硬门禁 ≤%.4f%%：%s）"
        % (res["dup_rate"] * 100, cfg.f("quality.max_duplicate_rate") * 100,
           "通过" if t["uniqueness_pass"] else "未通过"),
        "分数线单项判定（完整档位条件见第 15 节）: 及格线(D档) %.0f → %s｜"
        "良好线(C档) %.0f → %s｜优秀线(B档) %.0f → %s"
        % (t["target"], "达成" if res["score"] >= t["target"] else "未达",
           t["good"], "达成" if res["score"] >= t["good"] else "未达",
           t["excellent"], "达成" if res["score"] >= t["excellent"] else "未达")]

    def mark(ok):
        return "达标" if ok else "未达"

    if bench:
        bench_txt = ("压测 %d 行走同一条七步管道，预算 %.0fs 内完成【%s】"
                     "（verdict 取 runtime/bench.json 记录，秒数为波动指标不进本表）"
                     % (bench["rows"], bench["budget"],
                        "达标" if bench["pass"] else "未达标"))
    else:
        bench_txt = "本次 --no-bench 未压测，100 万行子条件不计达标"
    s_tier = [
        "D档 及格「%s」: 七步管道 %d/%d 条台账留痕 "
        "%d→%d 行｜质量 %.1f ≥ %.0f｜PEP 8 子集 %.1f%%（%d/%d 项）≥ %.1f%% → %s"
        % (WO_ROW["D"], t["pipeline_steps"], core.EXPECTED_AUDIT_STEPS,
           res["raw_rows"], len(res["clean"]), res["score"], t["target"],
           t["pep8_score"], t["pep8_checks"][0], t["pep8_checks"][1],
           t["pep8_min_D"], mark(t["tier_D_pass"])),
        "C档 良好「%s」: 质量 %.1f ≥ %.0f｜同进程二次运行同一输入："
        "%d/%d 步行数增量一致、clean_log 文本逐字节一致（台账 %d 行，%s，无时间戳） → %s"
        % (WO_ROW["C"], res["score"], t["good"],
           repro["steps"], t["log_repro_steps"], log_lines, artifacts["log_path"],
           mark(t["tier_C_good"])),
        "B档 优秀「%s」: 质量 %.1f ≥ %.0f｜"
        "PEP 8 子集 %.1f%% ≥ %.1f%%｜使用示例 %s（由 tests 逐字执行，防文案腐烂） → %s"
        % (WO_ROW["B"], res["score"], t["excellent"],
           t["pep8_score"], t["pep8_min_B"],
           usage["ref"] if usage["found"] else "未找到",
           mark(t["tier_B_excellent"])),
        "A档 超优「%s」: 增量重放 clean.csv "
        "与全量逐字节一致（新增 %d 行）｜自定义验证规则 %d 条逐条计数、本次剔 %d 行"
        "（分步见第 8 节）｜%s → %s"
        % (WO_ROW["A"], replay["new_rows"], t["custom_rules_count"],
           t["custom_rules_removed"], bench_txt, mark(t["tier_A_super"]))]
    s_tier.append(
        "保底自检（不计入工单档位）: 程序完整出结果——%d 条台账全部执行、无异常中断，"
        "%d 行进 / %d 行出，重复率 %.4f%%"
        % (len(res["audits"]), res["raw_rows"], len(res["clean"]),
           res["dup_rate"] * 100))
    s_style = [
        "内置 PEP 8 子集（标准库 ast + 行长/docstring/命名检查，与 p11_exercises "
        "同一口径，非 pylint 评分）：达标率 %.1f%%（检查项 %d，通过 %d，违规 %d，"
        "行长上限 %d）"
        % (pep8["score"], pep8["total"], pep8["passed"],
           len(pep8["violations"]), pep8["max_line_length"]),
        "覆盖文件 %d 个（src/ + tests/ + run.py）｜分类计数：命名 %d｜"
        "缺 docstring %d｜超长行 %d"
        % (pep8["checked_files"], pep8["naming_violations"],
           pep8["missing_docstrings"], pep8["long_lines"]),
        "分层线（config/rules.yaml）: D 档 ≥%.1f%% → %s｜B 档 ≥%.1f%% → %s"
        % (t["pep8_min_D"], "达成" if t["pep8_pass_D"] else "未达",
           t["pep8_min_B"], "达成" if t["pep8_pass_B"] else "未达"),
        "违规样例（前 5 条）: " + ("；".join(
            "%s L%d %s" % (v[0], v[2], v[1])
            for v in pep8["top_violations"][:5]) or "无")]
    s_extra = list(inc_lines or []) + list(evidence["bench_lines"]) + [
        "增量重放(A档硬断言): 全量基线重放同一输入 → clean.csv 与全量结果逐字节%s"
        "（新增 %d 行，重放后 %d 行）"
        % ("一致" if replay["csv_identical"] else "不一致",
           replay["new_rows"], replay["clean_rows"]),
        "自定义规则(A层): YAML 提供 %d 条，本次共剔 %d 行，逐条计数见第 8 节台账"
        % (len(cfg.lst("pipeline.custom_rules")), t["custom_rules_removed"]),
        "被剔异常留痕: %s（%d 行，含 hit_stat/hit_business 双旗标）"
        % (artifacts["anom_path"], artifacts["anom_rows"])]
    s_concl = [
        "清洗率 %.2f%%，输出剩余缺失单元格 %d 个，校验项 %d/%d 通过"
        % (artifacts["clean_rate"] * 100, int(res["clean"].isna().sum().sum()),
           sum(1 for v in res["checks"].values() if v), len(res["checks"])),
        "改规则只改 config/rules.yaml（阈值/列名/策略/输出路径/自定义规则），代码零改动",
        "下一步：把 anomalies.csv 的被剔点交工艺复盘，统计误剔率（B06 进阶口径）"]
    return [
        ("1. 输入口径", s_input),
        ("2. 七步管道台账（步/操作/行数）", s_ledger),
        ("3. TODO-1 摸底 / EDA", a[k_check]["detail"]),
        ("4. TODO-3 类型转换", ["操作: " + a["TODO-3 类型转换"]["action"]]
         + a["TODO-3 类型转换"]["detail"]),
        ("5. TODO-2 缺失处理 + 三策略对比",
         ["操作: " + a["TODO-2 缺失处理"]["action"]] + a["TODO-2 缺失处理"]["detail"]
         + ["", "三策略对比（A 层决策矩阵，全部实测）："] + _strat_table(artifacts["strat"])),
        ("6. TODO-4 异常检测（IQR × 业务阈值双计数）",
         ["操作: " + a["TODO-4 异常检测"]["action"]] + a["TODO-4 异常检测"]["detail"]),
        ("7. TODO-5 去重", ["操作: " + a["TODO-5 去重"]["action"]]
         + a["TODO-5 去重"]["detail"]),
        ("8. 自定义规则(A层)", ["操作: " + a["自定义规则(A层)"]["action"]]
         + a["自定义规则(A层)"]["detail"]),
        ("9. 工艺红线旗标 warn/danger",
         ["操作: " + a["工艺红线旗标"]["action"]] + a["工艺红线旗标"]["detail"]),
        ("10. TODO-6 质量校验", ["操作: " + a["TODO-6 校验"]["action"]]
         + a["TODO-6 校验"]["detail"]),
        ("11. 质量评分与门禁（85/88/90）", s_quality),
        ("12. 设备维度 TopK（配置 topk=%d）" % cfg.topk, core.device_summary(res["clean"], cfg)),
        ("13. A 层拓展实测（增量 / 压测 / 留痕）", s_extra),
        ("14. 代码规范实测（内置 PEP 8 子集）", s_style),
        ("15. 工单分层达标（D 及格 / C 良好 / B 优秀 / A 超优）", s_tier),
        ("16. 结论与建议", s_concl),
    ]


def run(cfg, out_dir, input_path=None, bench=True, incremental=False, stamp=None):
    """默认全流程：真实 CSV → 七步 → 工单四行档位取证 → 落盘 → 报告。"""
    path, _ = resolve_input(cfg, input_path)
    df, meta = load_raw(path, cfg)
    res = run_pipeline(df, cfg)
    evidence = collect_evidence(res, cfg, path, bench=bench)
    res["tiers"] = core.workorder_tiers(res["tiers"], cfg, evidence)
    artifacts = write_outputs(res, cfg, out_dir, path, meta)
    inc_lines = incremental_evidence(res, cfg, artifacts["state_path"])
    sections = build_sections(cfg, res, meta, path, artifacts, evidence, inc_lines)
    _save(sections, cfg, out_dir, stamp)
    return sections


def _save(sections, cfg, out_dir, stamp=None):
    return report.save(sections, os.path.join(out_dir, cfg.s("io.out_report", "report.txt")),
                       stamp=stamp)


def peek(cfg, input_path=None):
    """--peek 预览：只摸底不写业务产物。"""
    path, candidates = resolve_input(cfg, input_path)
    df, meta = load_raw(path, cfg)
    typed, a_type = core.convert_types(df, cfg)
    _, a_check = core.inspect_schema(df, cfg)
    lines = ["输入: %s（sha256 %s，物理行 %d，解析行 %d）"
             % (path, meta["sha256"], meta["physical_rows"], len(df)),
             "表头: %s" % meta["header"]]
    lines.append("原始前 10 行:")
    lines.extend("  " + x for x in df.head(10).to_string(index=False).splitlines())
    lines.append("脏数据画像（TODO-1 摸底）:")
    lines.extend("  " + d for d in a_check["detail"])
    lines.append("转型后（TODO-3 to_numeric / to_datetime）:")
    lines.extend("  " + d for d in a_type["detail"])
    bad = pd.to_numeric(typed["temp"], errors="coerce")
    tmax = cfg.f("pipeline.temp_max")
    mask = bad.isna() | (bad > tmax)
    lines.append("问题行样例（缺失或 temp>%.0f）:" % tmax)
    lines.extend("  " + r for r in typed[mask].head(cfg.topk)
                 .to_string(index=False).splitlines())
    lines.append("问题类型计数: temp 缺失 %d｜temp 越界 %d｜整行重复 %d｜语义重复 %d｜"
                 "status 取值 %s"
                 % (int(bad.isna().sum()), int((bad > tmax).sum()),
                    int(df.duplicated().sum()),
                    int(df.duplicated(subset=cfg.lst("pipeline.dedupe_subset")).sum()),
                    sorted(set(df[cfg.s("pipeline.status_column")].dropna().astype(str)))))
    lines.append("候选输入路径（改 io.input 或用 --input 切换）: %s" % candidates)
    lines.append("peek 模式不写 output/，跑完整管道请去掉 --peek")
    return [("peek 预览（课前导学单第 3 条）", lines)]


def bench_evidence(cfg):
    """A 档超优口径：100 万行端到端 < 5 分钟（只计时管道，不计时数据生成）。

    返回 (报告行, 实测 info)；精确秒数/吞吐只写 runtime/bench.json（波动指标），
    info 仅回传由预算判定的 verdict 布尔——保证 output/ 逐字节复现。
    """
    n = cfg.i("perf.bench_rows")
    budget = cfg.f("perf.bench_budget_seconds")
    raw = core.generate_raw(n=n, seed=cfg.seed)
    t0 = time.perf_counter()
    res = run_pipeline(raw, cfg)
    secs = time.perf_counter() - t0
    io_utils.write_json(os.path.join(ROOT, "runtime", "bench.json"),
                        {"bench_rows": int(len(raw)), "seconds": round(secs, 3),
                         "budget_seconds": budget, "throughput_rows_per_second":
                         int(len(raw) / max(secs, 1e-9)),
                         "rows_out": len(res["clean"]), "quality_score": res["score"]})
    verdict = "达标" if secs < budget else "未达标"
    lines = ["100 万行压测(A档): %d 行合成脏数据(seed=%d) 走同一条七步管道 → "
             "预算 %.0fs 内完成【%s】，输出 %d 行、质量分 %.1f/100"
             % (len(raw), cfg.seed, budget, verdict, len(res["clean"]), res["score"]),
             "精确耗时/吞吐为波动指标，写 runtime/bench.json（不进 output/，"
             "以保证逐字节复现）；stdout 同步打印"]
    info = {"rows": int(len(raw)), "rows_out": int(len(res["clean"])),
            "budget": float(budget), "pass": bool(secs < budget),
            "quality_score": res["score"]}
    return lines, info


def incremental_evidence(res, cfg, state_path):
    """A 层增量处理证据：按本次基线重放应得 0 新增；基线回退 1 天看增量行数。"""
    state = core.build_state(res["clean"], cfg)
    typed = res["typed"]
    same, skipped = core.incremental_split(typed, state, cfg)
    back = {k: (_dt.datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")
                - _dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
            for k, v in state["last_ts_by_device"].items()}
    part, skipped2 = core.incremental_split(typed, {"last_ts_by_device": back}, cfg)
    return ["增量处理(A层): 按本次基线重放 → 新增 %d 行（跳过 %d 行，幂等）；"
            "基线回退 1 天 → 增量 %d 行（跳过 %d 行）"
            % (len(same), skipped, len(part), skipped2),
            "基线文件: %s（每设备最大时间戳；下次 --incremental 只算新数据）" % _rel(state_path)]


def run_incremental(cfg, out_dir, input_path=None, stamp=None):
    """增量模式：读 state.json 基线 → 只处理新行 → 追加 clean.csv → 更新基线。

    返回 (sections, info)；info 含 new_rows/added_rows/clean_before/clean_after，
    供 A 档「增量重放与全量逐字节一致」硬断言取数。
    """
    path, _ = resolve_input(cfg, input_path)
    df, _meta = load_raw(path, cfg)
    state_path = os.path.join(out_dir, cfg.s("io.out_state", "state.json"))
    state = io_utils.read_json(state_path, default=None)
    typed, _ = core.convert_types(df, cfg)
    new, skipped = core.incremental_split(typed, state, cfg)
    cols = cfg.lst("pipeline.required_columns")
    clean_path = os.path.join(out_dir, cfg.s("io.out_clean_csv", "clean.csv"))
    before = len(pd.read_csv(clean_path)) if os.path.exists(clean_path) else 0
    lines = ["基线: %s｜输入 %d 行 → 增量 %d 行（跳过已入基线 %d 行）"
             % (state_path, len(typed), len(new), skipped)]
    info = {"new_rows": int(len(new)), "added_rows": 0, "skipped": int(skipped),
            "clean_before": int(before), "clean_after": int(before)}
    if len(new) == 0:
        lines.append("无增量：clean.csv 保持 %d 行不变（幂等重放）" % before)
        _save([("增量处理(A档)", lines)], cfg, out_dir, stamp)
        return [("增量处理(A档)", lines)], info
    res = run_pipeline(new, cfg)
    add = res["clean"][cols]
    merged = add
    if os.path.exists(clean_path):
        old = pd.read_csv(clean_path, parse_dates=[cfg.s("pipeline.ts_column")])
        merged = pd.concat([old, add], ignore_index=True)
        merged, a_dup = core.dedupe(merged, cfg)
        lines.append("与历史 %d 行合并并语义去重 → 去重删 %d 行"
                     % (len(old), a_dup["removed"]))
    merged[cols].to_csv(clean_path, index=False)
    io_utils.write_json(state_path, core.build_state(merged, cfg))
    lines.append("本次新增入表 %d 行；clean.csv %d → %d 行；基线已更新"
                 % (len(add), before, len(merged)))
    info.update({"added_rows": int(len(add)), "clean_after": int(len(merged))})
    sections = [("增量处理(A档)", lines)]
    _save(sections, cfg, out_dir, stamp)
    return sections, info
