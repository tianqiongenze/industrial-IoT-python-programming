# 工单 P3《产线KPI仪表盘与每日分析报告》（第5周·4课时·难度⭐⭐⭐）

## 任务情境
交付两个数据产品：①"产线驾驶舱"仪表盘（5 KPI+时间筛选）；②每日自动分析报告（HTML+PDF四段式，生成<2分钟）。数据源为P2.1清洁数据。

## 课前导学单
1. 微课《Streamlit速成+Jinja2模板》（6分钟）；
2. 预习自测：Streamlit每次交互后脚本如何重跑？缓存用哪个装饰器？
3. 跑通starter最小仪表盘（`streamlit run W05_dashboard.py`）。

### 预习教材与上次课检查（62号轮·课前必读）

> **📖 课前预习｜本课教材**：《Python程序设计项目化教程（活页式）》**项目6**
> 预习知识点：matplotlib绘图(subplot/bar)；Streamlit/Plotly概览
> 学法提示：先读教材对应项目节→再看微课→完成导学单预习自测
> **✓ 课中检查｜上周（P4）抽查**：30维特征<100ms——随机2人口述/白板，答对记过程分

## 任务要求（P3.1仪表盘）
1. 5个KPI：产量趋势(折线)/良率(指标卡)/设备状态(红绿灯)/今日告警(表格)/效率对标(进度条)；
2. 侧栏筛选：日期范围+设备下拉；
3. Plotly交互图；st.cache_data缓存数据处理。

## 任务要求（P3.2日报）
1. 四段式：生产概览/详细分析/异常识别/数据附表；
2. Jinja2渲染HTML + reportlab生成PDF（图文混排）；
3. 异常识别：自动列出超阈值记录并给出原因建议模板。

## 决策矩阵（可视化框架）
| 框架 | 上手速度 | 交互能力 | 部署重量 | 决策 |
|------|---------|---------|---------|------|
| Streamlit | | | | |
| Dash | | | | |
| 纯HTML+JS | | | | |

## 验收标准
| 等级 | 标准 |
|------|------|
| 及格(D) | 5 KPI可用+时间筛选；日报四部分完整+PDF正确 |
| 良好(C) | 联动筛选流畅；日报生成<2分钟 |
| 优秀(B) | ≥7指标+钻取交互；异常自动识别；美观度≥4/5 |
| 超优(A) | 优秀+定时自动生成(mailto/计划任务)+移动端适配 |

## 提交物
代码 + 仪表盘截图 + 样例PDF日报 + 生成耗时记录


### 知识四要素详解（V1.2深度版·与授课PPT同源）

**B01 Streamlit脚本式交互**
- 定义：Streamlit=整页重放的幻灯片：每次点交互从头跑一遍脚本
- 使用场景：零前端基础出交互页面——数据分析师的浏览器
- 应用实例：st.title('产线KPI'); st.sidebar.selectbox('设备', devs)
- 扩展与误区：误区：用Web框架思维写全局状态——重跑虽笨但可预测，cache治重算
- 原理：Streamlit脚本式交互：从上到下执行一遍=渲染一次，控件改值→整脚本重跑——没有回调没有路由，写脚本即写应用
- 判断依据：数据科学 demo/内部仪表盘从想法到上线一小时——不用学前端框架（React/Vue）的捷径
- 逐行解释：st.title('产线驾驶舱') 标题；st.slider('阈值',0,100,80) 滑块；st.line_chart(df) 图——纯Python顺序写，保存即热更新浏览器
- 进阶优化：st.session_state跨重跑存状态；st.cache_data缓存下一节；fragment局部刷新（进阶性能优化）

**B02 cache缓存**
- 定义：@st.cache_data=给函数盖'已算'章：参数不变直接取上次结果
- 使用场景：读库/重计算函数加缓存——交互秒开
- 应用实例：@st.cache_data def load(): return pd.read_sql(…)
- 扩展与误区：误区：数据更新了还拿旧缓存——记得clear或设TTL过期时间
- 原理：@st.cache_data把函数结果缓存：同参数再调用直接取缓存跳过计算——10秒的查询第二次秒开
- 判断依据：读CSV/算KPI这类'输入不变结果不变'的函数统统加缓存——仪表盘流畅的秘密
- 逐行解释：@st.cache_data def load(): return pd.read_csv('big.csv') 首跑算10s；改滑块触发重跑时load()直接命中缓存——重渲染不重算
- 进阶优化：ttl=300五分钟过期保数据新鲜；clear()手动失效；cache_resource缓存模型对象（不序列化的大件）

**B03 st.metric指标卡**
- 定义：st.metric=大字报KPI卡：数字+涨跌箭头一眼看板
- 使用场景：KPI仪表盘的第一视觉元素——OEE/停机/产量三卡
- 应用实例：c1.metric('OEE','87%',delta='+2%')
- 扩展与误区：误区：delta正负好坏想当然——停机数上升是坏事，delta_color要对
- 原理：st.metric指标卡=数字+涨跌箭头：大字号当前值、小三角环比变化——管理层一眼读数的原子组件
- 判断依据：驾驶舱五个KPI（OEE/合格率/停机/能耗/报警）横排metric——比表格直观一个量级
- 逐行解释：st.metric('合格率','98.2%','+0.4%') 值+delta；delta_color='inverse'跌为绿（报警类指标反向）；columns(5)五卡横排
- 进阶优化：metric动态取数（df实时算）；st.column_config.ProgressColumn表格内进度条——进阶组件库

**B04 Plotly交互图**
- 定义：Plotly=会动会说话的图：悬停看数/框选放大/图例开关
- 使用场景：仪表盘交互图表——静态图给不了的能力
- 应用实例：px.line(df, x='ts', y='temp') → st.plotly_chart(fig)
- 扩展与误区：误区：matplotlib对象塞给plotly_chart——两套体系不互通，统一用一
- 原理：Plotly交互图：悬浮看数值、框选缩放、双击复位——静态图matplotlib给报告，交互图Plotly给驾驶舱
- 判断依据：趋势图要'拖动缩放查异常段'的场景用Plotly——中控大屏标配
- 逐行解释：import plotly.express as px; px.line(df,x='ts',y='temp') 一行交互图；st.plotly_chart(fig)嵌入Streamlit——悬浮出数值条
- 进阶优化：px.scatter_matrix多维散点矩阵；dark模板px.defaults.template='plotly_dark'贴大屏；fig.write_html导出可交互文件

**B05 Jinja2模板**
- 定义：Jinja2=填空合同：{{变量}}挖坑，render时数据填坑
- 使用场景：HTML日报模板一次写好，数据每天自动填
- 应用实例：Template('…{{kpi}}…').render(kpi='87%')
- 扩展与误区：误区：模板里拼SQL/逻辑——模板只管样式，逻辑留在Python侧
- 原理：Jinja2模板=HTML里挖{{占位符}}，数据填坑渲染成最终页面——版式与数据分离，改版式不动代码
- 判断依据：日报要邮件正文HTML版：模板写死骨架，每天只注入数字——同源双输出（PDF+邮件）
- 逐行解释：Template(open('tpl.html').read()).render(kpis=kpis,rows=rows) 数据填{{kpis.oee}}——设计师改HTML，工程师管render
- 进阶优化：模板过滤器{{x|round(2)}}；自动转义防注入（autoescape=True）；宏macro做组件复用——前端工程化最小集

**B06 四段式日报**
- 定义：四段式=新闻倒金字塔：概览→分析→异常→附表（与02课W10同口径）
- 使用场景：跨课统一口径：P3日报与02课PDF日报同构——一次学会两处复用
- 应用实例：概览一段+分析一图+异常一表+附录数据
- 扩展与误区：误区：两课各写一套格式——统一模板思维，资产可迁移
- 原理：四段式日报=标题结论区→KPI表格区→趋势图区→异常明细区——'结论先行、证据随后、异常兜底'的读报动线
- 判断依据：executive meeting 5分钟过报：先看结论行（合格率98.2%↑），要细节往下翻——版式服务决策速度
- 逐行解释：st.header(f'{date} 生产日报') 标题；st.metric行KPI；st.plotly_chart趋势；st.dataframe(异常Top10) 明细——四段自上而下
- 进阶优化：异常自动高亮（合格率<95%标红）；st.download_button一键导出PDF——闭环到归档



### 工程化要求（GB/T 8566 过程映射 · TOGAF 技术架构落地 · 71m轮）

> 本工单除功能实现外，须满足以下工程化要求（评分占比 15%，逐项检查）：
1. KPI 计算与图表渲染模块分离
2. cache 缓存加 TTL（数据新鲜度）
3. 日报模板与数据分离（Jinja2/reportlab）
> 提交前自查：`python -m pytest`（如有测试）全绿；requirements.txt 锁定；README 可复现。
> 国标与 TOGAF 完整对照见《工程化实践指南（国标GB-T8566+TOGAF）.md》。

## 避坑
- Streamlit每次重跑重复读大文件 → @st.cache_data；
- Jinja2模板变量与Python命名不一致（静默空白）；
- reportlab中文字体（复用02包SimHei方案）。

> **本课主用工具**：PyCharm CE + conda环境(pp03) + Git（每周提交）（图文步骤见 `../软件操作指南/`：05-PyCharm使用指南.md、03-Git与GitHub-Gitee使用指南.md）
