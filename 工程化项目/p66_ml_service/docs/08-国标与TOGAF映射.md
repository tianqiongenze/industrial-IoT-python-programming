# 08 国标与 TOGAF 映射表（GB/T 8566《信息技术 软件生存周期过程》）

> 项目：故障诊断模型与边缘部署（W08 第15次课 · 工单 P6）

## 一、GB/T 8566 过程组落地
| 过程组 | 本项目动作 | 交付证据 |
|---|---|---|
| 获取过程 | 工单任务书 P6 明确五步流/门禁/服务/版本四条验收 | 工单任务书/P6工单-故障诊断模型与边缘部署.md |
| 供应过程 | 上游 P2.2 特征产物、P5 仓库为输入；向 P7 输出 model_v1.joblib+服务能力承诺 | docs/06 变更记录 |
| 开发过程·需求分析 | 需求清单→用户故事→验收标准（F-01…F-12 全部有落点） | docs/01 |
| 开发过程·架构设计 | TOGAF 四域+依赖方向+门禁/服务两份 ADR | docs/02 + docs/07 |
| 开发过程·详细设计 | 接口表/异常策略/**工单任务→file:line 映射** | docs/03 §5 |
| 开发过程·实现 | PEP8 + 19 键配置外置 + 特征契约单源 | src/ml_service/ |
| 开发过程·集成 | pipeline 端到端+bench.json 缓存可复现策略 | run.py 输出 + tests/test_pipeline.py |
| 运行过程 | 运行手册（--serve/--bench/--predict/--link-p5/--export-onnx+curl 验收） | docs/05 |
| 维护过程 | 变更记录+基线 B2+manifest 工件审计 | docs/06 |
| 支持过程·配置管理 | rules.yaml 全键被读取；requirements 锁定 | docs/05 §3 + requirements.txt |
| 支持过程·质量保证 | pytest 30 全绿（含 live HTTP）+缺陷 DEF-1…4 闭合 | docs/04 |
| 支持过程·验证 | F1 真实数值断言、400/404 真实往返、联动回写库内可查 | tests/ 对应各节 |
| 支持过程·确认 | 答辩证据链：report.txt 的 CM/GridSearch/压测/ONNX 探测均运行时真实产物 | output/report.txt |

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
| 数据架构 | docs/01 §4 F-01/F-02/F-11 + docs/03 §1 契约与联动设计 + manifest |
| 应用架构 | docs/02 + docs/03 模块接口 + docs/07 ADR-002 |
| 技术架构 | docs/02 + docs/05 运行手册 |
