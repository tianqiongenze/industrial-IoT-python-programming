# -*- coding: utf-8 -*-
"""工程化项目终验（本机版，替代写死 Windows 路径的 _docx_work/eng/verify_projects.py）。

每项目三道闸 + 规模统计：
  1. pytest -q 全绿
  2. run.py 产出非空 output/report.txt
  3. 两次运行（PYTHONHASHSEED 不同）结果一致 —— 只随墙钟变化的实测值免比，
     判定文字（等级/达标/条数）仍逐字节比；免比部分计数打印，防止把真实数据漂移一起免掉
用法：python verify_local.py [项目名 ...]   （缺省扫全部 p* 目录）
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("PY", "/opt/anaconda3/envs/pp03/bin/python")


MEASURE = re.compile(
    r"(生成时间|时间戳|实测耗时|实测|耗时|用时|trained_at|timing\.txt|墙钟)")
# 墙钟实测值：报告里一律带小数（26.60 ms），阈值/仿真定级值一律是整数（100 ms / 8ms）。
# 只把"带小数的 ms 数字"打码，同一行的判定文字（等级、✔、阈值）仍逐字节比较，
# 这样性能回归会把 ✔ 改成 ✗、把 优秀B 改成 良好C，依然能被比出来。
MS_VALUE = re.compile(r"\d+\.\d+(?=\s*(?:ms|毫秒))")
# result.json 里同样口径：只有计时类 key 下的数值叶子免比，其余（特征值/等级/条数）全比
JSON_TIME_KEY = re.compile(r"(perf|timing|latenc|elapsed|duration|took|_ms$)")


def _prune_json(node):
    """返回 (规范化的树, 免比叶子数)。"""
    n = [0]

    def walk(v, key=""):
        if isinstance(v, dict):
            return {k: walk(x, k) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [walk(x, key) for x in v]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if JSON_TIME_KEY.search(key):
                n[0] += 1
                return "<time>"
        return v

    return walk(node), n[0]


def mask_text(lines):
    """行级免比口径：整行是墙钟/时间戳 → 丢掉；行内带小数的 ms 实测值 → 打码。"""
    keep = [MS_VALUE.sub("#", l) for l in lines if not MEASURE.search(l)]
    skipped = (len(lines) - len(keep)) + sum(1 for l in lines if MS_VALUE.search(l))
    return keep, skipped


def norm_digest(path):
    """可复现性比较口径：数据推导出来的行必须逐字节相同；
    只随墙钟变化的"实测耗时/生成时间"允许不同（打码后仍比对整行其余文字），
    免比的部分会计数打印，防止把真实的数据漂移一起免掉。"""
    if not os.path.exists(path):
        return "-", 0
    raw = open(path, encoding="utf-8", errors="ignore").read()
    skipped = 0
    if path.endswith(".json"):
        try:
            tree, skipped = _prune_json(json.loads(raw))
            raw = json.dumps(tree, ensure_ascii=False, sort_keys=True, indent=1)
        except ValueError:
            pass
    keep, extra = mask_text(raw.splitlines())
    return hashlib.sha256("\n".join(keep).encode("utf-8")).hexdigest()[:12], skipped + extra


def digest(path):
    if not os.path.exists(path):
        return "-"
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]


def run(cmd, cwd, hashseed=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if hashseed is not None:
        env["PYTHONHASHSEED"] = str(hashseed)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=900, env=env)
    out = (r.stdout or b"").decode("utf-8", "ignore")
    err = (r.stderr or b"").decode("utf-8", "ignore")
    return r.returncode, out, err


def source_text(d):
    txt = []
    for root, ds, fs in os.walk(d):
        if ".pytest_cache" in root or "__pycache__" in root or ".git" in root:
            continue
        for f in fs:
            if f.endswith((".py", ".md", ".yaml", ".toml")):
                try:
                    txt.append(open(os.path.join(root, f), encoding="utf-8").read())
                except Exception:
                    pass
    return "\n".join(txt)


def check(proj):
    d = os.path.join(HERE, proj)
    rep = os.path.join(d, "output", "report.txt")
    res = os.path.join(d, "output", "result.json")
    rows = []

    rc, out, err = run([PY, "-m", "pytest", "-q"], d)
    last = (out.strip().splitlines() or [err.strip().splitlines()[-1] if err.strip() else "?"])[-1]
    rows.append(("pytest", rc == 0, last[:120]))

    if os.path.exists(rep):
        os.remove(rep)
    rc, out, err = run([PY, "run.py", "--quiet"], d, hashseed=1)
    made = os.path.exists(rep) and os.path.getsize(rep) > 0
    detail = "%dB" % os.path.getsize(rep) if made else (
        (err.strip().splitlines() or ["no report.txt"])[-1][:110])
    rows.append(("run.py", rc == 0 and made, detail))

    sig1 = (norm_digest(rep), norm_digest(res))
    rc, out, err = run([PY, "run.py", "--quiet"], d, hashseed=7)
    sig2 = (norm_digest(rep), norm_digest(res))
    same = sig1[0][0] == sig2[0][0] and sig1[1][0] == sig2[1][0]
    rows.append(("repeat", rc == 0 and same,
                 "%s %s 免比行=%d/%d %s" % (sig1[0][0], sig1[1][0], sig1[0][1], sig1[1][1],
                                          "(两次PYTHONHASHSEED不同仍一致)" if same else "(数据行有漂移)")))

    t = source_text(d)
    tiers = {k: len(re.findall(r"%s层|%s\s*[\u4e00-\u9fa5]" % (k, k), t)) for k in "ABCD"}
    n_py = sum(1 for r0, _d0, f0 in os.walk(d) for f in f0
               if f.endswith(".py") and ".pytest_cache" not in r0 and "__pycache__" not in r0)
    n_doc = len([f for f in os.listdir(os.path.join(d, "docs"))
                 if f.endswith(".md")]) if os.path.isdir(os.path.join(d, "docs")) else 0
    n_test = len(re.findall(r"^def test_|^    def test_", t, re.M))
    rows.append(("scale", True, "py=%d docs=%d testfn=%d tier=%s" % (
        n_py, n_doc, n_test, "".join("%s:%d " % (k, v) for k, v in tiers.items()))))

    print("-" * 78)
    print(proj)
    okall = True
    for name, ok, detail in rows:
        if name != "scale":
            okall = okall and ok
        print("  [%s] %-7s %s" % ("OK" if ok else "!!", name, detail))
    return okall


def main():
    projs = sys.argv[1:] or sorted(
        p for p in os.listdir(HERE)
        if re.match(r"^p\d", p) and os.path.isdir(os.path.join(HERE, p)))
    bad = [p for p in projs if not check(p)]
    print("=" * 78)
    print("项目数 %d ｜ 全绿 %d ｜ 有失败 %s" % (len(projs), len(projs) - len(bad), bad or "无"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
