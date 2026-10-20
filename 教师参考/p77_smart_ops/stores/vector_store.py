# -*- coding: utf-8 -*-
"""存储引擎④ 向量库：ChromaDB（嵌入式持久化）——故障案例语义检索

离线要点：不下载任何嵌入模型——自实现"中文哈希嵌入"（字→bigram→定长向量）。
语义检索流程: 案例文本 → 哈希嵌入 → Chroma持久化 → query_embedding 近邻召回
真实项目升级位（工单P7-A层）: 换 bge-small-zh / text2vec 本地模型，接口不变。

单独运行: /opt/anaconda3/bin/python -m stores.vector_store
"""
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from config import CHROMA_DIR

DIM = 256


class HashEmbedding(EmbeddingFunction):
    """确定性中文嵌入：字级+bigram 哈希到固定维度（离线、零下载、可复现）"""

    def __init__(self):
        super().__init__()

    @staticmethod
    def name() -> str:
        return "hash-bigram-zh"

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(t) for t in input]

    def _embed(self, text: str) -> list:
        v = [0.0] * DIM
        grams = list(text) + [text[i:i + 2] for i in range(len(text) - 1)]
        for g in grams:
            v[hash(g) % DIM] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [round(x / norm, 6) for x in v]


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


def seed():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = client.get_or_create_collection("fault_cases", embedding_function=HashEmbedding())
    for c in CASES:
        col.upsert(ids=[c["id"]], documents=[c["text"]], metadatas=[c["meta"]])
    return col


def search(query: str, k: int = 2) -> list:
    """语义近邻召回：'振动变大' 也能召回 '振动爬升' 案例"""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = client.get_or_create_collection("fault_cases", embedding_function=HashEmbedding())
    r = col.query(query_texts=[query], n_results=min(k, col.count()))
    return [{"case": d, "meta": m, "dist": round(s, 3)}
            for d, m, s in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]


if __name__ == "__main__":
    import json
    seed()
    print(json.dumps(search("泵振动持续变大怎么办", 2), ensure_ascii=False, indent=1))
