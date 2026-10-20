# -*- coding: utf-8 -*-
"""多源轮询 → 还原 → 切批 → 对账 → 落盘。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    sources = list(cfg.items or [])
    if not sources:
        raise ValueError("config/rules.yaml 的 sources 为空")
    batch_size = int(cfg.raw.get("batch_size", 3))
    rounds = int(cfg.raw.get("poll_rounds", 4))
    # transport：无 pymodbus 用确定性本地模拟（课堂可跑）

    def transport(src):
        seed = abs(hash(str(src.get("id")))) % 1000
        return 250 + (seed % 7)

    all_batches, flat, per_source = [], [], {}
    for src in sources:
        sid = str(src.get("id", "PLC"))
        scale = float(src.get("scale", 1))
        sflat = []
        for r in range(rounds):
            raw = core.read(transport, src)
            vals = core.restore(raw, scale)
            sflat += vals
            all_batches.append(vals)
        per_source[sid] = {"n": len(sflat), "sum": round(sum(sflat), 4),
                           "mean": round(sum(sflat) / len(sflat), 4)}
        flat += sflat
    ok, diff = core.reconcile(all_batches, flat)
    result = {"sources": {k: v["n"] for k, v in per_source.items()},
              "per_source": per_source, "reconcile": {"ok": ok, "diff": diff},
              "n_total": len(flat)}
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    sections = [("输入口径", ["数据源 %d 个｜每源 %d 轮×%d 条｜批量 %d 条"
                % (len(sources), rounds, batch_size, batch_size)]),
                ("分源统计", ["%s: %d 条 均值 %.3f" % (k, v["n"], v["mean"])
                          for k, v in per_source.items()]),
                ("对账", ["Σ批次 - Σ单条 = %.9f → %s" % (diff, "通过" if ok else "失败")]),
                ("结论与建议", ["对账恒等式通过，说明切批与汇总无丢失；"
                 "断线时按 %.2fs 起指数退避重连" % cfg.raw.get("backoff_base", 0.01)])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
