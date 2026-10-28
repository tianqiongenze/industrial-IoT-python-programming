# 故障诊断模型与边缘部署（03-Python程序设计-项目实战 · W08 第15次课 · 工单 P6）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。
>
> **v2.0**：训练在 **P2.2 真实特征产物**上进行；推理服务为**标准库 http.server 真实
> 实现**；模型工件 `model_v1.joblib`+版本清单；P5 库联动回写；压测数字真实测量。
> **v2.1**：补齐 **A 层三维评价**（LR/RF/GBM F1+训练耗时+可解释性 Top-3 表）；
> 墙钟 fit_ms 只写 `runtime/train_timing.json` 不入 `output/`；report 新增
> 「分层达标」判定行、result.json 增 `tiers`；`--no-bench` 验收口径。

## 一、30 秒跑起来
```bash
cd 工程化项目/p66_ml_service
/opt/anaconda3/envs/pp03/bin/python run.py            # 五步流→门禁→工件→教师自检→P5联动→报告
/opt/anaconda3/envs/pp03/bin/python run.py --serve    # 起服务（127.0.0.1:8899）：curl /health /predict
/opt/anaconda3/envs/pp03/bin/python run.py --bench    # 强制重新实测延迟 p50/p95/p99 与 QPS
/opt/anaconda3/envs/pp03/bin/python run.py --no-bench # 强制读压测缓存：output/ 字节不变的验收口径
/opt/anaconda3/envs/pp03/bin/python run.py --predict "$(python -c "import numpy as np,json;print(json.dumps(list(np.load('../../features.npy')[0])))")"
/opt/anaconda3/envs/pp03/bin/python run.py --link-p5   # 只重跑 P5 库联动回写
/opt/anaconda3/envs/pp03/bin/python run.py --export-onnx  # A层 ONNX 探测（未装依赖则如实报告）
/opt/anaconda3/envs/pp03/bin/python -m pytest -q      # 56 项测试应全绿（含 live HTTP 与 8 类错误探针实打）
```

## 二、目录结构
```
p66_ml_service/
├── run.py                     # 唯一入口（--serve/--bench/--no-bench/--predict/--link-p5/--export-onnx/…）
├── config/rules.yaml          # 20 键全被读取：数据路径/门禁/网格/CV/端口/压测条数/窗口/可解释性Top-k…
├── src/ml_service/
│   ├── data.py                # 特征契约 FEATURE_NAMES(30) + P2.2 真实源加载/文档化兜底
│   ├── core.py                # 五步流评估(CV+GridSearch留痕+CM+precision/recall)/门禁硬阻断/可解释性
│   │                          #   Top-k(LR=coef_、树=feature_importances_，crc32 稳定破并列)/fit_ms 计时出参/
│   │                          #   save_model+manifest 校验/教师包载入(跨版本告警转录)/predict_row
│   ├── service.py             # ThreadingHTTPServer：/health 真推理、/predict 400/404 契约、logging
│   │                          #   + 真实 HTTP 压测（warmup/p50/p95/p99/QPS）
│   ├── bridge.py              # P5 联动：库副本→窗口抽特征(32→30维)→预测→回写 diagnosis 字段
│   ├── onnx_export.py         # A层边缘路线：import 探测，缺依赖不伪造
│   ├── pipeline.py            # 编排 + bench.json 缓存可复现 + A层三维评价(F1+计时+可解释性)
│   │                          #   + 「分层达标」D/C/B/A 判定 + fit_ms 写 runtime/（不入 output/）
│   ├── config.py / io_utils.py / report.py
├── tests/                     # 56 项：契约/评估/门禁/服务400·404/联动回写/ONNX/端到端/确定性/配置/工单四行对照
│   │                          #   + test_explain_timing(Top-k排序·crc32破并列·k钳制·计时隔离)
│   │                          #   + test_tier_gates(分层达标数字取证·墙钟键隔离·--no-bench 字节一致)
├── output/                    # model_v1.joblib(+manifest) / warehouse_diagnosis.db / report.txt / result.json / bench.json
├── runtime/                   # train_timing.json：墙钟 fit_ms 实测（.gitignore 忽略，禁入 output/）
└── docs/01–08                 # 全套过程文档 + 工单任务→file:line 映射（docs/03 §5）
```

## 三、分层达标线（工单 P6 · 验收标准，report.txt 有「分层达标」逐行数字判定）
| 层 | 任务 | 本项目证据 |
|---|---|---|
| D·及格 | 跟做示例跑通出结果；教师包本地推理≥10样本 | report.txt「D层」预测序列+跨版本告警转录；「分层达标」D 行；--serve curl 200 |
| C·良好 | F1≥0.80 并保存 | model_v1.joblib+manifest；门禁硬阻断（不达标 RuntimeError）；「分层达标」C 行带 macro-F1 实数 |
| B·优秀 | 模型对比+调参记录+接入数据库联动；服务异常处理(404/参数错) | LR/RF/GBM/RF-tuned 对比表+GridSearch best_params/Top5；warehouse_diagnosis.db 回写可 SELECT；400/404 JSON 错误体（live-HTTP 测试） |
| A·超优 | 三维评价：LR/RF/GBM F1+训练耗时+可解释性；ONNX 导出或版本对比实验；P7 立项输入 | report.txt「A层·可解释性 Top-3」表（LR=coef_、树=feature_importances_，进 result.json）；fit_ms 实测写 runtime/train_timing.json（墙钟不入 output/）；onnx_export 探测报告如实呈现；manifest 工件审计链供 P7 复用 |

## 四、验收口径
- `pytest -q` 全绿（56 项）；`run.py` 与全部 flag 退出码 0（非法 --predict → 2）
- 报告含「工单验收四档对照」节：四行原文逐字取证，`service.error_selftest()` 真打 8 类请求拿到 200/400/404，压测两侧条数相等，教师包与新模型逐条比预测；本机取不了证的子项逐条点名，那一行只写「本节取证项 通过」
- 门禁为**硬阻断**：macro-F1<min_f1 直接 RuntimeError，工件不落盘（纯噪声用例测试取证）
- 训练数据=课程根 P2.2 真实 features.npy/labels.npy（报告来源行可核对）；合成仅作
  缺源兜底且注明来源
- 压测为**真实 HTTP 往返**：本环境实测 warmup 首发约 38 ms、p95≈1.1 ms、QPS≈1000
  （output/bench.json）；`--no-bench` 强制读缓存 ⇒ output/ 字节不变（测试取证）
- 墙钟红线：训练耗时 fit_ms **不写入 output/ 任何产物**，只落
  runtime/train_timing.json（.gitignore 忽略）；result.json 无 *_ms 训练键（自动断言）
- 两次默认运行 output/ 除"生成时间/trained_at_utc"外逐字节一致；可解释性并列按
  zlib.crc32(特征名) 破序，杜绝 PYTHONHASHSEED 漂移
- 写入只落本项目 output/（计时例外见上）；P5 库只操作副本，课程根零污染

## 五、三种代码形态的定位
| 形态 | 目录 | 定位 |
|---|---|---|
| ① starter | `../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../教师参考/` | 完成态参考（单文件示意） |
| ③ **工程化项目（本目录）** | `../工程化项目/` | **企业级工程结构 + 全套流程资料** |

## 六、过程文档（GB/T 8567）
[01 需求规格](docs/01-需求规格.md) · [02 架构说明](docs/02-架构说明.md) ·
[03 设计说明](docs/03-设计说明.md) · [04 测试计划与报告](docs/04-测试计划与报告.md) ·
[05 运行手册](docs/05-运行手册.md) · [06 配置管理与变更记录](docs/06-配置管理与变更记录.md) ·
[07 ADR-001/002](docs/07-ADR-001-架构决策记录.md) · [08 国标与TOGAF映射](docs/08-国标与TOGAF映射.md)
