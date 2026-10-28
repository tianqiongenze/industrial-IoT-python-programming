# Pandas 数据清洗管道（03-Python程序设计-项目实战 · W03 第5次课）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。

## 一、30 秒跑起来
```bash
cd 工程化项目/p21_pandas_clean
python run.py                 # 输出到 output/ 并打印摘要
python -m pytest -q           # 全量测试（34 例：test_core.py 11 ＋ test_config.py 9 ＋ test_entrypoints.py 1 ＋ test_workorder_tiers.py 13，应全绿）
```

## 二、目录结构
```
p21_pandas_clean/
├── run.py                  # 薄壳入口（sys.path 注入后转调 pd_clean.cli.main）
├── pyproject.toml          # 包元数据 + pytest 配置
├── requirements.txt        # 依赖清单
├── config/rules.yaml       # 规则外置：改配置不改代码
├── src/pd_clean/
│   ├── cli.py              # 命令行入口（[project.scripts] 目标：pd_clean.cli:main）
│   ├── config.py           # YAML 加载 + Settings（含 yaml_lite 兜底）
│   ├── core.py             # 纯函数领域逻辑（零 IO，可单测）
│   ├── io_utils.py         # CSV/JSON/原子写
│   ├── report.py           # 报告渲染
│   ├── stylecheck.py       # 内置 PEP 8 子集度量（D/B 档门禁取数，与 p11 同一口径）
│   └── pipeline.py         # load → process → evaluate → report
├── tests/
│   ├── test_core.py        # 正常/边界/异常三档
│   ├── test_config.py      # 配置加载与校验
│   ├── test_entrypoints.py # [project.scripts] 入口解析回归
│   └── test_workorder_tiers.py  # 工单 D/C/B/A 四行档位：真实运行取证＋配置翻转
├── output/                 # 7 份产物：report/clean.csv/台账/result.json/…（不含墙钟，逐字节可复现）
├── runtime/bench.json      # 压测秒数/吞吐（波动指标，刻意与 output/ 分家）
└── docs/                   # 01~08 全套过程文档（见下）
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
| ① starter | `../../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../../教师参考/` | 完成态参考（单文件示意） |
| ③ **工程化项目（本目录）** | `../`（`工程化项目/`） | **企业级工程结构 + 全套流程资料** |

## 五、验收口径（以《P2.1工单》验收表四行为准）
- `python -m pytest -q` 全绿（34 例）；`python run.py` 生成 `output/report.txt`
  ——本次实测 1206 行进 / 1186 行出，剔除 20 行、清洗率 1.66%，质量分 100.0/100，
  重复率 0.0000%
- 工单《P2.1》「验收标准」四行原文（`pipeline.WO_ROW`，报告第 15 节每档行首逐字引用）
  落成可测条件如下：**D 及格**「管道完整；质量≥85%；PEP 8≥75%」＝管道完整＋质量≥85＋PEP 8 子集≥75%；
  **C 良好**「质量≥88%；处理日志可复现」＝质量≥88＋
  同进程二次运行逐步行数增量与 clean_log 文本逐字节一致；**B 优秀**「质量≥90%；PEP 8≥85%；文档含使用示例」＝质量≥90＋
  PEP 8 子集≥85%＋文档含使用示例（第 六 节，tests 逐字执行）；**A 超优**「优秀+增量处理/自定义验证规则/100万行<5分钟」＝B 档＋
  增量重放 clean.csv 与全量逐字节一致＋自定义验证规则＋100 万行压测达标
  （verdict 取 `runtime/bench.json` 记录）。逐档实测数字见 `output/report.txt` 第 15 节
  与 `output/result.json` 的 `tiers`
- PEP 8 达标率由内置子集 `src/pd_clean/stylecheck.py`（与 p11_exercises 同一口径）
  实测，分层线在 `config/rules.yaml` 的 `pep8_pass_rate` / `pep8_pass_rate_high`
- 配置修改不需改代码（阈值/列名/策略/输出路径/自定义规则/PEP 8 分层线全在
  `config/rules.yaml`）；二次运行 `output/` 逐字节一致——种子固定＋报告不写墙钟，
  压测秒数只写 `runtime/bench.json`
- 过程文档 8 份齐全，可直接用于期末答辩的材料链

## 六、使用示例（可执行）

下面的块是**真实 API 调用**，`tests/test_workorder_tiers.py::test_usage_example_executes`
会原样抽取并执行它（B 档「文档含使用示例」闸门就锚在这一行，示例一腐烂测试立即变红）：

```python
from pd_clean import config, core, pipeline

cfg = config.load_config("config/rules.yaml")     # 规则外置：改配置不改代码
raw = core.generate_raw(n=120, seed=cfg.seed)     # 与课程脏数据同口径的合成表
res = pipeline.run_pipeline(raw, cfg)             # 七步管道（纯函数，零 IO）
print("清洗: %d → %d 行｜质量分 %.1f/100"
      % (res["raw_rows"], len(res["clean"]), res["score"]))
print("质量及格线判定:",
      "达成" if res["tiers"]["tier_D_pass"] else "未达")
assert int(res["clean"][cfg.s("pipeline.temp_column")].isna().sum()) == 0
assert int(res["clean"].duplicated(
    subset=cfg.lst("pipeline.dedupe_subset")).sum()) == 0
```

在项目根目录执行（`pip install -e .` 后，或 `PYTHONPATH=src`）：

```bash
awk '/^```python$/{f=1;next} /^```/{f=0} f' README.md > /tmp/p21_example.py
PYTHONPATH=src python /tmp/p21_example.py         # 期望输出 "清洗: N → M 行｜质量分 …"
```
