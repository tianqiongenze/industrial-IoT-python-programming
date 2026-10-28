# 特征工厂（03-Python程序设计-项目实战 · W04 第7次课）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。

## 一、30 秒跑起来
```bash
cd 工程化项目/p22_feature_factory
python run.py                 # 跑完整流水线并打印第 11 节结论（--quiet 只落盘）
python run.py --quiet         # 输出到 output/（摘要见 output/report.txt 第 11 节）
python -m pytest -q           # 全量测试（61 例 / 7 文件，应全绿）
```

## 二、目录结构
```
p22_feature_factory/
├── run.py                  # 薄壳入口（sys.path 注入后转调 feat_factory.cli.main）
├── pyproject.toml          # 包元数据 + pytest 配置
├── requirements.txt        # 依赖清单（精确版本锁定）
├── config/rules.yaml       # 规则外置：改配置不改代码
├── src/feat_factory/
│   ├── cli.py              # 命令行入口（[project.scripts] 目标：feat_factory.cli:main）
│   ├── config.py           # YAML 加载 + Settings（含 yaml_lite 兜底）与启动校验
│   ├── core.py             # 纯函数领域逻辑（零 IO：30 主特征＋5 衍生、恒等式、去冗余）
│   ├── vector_check.py     # C 层向量化 AST 静态闸门（扫 core 的 12 个特征函数）
│   ├── io_utils.py         # CSV/JSON/原子写
│   ├── report.py           # 报告渲染
│   └── pipeline.py         # load → 特征 → 防泄漏标准化 → RF/去冗余 → 落盘 → 报告
├── tests/
│   ├── test_core.py        # 5 例：正常/边界/异常三档（10/15 列形状、单边谱、坏输入）
│   ├── test_config.py      # 7 例：配置加载、零依赖兜底解析、产物清单自指
│   ├── test_drop_redundant.py   # 11 例：30 特征构成、7 条恒等式、去冗余优先级与阈值等号
│   ├── test_vectorization.py    # 11 例：AST 闸门 0 处逐样本循环、与 dis 的 FOR_ITER 计数对齐
│   ├── test_entrypoints.py      # 2 例：[project.scripts] 入口解析、非 --quiet 路径退出码 0
│   └── test_tier_gates.py       # 12 例：D/C/B/A 四级真数字、墙钟隔离、换种子逐字节一致
├── output/                 # 确定性产物（不含任何墙钟数值）
└── docs/                   # 01~08 全套过程文档（见下）
../runtime/timing.json      # 墙钟实测（best_ms/all_ms/load_ms）——故意在 output/ 之外
```

## 三、过程文档（GB/T 8567 文档编制）
| 文档 | 对应标准/方法 |
|---|---|
| [01 需求规格](docs/01-需求规格.md) | GB/T 9385 |
| [02 架构说明](docs/02-架构说明.md) | TOGAF 四域 |
| [03 设计说明](docs/03-设计说明.md) | 模块设计与异常策略 |
| [04 测试计划与报告](docs/04-测试计划与报告.md) | GB/T 15532 |
| [05 运行手册](docs/05-运行手册.md) | GB/T 8566 运行过程 |
| [06 配置管理与变更记录](docs/06-配置管理与变更记录.md) | GB/T 8566 配置管理 |
| [07 ADR-001](docs/07-ADR-001-架构决策记录.md) | 架构决策记录 |
| [08 国标与TOGAF映射](docs/08-国标与TOGAF映射.md) | GB/T 8566 过程组落地 |

## 四、三种代码形态的定位
| 形态 | 目录 | 定位 |
|---|---|---|
| ① starter | `../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../教师参考/` | 完成态参考（单文件示意） |
| ③ **工程化项目（本目录）** | `../工程化项目/` | **企业级工程结构 + 全套流程资料** |

## 五、验收口径
- `python -m pytest -q` 全绿（实测 61 passed / 7 文件）；`python run.py --quiet` 生成
  `output/report.txt`（12 节，其中 §8.5 是工单《验收标准》四档逐条对照）与 `output/result.json`
- 配置修改不需改代码（报警线、切分比例、冗余阈值、AST 扫描面全在 `config/rules.yaml`）；
  二次运行结果一致：随机种子固定，且墙钟时长只写 `../runtime/timing.json`，
  换 `PYTHONHASHSEED` 重跑 `output/` 逐字节一致
- 出厂口径实测：30 主特征（时域 10＋频域 15＋统计 5）＋5 衍生＝35 列；7 条恒等式全部成立
  （6 条严格恒等在机器精度内，Parseval `spec_energy≈2·var` 偏差 7.4e-04 < 5e-3）；
  逐样本循环 0 处（AST 扫 12 个特征函数）；`a16` 重要性第 1 名（US-02 达成）；
  ｜r｜≥0.95 冗余对 23 对 ⇒ 剔除 11 个、保留 19 个
- 四级达标（D 学徒 / C 操作员 / B 组长 / A 师傅）逐条取证见报告第 8 节，判据与工单
  《验收标准》表的档位差说明见 docs/03 §2「四级闸门与墙钟隔离」
- 过程文档 8 份齐全，可直接用于期末答辩的材料链
