# -*- coding: utf-8 -*-
"""A层·压测与 workers 调优：granian 多 worker vs 单 worker 的 QPS 对比

工单P7-A层要求"`ab -n 1000 -c 50` 压测并调 workers，产出选型+压测对比报告"。
本脚本把这件事变成可复现的一条命令，并把**实测**结果（不做乐观估计）打印成表：

  1) 逐个 worker 配置拉起 granian（ASGI=service.app:app）→ 打 /health → 收摊
  2) 压测器优先用系统 `ab`（工单口径）；没有 ab 则用标准库线程池客户端（口径写明）
  3) 没有 granian/litestar 时**不编数字**：直接跳过 HTTP 轮次，
     改测"应用层 QPS"（绕过 HTTP 栈直调 tools/model_predict），并在报告里标注差异

运行: /opt/anaconda3/envs/pp03/bin/python loadtest.py --workers 1,2,4
      LT_N=1000 LT_C=50 python loadtest.py            # 改压测口径（默认对齐工单）
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PY = sys.executable
PORT = int(os.environ.get("PORT", "8913"))
N = int(os.environ.get("LT_N", "1000"))
C = int(os.environ.get("LT_C", "50"))
PATH = os.environ.get("LT_PATH", "/health")


def _wait_ready(proc, path, timeout=25.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def _ab_metric(line):
    """'Requests per second:   1234.56 [#/sec] (mean)' → 1234.56（取冒号后首个数值）。"""
    tail = line.split(":", 1)[-1].split()
    return float(tail[0]) if tail else None


def _run_ab(path):
    """返回 (qps, failed, 工具名)；解析 ab 的 'Requests per second' 行。"""
    out = subprocess.run(["ab", "-n", str(N), "-c", str(C), "-k",
                          f"http://127.0.0.1:{PORT}{path}"],
                         capture_output=True, text=True, timeout=300).stdout
    qps = failed = None
    for line in out.splitlines():
        if line.startswith("Requests per second:"):
            qps = _ab_metric(line)
        elif line.startswith("Failed requests:"):
            failed = _ab_metric(line)
    return qps, failed, "ab"


def _run_stdlib(path):
    """无 ab 时的等价客户端：线程池打 N 个请求，QPS = N / 总墙钟时间。"""
    from concurrent.futures import ThreadPoolExecutor
    url = f"http://127.0.0.1:{PORT}{path}"
    t0 = time.time()

    def one(_):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return 0 if r.status == 200 else 1
        except Exception:
            return 1
    with ThreadPoolExecutor(max_workers=C) as ex:
        bad = sum(ex.map(one, range(N)))
    dt = time.time() - t0
    return (N / dt if dt > 0 else 0.0), bad, "stdlib-threadpool"


def _http_round(workers, path):
    """拉起一个 workers=N 的 granian 实例，压完即收摊（避免端口残留影响下一档）。"""
    cmd = [PY, "-m", "granian", "--interface", "asgi", "service.app:app",
           "--host", "127.0.0.1", "--port", str(PORT), "--workers", str(workers)]
    proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        if not _wait_ready(proc, path):
            return None, None, None, "启动失败（查看 granian 日志）"
        try:
            qps, failed, tool = (_run_ab(path) if shutil.which("ab")
                                 else _run_stdlib(path))
        except Exception as e:
            return None, None, None, f"压测器异常 {type(e).__name__}"
        if qps is None:
            return None, failed, tool, "压测器输出无法解析（换用 LT_* 变量或检查 ab 版本）"
        return qps, failed, tool, "ok"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _app_round(path):
    """HTTP 栈不可用时的兜底口径：直调一次推理链，只反映业务耗时（不含网络/序列化）。"""
    import json as _json
    from agent import tools
    t0 = time.time()
    r = tools.model_predict("PUMP-03")
    dt = (time.time() - t0) * 1000
    print(f"  model_predict(PUMP-03) {dt:.2f} ms | cache={r['cache']} "
          f"| proba_wear={_json.dumps(r['pred']['proba_wear'])}")
    print("  注意：该口径不含 HTTP/序列化/并发，只用于'无服务运行时'的成本参考。")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", default=os.environ.get("LT_WORKERS", "1,2,4"),
                    help="逗号分隔的 worker 档位")
    ap.add_argument("--path", default=PATH)
    a = ap.parse_args(argv)
    path = a.path
    tiers = [int(x) for x in a.workers.split(",") if x.strip()]

    have_granian = subprocess.run([PY, "-c", "import granian, litestar"],
                                  cwd=HERE, capture_output=True).returncode == 0
    print(f"压测口径：N={N} C={C} path={path} "
          f"客户端={'ab' if shutil.which('ab') else 'stdlib-threadpool（ab 不存在）'}")
    if not have_granian:
        print("granian/litestar 未安装 → HTTP 轮次跳过（不编造 QPS）。应用层对照耗时：")
        _app_round(path)
        return 0

    rows = []
    for w in tiers:
        qps, failed, tool, status = _http_round(w, path)
        rows.append((w, qps, failed, tool, status))
        time.sleep(1)
    print("-" * 68)
    print(f"{'workers':>8} | {'QPS(req/s)':>12} | {'failed':>7} | {'客户端':>20} | 状态")
    print("-" * 68)
    for w, qps, failed, tool, status in rows:
        q = "—" if qps is None else f"{qps:.1f}"
        f = "—" if failed is None else f"{failed:.0f}"
        print(f"{w:>8} | {q:>12} | {f:>7} | {(tool or '—'):>20} | {status}")
    print("-" * 68)
    ok = [r for r in rows if r[1]]
    if len(ok) > 1:
        base = ok[0]
        best = max(ok, key=lambda r: r[1])
        print(f"结论：workers={base[0]} → {base[1]:.1f} QPS；最优 workers={best[0]} → "
              f"{best[1]:.1f} QPS（提升 {best[1] / base[1]:.2f}×）。"
              f"再往上加会因 CPU 核数({os.cpu_count()})与 KV 后端成为瓶颈——"
              f"选型结论以本机实测为准，别抄社区数字。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
