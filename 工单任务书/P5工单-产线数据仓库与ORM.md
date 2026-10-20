# 工单 P5《产线数据仓库设计与ORM开发》（第7周·4课时·难度⭐⭐⭐⭐）

## 任务情境
P4采集数据入库沉淀：4表ER设计 + SQLAlchemy ORM入库 + KPI统计与故障溯源查询 + 索引优化。数据库用SQLite（零安装）。

## 课前导学单
1. 微课《ER建模四步+SQLAlchemy十分钟》（6分钟）；
2. 预习自测：一对多关系在表结构上如何表达？
3. 手绘四表ER草图：设备/测点/采集记录/告警事件。

### 预习教材与上次课检查（62号轮·课前必读）

> **📖 课前预习｜本课教材**：《Python程序设计项目化教程（活页式）》**项目4**
> 预习知识点：SQLAlchemy ORM；ER设计；批量写入与索引
> 学法提示：先读教材对应项目节→再看微课→完成导学单预习自测
> **✓ 课中检查｜上周（P6）抽查**：采集率≥95%——随机2人口述/白板，答对记过程分

## 任务要求（P5.1设计 + P5.2 ORM）
1. ER设计：4表+主外键+数据字典（字段名/类型/含义）；
2. ORM模型：SQLAlchemy声明式（Device/SensorPoint/Record/AlarmEvent + relationship）；
3. 入库：把P4缓冲数据批量写入（每批100条，事务提交）；
4. 统计查询：各设备平均温度；告警Top3设备；按时间段聚合；
5. 优化：给 records(device_id, ts) 建索引，EXPLAIN对比前后。

## 决策矩阵（数据访问方式）
| 方式 | 开发效率 | 性能可控性 | 团队协作 | 决策 |
|------|---------|-----------|---------|------|
| 裸SQL | | | | |
| SQLAlchemy Core | | | | |
| SQLAlchemy ORM | | | | |

## 验收标准
| 等级 | 标准 |
|------|------|
| 及格(D) | 4表设计合理；ORM入库成功；2条统计查询可用 |
| 良好(C) | 数据字典完整；批量事务；溯源查询正确 |
| 优秀(B) | 索引优化有EXPLAIN证据；N+1问题已规避 |
| 超优(A) | 优秀+复杂查询(多表JOIN聚合)+导入P3仪表盘形成闭环演示 |

## 提交物
代码 + ER图 + 数据字典.md + 优化前后查询耗时对比


### 知识四要素详解（V1.2深度版·与授课PPT同源）

**B01 仓库模式**
- 定义：仓库模式=档案室三级索引：设备档案1-N测点盒N-记录纸；告警挂档案
- 使用场景：时序数据入库的关系建模——三张主表
- 应用实例：devices / metrics / alarms 外键关联
- 扩展与误区：误区：一张大宽表塞所有——先画ER再建表，表错后面全返工
- 原理：仓库模式(Repository)=数据访问收拢一层：业务代码只调repo.list_devices()，SQL/ORM细节藏在里面——换数据库不动业务
- 判断依据：凡是'数据从哪来'可能变化（SQLite→PostgreSQL/加缓存）的项目，先建仓库层——解耦的物理隔离墙
- 逐行解释：class DeviceRepo: def list(self): return session.query(Device).all() 业务只见方法名；内部今天ORM明天裸SQL——调用方零感知
- 进阶优化：仓库+依赖注入便于测试（内存repo替身）；进阶Unit of Work管理事务边界

**B02 外键与数据字典**
- 定义：外键=档案间的挂锁引用；数据字典=每格抽屉的说明书
- 使用场景：表关系与字段口径的成文契约
- 应用实例：metrics.device_id REFERENCES devices.id
- 扩展与误区：误区：字段含义靠口口相传——字典进docs/新同事不看代码也能懂库
- 原理：外键=子表存父表主键的引用+数据库强制约束：插孤儿记录（测点指向不存在的设备）直接被库拒绝——数据完整性的守门员
- 判断依据：设备-测点-记录-告警四表的血缘全靠外键串起——删设备级联策略(cascade/set null)要显式声明
- 逐行解释：sensor.device_id REFERENCES devices(id) 外键声明；插入device_id=999的测点→IntegrityError被库拦下——应用层校验漏网它兜底
- 进阶优化：ON DELETE CASCADE级联删（慎用）/SET NULL保留孤表；外键要建索引（MySQL自动，SQLite手动）防全表扫

**B03 ORM声明式**
- 定义：ORM=用Python类'声明'表结构——类即表，字段即属性
- 使用场景：SQL写进类定义——类型安全+自动建表
- 应用实例：class Metric(Base): __tablename__='metrics'
- 扩展与误区：误区：ORM与裸SQL二选一——CRUD用ORM，复杂聚合报表裸SQL更快
- 原理：ORM声明式=用Python类描述表结构，SQL由框架生成：class Device(Base)即CREATE TABLE——写类不写SQL，类型检查进IDE
- 判断依据：表结构简单直接时ORM效率高；复杂报表查询仍可退回原生SQL（session.execute(text(...))）——两条腿走路
- 逐行解释：class Device(Base): __tablename__='devices'; id=Column(Integer,primary_key=True); name=Column(String(32)) ——Base.metadata.create_all一键建表
- 进阶优化：relationship()声明关联后dev.sensors直接拿子表（懒加载）；alembic管表结构演进版本化——生产必备

**B04 bulk批量插入**
- 定义：bulk=整车运输vs逐件快递：一次提交万行，快10倍
- 使用场景：万级记录必备——逐条insert是性能杀手
- 应用实例：session.bulk_save_objects(metrics_rows)
- 扩展与误区：误区：bulk完不commit——数据只在内存，进程一退全没
- 原理：bulk批量插入=一次executemany提交N行，比循环单插快百倍：网络往返从N次变1次——万条数据秒级入库
- 判断依据：历史数据回灌/批量导入场景必用bulk；逐条insert+autocommit是最常见的性能事故
- 逐行解释：session.bulk_insert_mappings(Record, rows) 万行一次；对比for r in rows: session.add(Record(**r)) 慢百倍——事务提交次数决定速度
- 进阶优化：分批提交（每5000行commit一次）防事务过大回滚整批；to_sql(pandas)底层也是批量——殊途同归

**B05 N+1陷阱**
- 定义：N+1=点一名学生跑一趟教务处——列表页逐条查询卡顿元凶
- 使用场景：查询列表页卡顿的头号原因
- 应用实例：session.query(Device).options(joinedload(Device.alarms))
- 扩展与误区：误区：小数据量感觉不到——数据上万秒变分钟，echo=True眼见为实
- 原理：N+1陷阱=查1次列表又触发N次子查询：取100台设备再逐台取测点=101条SQL——列表页越翻越慢的元凶
- 判断依据：仪表盘变慢先查SQL日志数：访问N台实体的循环里出现.子表属性即嫌疑现场
- 逐行解释：for d in devices: d.sensors  懒加载逐台触发SQL；joinedload(Device.sensors) 预加载一条JOIN搞定——selectinload批量IN查询次优
- 进阶优化：SQLAlchemy echo=True打印SQL自检；count(len)两数对不上即N+1实锤；进阶dataloader模式批量解析

**B06 索引与EXPLAIN**
- 定义：索引=书后索引页：查得快但每页写书都要多维护一份——有代价
- 使用场景：按设备查时段是最高频查询——(device_id,ts)复合索引正覆盖
- 应用实例：CREATE INDEX idx_dev_ts ON metrics(device_id, ts)
- 扩展与误区：误区：索引滥建——写入每行都更新所有索引，写多读少的表别加
- 原理：索引=拿空间换时间的查找加速结构（B+树）：WHERE命中的列建索引快万倍，但写操作变慢且占盘——不是越多越好
- 判断依据：查询慢先EXPLAIN看执行计划（全表扫SCAN→索引查SEARCH），再对症建索引——盲建索引是新手病
- 逐行解释：EXPLAIN QUERY PLAN SELECT ... WHERE ts>? 全表SCAN亮红灯；CREATE INDEX idx_ts ON records(ts) 建索引后SEARCH——前后对比就是实验报告
- 进阶优化：最左前缀原则（复合索引(a,b)只对a或a+b生效）；覆盖索引免回表；写多读少的表慎建——索引维护有成本



### 工程化要求（GB/T 8566 过程映射 · TOGAF 技术架构落地 · 71m轮）

> 本工单除功能实现外，须满足以下工程化要求（评分占比 15%，逐项检查）：
1. ORM 声明式建模，外键约束强制（孤儿记录被库拒绝）
2. 索引前后 EXPLAIN 对比写入报告
3. 批量插入用 bulk（禁循环单条 add）
> 提交前自查：`python -m pytest`（如有测试）全绿；requirements.txt 锁定；README 可复现。
> 国标与 TOGAF 完整对照见《工程化实践指南（国标GB-T8566+TOGAF）.md》。

## 避坑
- SQLite文件被P4进程占用 → 入库阶段停止采集器或用WAL模式；
- relationship缺back_populates导致重复查询；
- 时间戳存字符串 → 存ISO格式或DateTime类型。

> **本课主用工具**：PyCharm CE + conda环境(pp03) + Git（每周提交）（图文步骤见 `../软件操作指南/`：05-PyCharm使用指南.md、03-Git与GitHub-Gitee使用指南.md）
