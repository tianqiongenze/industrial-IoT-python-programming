# -*- coding: utf-8 -*-
"""A层·检索召回对比：全文LIKE vs 哈希嵌入 vs 真实语义模型（bge-small-zh）

工单P7-A层要求"哈希嵌入换 bge-small-zh 对比召回"。本脚本把四档后端在同一份
gold 标注查询集上并排出 recall@k，形成答辩要的**选型留痕**：

  like            —— 决策矩阵里的被淘汰方案（全文 LIKE 计数），基线
  hash-unigram    —— 只做字级哈希（消融组：证明 bigram 的价值）
  hash-bigram-zh  —— 本项目默认嵌入（零下载、离线、确定性）
  bge-small-zh    —— sentence-transformers + 本地权重（真语义模型）

诚实口径：本机没有 sentence-transformers/模型权重时，bge 一行**不编数字**，
输出 "未测" 并在附注里说明跳过原因与复现命令。

运行: /opt/anaconda3/envs/pp03/bin/python eval_retrieval.py [--k 2] [--json]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stores.vector_store import CASES, DIM, HashEmbedding, grams, slot, unit  # noqa: E402

# gold 查询集：运维问法 → 期望召回的案例 id（工单剧情里的真实场景）
QUERIES = [
    ("泵振动持续变大怎么办", ["case-001"]),
    ("3号泵站振动爬升轴承磨损", ["case-001"]),
    ("压力波动 叶轮堵塞", ["case-002"]),
    ("主风机振动超标地脚松动", ["case-003"]),
    ("风机螺栓紧固", ["case-003"]),
    ("电机电流异常联轴器不对中", ["case-004"]),
    ("激光对中", ["case-004"]),
]


class UnigramEmbedding(HashEmbedding):
    """消融组：只保留字级 gram（不拼 bigram），其余与默认嵌入一致。"""

    def _embed(self, text):
        v = [0.0] * DIM
        for g in list(text):
            v[slot(g)] += 1.0
        return unit(v)


def _unit(vec):
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


def _vecs(ef, texts):
    return [_unit(list(map(float, v))) for v in ef(texts)]


def _like_docs(query, corpus, k):
    """全文 LIKE 基线：按查询字命中的篇内字数排序（生产里就是 LIKE/FTS 检索）。"""
    score = [(sum(1 for ch in set(query) if ch in t), -i) for i, t in enumerate(corpus)]
    return [i for _, i in sorted(score, key=lambda x: (-x[0], x[1]))[:k]]


def _topk(qvec, dvecs, k):
    sims = [sum(a * b for a, b in zip(qvec, d)) for d in dvecs]
    return sorted(range(len(sims)), key=lambda i: -sims[i])[:k]


def recall_at_k(rank_fn, k):
    """recall@k = 命中 gold 的查询占比（单 gold 场景下即 top-k 命中率）。"""
    hit = sum(1 for q, gold in QUERIES if any(CASES[i]["id"] in gold for i in rank_fn(q, k)))
    return hit / len(QUERIES), hit


def embed_bge(texts):
    """返回 (vectors, 说明)——依赖/权重缺失时向量为 None，调用方据此标'未测'。"""
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(os.environ.get("BGE_MODEL", "BAAI/bge-small-zh-v1.5"))
        return [list(map(float, v)) for v in m.encode(texts)], "bge-small-zh 已加载"
    except Exception as e:                            # 缺包/缺权重/需联网——一律如实说明
        return None, f"跳过（{type(e).__name__}: {str(e)[:60]}）"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    docs = [c["text"] for c in CASES]

    rows = []
    r, h = recall_at_k(lambda q, k: _like_docs(q, docs, k), a.k)
    rows.append(("like 全文LIKE", r, h, "决策矩阵·被淘汰基线"))

    uni = UnigramEmbedding()
    dv = _vecs(uni, docs)
    r, h = recall_at_k(lambda q, k: _topk(_vecs(uni, [q])[0], dv, k), a.k)
    rows.append(("hash-unigram(无bigram)", r, h, "消融组"))

    bi = HashEmbedding()
    dv = _vecs(bi, docs)
    r, h = recall_at_k(lambda q, k: _topk(_vecs(bi, [q])[0], dv, k), a.k)
    rows.append(("hash-bigram-zh", r, h, "本项目默认（零下载离线）"))

    bq, note = embed_bge(docs)
    if bq is None:
        rows.append(("bge-small-zh", None, None, note))
    else:
        r, h = recall_at_k(lambda q, k: _topk(_unit(list(map(float, embed_bge([q])[0][0]))),
                                              bq, k), a.k)
        rows.append(("bge-small-zh", r, h, note))

    if a.json:
        print(json.dumps([{"backend": b, "recall_at_k": rr, "hits": hh, "note": nn}
                          for b, rr, hh, nn in rows], ensure_ascii=False, indent=1))
    else:
        print(f"故障案例库 {len(CASES)} 条｜gold 查询 {len(QUERIES)} 条｜k={a.k}｜DIM={DIM}"
              f"｜gram 口径={len(grams('振动变大'))} 元/4字")
        print("-" * 76)
        for b, rr, hh, nn in rows:
            cell = "未测" if rr is None else f"{rr:.3f}"
            print(f"{b:26s} recall@{a.k} = {cell:>6s} ({hh}/{len(QUERIES)})  {nn}")
        print("-" * 76)
        miss = [q for q, g in QUERIES
                if all(CASES[i]["id"] not in g
                       for i in _topk(_vecs(bi, [q])[0], dv, a.k))]
        if miss:
            print(f"哈希嵌入仍未命中：{miss}——共性是**同义改写**（变大↔爬升），"
                  f"词面不同则哈希无解，这正是 A 层换 bge-small-zh 的理由。")
        if rows[-1][1] is None:
            print("bge 行未测。复现：pip install sentence-transformers && "
                  "预下载 BAAI/bge-small-zh-v1.5，再 EMB_BACKEND=bge python -m stores.vector_store "
                  "重新播种后重跑本脚本。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
