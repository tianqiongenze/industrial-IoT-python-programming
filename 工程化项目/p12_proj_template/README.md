# 标准工程模板生成（03-Python程序设计-项目实战 · W01 第2次课）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。
> 工单 P1.2 的 D/C/B/A 四层要求，这里全部落成**可校验的文件与报告数字**，不是文档话术。

## 一、30 秒跑起来
```bash
cd p12_proj_template
/opt/anaconda3/envs/pp03/bin/python run.py       # 生成 output/skeleton/（15 文件）+ 报告
/opt/anaconda3/envs/pp03/bin/python -m pytest -q  # 81 条用例 / 6 文件，应全绿
```

## 二、目录结构
```
p12_proj_template/
├── run.py                  # 薄壳入口 → proj_template.cli:main
├── pyproject.toml          # 包元数据 + [project.scripts] + pytest 配置
├── requirements.txt        # 依赖清单（本项目仅标准库）
├── config/rules.yaml       # 规则外置：改配置不改代码（12 个键，见 docs/05）
├── src/proj_template/
│   ├── cli.py              # argparse 入口（build_parser/main）——修复 [project.scripts] 断链
│   ├── config.py           # YAML 加载 + Settings + DEFAULTS 兜底（含 yaml_lite）
│   ├── core.py             # 模板表 / ensure / verify / inventory / layer_facts / layer_gates
│   ├── env_probe.py        # A 层闸门工具可导入性真实探测（不执行 black/flake8 任何命令）
│   ├── io_utils.py         # CSV/JSON/原子写
│   ├── report.py           # 报告渲染
│   └── pipeline.py         # 生成 → 盘点 → 探测 → 工单四行对照 + 分层达标 → 落盘
├── tests/
│   ├── test_core.py        # 20 条：模板表/生成/自检/分层事实
│   ├── test_config.py      # 10 条：配置加载与校验
│   ├── test_entrypoints.py #  8 条：[project.scripts] 入口回归（断裂脚手架即缺陷）
│   ├── test_env_probe.py   # 17 条：探测三档 + "绝不谎报已运行"
│   ├── test_tier_gates.py  # 12 条：D/C/B/A 逐层取证 + 改配置翻闸门 + 可复现
│   └── test_workorder_rows.py # 14 条：工单验收标准四行原文对照 + 进程内真跑生成骨架
├── output/
│   ├── report.txt          # 七段报告（含「生成清单」「规范闸门环境探测」「工单验收四档对照」「分层达标」）
│   ├── result.json         # files/layers/tiers/tier_lines/workorder_*/probes/config_echo
│   └── skeleton/           # 生成的标准工程（含 .pre-commit-config.yaml、scripts/ 两支脚本）
└── docs/                   # 01~08 全套过程文档（见下）
```

## 三、工单四层 ↔ 实物证据（默认配置跑出来的数字）

> 本表是**课堂四档**（`tiers`，报告「分层达标」段）。工单《P1.2》验收标准的四行原文
> （及格/良好/优秀/超优，`core.WO_ROW`）另有一节「工单验收四档对照」逐行取证：其中
> 良好(C)『检查工具配置生效；pytest通过』课堂四档并不覆盖，由 `core.skeleton_smoke()` 在
> 本进程内真跑生成骨架的 3 个 `test_` 函数补上证据；本机取不了证的子项（真激活 conda、
> 真联网 pip、真触发 git 钩子、CI 未产出）逐条点名，那一行只写「本节取证项 通过」。
| 层 | 工单达标要求 | 实物 | 报告「分层达标」行 |
|---|---|---|---|
| D 学徒 | 跟做示例跑通，程序出结果 | 15 个文件 + 入口 `src.main:main` 可解析、`skeleton_smoke()` 进程内调用 `main()` 真返回 0 | `模板 15 个文件已落盘…入口解析 1/1｜四目录齐备 4/4 → 通过` |
| C 操作员 | venv 可用 + 仓库 + 结构完整 | `scripts/setup_venv.sh`（venv/依赖/git init）+ `.gitignore` 含 `venv/` | `setup_venv.sh 含 python -m venv venv=是…→ 达标` |
| B 组长 | 依赖可还原 + dev 分支规范合并 | 双 requirements（`-r` 引用 + 逐行钉下限）+ `scripts/git_dev_branch.sh`（`--no-ff`） | `运行依赖 2/2 条钉版本下限｜开发依赖 4/4…→ 达标` |
| A 师傅 | pre-commit 钩子：commit 前自动 black+flake8 | `.pre-commit-config.yaml`（`lint_tools` 逐工具一个 local hook）+ `env_probe` 探测 | `声明钩子 2 个（black, flake8）｜本机可导入闸门工具 0/2 → 闸门文件 达标；未安装的工具本次未运行（不谎报）` |

**诚实口径**：课程解释器 pp03 未安装 black/flake8/pylint/ruff/isort/pre-commit，
所以报告写"本次运行未调用任何检查工具"，A 层证据是"闸门文件已就位 + 探测如实上报"；
装上后同一行自动变成"本机可导入 2/2"。测试与流水线**从不执行 git，也从不创建 venv**。

## 四、过程文档（GB/T 8567 文档编制）
| 文档 | 对应标准/方法 |
|---|---|
| [01 需求规格](docs/01-需求规格.md) | GB/T 9385 |
| [02 架构说明](docs/02-架构说明.md) | TOGAF 四域 |
| [03 设计说明](docs/03-设计说明.md) | 核心算法 + 模块接口 + 异常策略 |
| [04 测试计划与报告](docs/04-测试计划与报告.md) | GB/T 15532（81 条节点名全列） |
| [05 运行手册](docs/05-运行手册.md) | GB/T 8566 运行过程（参数表 = rules.yaml） |
| [06 配置管理与变更记录](docs/06-配置管理与变更记录.md) | GB/T 8566 配置管理 |
| [07 ADR-001](docs/07-ADR-001-架构决策记录.md) | 架构决策记录 |
| [08 国标与TOGAF映射](docs/08-国标与TOGAF映射.md) | GB/T 8566 过程组落地 |

## 五、三种代码形态的定位
| 形态 | 目录 | 定位 |
|---|---|---|
| ① starter | `../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../教师参考/` | 完成态参考（单文件示意） |
| ③ **工程化项目（本目录）** | `../工程化项目/` | **企业级工程结构 + 全套流程资料** |

## 六、验收口径
- `python -m pytest -q` 全绿（81 条）；`python run.py` 生成 `output/report.txt`，「分层达标」四行全达标，「工单验收四档对照」四行取证项全通过、未取证子项 8 条逐条点名
- 改配置不改代码：`deps` 去掉版本下限 → B 层未达标；`emit_pre_commit: false` → A 层未达标（均有测试守护）
- `output/` 内除头部一条"生成时间"外，双 `PYTHONHASHSEED` 复跑逐字节一致
- 过程文档 8 份齐全，可直接用于期末答辩的材料链
