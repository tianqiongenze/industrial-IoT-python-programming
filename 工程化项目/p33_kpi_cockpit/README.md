# KPI 驾驶舱（03-Python程序设计-项目实战 · W05 第9次课）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。

## 一、30 秒跑起来
```bash
cd 工程化项目/p33_kpi_cockpit
python run.py                 # 输出到 output/ 并打印摘要
python -m pytest -q           # 全量测试（270 例 / 11 文件，应全绿）
streamlit run app.py          # 真仪表盘：点趋势折线点/选告警行 → 联动明细（A 层）
python run.py --app-check     # 不启浏览器的无头仪表盘自检（AppTest）
```

## 二、目录结构
```
p33_kpi_cockpit/
├── run.py                  # 薄壳入口（sys.path 注入后转调 kpi_cockpit.cli.main，含 --drill/--app-check/--determinism）
├── app.py                  # Streamlit 真仪表盘（on_select="rerun" 选择事件联动明细）
├── pyproject.toml          # 包元数据 + pytest 配置
├── requirements.txt        # 依赖清单
├── config/rules.yaml       # 规则外置：改配置不改代码（含 drill.max_rows/detail_columns）
├── src/kpi_cockpit/
│   ├── cli.py              # 命令行入口（[project.scripts] 目标：kpi_cockpit.cli:main）
│   ├── config.py           # YAML 加载 + Settings（含 yaml_lite 兜底）
│   ├── core.py             # 纯函数领域逻辑（drill_rows 联动明细，CLI/UI 同一真源）
│   ├── data_source.py      # TODO-0 数据源（clean.csv 优先 / seed 合成兜底）
│   ├── deps.py             # 可选依赖真探测
│   ├── io_utils.py         # CSV/JSON/原子写
│   ├── report.py           # 报告渲染（四段式日报 HTML/PDF）
│   ├── schedule.py         # A 层定时（crontab/systemd/mailto/移动端）
│   └── pipeline.py         # load → process → evaluate → report + 分层达标证据
├── tests/                  # 11 个文件 270 例：core 边界、AppTest 无头、pipeline 端到端、
│                           # test_tier_gates.py（D/C/B/A 分层闸门，可证伪）、
│                           # test_workorder_rows.py（四行逐字对表工单原文）、test_entrypoints.py（scripts 入口解析）
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
| ① starter | `../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../教师参考/` | 完成态参考（单文件示意） |
| ③ **工程化项目（本目录）** | `../工程化项目/` | **企业级工程结构 + 全套流程资料** |

## 五、验收口径
- `python -m pytest -q` 全绿（270 例 / 11 文件）；`python run.py` 生成 `output/report.txt`
- 配置修改不需改代码；二次运行结果一致（种子固定；证据指纹用 zlib.crc32，不吃 PYTHONHASHSEED）
- `output/report.txt` 含「工单 TODO 覆盖」「分层达标（D/C/B/A）」「联动钻取证据（A 层·可复核）」，
  `output/result.json` 含 `tiers` 布尔闸门（drill.max_rows 改 0 → `tiers.A=false`，当场可证伪）
- A 层联动明细走真选择事件：st.plotly_chart/st.dataframe 的 `on_select="rerun"` →
  同一份 `core.drill_rows()`（AppTest 无头断言接线，CLI 复放选择事件断言行为）
- 过程文档 8 份齐全，可直接用于期末答辩的材料链
