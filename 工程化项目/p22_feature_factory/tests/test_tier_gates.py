# -*- coding: utf-8 -*-
"""分层工单闸门（D/C/B/A）+ 墙钟隔离 + 逐字节复现（对齐 p41/p66 的同名测试风格）。

在**真实流水线**上取证（tmp 目录跑 run，不打桩）：
  * result.json 的 tiers 四个布尔与报告「分层达标」段的 "X层 … → 达标" 行一致；
  * 报告里的等级标签逐字对齐教师版 notebook cell-0 的达标要求（旧的
    "及格 D/良好 C/优秀 B/超优 A" 是错的口径，这里钉死不让它回来）；
  * 墙钟红线：output/ 内（report.txt 与 result.json）不出现任何时长数值，
    实测 ms 只落 config: io.out_timing_json 指向的 runtime/timing.json；
  * 复现红线：换 PYTHONHASHSEED 重跑，output/ 下每个文件**逐字节**相同
    （不做任何"实测行免比"的打码）；
  * 改配置不改代码：只动 rules.yaml 的文本就能把某一层判成未达标。
"""
import glob
import hashlib
import json
import os
import re
import sys

import pytest

from feat_factory import config as C
from feat_factory import pipeline as P

CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 教师版 W04 cell-0「达标要求」列原文（逐字）
CELL0 = {
    "D": "跟做示例跑通第①个留白(var), 程序出结果",
    "C": "30特征正确+向量化为主",
    "B": "<100ms+特征字典含物理含义",
    "A": "相关系数矩阵热力图：剔除|r|>0.95的冗余特征并说明取舍；示范讲解",
}
TIER_PREFIX = {"D": "D层 学徒·跟做保底", "C": "C层 操作员·基础完成",
               "B": "B层 组长·标准达成", "A": "A层 师傅·进阶拓展"}


def _write_cfg(tmp_path, overrides=()):
    """把项目配置复制到 tmp，并把墙钟文件改写到 tmp/runtime（可选文本替换＝改配置）。"""
    text = open(CFG_PATH, encoding="utf-8").read()
    timing = os.path.join(str(tmp_path), "runtime", "timing.json").replace("\\", "/")
    text = text.replace('"../runtime/timing.json"', '"%s"' % timing)
    for old, new in overrides:
        assert old in text, old
        text = text.replace(old, new)
    path = os.path.join(str(tmp_path), "rules.yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _run(tmp_path, overrides=(), name="out"):
    out = os.path.join(str(tmp_path), name)
    cfg = C.load_config(_write_cfg(tmp_path, overrides))
    res = P.run(cfg, out_dir=out)
    data = json.loads(open(os.path.join(out, "result.json"),
                           encoding="utf-8").read())
    return out, data, res["text"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("tiers"))


def _tier_lines(text):
    return [l for l in text.splitlines() if re.match(r"^[DCBA]层 ", l)]


# ------------------------------------------------------------------ 四级取证
def test_four_tiers_pass_with_real_numbers(built):
    _out, data, text = built
    assert set(data["tiers"]) == {"A", "B", "C", "D"}
    assert all(data["tiers"][k] is True for k in "ABCD")
    lines = _tier_lines(text)
    assert len(lines) == 4, lines
    for k in "DCBA":
        line = next(l for l in lines if l.startswith(TIER_PREFIX[k]))
        assert "→ 达标" in line, line
        assert re.search(r"\d", line), line                 # 每行都带真实数字
    assert data["grade"].startswith("A 师傅·进阶拓展（四级全达标）")


def test_tier_labels_quote_the_workbook_cell_zero_verbatim(built):
    """标签逐字对齐 notebook cell-0；旧的"及格 D/良好 C/优秀 B/超优 A"不得复活。"""
    _out, data, text = built
    for k in "ABCD":
        assert CELL0[k] in text, k                          # 报告里原文出现
        assert CELL0[k] == data["tier_requirements"][k].replace(
            "0.95", "0.95") or CELL0[k] in data["tier_requirements"][k], k
    for wrong in ("及格 D", "良好 C", "优秀 B", "超优 A",
                  "良好线(C)", "优秀线(B)", "当前等级"):
        assert wrong not in text, wrong


def test_section_tier_block_is_exactly_the_four_tier_lines(built):
    """报告「分层达标」段 = 4 条判定行 + 1 条等级判定行（无手写文案混入）。"""
    _out, _data, text = built
    cur = None
    buckets = {}
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1]
            buckets[cur] = []
        elif cur:
            buckets[cur].append(line)
    tier_sec = [k for k in buckets if "分层达标" in k]
    assert len(tier_sec) == 1, buckets.keys()
    body = [l for l in buckets[tier_sec[0]] if l and not l.startswith("---")]
    assert body[:4] == _tier_lines(text)
    assert body[4].startswith("等级判定 : ")
    assert len(body) == 5                                   # 段内不多塞手写文案


def test_c_layer_quotes_the_ast_static_check(built):
    """C 层行必须把 AST 检查的数字搬出来（0 处逐样本循环 + 扫描面 12 个函数）。"""
    _out, data, text = built
    vec = data["vectorization"]
    assert vec["ok"] is True and vec["n_forbidden"] == 0
    assert vec["n_targets"] == vec["n_scanned"] == 12       # 无漏扫、无空转
    assert vec["missing_targets"] == []
    line = next(l for l in _tier_lines(text) if l.startswith("C层"))
    assert "主特征 30" in line and "频域 15" in line
    assert "AST 扫描 12 个特征函数" in line
    assert "逐样本 for/while/推导式 0 处" in line
    assert vec["summary"].startswith("向量化静态检查 : AST 扫描 12 个特征函数")


def test_a_layer_prune_numbers_in_report_equal_the_real_ones(built):
    """A 层行的剔除/保留条数与冗余对数，必须与 result.json 的实测对得上。"""
    out, data, text = built
    red = data["redundancy"]
    kept, dropped = red["kept"], red["dropped"]
    assert len(kept) + len(dropped) == data["features"]["primary"] == 30
    assert set(kept) & {d["feature"] for d in dropped} == set()
    assert all(d["abs_r"] >= red["threshold"] - 5e-5 for d in dropped)
    assert red["pair_counts"]["primary"] >= len(dropped)
    assert red["pair_counts"]["exact_one"] == 1
    line = next(l for l in _tier_lines(text) if l.startswith("A层"))
    assert "剔除 %d 个、保留 %d 个" % (len(dropped), len(kept)) in line
    assert "冗余对 %d 对" % red["pair_counts"]["primary"] in line
    # 热力图必须真落盘，且 A 层行指到的路径与产物清单里的路径是同一个字符串
    assert os.path.exists(os.path.join(out, "corr_heatmap.png"))
    heat = [l.split()[0] for l in data["outputs"]
            if os.path.basename(l.split()[0]) == "corr_heatmap.png"]
    assert len(heat) == 1, data["outputs"]
    assert "热力图 %s" % heat[0] in line, line
    # 恒等对至多留一个（kurtosis ↔ kurtosis_excess）
    assert len({"kurtosis", "kurtosis_excess"} & set(kept)) <= 1


def test_b_layer_gate_is_the_100ms_line_and_dict_has_meaning(built):
    _out, data, text = built
    assert data["perf"]["target_ms"] == 100.0
    assert data["perf"]["verdict"] == "达标"
    assert data["perf"]["within_target"] is True
    line = next(l for l in _tier_lines(text) if l.startswith("B层"))
    assert "≤ B 层线 100 ms" in line and "物理含义非空 35 条（空白 0）" in line


# ------------------------------------------------------------------ 墙钟红线
def test_output_has_no_wallclock_values(built):
    """output/ 内不许出现时长数值：报告里出现的每个 "N ms" 都必须是配置阈值本身。"""
    out, data, text = built
    thresholds = {"%g" % data["perf"]["target_ms"],
                  "%g" % data["perf"]["excellent_ms"]}
    found = set(re.findall(r"(\d+(?:\.\d+)?)\s*(?:ms|毫秒)", text))
    assert found <= thresholds, (found - thresholds,
                                 [l for l in text.splitlines() if "ms" in l])
    assert not re.search(r"\d+\.\d+\s*(?:ms|毫秒)", text)     # 小数毫秒 = 实测值
    for key in ("best_ms", "all_ms", "load_ms", "elapsed", "duration",
                "took_ms", "trained_at"):
        assert key not in text
        raw = open(os.path.join(out, "result.json"), encoding="utf-8").read()
        assert key not in raw

    def leaves(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from leaves(v, k)
        elif isinstance(node, list):
            for v in node:
                yield from leaves(v, key)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            yield key, node

    bad = [k for k, v in leaves(data)
           if k.endswith("_ms") and k not in ("target_ms", "excellent_ms")]
    assert bad == []
    assert data["perf"]["timing_json"].endswith("timing.json")


def test_measured_ms_lands_in_runtime_not_output(built):
    out, data, text = built
    runtime = os.path.join(os.path.dirname(out), "runtime", "timing.json")
    assert os.path.exists(runtime)
    assert not [f for f in os.listdir(out) if "timing" in f]
    t = json.loads(open(runtime, encoding="utf-8").read())
    assert t["best_ms"] > 0 and len(t["all_ms"]) == data["perf"]["repeats"]
    assert t["load_ms"] > 0
    assert "墙钟" in t["note"]
    assert "../runtime/timing.json" not in text      # tmp 配置已改写成绝对路径
    assert "runtime/timing.json" in text


# ------------------------------------------------------------------ 逐字节复现
def _digests(out):
    """output/ 下每个文件的 sha256（一个都不排除：report.txt/result.json 也在内）。"""
    return {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
            for p in sorted(glob.glob(os.path.join(out, "*")))}


def _run_with_seed(tmp_path, seed, name):
    """换 PYTHONHASHSEED 起**子进程**跑 run.py（进程内设环境变量不生效，必须子进程）。"""
    import subprocess

    cfg = _write_cfg(tmp_path, ())
    out = os.path.join(str(tmp_path), name)
    env = dict(os.environ, PYTHONHASHSEED=str(seed),
               PYTHONPATH=os.pathsep.join([os.environ.get("PYTHONPATH", ""),
                                           os.path.join(HERE, "src")]).strip(":"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "run.py"),
                        "--config", cfg, "--outdir", out, "--quiet"],
                       env=env, cwd=HERE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return out


def test_output_is_byte_identical_across_two_hash_seeds(tmp_path):
    """换 PYTHONHASHSEED 重跑：output/ 每个文件逐字节相同（不打码、不免比）。"""
    a = _run_with_seed(tmp_path, 1, "seed1")
    b = _run_with_seed(tmp_path, 7, "seed2")
    da, db = _digests(a), _digests(b)
    assert len(da) >= 9, sorted(da)                         # 真的产出了全套产物
    assert set(da) == set(db)
    assert da == db, {k: (da[k], db[k]) for k in da if da[k] != db[k]}


# ------------------------------------------------------------------ 改配置即可翻闸门
def test_config_only_change_can_fail_a_tier(tmp_path):
    """只改 rules.yaml 文本（不动一行代码）：关掉 AST 闸门 ⇒ C 层判未达标。"""
    _out, data, text = _run(tmp_path, [("enabled: true", "enabled: false")],
                            name="off")
    assert data["tiers"]["C"] is False and data["tiers"]["D"] is True
    assert "已关闭" in text
    assert "C层 操作员·基础完成（30特征正确+向量化为主）" in text
    assert "→ 未达标" in next(l for l in _tier_lines(text) if l.startswith("C层"))


def test_config_only_threshold_change_moves_the_prune_counts(tmp_path):
    """阈值 0.95→0.99 只改配置：冗余对数与剔除条数随之下降，A 层仍按新口径取证。"""
    _out, data, text = _run(tmp_path, [("corr_threshold: 0.95",
                                        "corr_threshold: 0.99")], name="t99")
    line = next(l for l in _tier_lines(text) if l.startswith("A层"))
    assert "剔除|r|>0.99" in text
    assert "冗余对 %d 对" % data["redundancy"]["pair_counts"]["primary"] in line
    assert "剔除 %d 个、保留 %d 个" % (len(data["redundancy"]["dropped"]),
                                       len(data["redundancy"]["kept"])) in line
    assert data["redundancy"]["pair_counts"]["primary"] < 23


def test_config_only_slow_line_fails_b_layer(tmp_path):
    """把 B 层线调到 1ms（并同步 excellent_ms）：耗时判定即刻翻成未达标。"""
    _out, data, text = _run(tmp_path, [("target_ms: 100.0", "target_ms: 1.0"),
                                       ("excellent_ms: 50.0",
                                        "excellent_ms: 0.5")], name="slow")
    assert data["tiers"]["B"] is False and data["tiers"]["D"] is True
    assert data["perf"]["verdict"] == "未达标"
    assert "＞ B 层线 1 ms" in text
    assert "未达标：B" in data["grade"]
