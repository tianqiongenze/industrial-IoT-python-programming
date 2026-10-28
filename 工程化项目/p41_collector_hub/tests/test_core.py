# -*- coding: utf-8 -*-
"""核心层测试：读数重连、退避、丢弃计数、采集率与计数自洽恒等式。"""
import pytest

from collector_hub import core


def flaky(fail_map):
    """构造 transport：fail_map[slot] = 恢复前连续失败的尝试数。"""
    def transport(src, slot, attempt):
        if attempt < int(fail_map.get(slot, 0)):
            raise core.LinkDown("slot %d attempt %d down" % (slot, attempt))
        return 250
    return transport


def test_restore_divides_by_scale():
    assert core.restore([250, 300], 10) == [25.0, 30.0]


@pytest.mark.parametrize("s", [0, -1])
def test_restore_rejects_non_positive_scale(s):
    with pytest.raises(ValueError):
        core.restore([1], s)


def test_reconcile_true_when_sum_matches():
    ok, diff = core.reconcile([[1.0, 2.0], [3.0]], [1.0, 2.0, 3.0])
    assert ok and diff == 0.0


def test_reconcile_false_when_sum_differs():
    ok, diff = core.reconcile([[1.0, 2.0]], [1.0, 2.0, 9.0])
    assert not ok and abs(diff + 9.0) < 1e-9


def test_sleep_with_exponential():
    assert core.sleep_with(0.01, 0) == 0.01
    assert core.sleep_with(0.01, 3) == 0.08


def test_read_retry_no_failure_single_attempt():
    value, attempts, backoff = core.read_retry(flaky({}), {"id": "P"}, 0, 3, 0.01)
    assert (value, attempts, backoff) == (250, 1, 0.0)


def test_read_retry_recovers_after_two_failures():
    value, attempts, backoff = core.read_retry(flaky({2: 2}), {"id": "P"}, 2, 3, 0.01)
    assert value == 250
    assert attempts == 3                      # 首读 + 2 次重连
    assert abs(backoff - 0.03) < 1e-12        # 0.01 + 0.02


def test_read_retry_gives_up_when_retries_exhausted():
    with pytest.raises(core.LinkDown):
        core.read_retry(flaky({2: 4}), {"id": "P"}, 2, 3, 0.01)


def test_read_retry_zero_limit_does_not_reconnect():
    """不重连对照组：首读失败立刻放弃。"""
    with pytest.raises(core.LinkDown):
        core.read_retry(flaky({0: 1}), {"id": "P"}, 0, 0, 0.01)


def test_collect_keeps_all_slots_when_reconnect_works():
    src = {"id": "P1", "latency_ms": 10.0}
    batches, flat, st = core.collect(flaky({}), src, 2, 3, 3, 0.01)
    assert st["planned"] == 6 and st["ok"] == 6 and st["drop"] == 0
    assert len(batches) == 2 and all(len(b) == 3 for b in batches)
    assert flat == [250] * 6


def test_collect_drops_only_beyond_retry_limit():
    """slot0 能重连成功、slot1 超上限 → 计 1 条丢弃，其余 5 条成功。"""
    src = {"id": "P1", "latency_ms": 10.0}
    batches, flat, st = core.collect(flaky({0: 2, 1: 9}), src, 2, 3, 3, 0.01)
    assert st["planned"] == 6 and st["ok"] == 5 and st["drop"] == 1
    assert len(flat) == 5 and len(batches[0]) == 2
    assert st["calls"] == 11 and st["retry"] == 5
    assert st["calls"] == st["ok"] + st["drop"] + st["retry"]
    assert core.check(st)[0] is True
    # 丢弃的那条在放弃前已烧掉 0.01+0.02+0.04=70ms，必须计入等待与耗时，不能凭空消失
    assert st["max_wait_ms"] == pytest.approx(70.0, abs=1e-9)
    assert st["backoff_ms"] == pytest.approx(100.0, abs=1e-9)
    assert st["latency_ms"] == pytest.approx(11 * 10.0 + 100.0, abs=1e-9)


def test_collect_no_retry_baseline_loses_every_faulted_slot():
    src = {"id": "P1", "latency_ms": 10.0}
    _, flat, st = core.collect(flaky({0: 1, 3: 1}), src, 2, 3, 0, 0.01)
    assert st["planned"] == 6 and st["ok"] == 4 and st["drop"] == 2
    assert st["retry"] == 0 and len(flat) == 4
    assert st["calls"] == 6 and st["backoff_ms"] == 0.0


def test_collect_counts_simulated_latency_and_backoff():
    src = {"id": "P1", "latency_ms": 20.0}
    _, _, st = core.collect(flaky({0: 2}), src, 1, 1, 3, 0.01)
    assert st["calls"] == 3
    assert abs(st["latency_ms"] - (3 * 20.0 + 30.0)) < 1e-9
    assert abs(st["backoff_ms"] - 30.0) < 1e-9
    assert abs(st["max_wait_ms"] - 30.0) < 1e-9


def test_merge_sums_counters_and_maximizes_wait():
    a = core.new_stats()
    b = core.new_stats()
    for k, v in (("planned", 3), ("ok", 2), ("drop", 1), ("retry", 4), ("calls", 7)):
        a[k] += v
        b[k] += v
    a["backoff_ms"] = 10.0
    b["backoff_ms"] = 70.0
    a["max_wait_ms"] = 10.0
    b["max_wait_ms"] = 70.0
    m = core.merge(a, b)
    assert (m["planned"], m["ok"], m["drop"], m["retry"], m["calls"]) == (6, 4, 2, 8, 14)
    assert m["backoff_ms"] == 80.0 and m["max_wait_ms"] == 70.0


def test_rate_is_success_over_planned():
    assert core.rate(35, 36) == pytest.approx(97.22222, abs=1e-4)
    assert core.rate(0, 5) == 0.0


@pytest.mark.parametrize("ok,planned", [(1, 0), (1, -3)])
def test_rate_rejects_non_positive_planned(ok, planned):
    with pytest.raises(ValueError):
        core.rate(ok, planned)


def test_check_flags_inconsistent_counters():
    st = core.new_stats()
    st.update(planned=5, ok=4, drop=1, retry=0, calls=5)
    assert core.check(st)[0] is True
    bad = dict(st, calls=99)
    ok, detail = core.check(bad)
    assert ok is False
    assert detail["ok+drop==planned"] is True
    assert detail["calls==ok+drop+retry"] is False
