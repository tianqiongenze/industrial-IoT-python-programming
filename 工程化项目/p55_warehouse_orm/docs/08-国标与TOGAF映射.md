# 08 国标与 TOGAF 映射表（GB/T 8566《信息技术 软件生存周期过程》）

> 项目：产线数据仓库与 ORM（SQLAlchemy 2.x · W07 第13次课）

## 一、GB/T 8566 过程组落地
| 过程组 | 本项目动作 | 交付证据 |
|---|---|---|
| 获取过程 | 工单任务书 P5 明确范围与验收 | 工单任务书/P5工单-产线数据仓库与ORM.md |
| 供应过程 | 按工期与 P6/P7 下游数据承诺（warehouse.db 供 P6 联动） | docs/06 变更记录 |
| 开发过程·需求分析 | 需求清单→用户故事→验收标准（F-01…F-11 全部有落点） | docs/01 |
| 开发过程·架构设计 | TOGAF 四域+依赖方向+仓库模式 | docs/02 + docs/07 ADR（v2 更正） |
| 开发过程·详细设计 | 接口表/异常策略/**任务卡→file:line 映射** | docs/03 §5 |
| 开发过程·实现 | PEP8 + 配置外置 + 声明式模型 | src/warehouse_orm/ |
| 开发过程·集成 | pipeline 端到端+缓存可复现策略 | run.py 输出 + tests/test_pipeline.py |
| 运行过程 | 运行手册（含 --query/--index-bench/--buffer） | docs/05 |
| 维护过程 | 变更记录+基线 B2 | docs/06 |
| 支持过程·配置管理 | rules.yaml 全键被读取；requirements 锁定 | docs/05 §3 + requirements.txt |
| 支持过程·质量保证 | pytest 29 全绿+缺陷记录（DEF-1/2 已闭合） | docs/04 |
| 支持过程·验证 | 查询结果与手动 JOIN 口径互证、ORM=裸SQL 断言 | tests/test_queries.py |
| 支持过程·确认 | 答辩证据链：EXPLAIN 真实行/数据字典/N+1 计数 | output/report.txt |

## 二、GB/T 标准对应
| 标准 | 名称 | 本项目落点 |
|---|---|---|
| GB/T 8566 | 软件生存周期过程 | 本表过程分类 |
| GB/T 9385 | 软件需求规格说明 | docs/01 |
| GB/T 15532 | 软件测试规范 | docs/04 |
| GB/T 8567 | 软件文档编制 | docs/01–08 全套 |

## 三、TOGAF 四域 ↔ 文档映射
| TOGAF 域 | 对应文档 |
|---|---|
| 业务架构 | docs/01 需求规格（US-01…05） |
| 数据架构 | docs/01 §4 + docs/03 §1 四表ER/索引设计 + output/report.txt 数据字典 |
| 应用架构 | docs/02 + docs/03 模块接口 |
| 技术架构 | docs/02 + docs/05 运行手册 |
