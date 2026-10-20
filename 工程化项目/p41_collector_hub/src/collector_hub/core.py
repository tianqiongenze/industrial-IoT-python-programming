# -*- coding: utf-8 -*-
"""采集中枢：读数、还原、对账恒等式、指数退避（transport 可注入）。"""


def read(transport, src):
    """从指定源读一批寄存器原值（transport 可注入，便于测试）。"""
    return [transport(src) for _ in range(int(src.get("n", 3)))]


def restore(raw, scale):
    """单位还原：寄存器原值 ÷ scale。"""
    if scale <= 0:
        raise ValueError("scale 必须为正（当前 %.3f）" % scale)
    return [v / scale for v in raw]


def reconcile(batches, flat):
    """对账恒等式：Σ批次应等于 Σ单条。"""
    sb = sum(sum(b) for b in batches)
    sf = sum(flat)
    return abs(sb - sf) < 1e-9, round(sb - sf, 9)


def sleep_with(backoff_base, attempt):
    """指数退避：base × 2^attempt。"""
    return backoff_base * (2 ** attempt)
