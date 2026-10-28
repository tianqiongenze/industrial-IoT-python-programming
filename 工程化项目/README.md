# 03-Python程序设计-项目实战 · 工程化项目索引（第三种代码形态）

> 每个工单一个**可运行的 Python 工程化项目**：多文件分层、规则外置、pytest 分档测试、
> 8 份国标/TOGAF 过程文档。本索引 2026-10-27 按磁盘实况重写（旧版目录名 `W01_exercises…W08_ml_service`
> 从未存在过，真实目录名见下表）。

## 一、三种代码形态的定位

| 形态 | 目录 | 定位 |
|---|---|---|
| ① starter | `../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../教师参考/` | 完成态参考（`solutions.py` 九题自检 + `p77_smart_ops/` 包） |
| ③ **工程化项目（本目录）** | `工程化项目/` | **企业级工程结构 + 全套流程资料** |

## 二、项目清单（8 个，与课堂 notebook 一一对应）

| 工单 | 课堂 notebook（教师版，在 `../Jupyter实训/`） | 本目录项目 | 核心功能 | 过程文档 | 测试文件 | 用例（pytest 收集） |
|---|---|---|---|---|---|---|
| 03-P1.1 | `W01_P1.1_Python基础_教师版.ipynb` | `p11_exercises/` | Python 五题闯关 | 9 | 10（含 `test_tier_a/b/c/d.py`） | 190 |
| 03-P1.2 | `W02_P1.2_标准Python_教师版.ipynb` | `p12_proj_template/` | 标准工程模板生成 | 8 | 6 | 81 |
| 03-P2.1 | `W03_P2.1_Pandas数据_教师版.ipynb` | `p21_pandas_clean/` | Pandas 数据清洗管道 | 8 | 4 | 34 |
| 03-P2.2 | `W04_P2.2_NumPy故障特_教师版.ipynb` | `p22_feature_factory/` | 特征工厂（时域15+频域15） | 8 | 7 | 61 |
| 03-P3 | `W05_P3_产线KPI仪表盘_教师版.ipynb` | `p33_kpi_cockpit/` | KPI 驾驶舱 | 8 | 11 | 270 |
| 03-P4.1 | `W06_P4.1_多源数据采集系统_教师版.ipynb` | `p41_collector_hub/` | 多源数据采集中枢 | 8 | 4 | 47 |
| 03-P5 | `W07_P5_产线数据仓库与O_教师版.ipynb` | `p55_warehouse_orm/` | 数据仓库 ORM | 8 | 6 | 58 |
| 03-P6 | `W08_P6_故障诊断模型与部_教师版.ipynb` | `p66_ml_service/` | 模型训练与边缘服务 | 8 | 8 | 56 |

合计 **797 条用例**，全部在 `/opt/anaconda3/envs/pp03/bin/python` 下 `python -m pytest -q` 实跑通过。

- 用例数 = 各项目 `pytest --collect-only` 的真实节点数相加（参数化展开后的条数）。
  `verify_local.py` 的 `scale` 行里那个 `testfn=` 是**源码里 `def test_` 的字面计数**，口径不同：
  p11 `testfn=142` 对 190 条、p33 `testfn=229` 对 270 条、p41 `testfn=45` 对 47 条（参数化展开变多），
  p12 `testfn=82` 对 81 条（`core.py` 的骨架模板字符串里也写着 `def test_`，会被多算一条）。
- `p11_exercises/` 比其余项目多一份 `docs/09-C转Python迁移笔记.md`。
- **03-P7 不在本目录**：它以 `../Jupyter实训/W09_P7_智能运维平台综合_教师版.ipynb`（五库+RAG+部署三件套）
  和 `../教师参考/p77_smart_ops/`（`verify.sh` 19 项 `ALL PASS`）两形态交付，本目录没有 `p77_*` 项目。

## 三、单个项目的结构

```
<slug>/
├── README.md               # 三种形态定位 + 目录 + 验收口径
├── pyproject.toml          # 包元数据 + pytest 配置
├── requirements.txt        # 依赖清单
├── .gitignore
├── run.py                  # 唯一入口（argparse CLI：--config/--outdir/--quiet + 工单专属开关）
├── config/rules.yaml       # 规则外置：改配置不改代码
├── src/<pkg>/
│   ├── config.py           # YAML 加载 + Settings（含 yaml_lite 零依赖兜底）
│   ├── core.py             # 纯函数领域逻辑（零 IO，可单测）
│   ├── io_utils.py         # CSV/JSON/原子写
│   ├── report.py           # 报告渲染
│   ├── pipeline.py         # load → process → evaluate → report 编排
│   └── <工单专属模块>       # p11: cli/exercises/selfcheck/stylecheck；p33: data_source/deps/schedule
│                           # p55: models；p66: data/bridge/service/onnx_export
├── tests/                  # 正常 / 边界 / 异常三档（p11 另有分层 test_tier_*）
├── docs/                   # 8 份过程文档
│   ├── 01-需求规格.md       # GB/T 9385
│   ├── 02-架构说明.md       # TOGAF 四域
│   ├── 03-设计说明.md
│   ├── 04-测试计划与报告.md  # GB/T 15532
│   ├── 05-运行手册.md       # 配置表与 config/rules.yaml 逐字对齐
│   ├── 06-配置管理与变更记录.md  # GB/T 8566 配置管理
│   ├── 07-ADR-001-架构决策记录.md
│   └── 08-国标与TOGAF映射.md  # GB/T 8566 过程组落地表
└── output/                 # 运行产物（report.txt + result.json + 图/表），重跑即覆盖；
                            # 仓库里保留一份当前产物作为"可复现"的对照基线
```

墙钟计时类产物**不进 `output/`**：`p22_feature_factory` 写 `../runtime/timing.json`，
`p21_pandas_clean` 写本项目 `runtime/bench.json`。这样 `output/` 内每个文件都可逐字节复现。

## 四、30 秒跑起来

本课程包的校准解释器是 `/opt/anaconda3/envs/pp03/bin/python`（Python 3.12，
numpy/pandas/sklearn/streamlit/pymodbus/litestar 齐；**无** fastapi/pylint/flake8/black，
所以代码规范检查用的是零依赖的 stdlib 自检，不是外部 linter）。

```bash
cd <slug>
/opt/anaconda3/envs/pp03/bin/python run.py            # 生成 output/report.txt + result.json
/opt/anaconda3/envs/pp03/bin/python -m pytest -q      # 全量测试（应全绿）
```

`run.py` 三个通用开关是 `--config` / `--outdir` / `--quiet`（`--quiet` 只落盘不打印）；
`p12`/`p22`/`p41` 只有这三个，其余项目各有工单专属开关：
`p11 --tier B/--list-tools/--no-notes/--root`（入口在 `src/exercise_five/cli.py`）、
`p21 --incremental/--input/--peek/--no-bench/--stamp`、
`p33 --pdf/--drill/--source/--csv/--date/--start/--end/--device/--schedule-at/--schedule-fire/--determinism/--app-check/--stamp`、
`p55 --query/--index-bench/--buffer`、
`p66 --serve/--predict/--bench/--no-bench/--export-onnx`。
完整清单看 `python run.py --help`。

## 五、验收口径

- `python -m pytest -q` 全绿；`python run.py` 生成非空 `output/report.txt`。
- **两次运行逐字节一致**：用不同 `PYTHONHASHSEED` 各跑一遍再比指纹。
  只有墙钟实测值免比（报告里带小数的 `ms`、`result.json` 里计时类 key 的数值叶子），
  等级/达标/条数/特征值一律逐字节比较，免比行数会打印出来（`免比行=N/M`），防止把真实数据漂移一起免掉。
  注意 `hash()` 对字符串是按 `PYTHONHASHSEED` 随机的，需要稳定散列的位点用 `zlib.crc32`。
- 配置修改不需改代码；`docs/05-运行手册.md` 的参数表与 `config/rules.yaml` 逐字对齐。
  p41 已把这条口径做成闸：`tests/test_config.py::test_docs05_param_table_matches_rules_yaml_keys_and_defaults`
  （键集合双向相等 + 默认值同值；实测把 `docs_min` 的手册值写成 9 立即判红）。
- **工单四档与课堂四档分开判**：每个项目的 `report.txt` 都有「工单验收四档对照」/
  `X档 及格「…」` 一节，行首四行原文来自单一真源（`WO_ROW` 常量），并由一条**逐字对表课程仓
  `工单任务书/P*.md` 验收表**的用例钉住——工单改了措辞而代码没跟，当场判红；项目被单独打包带走
  （工单文件不在相对位置）则自动 skip，不误伤：
  p11 `tests/test_pipeline_cli.py::test_workorder_rows_are_quoted_verbatim`、
  p12 `tests/test_workorder_rows.py::test_rows_quote_the_work_order_verbatim`、
  p21 `tests/test_workorder_tiers.py::test_workorder_rows_are_quoted_verbatim`、
  p22/p66 `tests/test_workorder_rows.py::test_constants_match_the_work_order_file_itself`、
  p33 `tests/test_workorder_rows.py::test_wo_row_constant_matches_the_work_order`、
  p41 `tests/test_workorder_rows.py::test_constants_match_the_work_order_file_itself`、
  p55 `tests/test_tier_gates.py::test_workorder_rows_are_quoted_verbatim`。
  两套字母**不同源**（课堂 D 跟做保底 / C 基础完成 / B 标准达成 / A 进阶拓展 vs
  工单 及格/良好/优秀/超优），报告里必须写「档位口径说明」，工单独有的条款（如 P4 的
  「采集率≥99.5%＋延迟<100ms＋线程安全」）要单独取证，不许拿课堂档位冒充。
- 8 份过程文档齐全，可直接构成期末答辩的材料链。

## 六、一键复核：`verify_local.py`（本目录）

```bash
cd 工程化项目
/opt/anaconda3/envs/pp03/bin/python verify_local.py            # 扫全部 p* 目录
/opt/anaconda3/envs/pp03/bin/python verify_local.py p22_feature_factory   # 只扫一个
```

每项目四行：`pytest` / `run.py` 产物字节数 / `repeat`（双 HASHSEED 指纹 + 免比行数）/ `scale`（py·docs·测试函数·分层字样计数）。
当前状态：**项目数 8 ｜ 全绿 8 ｜ 有失败 无**。

> 仓库根的 `_docx_work/eng/verify_projects.py` 写死了
> `C:/Users/Lenovo/AppData/Local/Temp/audit/env314/Scripts/python.exe`，本机不可用；
> 以本目录 `verify_local.py` 为准（解释器可用环境变量 `PY` 覆盖）。

## 七、改代码前先读：生成器会整体覆盖

这 8 个项目由**仓库根**的生成器产出（路径不在本目录内，别按本目录相对路径找）：

```
../../_docx_work/eng/          # 相对本目录两级：本目录在 03-Python程序设计-项目实战/ 下，
                               # 其上一级即仓库根；绝对路径 <仓库根>/_docx_work/eng/
                               # （旧版这里写成 ../../../ 是错的，该路径不存在）
├── eng_specs.py + specs_01/02/03/05.py   # 规格：specs_03.py 里 8 个 P(id="03-P…")，slug 与磁盘一致
├── eng_gen.py                      # 模板 + 写盘库（不是命令行程序）
└── build_all.py                    # 真正的驱动：python build_all.py
```

两个必须知道的坑：

1. **`eng_gen.py --build --only 03-W04` 这条命令不存在。** `eng_gen.py` 文件头这么写，
   但它内部没有任何 `argparse`/CLI（全文只有模板字符串和写盘函数）；
   真正的一键生成是 `python build_all.py`，而它**不接受项目筛选参数**——
   一旦运行就遍历 `eng_specs.SPECS` 重写**四门课的全部工程化项目**，
   再跑 autopep8 排版、`strip_unused_imports()` 删导入、flake8 校验（本机没装 flake8，校验会空跑）。
2. `write_text()` 是 `open(path, "w")` **无条件覆盖**，所以本目录里的**手工修复会被抹掉**，
   包括但不限于：`p22_feature_factory` 的产物清单自指修复 + `tests/test_config.py` 回归测试、
   `p11_exercises` 的分层 `test_tier_*.py`（规格里根本没有这些测试）、
   `p21_pandas_clean` 与 `p22_feature_factory` 两份 `docs/05-运行手册.md` 参数表、
   **8 份报告里的「工单验收四档对照 / X档 及格「…」」取证节**（原文单一真源 `WO_ROW`：
   p12 在 `core.py`，p21/p22/p33/p41/p55/p66 在 `pipeline.py`，p11 是 `selfcheck.py` 的
   `_tier_criterion()`（渲染进 `result.json` 的 `tiers[t]["criterion"]`）；判定函数
   `workorder_gates()`/`_workorder_gates()`/`_tier_lines()`，
   p12 还含进程内真跑的 `core.skeleton_smoke()`，p33/p41/p55/p66 另含逐档翻红的可证伪用例）、
   **8 个逐字对表 `工单任务书/P*.md` 的锁用例**（`tests/test_workorder_rows.py` × 5、
   p21 `tests/test_workorder_tiers.py`、p55 并入 `tests/test_tier_gates.py`、
   p11 并入 `tests/test_pipeline_cli.py`）、
   p41 `tests/test_config.py::test_docs05_param_table_matches_rules_yaml_keys_and_defaults`
   （手册↔配置对齐闸）、
   `p11_exercises` 的 `src/exercise_five/notes.py` 与它渲染出的 `docs/09-C转Python迁移笔记.md`。
   判定依据：在 `<仓库根>/_docx_work/eng/` 下 grep
   `四档对照`/`skeleton_smoke`/`WO_ROW`/`迁移笔记`/`notes.py`/`test_tier_`/`workorder_rows` **零命中**
   （只有 `工单任务书` 这个词在共用文档模板里出现 2 次，与验收表取证逻辑无关）——
   这些都只存在于磁盘，生成器一份都不知道。
   尤其注意 p11 的 `docs/09-C转Python迁移笔记.md` 是**生成物**：
   `tests/test_pipeline_cli.py::test_shipped_run_adjudicates_all_four_tiers_pass`
   会先快照仓库里那份的字节、跑一遍流水线，再 `assert` 字节没变——
   所以改了 `src/exercise_five/config.py`（例如删一个配置键）后第一次跑 pytest 会红，
   因为落盘的那份还是旧版；`python run.py` 重生成后再跑就绿，这不是回归。
   已回贴到源头的一处：`specs_03.py` 里 p41 的 `abs(hash(...))` 已改成
   `zlib.crc32(...)`（内置 `hash()` 受 `PYTHONHASHSEED` 随机化，会把可复现闸门锁死），
   与磁盘上的 `p41_collector_hub/src/collector_hub/pipeline.py` 一致；
   其余手工修复**尚未**回贴到 `specs_03.py`，重放前请按 diff 处理。

要重放：先把这些项目的 `git diff` 存成补丁，生成后再贴回来；
或者改 `specs_03.py`（源头）而不是改生成后的项目文件。
重放后务必回到本目录跑 `verify_local.py`，8 项全绿才算没退回。
