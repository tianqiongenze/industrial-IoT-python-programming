# P7 智能运维平台（两江智造集团·综合项目·扩展第9周选做）

> 剧情接P6：方总监验收后拍板——"把12周的数据资产变成一个**不睡觉的运维平台**"。
> 你要交付：多模存储 + 缓存 + LLM智能体 + 异步服务，**可直接部署上线**。

## 技术决策矩阵（为什么这么选——写进工单留痕）

| 维度 | 选型 | 理由（对比被淘汰方案） |
|---|---|---|
| Web框架 | **Litestar 2** 全异步 | 类型安全/依赖注入/OpenAPI开箱；比裸http.server并发高两个数量级 |
| 运行时 | **Granian**（Rust） | 多worker多运行时；社区基准与uvicorn互有胜负——**以ab实测为准**（B层作业） |
| 关系型 | SQLite(WAL)+SQLAlchemy 2.0 | 零运维；JSON列兼顾文档型场景（换PostgreSQL只改连接串） |
| 时序 | **DuckDB** 嵌入式OLAP | ASOF对齐/窗口降采样一条SQL；SQLite逐行扫时序慢一个量级 |
| 图 | **Kùzu** 嵌入式图库 | 原生Cypher查拓扑影响路径；Neo4j要装JVM服务。⚠官方2025-10归档，锁0.11.3最终版（Cypher可迁移LadybugDB/ArcadeDB） |
| 向量 | **ChromaDB** 嵌入式 | 案例语义检索；哈希嵌入零下载离线可跑（A层换bge-small-zh） |
| 缓存/KV | **Redis**(TTL/原子INCR限流) | 机房无Redis→diskcache等价回退，接口不变 |
| LLM | 本地规则引擎(OpenAI兼容) | 离线可跑；设OPENAI_BASE_URL即切真实大模型（数据脱敏前置） |

## 目录
```
config.py            路径/端口/开关        train_model.py   诊断模型五步流
stores/relational.py ①关系型台账          stores/timeseries.py ②DuckDB时序
stores/graph.py      ③Kùzu拓扑影响路径    stores/vector_store.py ④Chroma案例
stores/kv.py         ⑤Redis/diskcache     agent/llm.py     离线⇄真实LLM
agent/tools.py       6个工具(OpenAI协议)   agent/engineer.py ReAct循环
service/app.py       Litestar异步API      deploy/          granian/systemd/Docker
verify.sh            端到端断言（ALL PASS才可分享）
```

## 上手三步
```bash
redis-server --port 6399 --daemonize yes   # 可选；没有则自动回退diskcache
/opt/anaconda3/bin/python -m stores.relational && /opt/anaconda3/bin/python -m stores.timeseries \
  && /opt/anaconda3/bin/python -m stores.graph && /opt/anaconda3/bin/python -m stores.vector_store \
  && /opt/anaconda3/bin/python train_model.py
bash verify.sh                             # 五库+服务端到端：ALL PASS ✅
```

## API（granian默认 127.0.0.1:8900）
- `GET /health` — 存活+KV后端
- `GET /api/device/{code}` — 设备360°（台账+时序特征，缓存10s，live/cache字段演示命中）
- `POST /api/predict {"device":"PUMP-03"}` — 模型推理（缓存10s，HIT/MISS可见）
- `POST /api/agent/ask {"question":"..."}` — 智能体五步取证→诊断工单（限流60次/时）

## 与课程的衔接
P2.2特征→train_model；P5仓库→relational；P6模型→predict工具；P4采集→时序入库。
学生版见 `../../学生代码框架/p77_smart_ops/`（5处TODO-P7按图索骥，教师版即本目录）。
