# -*- coding: utf-8 -*-
"""采集中枢：读数、还原、对账恒等式、断线重试与采集率（transport 可注入）。

transport 协议：transport(src, slot, attempt) -> 寄存器原值，链路中断时抛 LinkDown。
slot 为该源本次会话内的读数序号（0 基），attempt 为第几次尝试（0 基=首读）。
所有计数（planned/ok/drop/retry/calls/latency）都由配置推导，不含墙钟，可逐字节复现。
"""


class LinkDown(Exception):
    """链路中断/读超时：由 transport 抛出，交由重试层决定重连或丢弃。

    放弃时带上已烧掉的尝试数与累计退避，丢弃条目才不会漏记耗时。
    """
    attempts = 1
    backoff_seconds = 0.0


def new_stats():
    """APM 计数初值：calls=传输调用次数，retry=重试次数，latency_ms=模拟链路耗时。"""
    return {"planned": 0, "ok": 0, "drop": 0, "retry": 0, "calls": 0,
            "backoff_ms": 0.0, "max_wait_ms": 0.0, "latency_ms": 0.0}


def merge(*stats):
    """合并多份 APM 计数（分源 → 全局）；max_wait_ms 取最大值，其余求和。"""
    total = new_stats()
    for st in stats:
        for k in total:
            if k == "max_wait_ms":
                total[k] = max(total[k], st[k])
            else:
                total[k] += st[k]
    return total


def sleep_with(backoff_base, attempt):
    """指数退避：base × 2^attempt。"""
    return backoff_base * (2 ** attempt)


def read_retry(transport, src, slot, retry_limit, backoff_base):
    """读一条：失败按指数退避重连，最多重连 retry_limit 次。

    retry_limit=0 即"不重连"（首读失败立刻放弃）。
    返回 (值, 尝试次数, 累计退避秒)；重试用尽仍失败则向上抛 LinkDown。
    """
    attempt, backoff_total = 0, 0.0
    while True:
        try:
            value = transport(src, slot, attempt)
        except LinkDown as exc:
            if attempt >= retry_limit:
                exc.attempts = attempt + 1
                exc.backoff_seconds = backoff_total
                raise
            backoff_total += sleep_with(backoff_base, attempt)
            attempt += 1
        else:
            return value, attempt + 1, backoff_total


def collect(transport, src, rounds, batch_size, retry_limit, backoff_base):
    """采完一个源：rounds 轮 × batch_size 条，断线自动重连。

    返回 (批次列表, 展平读数列表, APM 计数)。重试用尽的条目计入 drop，
    因此 len(展平) 可能小于 planned —— 这正是"丢弃数"的口径。
    """
    base_ms = float(src.get("latency_ms", 10.0))
    batches, flat, st = [], [], new_stats()
    for r in range(int(rounds)):
        batch = []
        for i in range(int(batch_size)):
            st["planned"] += 1
            slot = r * int(batch_size) + i
            try:
                value, attempts, backoff = read_retry(
                    transport, src, slot, int(retry_limit), backoff_base)
            except LinkDown as exc:
                attempts, backoff = exc.attempts, exc.backoff_seconds
                st["drop"] += 1
            else:
                batch.append(value)
                flat.append(value)
                st["ok"] += 1
            st["calls"] += attempts
            st["retry"] += attempts - 1
            st["backoff_ms"] += backoff * 1000.0
            st["max_wait_ms"] = max(st["max_wait_ms"], backoff * 1000.0)
            st["latency_ms"] += attempts * base_ms + backoff * 1000.0
        batches.append(batch)
    return batches, flat, st


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


def rate(ok, planned):
    """采集率(%) = 成功条数 ÷ 计划条数；planned 含最终丢弃的条目。"""
    if planned <= 0:
        raise ValueError("计划读数必须为正（当前 %d）" % planned)
    return 100.0 * ok / planned


def check(st):
    """APM 计数自洽校验：成功+丢弃=计划，且 调用=成功+丢弃+重试。"""
    balanced = (st["ok"] + st["drop"] == st["planned"]
                and st["calls"] == st["ok"] + st["drop"] + st["retry"])
    return balanced, {
        "ok+drop==planned": st["ok"] + st["drop"] == st["planned"],
        "calls==ok+drop+retry": st["calls"] == st["ok"] + st["drop"] + st["retry"],
    }
