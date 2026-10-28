# -*- coding: utf-8 -*-
"""存储引擎④ 向量库：ChromaDB（嵌入式持久化）——故障案例语义检索

离线要点：不下载任何嵌入模型——自实现"中文哈希嵌入"（字→bigram→定长向量）。
语义检索流程: 案例文本 → 哈希嵌入 → Chroma持久化 → query_embedding 近邻召回
真实项目升级位（工单P7-A层）: 换 bge-small-zh / text2vec 本地模型，接口不变。

⚠ 工程红线（教师版已修复的历史坑，答辩常问）：
  嵌入**禁止**用内置 hash()——CPython 对 str 启用 PYTHONHASHSEED 随机化，
  播种进程与检索进程算出的向量不一致 → 入库后跨进程检索召回随机漂移。
  必须用与进程无关的稳定摘要（zlib.crc32），"可复现"才成立。

单独运行: /opt/anaconda3/envs/pp03/bin/python -m stores.vector_store
"""
import zlib

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from config import BGE_MODEL, CHROMA_DIR, COLLECTION, EMB_BACKEND

DIM = 256

CASES = [
    {"id": "case-001", "text": "3号泵站振动爬升 轴承磨损 特征频率吻合 更换轴承后恢复",
     "meta": {"device": "PUMP-03", "action": "更换轴承", "year": 2025}},
    {"id": "case-002", "text": "循环泵压力波动 叶轮堵塞 清洗叶轮 振动恢复正常",
     "meta": {"device": "PUMP-03", "action": "清洗叶轮", "year": 2024}},
    {"id": "case-003", "text": "主风机振动超标 地脚螺栓松动 紧固后温度振动下降",
     "meta": {"device": "FAN-02", "action": "紧固螺栓", "year": 2025}},
    {"id": "case-004", "text": "电机电流异常 联轴器对中不良 激光对中后电流恢复",
     "meta": {"device": "MOTOR-A2-1", "action": "激光对中", "year": 2023}},
]


def grams(text: str) -> list:
    """字 + bigram 词元（与工单点位 P7-4 的教学口径一致）。"""
    return list(text) + [text[i:i + 2] for i in range(len(text) - 1)]


def slot(gram: str, dim: int = DIM) -> int:
    """词元 → 维槽位。**必须**用与进程无关的稳定摘要：
    内置 hash() 受 PYTHONHASHSEED 随机化污染，播种进程与检索进程槽位不同 → 召回随机漂移。
    """
    return zlib.crc32(gram.encode("utf-8")) % dim


def unit(v: list) -> list:
    """L2 归一化（余弦检索下等价于单位向量），全零向量原样返回。"""
    norm = sum(x * x for x in v) ** 0.5 or 1.0
    return [round(x / norm, 6) for x in v]


class HashEmbedding(EmbeddingFunction):
    """确定性中文嵌入：字级+bigram 哈希到固定维度（离线、零下载、可复现）

    试过 IDF 加权，但在 eval_retrieval.py 的 gold 查询集上 recall@1/2/3 与不加权完全持平
    （0.857/0.857/1.000），故**不加这层复杂度**——工程优化要有对照实验支撑，不能凭感觉。
    """

    def __init__(self, dim: int = DIM) -> None:
        # 基类 __init__ 会发 DeprecationWarning（要求子类自己实现），故显式覆盖且不调 super
        self.dim = dim

    @staticmethod
    def name() -> str:
        return "hash-bigram-zh"

    def default_space(self) -> str:
        return "cosine"            # 嵌入已 L2 归一化，余弦距离=1-内积

    def supported_spaces(self) -> list:
        return ["cosine"]

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(t) for t in input]

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @classmethod
    def from_config(cls, config):
        return cls(int(config.get("dim", DIM)))

    @classmethod
    def build_from_config(cls, config):
        # chromadb>=1.5 从持久化配置重建嵌入函数：必须是 classmethod，
        # 写成实例方法会在反序列化时被当成 self=config 而报 TypeError（跨进程一致性依赖这里）
        return cls.from_config(config or {})

    def _embed(self, text: str) -> list:
        v = [0.0] * self.dim
        for g in grams(text):
            v[slot(g, self.dim)] += 1.0
        return unit(v)


def resolve_embedding(backend=None):
    """A层升级位：按后端名返回 (embedding_function, label)，缺依赖时**诚实回退**不谎报。

    backend: hash（默认，零下载）| bge（需 sentence-transformers + 本地权重）
    回退原因会打到 stdout，召回对比见 eval_retrieval.py。
    """
    backend = (backend if backend is not None else EMB_BACKEND or "hash").lower()
    if backend in ("bge", "bge-small-zh", "sentence"):
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction)
            ef = SentenceTransformerEmbeddingFunction(model_name=BGE_MODEL)
            return ef, f"bge-small-zh({BGE_MODEL})"
        except Exception as e:                       # 离线机房无模型/无依赖
            print(f"[vector] 请求 bge 嵌入失败({type(e).__name__})→诚实回退 hash-bigram-zh")
    return HashEmbedding(), HashEmbedding.name()


def _collection(ef, label=None):
    """label 非空=按后端建库（首次生效）；检索时只复用已存在的集合。"""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    if label:
        return client.get_or_create_collection(
            COLLECTION, embedding_function=ef,
            metadata={"hnsw:space": "cosine", "embedding": label})
    return client.get_or_create_collection(COLLECTION, embedding_function=ef)


def seed():
    ef, label = resolve_embedding()
    col = _collection(ef, label=label)
    for c in CASES:
        col.upsert(ids=[c["id"]], documents=[c["text"]], metadatas=[c["meta"]])
    return col


def search(query: str, k: int = 2) -> list:
    """语义近邻召回（实测口径，别把话说满——见 eval_retrieval.py 的 recall 对照）：

      · '3号泵站振动爬升轴承磨损' 这类**词面重合**的问法：top-1 即命中（dist≈0.36）
      · '泵振动持续变大怎么办' 这类**同义改写**（变大↔爬升）：k=2 漏，k=3 才回
        ——哈希嵌入解不了词面不同的同义，这正是工单P7-A层换 bge-small-zh 的实测理由。

    工单点位 P7-4 答案要点：PersistentClient → get_or_create_collection 时**必须传同一个
    embedding_function**（否则查询向量与库内向量不在同一空间）→ col.query(query_texts=...)
    → 组装 [{"case","meta","dist"}]。
    高频翻车点：空库时 n_results=0 会让 Chroma 抛错；先取 count()，空库返回 [] 并告警，
    k 用 max/min 夹紧到 [1, count]。
    """
    ef, _ = resolve_embedding()
    col = _collection(ef)
    n = col.count()
    if not n:                                        # 空输入边界：不抛异常，显式告警
        print("[vector] 案例库为空——请先 python -m stores.vector_store 播种")
        return []
    r = col.query(query_texts=[query], n_results=min(max(int(k), 1), n))
    return [{"case": d, "meta": m, "dist": round(s, 3)}
            for d, m, s in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]


if __name__ == "__main__":
    import json
    seed()
    # k=3：把同义改写问法漏掉的 case-001 也显示出来，配合 eval_retrieval.py 讲"为什么要换模型"
    print(json.dumps(search("泵振动持续变大怎么办", 3), ensure_ascii=False, indent=1))
