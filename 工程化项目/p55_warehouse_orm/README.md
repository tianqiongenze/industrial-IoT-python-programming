# 产线数据仓库与 ORM（03-Python程序设计-项目实战 · W07 第13次课 · 工单 P5）

> **第三种代码形态：Python 工程化项目** —— 多文件、规则外置、测试齐全、文档完备，
> 符合 GB/T 8566（软件生存周期过程）/ GB/T 9385（需求规格）/ GB/T 15532（测试规范）/
> GB/T 8567（文档编制），并以 TOGAF 四域描述架构。
>
> **v2.1**：按工单 P5 验收表落地 **D/C/B/A 分层达标闸门**（每档逐条实测、可被配置证伪），
> 并新增四表溯源、复杂多表 JOIN 聚合与 P3 仪表盘闭环交接；墙钟毫秒移出 output/ 落 runtime/。
> **v2.0**：按工单 P5 要求实现于 **SQLAlchemy 2.x 声明式 ORM**（v1.0 的手写极简 ORM
> 方案已废弃，决策更正见 docs/07 ADR-001 v2）。

## 一、30 秒跑起来
```bash
cd 工程化项目/p55_warehouse_orm
/opt/anaconda3/envs/pp03/bin/python run.py        # 建库→种子→P4缓冲批量导入→查询→溯源/聚合→分层报告
/opt/anaconda3/envs/pp03/bin/python run.py --query all        # 只打印统计查询
/opt/anaconda3/envs/pp03/bin/python run.py --index-bench      # 重新实测索引前后耗时/EXPLAIN（写 runtime/）
/opt/anaconda3/envs/pp03/bin/python -m pytest -q               # 57 项测试应全绿
/opt/anaconda3/envs/pp03/bin/python ../verify_local.py p55_warehouse_orm   # 三闸门：pytest/run.py/逐字节复现
cd ../p33_kpi_cockpit && /opt/anaconda3/envs/pp03/bin/python run.py --source csv \
    --csv ../p55_warehouse_orm/output/p3_dashboard_handoff.csv # 闭环：P3 读 P5 仓库出仪表盘
```

## 二、目录结构
```
p55_warehouse_orm/
├── run.py                     # 唯一入口（--query/--index-bench/--buffer/--config/--outdir/--quiet）
├── config/rules.yaml          # 15 键全被读取：db_url/buffer_db/seed/n_records/batch_size/warn/danger/
│                              #   unit/topk/index_bench_rows/index_bench_reps/buffer_stand_in_rows/
│                              #   min_stat_queries/n_plus_one_loader/p3_handoff
├── src/warehouse_orm/
│   ├── models.py              # 四表声明式：Device(含 area 车间)/SensorPoint/Record/AlarmEvent
│   │                          #   + relationship 一对多 + __table_args__ 联合索引 idx_dev_ts(point_id, ts)
│   ├── core.py                # 引擎(外键PRAGMA)/种子bulk+提交计数/P4缓冲bulk入库/三条统计查询/
│   │                          #   窗口环比(ORM+text()裸SQL)/数据字典+完整性计数/四表溯源/
│   │                          #   设备×小时四表JOIN聚合(+逐行手算互证)/索引基准(EXPLAIN计划形态)/
│   │                          #   N+1取证(事件计数,三种loader)/慢查询计划/P3交接导出+校验/外键取证
│   ├── pipeline.py            # 编排 + 分层闸门(tiers/tier_criteria) + 墙钟隔离与基准缓存策略
│   ├── config.py / io_utils.py / report.py
├── tests/                     # 57 项：模型/关系/外键/查询/批量/基准/溯源/聚合/交接/端到端/配置/分层闸门
├── output/                    # 确定性证据：warehouse.db / report.txt / result.json /
│                              #   p3_dashboard_handoff.csv（A层交接，P3 直读）
├── runtime/                   # 墙钟实测（.gitignore）：bench.json（前后毫秒/提速倍数/慢查询毫秒）/ bench.db
└── docs/01–08                 # 全套过程文档 + 任务卡→file:line 映射（docs/03 §5）+ 未达标怎么补（§6）
```

## 三、分层达标线（工单 P5 验收表 · 逐条实测，判定见 output/report.txt「分层达标」）
| 档 | 工单验收行 | 判据（可数） | 本次实测 | 判定 |
|---|---|---|---|---|
| 及格 D | 4表设计合理；ORM入库成功；2条统计查询可用 | 建表数=4 且缺表为空；入库行数==种子+缓冲；返回真实行的查询 ≥ min_stat_queries | 4/4 张；1436==500+936；3/3 条（T4a 3、T4b 3、T4c 12 行，门槛 2） | 达标 |
| 良好 C | 数据字典完整；批量事务；溯源查询正确 | 有成文含义列数==总列数且未登记清单空；bulk_save_objects 分批且种子/缓冲各提交≥2 次；四表 JOIN 命中告警数==告警总数且孤儿行 0 | 18/18 列；提交 5+10=15 次（每批≤100）；57/57 命中、孤儿 0 | 达标 |
| 优秀 B | 索引优化有EXPLAIN证据；N+1问题已规避 | 建索引前 SCAN、建索引后 SEARCH USING INDEX、区间命中>0；预加载 SELECT 条数<懒加载条数 | 20000 行基准命中 240 行，SCAN→SEARCH COVERING INDEX；懒加载 4 条 vs joinedload 1 条（3 设备） | 达标 |
| 超优 A | 优秀+复杂查询(多表JOIN聚合)+导入P3仪表盘形成闭环演示 | 四表 JOIN 聚合桶数>0 且与逐行手算一致；交接 CSV 落盘、P3 契约列齐、时间 0 解析失败、0 未知设备 | 36 桶（3设备×12小时）手算互证一致；output/p3_dashboard_handoff.csv 36 行×6 列，0 缺列/0 解析失败 | 达标 |

「工单验收行」一列是《P5工单-产线数据仓库与ORM》验收表的**逐字原文**，单点在
`src/warehouse_orm/pipeline.py` 的 `WO_ROW`，报告「分层达标」每档行首直接引用它
（`tests/test_tier_gates.py::test_workorder_rows_are_quoted_verbatim` 读课程仓工单文件回归锁定）。
「本次实测」是**出货那次运行**的数字：入库行数＝种子 500＋缓冲行数，缓冲来自课程根 `buffer.db`
（由 P4 采集器 `p41_collector_hub/run.py` 写出），所以 P4 重新生成会让这里的行数/桶数一起变；
档位判定只看结构关系（行数==种子+缓冲、命中数==告警总数、桶数>0 且与手算一致），不绑具体数字。
判定逐级累加（C 含 D、B 含 C、A 含 B）；每档都能**只改 config/rules.yaml 不改代码**被判未达标
（证伪用例见 `tests/test_tier_gates.py`，补法见 `docs/03 §6`）。分层任务卡（学徒/操作员/组长/师傅）
覆盖见 `docs/03 §5`。

## 四、验收口径
- `pytest -q` 全绿（58 项）；`run.py` 与全部 flag 退出码 0
- `verify_local.py p55_warehouse_orm` 三闸门 [OK]：pytest / run.py / 两个 PYTHONHASHSEED 下
  两次运行 output/ **逐字节一致**
- 外键约束由库强制（孤儿记录 IntegrityError 被拒，库内孤儿行实测 0，测试取证）
- 索引对比为**真实测量**：20000 行同构副本表实测，执行计划由 `SCAN bench_records` 变
  `SEARCH bench_records USING COVERING INDEX idx_bench_dev_ts`；毫秒数与提速倍数只在
  `runtime/bench.json`（墙钟值不进 output/）；若无加速报告会如实说明
- N+1 用 `before_cursor_execute` 事件监听**数 SELECT 条数**（确定性，非计时）取证
- A 层闭环不是口头声明：`tests/test_queries.py::test_p3_handoff_readable_by_p3_cockpit`
  直接调用 p33 的 `data_source.load(source="csv")` 读交接文件（P3 不在环境则 skip）
- 写入只落本项目 output/（实测值落 runtime/），课程根零污染


## 五、过程文档（GB/T 8567）
[01 需求规格](docs/01-需求规格.md) · [02 架构说明](docs/02-架构说明.md) ·
[03 设计说明](docs/03-设计说明.md) · [04 测试计划与报告](docs/04-测试计划与报告.md) ·
[05 运行手册](docs/05-运行手册.md) · [06 配置管理与变更记录](docs/06-配置管理与变更记录.md) ·
[07 ADR-001(v2)](docs/07-ADR-001-架构决策记录.md) · [08 国标与TOGAF映射](docs/08-国标与TOGAF映射.md)
