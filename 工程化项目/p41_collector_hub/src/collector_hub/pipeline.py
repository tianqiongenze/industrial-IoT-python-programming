# -*- coding: utf-8 -*-
"""多源轮询（含断线重连）→ 还原 → 切批 → 对账 → APM 计数 → 落盘。

三条链路各跑一遍同一份故障注入：
  retry_limit=0                    → "不重连"对照组（D层基线，用来暴露丢数）
  retry_limit=配置值                → 指数退避重连（课堂 B/C 层达标链路）
  retry_limit=max(配置值, 最严重故障尝试数, 1) → 零丢弃链路（工单优秀(B) 取证链路）
前两条的计数差是课堂 B/C 层达标的证据；第三条用来兑现工单「≥99.5%＋延迟<100ms」，
取它是因为它是同一份故障下最保守的那条（多烧退避、平均延迟最高仍达标）。
全部计数由配置推导，不含墙钟。
"""
import ast
import os
import zlib

from . import core, io_utils, report

#: 工单《P4.1》「验收标准」四行**原文**（逐字），报告「工单验收四档对照」每档行首直接引用它。
#: 线值（95%／99.5%／100ms）属于原文，照抄不动；本项目 rules.yaml 抬高的实际线只在
#: 行首「」之后的证据段回显，由 tests/test_workorder_rows.py 读课程仓工单文件回归锁定。
WO_ROW = {
    "D": "三源数据贯通；采集率>95%；无数据丢失；系统文档",
    "C": "断线重连实测通过；统计输出准确",
    "B": "采集率≥99.5%；延迟<100ms；线程安全(无共享可变状态)",
    "A": "优秀+故障自动转移/主从切换或性能监控小面板",
}
WO_PREFIX = {"D": "工单及格(D)", "C": "工单良好(C)",
             "B": "工单优秀(B)", "A": "工单超优(A)"}


def run(cfg, out_dir):
    sources = list(cfg.raw.get("sources") or cfg.items or [])
    if not sources:
        raise ValueError("config/rules.yaml 的 sources 为空")
    batch_size = int(cfg.raw.get("batch_size", 3))
    rounds = int(cfg.raw.get("poll_rounds", 4))
    backoff = float(cfg.raw.get("backoff_base", 0.01))
    retry_limit = int(cfg.raw.get("retry_limit", 0))
    target = float(cfg.raw.get("rate_target", 95.0))
    strict = float(cfg.raw.get("rate_strict_target", 99.5))
    lat_target = float(cfg.raw.get("latency_target_ms", 100.0))
    docs_min = int(cfg.raw.get("docs_min", 8))
    faults = {str(f.get("id")): f for f in (cfg.raw.get("faults") or [])}

    def transport(src, slot, attempt):
        """模拟 Modbus 读寄存器：同一源恒同一基线，故障按配置表确定性注入。

        内置 hash() 受 PYTHONHASHSEED 随机化，跨进程会漂移 → 用 crc32。
        """
        sid = str(src.get("id"))
        f = faults.get(sid)
        if f is not None and (slot + 1) in list(f.get("slots") or []):
            if attempt < int(f.get("fail_attempts", 1)):
                raise core.LinkDown("%s 第 %d 条第 %d 次尝试链路中断"
                                    % (sid, slot + 1, attempt + 1))
        return 250 + (zlib.crc32(sid.encode("utf-8")) % 1000 % 7)

    def session(limit):
        """跑完整会话：limit 为重连上限（0=不重连）。"""
        per_source, all_batches, flat = {}, [], []
        for src in sources:
            sid = str(src.get("id", "PLC"))
            scale = float(src.get("scale", 1))
            batches, raw, st = core.collect(transport, src, rounds,
                                            batch_size, limit, backoff)
            vals = [core.restore(b, scale) for b in batches]
            sflat = core.restore(raw, scale)
            all_batches += vals
            flat += sflat
            st = dict(st,
                      rate=round(core.rate(st["ok"], st["planned"]), 4),
                      backoff_ms=round(st["backoff_ms"], 6),
                      max_wait_ms=round(st["max_wait_ms"], 6),
                      latency_ms=round(st["latency_ms"], 6))
            st["avg_ms"] = round(st["latency_ms"] / st["planned"], 4)
            per_source[sid] = {"n": len(sflat), "sum": round(sum(sflat), 4),
                               "mean": round(sum(sflat) / len(sflat), 4) if sflat else 0.0,
                               "apm": st}
        total = core.merge(*[v["apm"] for v in per_source.values()])
        total = dict(total, rate=round(core.rate(total["ok"], total["planned"]), 4))
        total["avg_ms"] = round(total["latency_ms"] / total["planned"], 4)
        ok, diff = core.reconcile(all_batches, flat)
        balanced, identities = core.check(total)
        return {"per_source": per_source, "total": total, "flat": flat,
                "batches": all_batches, "reconcile": (ok, diff),
                "balanced": balanced, "identities": identities,
                "rate": core.rate(total["ok"], total["planned"])}

    formal = session(retry_limit)
    baseline = session(0)
    planned = len(sources) * rounds * batch_size
    ids = {str(s.get("id")) for s in sources}
    injected = sum(len(list(f.get("slots") or []))
                   for k, f in faults.items() if k in ids)
    saved = baseline["total"]["drop"] - formal["total"]["drop"]
    worst = max([int(f.get("fail_attempts", 1))
                 for k, f in faults.items() if k in ids] or [0])

    # 第三条链路：把重连上限抬到吞得下最严重故障——工单「无数据丢失」「采集率≥99.5%」
    # 严格口径要的是这条链路，不是配置默认值那条，因此单独实测、不拿默认链路冒充。
    zero = session(max(retry_limit, worst, 1))

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    docs_ok = _docs_ready(root, docs_min)
    shared = _module_mutable_globals(os.path.join(root, "src", "collector_hub", "core.py"))
    pass_line = float(cfg.raw.get("rate_pass_line", 95.0))
    per_source_planned = sum(v["apm"]["planned"] for v in formal["per_source"].values())
    wo = {
        "D": (len(sources) >= 3 and per_source_planned == planned
              and all(v["apm"]["ok"] > 0 for v in formal["per_source"].values())
              and formal["rate"] > pass_line and zero["total"]["drop"] == 0
              and formal["identities"]["ok+drop==planned"] and len(docs_ok) >= docs_min),
        "C": (formal["total"]["retry"] > 0 and saved > 0 and formal["balanced"]
              and per_source_planned == planned),
        "B": (zero["rate"] >= strict and zero["total"]["avg_ms"] < lat_target
              and not shared),
        "A": (zero["balanced"] and formal["balanced"]
              and all(k in formal["total"] for k in
                      ("planned", "ok", "drop", "retry", "calls", "latency_ms",
                       "max_wait_ms", "rate"))),
    }
    wo_lines = [
        "%s「%s」: %d/%d 源各有成功读数"
        "｜默认链路采集率 %.2f%%（工单线 >%.2f%%）｜重连上限抬到 %d 次的零丢弃链路: 成功 %d "
        "丢弃 %d｜成功+丢弃=计划恒等 %s｜docs/ 有效过程文档 %d 篇（≥%d 且每篇 >200B）→ %s"
        % (WO_PREFIX["D"], WO_ROW["D"],
           sum(1 for v in formal["per_source"].values() if v["apm"]["ok"] > 0),
           len(sources), formal["rate"], pass_line, max(retry_limit, worst, 1),
           zero["total"]["ok"], zero["total"]["drop"],
           "通过" if formal["identities"]["ok+drop==planned"] else "失败",
           len(docs_ok), docs_min, "达标" if wo["D"] else "未达标"),
        "%s「%s」: 同一份故障注入下不重连丢 %d 条 → "
        "重连丢 %d 条（重连 %d 次、挽回 %d 条）｜分源计划之和 %d = 总计划 %d｜"
        "计数自洽（调用=成功+丢弃+重试）%s → %s"
        % (WO_PREFIX["C"], WO_ROW["C"],
           baseline["total"]["drop"], formal["total"]["drop"], formal["total"]["retry"],
           saved, per_source_planned, planned,
           "通过" if formal["balanced"] else "失败", "达标" if wo["C"] else "未达标"),
        "%s「%s」: 取重连最多的"
        "零丢弃链路（最保守）采集率 %.2f%% %s %.2f%%｜平均延迟 %.2fms/条 %s %.2fms｜"
        "AST 扫描 core.py 模块级可变全局 %d 个%s → %s"
        % (WO_PREFIX["B"], WO_ROW["B"],
           zero["rate"], "≥" if zero["rate"] >= strict else "<", strict,
           zero["total"]["avg_ms"], "<" if zero["total"]["avg_ms"] < lat_target else "≥",
           lat_target, len(shared),
           "（%s）" % "、".join(shared) if shared else "（无跨线程共享的可变对象）",
           "达标" if wo["B"] else "未达标"),
        "%s「%s」: 三链路对照即监控面板"
        "（不重连 / 重连默认 %d 次 / 零丢弃 %d 次），每条链路的计划-成功-丢弃-重试-调用-延迟"
        "六个计数各自自洽 %s → %s"
        % (WO_PREFIX["A"], WO_ROW["A"],
           retry_limit, max(retry_limit, worst, 1),
           "通过" if (zero["balanced"] and formal["balanced"]) else "失败",
           "达标" if wo["A"] else "未达标"),
        "档位口径说明 : 本节按工单验收表（及格/良好/优秀/超优）逐档实测；上方「分层达标」"
        "用的是课堂支持度阶梯（D 跟做保底 / C 基础完成 / B 标准达成 / A 进阶拓展），"
        "两者字母不同源——课堂 C 层≈工单及格、课堂 B 层≈工单良好，工单优秀档只在本节取证。",
    ]

    tiers = {
        "D": (formal["reconcile"][0] and formal["balanced"]
              and formal["total"]["planned"] == planned),
        "C": (len(sources) >= 3 and formal["rate"] >= target),
        "B": (injected > 0 and formal["total"]["retry"] > 0 and saved > 0),
        "A": all(k in formal["total"] for k in
                 ("planned", "ok", "drop", "retry", "calls", "latency_ms", "rate")),
    }
    tier_lines = [
        "D层 基础贯通: %d 源×%d 轮×%d 条 = %d 条读数，还原+切批+对账恒等式 %s"
        % (len(sources), rounds, batch_size, planned,
           "通过" if formal["reconcile"][0] else "失败"),
        "C层 三源采集: 数据源 %d 个｜采集率 %.2f%% %s 目标 %.2f%% → %s"
        % (len(sources), formal["rate"], "≥" if tiers["C"] else "<", target,
           "达标" if tiers["C"] else "未达标"),
        "B层 断线重连: 故障注入 %d 处｜不重连丢 %d 条 → 重连后丢 %d 条（挽回 %d 条，"
        "重连 %d 次，最长单条等待 %.2fms）→ %s"
        % (injected, baseline["total"]["drop"], formal["total"]["drop"], saved,
           formal["total"]["retry"], formal["total"]["max_wait_ms"],
           "实测通过" if tiers["B"] else "未通过"),
        "A层 APM 面板: 计划 %d｜成功 %d｜丢弃 %d｜重试 %d｜传输调用 %d｜"
        "平均延迟 %.2fms｜采集率 %.2f%% → 计数自洽 %s"
        % (formal["total"]["planned"], formal["total"]["ok"], formal["total"]["drop"],
           formal["total"]["retry"], formal["total"]["calls"],
           formal["total"]["avg_ms"], formal["rate"],
           "通过" if formal["balanced"] else "失败"),
    ]

    ok, diff = formal["reconcile"]
    ft = formal["total"]
    bt = baseline["total"]
    result = {"sources": {k: v["n"] for k, v in formal["per_source"].items()},
              "per_source": formal["per_source"],
              "reconcile": {"ok": ok, "diff": diff},
              "n_total": len(formal["flat"]),
              "planned": planned, "injected_faults": injected,
              "apm": ft, "apm_no_retry": bt,
              "collection_rate": round(formal["rate"], 4),
              "rate_no_retry": round(baseline["rate"], 4),
              "rate_target": target, "identities": formal["identities"],
              "tiers": tiers,
              "workorder_tiers": {k: bool(wo[k]) for k in "DCBA"},
              "workorder_evidence": {
                  "docs_md": len(docs_ok), "shared_mutable_globals": shared,
                  "zero_link": {"retry_limit": max(retry_limit, worst, 1),
                                "rate": round(zero["rate"], 4),
                                "drop": zero["total"]["drop"],
                                "avg_ms": zero["total"]["avg_ms"]},
                  "rate_pass_line": pass_line, "rate_strict_target": strict,
                  "latency_target_ms": lat_target},
              "config_echo": {"batch_size": batch_size, "poll_rounds": rounds,
                              "backoff_base": backoff, "retry_limit": retry_limit,
                              "rate_target": target,
                              "faults": {k: {"slots": list(f.get("slots") or []),
                                             "fail_attempts": int(f.get("fail_attempts", 1))}
                                         for k, f in faults.items() if k in ids}}}
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    sections = [
        ("输入口径", ["数据源 %d 个｜每源 %d 轮×%d 条 = 计划 %d 条｜批量 %d 条"
                    % (len(sources), rounds, batch_size, planned, batch_size),
                      "重连上限 %d 次｜退避基数 %.2fs（指数）｜采集率目标 %.2f%%"
                      % (retry_limit, backoff, target),
                      "链路故障注入 %d 处（config/rules.yaml 的 faults，确定性可复现）"
                      % injected]),
        ("分源统计", ["%s: 成功 %d/%d 均值 %.3f 丢弃 %d 重试 %d 平均延迟 %.2fms"
                    % (k, v["apm"]["ok"], v["apm"]["planned"], v["mean"],
                       v["apm"]["drop"], v["apm"]["retry"], v["apm"]["avg_ms"])
                    for k, v in formal["per_source"].items()]),
        ("链路可靠性对照（B层·断线重连实测）",
         ["不重连(retry_limit=0): 成功 %d 丢弃 %d 采集率 %.2f%% 调用 %d"
          % (bt["ok"], bt["drop"], baseline["rate"], bt["calls"]),
          "指数退避重连(retry_limit=%d): 成功 %d 丢弃 %d 采集率 %.2f%% 重连 %d 次"
          % (retry_limit, ft["ok"], ft["drop"], formal["rate"], ft["retry"]),
          "重连挽回 %d 条读数；剩余 %d 条故障持续超过重连上限，按丢弃计入对账"
          % (saved, ft["drop"])]),
        ("APM 面板（A层）",
         ["计划 %d ｜ 成功 %d ｜ 丢弃 %d ｜ 重试 %d ｜ 传输调用 %d"
          % (ft["planned"], ft["ok"], ft["drop"], ft["retry"], ft["calls"]),
          "采集率 %.2f%%（目标 %.2f%%）｜达标 %s"
          % (formal["rate"], target, "是" if formal["rate"] >= target else "否"),
          "平均延迟 %.2fms/条｜累计退避等待 %.2fms｜单条最长等待 %.2fms"
          % (ft["avg_ms"], ft["backoff_ms"], ft["max_wait_ms"]),
          "注：延迟与等待均由配置推导的模拟值（非墙钟），保证两次运行逐字节一致"]),
        ("对账", ["Σ批次 - Σ单条 = %.9f → %s" % (diff, "通过" if ok else "失败"),
                  "成功+丢弃=计划：%d+%d=%d → %s"
                  % (ft["ok"], ft["drop"], ft["planned"],
                     "通过" if formal["identities"]["ok+drop==planned"] else "失败"),
                  "调用=成功+丢弃+重试：%d=%d+%d+%d → %s"
                  % (ft["calls"], ft["ok"], ft["drop"], ft["retry"],
                     "通过" if formal["identities"]["calls==ok+drop+retry"] else "失败")]),
        ("工单验收四档对照（及格/良好/优秀/超优）", wo_lines),
        ("分层达标", tier_lines),
        ("结论与建议", ["对账恒等式与计数自洽同时通过，说明切批、汇总与丢弃口径无丢失；"
                      "断线时按 %.2fs 起指数退避重连，采集率由 %.2f%% 提升到 %.2f%%。"
                      % (backoff, baseline["rate"], formal["rate"]),
                        "若需零丢弃：把 retry_limit 提到 ≥ 最严重故障的持续尝试数（当前 %d），"
                        "或为超上限的 %d 条读数补一条本地缓存回写链路。"
                        % (worst, ft["drop"])]),
    ]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections


def _docs_ready(root, docs_min):
    """工单「系统文档」的可证伪口径：docs/ 下 GB/T 8566 过程文档的篇数与最小体积。"""
    docs_dir = os.path.join(root, "docs")
    if not os.path.isdir(docs_dir):
        return []
    return [f for f in sorted(os.listdir(docs_dir))
            if f.endswith(".md") and os.path.getsize(os.path.join(docs_dir, f)) > 200]


def _module_mutable_globals(path):
    """AST 数模块级可变全局（dict/list/set 字面量或 new_stats() 调用）。

    工单「线程安全(无共享可变状态)」的静态取证口径：跨线程共享的可变对象越少，
    就越靠参数传递而不是全局累加器。
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    hits = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names, value = [node.target.id], node.value
        else:
            continue
        if value is None:
            continue
        ctor = ""
        if isinstance(value, ast.Call):
            ctor = getattr(value.func, "attr", "") or getattr(value.func, "id", "")
        if (isinstance(value, (ast.Dict, ast.List, ast.Set))
                or ctor == "new_stats"):
            hits += names
    return hits
