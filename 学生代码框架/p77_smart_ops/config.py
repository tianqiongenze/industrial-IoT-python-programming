# -*- coding: utf-8 -*-
"""P7 智能运维平台 —— 全局配置（路径/开关）

设计原则（对应工单P7技术决策矩阵）：
- 机房离线可跑：所有依赖均为 pip 离线轮子；Redis 不可用时自动回退 diskcache
- 一库一文件：stores/ 下每个存储引擎独立可运行（python -m stores.relational 等）
- 端口约定：granian 8900 / redis 6399（避开 01 包 mock_llm 8899）
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
MODELS = os.path.join(DATA, "models")
for _d in (DATA, MODELS):
    os.makedirs(_d, exist_ok=True)

SQLITE_URL = f"sqlite:///{os.path.join(DATA, 'smart_ops.db')}"
DUCK_FILE = os.path.join(DATA, "vibration.duckdb")
KUZU_DIR = os.path.join(DATA, "topology.kuzu")
CHROMA_DIR = os.path.join(DATA, "chroma")
DISK_CACHE = os.path.join(DATA, "diskcache")
CLF_FILE = os.path.join(MODELS, "p77_clf.joblib")

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6399/0")
# LLM：默认本地规则引擎（离线）；设置 OPENAI_BASE_URL 即切真实大模型
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")   # 例 http://127.0.0.1:8899/v1
LLM_MODEL = os.environ.get("LLM_MODEL", "local-mock")

SERVICE_HOST = os.environ.get("HOST", "127.0.0.1")
SERVICE_PORT = int(os.environ.get("PORT", "8900"))
