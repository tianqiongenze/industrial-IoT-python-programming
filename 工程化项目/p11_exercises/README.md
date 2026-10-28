# Python 五题闯关（03-Python程序设计-项目实战 · W01 第1次课 · 工单 P1.1）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。
> 需求权威：`../工单任务书/P1.1工单-Python基础练习五题.md`。

## 一、30 秒跑起来
```bash
conda activate pp03                                   # Python 3.12.11
python run.py                                         # 五题 + 断言 + 分层达标 + 报告
python -m pytest -q -p no:cacheprovider               # 190 项测试，全绿
python run.py --tier B                                # 按工单优秀(B) 档线复核
python run.py --list-tools                            # 探测 pylint/flake8/black/pre-commit
python run.py --help                                  # 全部旗标
```

## 二、五题 ↔ 实现（一题一函数，主函数只做调用与输出）
| 题 | 工单要求 | 实现 | 报告实测 |
|---|---|---|---|
| 题1 | ℃→℉ **和** K（双结果） | `core.convert_temperature()` `src/exercise_five/core.py:59` | 100℃ → 212.00℉ / 373.15K |
| 题2 | 一元二次，含无实根 | `core.solve_quadratic()` `core.py:87`（稳定求根式） | Δ<0 → 无实根；b=-1e6 极值残差 0 |
| 题3 | 设备清单字典 CRUD | `core.Registry` `core.py:232`（ID 全链路归一化） | 初始化 3 台 → 删 `02` → 2 台（真删） |
| 题4 | `Device` + `PLC` 子类（含 scan） | `core.PLC` `core.py:159`，覆盖 `start()` `core.py:196`，`scan()` `core.py:201` | `S7-1200启动, 扫描8ms` + 3 轮扫描 |
| 题5 | 异常保护文件读取 | `core.safe_read()` `core.py:296` | FILE_NOT_FOUND / BAD_ENCODING / IS_DIRECTORY / EMPTY_PATH |

## 三、目录结构
```
p11_exercises/
├── run.py                      # 唯一入口（注入 sys.path 后调 cli.main）
├── pyproject.toml              # 包元数据 + 入口点 + pytest/black/pylint 配置
├── requirements.txt            # 真实版本（PyYAML/pytest）+ 未装工具清单
├── config/rules.yaml           # 规则外置：每个键都有消费方
├── src/exercise_five/
│   ├── cli.py                  # argparse：--config/--outdir/--root/--tier/--no-notes/--list-tools/--quiet
│   ├── config.py               # YAML 加载（PyYAML↔yaml_lite 双解析器）+ Settings + ID 归一化 + 校验
│   ├── core.py                 # 五题领域逻辑（零 IO，可单测）
│   ├── exercises.py            # 一题一函数，产出报告行与 payload
│   ├── selfcheck.py            # 50 条内置断言（每题含 空输入/极值/异常）+ 工单 D/C/B/A 达标线
│   ├── stylecheck.py           # 工具真实探测 + 标准库 PEP 8 子集 + 注释/命名/结构实测
│   ├── testmap.py              # tests/ 逐题命名用例真实计数（超优 A"每题附测试用例"）
│   ├── notes.py                # 《C→Python 迁移笔记》生成器 + 完整性实测（≥10 条、逐题 5/5）
│   ├── pipeline.py             # load → 造样例 → 五题 → 断言 → 度量 → 报告
│   ├── report.py               # 确定性渲染/落盘/控制台
│   └── io_utils.py             # 原子写 / 字节写 / CSV / JSON
├── tests/                      # 10 文件 190 项：core/config/exercises/selfcheck/stylecheck
│                               #   + test_tier_d/c/b/a 工单四档验收 + test_pipeline_cli 端到端
├── docs/01~08                  # 国标 + TOGAF 全套过程文档（与代码逐条 file:line 对齐）
├── docs/09-C转Python迁移笔记.md # A 层交付物（每次 run.py 由 notes.py 重写）
└── output/                     # report.txt / result.json / samples/（确定性生成物）
```

## 四、分层（工单 ABCD）怎么自检
定档唯一权威 = `../工单任务书/P1.1工单-Python基础练习五题.md` 的分层表四行；
课堂 notebook 的"学徒/操作员/组长/师傅"阶梯比工单上移一档（它没有"良好(C)"这一层），
因此本项目把闸门重锚到工单字母上，课堂跟做组降级为"保底自检"单独留痕。

| 工单档 | 工单达标线（权威原文） | 自动判定与出厂实测证据 | 现场命令 |
|---|---|---|---|
| D 及格 | ≥3题正确运行；PEP 8≥75%；有基础注释 | `selfcheck.py:321` `tier_gate()`：正确 5/5 题｜PEP 8 内置子集 100.0%（检查项 4761/4761）≥ 75%｜有 docstring 的公开函数 53/53、模块 13/13 | `python run.py --tier D` |
| C 良好 | 4题；命名有意义（落地把「4题」钉成「第 4 题必须正确 + 总正确数 ≥4」） | 同上：第4题正确、正确 5/5 ≥ 4｜命名有意义合格率 100.0%（公开函数/方法名 72/72）≥ 线 90.0%（`stylecheck.check_naming_meaningful()`，线值 `rules.yaml: naming_meaningful_rate`） | `python run.py --tier C` |
| B 优秀 | 5题全对；PEP 8≥85%；结构清晰 | 同上：题1-5 全对 + 断言 B 子集全过 + 命名规范违规 0 + PEP 8 100.0%（≥ 线 85.0%，`pep8_pass_rate_b`）+ 结构四件套 4/4、一题一函数 5/5（均含 docstring）、src 模块 docstring 12/12 | `python run.py --tier B` |
| A 超优 | 优秀+每题附测试用例与《迁移笔记》 | 同上 + `testmap.py`（逐题命名用例真实计数：题1 24｜题2 17｜题3 26｜题4 19｜题5 18，线 `tests_per_question_min`）+ `notes.py:audit()`（docs/09 存在、实测 15 条、逐题易错点 5/5、P1.2 布局映射章节齐全）；"优秀(B) 层达标"是 A 档第一条证据 | `python run.py --tier A` && `python -m pytest -q` |
| 保底自检（不计入工单档位） | 课堂跟做：题1/2 跑通 + 改参数再跑 + 记录一处差异 | 同文件"保底"组 3/3 通过，报告里单列【保底】块，不占工单字母 | 看 report.txt【保底】块 |

## 五、诚实边界（务必读）
- 本环境 **未安装** pylint / flake8 / black / pre-commit（`python -m pylint --version`
  实测报 No module named pylint）。因此工单要求的 "PEP 8 ≥75%（及格 D 行）/≥85%（优秀 B 行）" 由
  `stylecheck.py` 用标准库（`ast`+`tokenize`）实测（总分 + 逐文件 `per_file` 明细）并
  **明确标注"非 pylint 评分"**，两条达标线外置在 `config/rules.yaml`（`pep8_pass_rate_d` /
  `pep8_pass_rate_b`，改配置不改代码，`validate()` 保证 D 线 ≤ B 线）；
  pylint 一栏只会写"不可用"，不会出现编造的百分比。装上工具后无需改代码。
- 工单"命名有意义""每题附测试用例""《迁移笔记》"三行原本无人判定，本项目把它们做成
  可复算的实测：命名合格率（生产码公开函数/方法名）、`tests/` 逐题命名用例计数、笔记完整性审计。
- 超优(A) "pytest 全绿"在报告里是 ℹ 信息项：脚本不替现场执行下结论，
  请自己跑 `python -m pytest -q -p no:cacheprovider`（当前实测 190 passed）。
- 本项目不执行任何 git 写操作（Git 工作流是工单 P1.2 的 `gitflow` 模块负责，
  且只在临时沙箱里跑）。
- 生成物只落在本项目 `output/`（外加 A 层要求的 `docs/09` 一份笔记）。

## 六、过程文档（GB/T 8567 文档编制）
| 文档 | 对应标准/方法 |
|---|---|
| [01 需求规格](docs/01-需求规格.md) | GB/T 9385（含 §8 工单条目→file:line 追踪地图） |
| [02 架构说明](docs/02-架构说明.md) | TOGAF 四域 + 模块职责 |
| [03 设计说明](docs/03-设计说明.md) | 签名表 / 算法 / 异常策略 |
| [04 测试计划与报告](docs/04-测试计划与报告.md) | GB/T 15532（含实测 190 项与缺陷记录） |
| [05 运行手册](docs/05-运行手册.md) | GB/T 8566 运行过程（含配置键→代码位置表） |
| [06 配置管理与变更记录](docs/06-配置管理与变更记录.md) | GB/T 8566 配置管理 |
| [07 ADR](docs/07-ADR-001-架构决策记录.md) | 三条架构决策记录 |
| [08 国标与TOGAF映射](docs/08-国标与TOGAF映射.md) | GB/T 8566 过程组落地 |
| [09 C→Python 迁移笔记](docs/09-C转Python迁移笔记.md) | A 层交付物（自动生成，实测 15 条） |

## 七、三种代码形态的定位
| 形态 | 目录 | 定位 |
|---|---|---|
| ① starter | `../学生代码框架/` | 学生填空起步（TODO 骨架） |
| ② 教师参考 | `../教师参考/` | 完成态参考（单文件示意） |
| ③ **工程化项目（本目录）** | `../工程化项目/` | **企业级工程结构 + 全套流程资料** |

## 八、验收口径
- `python -m pytest -q -p no:cacheprovider` 全绿（190 项）；`python run.py` 退出码 0
  并生成 `output/report.txt`（逐题 PASS/FAIL + 工单四档达标 + 规范实测）。
- 改配置不改代码：`config/rules.yaml` 全部键被消费，未知键报"死配置"。
- 确定性：连跑两次 `output/` 逐字节一致（`tests/test_pipeline_cli.py::test_two_runs_are_identical`）。
- 无占位符：`grep -rn "TODO\|你的代码\|NotImplementedError\|pass  #" src run.py tests` 无输出。
