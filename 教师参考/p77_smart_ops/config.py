# -*- coding: utf-8 -*-
"""P7 智能运维平台 —— 全局配置（路径/开关）

设计原则（对应工单P7技术决策矩阵）：
- 机房离线可跑：所有依赖均为 pip 离线轮子；Redis 不可用时自动回退 diskcache
- 一库一文件：stores/ 下每个存储引擎独立可运行（python -m stores.relational 等）
- 端口约定：granian 8900 / redis 6399（避开 01 包 mock_llm 8899）
"""
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
# P77_DATA_DIR：把存储路径外置，pytest/多实例部署可指向独立目录，避免测试污染教学数据
DATA = os.environ.get("P77_DATA_DIR") or os.path.join(ROOT, "data")
MODELS = os.path.join(DATA, "models")
for _d in (DATA, MODELS):
    os.makedirs(_d, exist_ok=True)

SQLITE_URL = f"sqlite:///{os.path.join(DATA, 'smart_ops.db')}"
DUCK_FILE = os.path.join(DATA, "vibration.duckdb")
KUZU_DIR = os.path.join(DATA, "topology.kuzu")
CHROMA_DIR = os.path.join(DATA, "chroma")
DISK_CACHE = os.path.join(DATA, "diskcache")
CLF_FILE = os.path.join(MODELS, "p77_clf.joblib")
COLLECTION = os.environ.get("COLLECTION", "fault_cases")

# 数据口径时点：与 stores.timeseries 的合成采样起点一致。
# 入库时间戳一律取 AS_OF 而非 utcnow()——否则同一次播种两次运行结果不同，
# "确定性可复现"这条工程纪律就无从谈起（工单P7 评分项·技术质量）。
AS_OF = datetime(2026, 9, 9, 10, 0, 0)

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6399/0")
# LLM：默认本地规则引擎（离线）；设置 OPENAI_BASE_URL 即切真实大模型
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")   # 例 http://127.0.0.1:8899/v1
LLM_MODEL = os.environ.get("LLM_MODEL", "local-mock")

# A层升级位：EMB_BACKEND=bge 时尝试真实语义嵌入（缺依赖即诚实回退哈希嵌入）
EMB_BACKEND = os.environ.get("EMB_BACKEND", "hash")
BGE_MODEL = os.environ.get("BGE_MODEL", "BAAI/bge-small-zh-v1.5")

# 缓存三问之"TTL 多长"——设备视图/模型推理外置可调（改配置不改代码）
CACHE_TTL_DEV = int(os.environ.get("CACHE_TTL_DEV", "10"))
CACHE_TTL_PRED = int(os.environ.get("CACHE_TTL_PRED", "10"))
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "60"))

SERVICE_HOST = os.environ.get("HOST", "127.0.0.1")
SERVICE_PORT = int(os.environ.get("PORT", "8900"))
