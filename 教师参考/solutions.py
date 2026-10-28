# -*- coding: utf-8 -*-
"""《Python程序设计（项目实战）》教师参考实现（9个工单全部可离线自检）

用法（在课程包根目录 03-Python程序设计-项目实战/ 下运行）:
    /usr/local/bin/python3.11 教师参考/solutions.py p11        # 单项
    /usr/local/bin/python3.11 教师参考/solutions.py p11 p66    # 指定多项
    /usr/local/bin/python3.11 教师参考/solutions.py all       # 依次全跑, 每项打印 PASS/FAIL,
                                                               # 有失败则退出码非0

覆盖范围与口径（与 工单任务书/*.md 一一对应）:
    p11 五题(含题4 Device基类+PLC子类) + A层边界断言      p12 标准工程模板生成器(临时目录, 生成后自检并清理)
    p21 七步清洗管道(每步行数留痕+分组插值+质量评分断言)  p22 21维特征向量化提取(f2/f3为第2/3峰**频率**)
    p33 5个KPI+Plotly图表+四段式日报HTML(无需streamlit)   p41 三线程多源采集(退避重试/去重/告警/批量入库)
    p55 四表仓库+种子数据+4a/4b/4c+窗口函数环比+索引对比  p66 LR/RF/GB三模型对比+GridSearch+混淆矩阵
    p77 五库平台端到端(驱动 教师参考/p77_smart_ops/verify.sh，非单文件重写)

离线兜底（无需任何硬件/额外服务）:
    · p41 未安装 pymodbus → 内置同寄存器布局的进程内PLC模拟器；未安装 paho-mqtt → 本地生成
      同主题契约(device/+/status)的JSON状态报文。不需要再先启动 工具/plc_simulator.py。
    · p33 未安装 streamlit → 只算KPI/建figure/出HTML；未安装 reportlab → 跳过PDF并打印说明。
    · 兼容 SQLAlchemy 1.3 与 2.x（p55/solutions_multi 均不依赖 2.0 独有API）。

落盘纪律: 除课程既有教学产物 daily_report.html（存在才就地更新）外，所有中间产物一律写入
系统临时目录（tempfile），绝不往仓库里丢 buffer.db / warehouse.db / 生成的工程骨架。
"""
import os
import sys

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
COURSE_ROOT = os.path.dirname(MODULE_DIR)
MODEL_FILE = "model_v1.joblib"          # 工单P6 任务要求5: 模型文件名+版本说明行
DEVICES = ["DEV-01", "DEV-02", "DEV-03", "DEV-04"]


def _find_data(name):
    """按 当前目录→课程根→教师参考→学生代码框架 顺序定位数据文件（相对路径不再挑运行目录）。"""
    for d in (os.getcwd(), COURSE_ROOT, MODULE_DIR,
              os.path.join(COURSE_ROOT, "学生代码框架")):
        path = os.path.join(d, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"未找到数据文件 {name}（请在课程包根目录运行本脚本）")


def _tmp_dir(tag):
    """本次运行的临时产物目录（系统临时区，不进仓库）。"""
    import tempfile
    path = os.path.join(tempfile.mkdtemp(prefix=f"solutions_{tag}_"), "")
    print(f"[落盘] 临时目录: {path}")
    return path


# ======================================================================
# P1.1 Python基础五题
# ======================================================================
def p11():
    """工单P1.1 五题参考实现：题1换算/题2求根/题3字典CRUD/题4 Device+PLC继承/题5安全读取 + A层边界断言。"""
    import math
    import tempfile
    from pathlib import Path

    # ---------- 题1(⭐) 温度单位换算器 ----------
    def ex1(c):
        """℃ → (℉, K)。空输入/None 按 0℃ 兜底（A层：脏输入不炸管道）。"""
        c = 0.0 if c in (None, "", " ") else float(c)
        return c * 9 / 5 + 32, c + 273.15

    # ---------- 题2(⭐⭐) 一元二次方程 ----------
    def ex2(a, b, c):
        """返回根的元组（大根在前，与骨架断言同口径）；无实根/退化不可解返回 None。"""
        if a == 0:                                   # 退化：一次方程 bx+c=0
            return None if b == 0 else (-c / b,)
        d = b * b - 4 * a * c
        if d < 0:
            return None                              # 工程口径：负判别式交上层决策
        r = math.sqrt(d)
        return ((-b + r) / (2 * a), (-b - r) / (2 * a))

    # ---------- 题3(⭐⭐) 设备清单管理（dict CRUD） ----------
    def ex3():
        """增(DEV-01/DEV-02)→改(DEV-02状态)→删(DEV-01)，返回最终字典。"""
        devices = {}                                 # id -> {"name":..., "status":...}
        devices["DEV-01"] = {"name": "空压机", "status": "运行"}
        devices["DEV-02"] = {"name": "冷却泵", "status": "停止"}
        devices["DEV-02"]["status"] = "运行"          # 改：引用直达，O(1)
        assert devices.pop("DEV-01")["name"] == "空压机"   # 删：pop 顺带验证取回值
        return devices

    # ---------- 题4(⭐⭐⭐) Device 基类 + PLC 子类 ----------
    class Device:
        """基类：设备共性=标识+名称+状态+启停动作（C的struct+函数组 → 类）。"""

        def __init__(self, dev_id, name):
            self.dev_id, self.name = dev_id, name
            self.status = "停止"

        def start(self):
            self.status = "运行"
            return f"{self.name}({self.dev_id}) 已启动"

        def stop(self):
            self.status = "停止"
            return f"{self.name}({self.dev_id}) 已停机"

    class PLC(Device):
        """子类：新增 scan_ms 属性 + scan() 方法，覆盖 start() 输出扫描周期。"""

        def __init__(self, dev_id, name, scan_ms=8):
            if scan_ms <= 0:
                raise ValueError(f"扫描周期须为正毫秒数，收到 {scan_ms}")
            super().__init__(dev_id, name)
            self.scan_ms = scan_ms

        def start(self):                             # 覆盖
            super().start()
            return f"{self.name}启动, 扫描{self.scan_ms}ms, 状态{self.status}"

        def scan(self):
            return {"dev_id": self.dev_id, "status": self.status,
                    "scan_ms": self.scan_ms}

    # ---------- 题5(⭐⭐) 带异常保护的文件读取器 ----------
    def ex5(path):
        """读文本；不存在→FILE_NOT_FOUND，编码错→BAD_ENCODING（try/except，禁 os.path.exists 预判）。"""
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "FILE_NOT_FOUND"
        except UnicodeDecodeError:
            return "BAD_ENCODING"

    # ====================== 验收断言（含A层边界） ======================
    checks = []

    def ok(desc, cond):
        assert cond, desc
        checks.append(desc)

    # 题1：常规 + 空输入 + 极值（绝对零度）
    ok("题1 100℃→(212.0, 373.15)", ex1(100) == (212.0, 373.15))
    ok("题1 空输入兜底 ''/None→(32.0, 273.15)", ex1("") == (32.0, 273.15)
       and ex1(None) == (32.0, 273.15))
    ok("题1 极值 -273.15℃ 的K≈绝对零度", abs(ex1(-273.15)[1]) < 1e-9)
    # 题2：两实根 / 无实根 / 重根 / 退化一次 / 全零不可解 / 大系数极值
    ok("题2 x²-3x+2 → (2.0, 1.0)", ex2(1, -3, 2) == (2.0, 1.0))
    ok("题2 x²+1 无实根 → None", ex2(1, 0, 1) is None)
    ok("题2 x²-2x+1 重根 → (1.0, 1.0)", ex2(1, -2, 1) == (1.0, 1.0))
    ok("题2 a=0 退化一次 2x-4 → (2.0,)", ex2(0, 2, -4) == (2.0,))
    ok("题2 a=b=0 不可解 → None", ex2(0, 0, 0) is None)
    big = ex2(1, 0, -10 ** 8)
    ok("题2 极值 x²-1e8 → ±1e4", big and abs(big[0] - 10000.0) < 1e-6
       and abs(big[1] + 10000.0) < 1e-6)
    # 题3：CRUD 终态
    ok("题3 终态只剩 DEV-02 且状态=运行",
       ex3() == {"DEV-02": {"name": "冷却泵", "status": "运行"}})
    # 题4：继承关系 / scan_ms / start() 返回值 / 覆盖 / 异常边界
    plc = PLC("DEV-01", "S7-1200", 8)
    ok("题4 PLC 是 Device 的子类", issubclass(PLC, Device) and isinstance(plc, Device))
    ok("题4 新增属性 scan_ms=8 且初始状态=停止", plc.scan_ms == 8 and plc.status == "停止")
    msg = plc.start()
    ok("题4 start() 返回字符串且含扫描周期", isinstance(msg, str) and "8ms" in msg)
    ok("题4 start() 副作用=状态转运行", plc.status == "运行")
    ok("题4 start 已覆盖(非基类同函数)", PLC.start is not Device.start)
    ok("题4 scan() 返回快照", plc.scan() == {"dev_id": "DEV-01", "status": "运行",
                                            "scan_ms": 8})
    ok("题4 基类 start 口径不变", Device("DEV-09", "风机").start() == "风机(DEV-09) 已启动")
    ok("题4 基类 stop 口径不变", Device("DEV-09", "风机").stop() == "风机(DEV-09) 已停机")
    try:
        PLC("DEV-02", "非法PLC", 0)
        raised = False
    except ValueError:
        raised = True
    ok("题4 异常边界 scan_ms<=0 → ValueError", raised)
    # 题5：缺失/编码错/空文件/正常，四种出口全在临时目录里造，绝不依赖仓库文件
    with tempfile.TemporaryDirectory(prefix="p11_") as tmp:
        missing = os.path.join(tmp, "absent_5f3a9c.txt")          # 保证不存在
        bad_enc = Path(tmp, "bad_encoding.txt"); bad_enc.write_bytes(b"\xff\xfe\x00abc")
        empty = Path(tmp, "empty.txt"); empty.write_text("", encoding="utf-8")
        good = Path(tmp, "good.txt"); good.write_text("DEV-01,4.2\n", encoding="utf-8")
        ok("题5 文件不存在 → FILE_NOT_FOUND", ex5(missing) == "FILE_NOT_FOUND")
        ok("题5 非UTF-8字节 → BAD_ENCODING", ex5(bad_enc) == "BAD_ENCODING")
        ok("题5 空文件 → ''（存在但无内容）", ex5(empty) == "")
        ok("题5 正常读取内容", ex5(good).strip() == "DEV-01,4.2")

    for line in checks:
        print("  ✓", line)
    print(f"P1.1 五题参考：{len(checks)} 项断言全部通过（含A层空输入/极值/异常边界）")


# ======================================================================
# P1.2 标准Python工程模板
# ======================================================================
def p12():
    """工单P1.2 参考实现：模板生成器（表驱动）→ 写入临时目录 → 结构/AST/测试三级自检 → 清理。"""
    import ast
    import os
    import shutil

    README = """# {name}

## 一、跑起来
```bash
conda create -n pp03 python=3.11 && conda activate pp03   # 课程环境（沙箱隔离）
pip install -r requirements.txt                            # 运行依赖
pip install -r requirements-dev.txt                        # 质量工具链
python run.py                                              # 入口
python -m pytest -q                                        # 单元测试
python -m pylint src/                                      # 评分门槛 ≥8.5/10
```

## 二、目录（目录即分工）
- `src/`   生产区：业务代码，一职责一模块
- `tests/` 质检区：pytest 用例，与 src 模块成对（test_模块名.py）
- `config/` 图纸：settings.yaml，规则外置——改配置不改代码
- `data/`   原料：输入数据（不入库，见 .gitignore）
- `docs/`   档案：过程文档/数据字典/使用示例

## 三、协作约定
- 分支：main 保护，日常在 dev 开发后合并
- 提交信息前缀：`feat:` / `fix:` / `docs:` / `test:` / `chore:`，无前缀不合并
- 提交前：pre-commit 钩子自动跑 black + flake8
"""

    GITIGNORE = """__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.venv/
venv/
env/
# conda 环境目录不入库（两种口径都堵上）
envs/
*.sqlite3
data/*
!data/.gitkeep
output/*.log
"""

    FILES = {
        "README.md": README,
        ".gitignore": GITIGNORE,
        "requirements.txt": "pandas>=2.0\nnumpy>=1.26\nscikit-learn>=1.3\n"
                            "SQLAlchemy>=2.0\nplotly>=5.18\nPyYAML>=6.0\n",
        "requirements-dev.txt": "pytest>=7.0\npylint>=2.17\nblack>=23.0\n"
                               "flake8>=6.0\npre-commit>=3.5\n",
        ".pre-commit-config.yaml": (
            "repos:\n"
            "  - repo: https://github.com/psf/black\n"
            "    rev: 23.12.1\n"
            "    hooks: [{id: black}]\n"
            "  - repo: https://github.com/pycqa/flake8\n"
            "    rev: 6.1.0\n"
            "    hooks: [{id: flake8}]\n"),
        "config/settings.yaml": ("project:\n  name: {name}\n  version: 1.0.0\n"
                                 "paths:\n  data_dir: data\n  output_dir: output\n"
                                 "quality:\n  min_score: 85\n  temp_max_c: 120\n"),
        "src/__init__.py": '"""{name} 实现包。"""\n__version__ = "1.0.0"\n',
        "src/main.py": (
            '"""P1.1 题1 温度换算 + 日志/配置外置的最小工程实现。"""\n'
            "import logging\nimport os\n\n"
            'logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s '
            '%(message)s")\n'
            "LOG = logging.getLogger(__name__)\n"
            "DEFAULT_UNIT = \"F\"\n\n\n"
            "def convert(c, unit=DEFAULT_UNIT):\n"
            '    """℃ → ℉(F) 或 K；空输入按 0℃。"""\n'
            "    c = 0.0 if c in (None, \"\", \" \") else float(c)\n"
            "    if unit == \"F\":\n        return c * 9 / 5 + 32\n"
            "    if unit == \"K\":\n        return c + 273.15\n"
            "    raise ValueError(f\"未知单位 {unit}\")\n\n\n"
            "def main():\n"
            "    LOG.info(\"%%s 启动\", os.path.basename(__file__))\n"
            "    print(f\"100℃ -> {convert(100):.1f}℉\")\n"
            "    return 0\n\n\n"
            "if __name__ == \"__main__\":\n    raise SystemExit(main())\n"),
        "tests/__init__.py": "",
        "tests/test_main.py": (
            '"""P1.2 单元测试示例：针对 P1.1 题1 写 3 条断言（工单任务要求5）。"""\n'
            "import os\nimport sys\n\n"
            "sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath("
            "__file__))), \"src\"))\n\n"
            "from main import convert  # noqa: E402\n\n\n"
            "def test_boiling_point():\n    assert convert(100) == 212.0\n\n\n"
            "def test_zero_input_boundary():\n    assert convert(\"\") == 32.0\n\n\n"
            "def test_kelvin_and_bad_unit():\n    assert convert(0, \"K\") == 273.15\n"
            "    try:\n        convert(0, \"X\")\n        raise AssertionError(\"应抛 "
            "ValueError\")\n    except ValueError:\n        pass\n"),
        "run.py": ("import os\nimport sys\n\n"
                   "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "
                   "\"src\"))\n\nfrom main import main  # noqa: E402\n\n"
                   "if __name__ == \"__main__\":\n    raise SystemExit(main())\n"),
        "docs/过程文档.md": "# 过程文档\n\n六步法留痕：资讯→计划→决策→实施→检查→评价。\n"
                            "本项目决策记录：检查工具选 pylint（打分）+ pre-commit（强制门）。\n",
        "data/.gitkeep": "",
    }
    REQUIRED = sorted(FILES) + ["src/main.py", "tests/test_main.py"]
    PKG = "proj_template"

    root = os.path.join(_tmp_dir("p12"), "proj_template")
    os.makedirs(root, exist_ok=True)

    # ---- 1) 原子生成（表驱动：加一行=出一个文件） ----
    for rel, tpl in FILES.items():
        dst = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(tpl.replace("{name}", PKG))     # 只替换占位符，模板里的 {..} 原样保留
    print(f"[生成] {len(FILES)} 个文件 → {root}")

    # ---- 2) 结构自检：目录 + 必需文件齐全 ----
    for rel in REQUIRED:
        assert os.path.exists(os.path.join(root, *rel.split("/"))), f"缺文件 {rel}"
    for d in ("src", "tests", "config", "docs", "data"):
        assert os.path.isdir(os.path.join(root, d)), f"缺目录 {d}/"
    print(f"[结构] src/tests/config/docs/data 五区 + README + .gitignore 齐全（共 "
          f"{sum(len(f) for _, _, f in os.walk(root))} 文件）")

    # ---- 3) 语法自检：所有 .py 必须能被 ast 解析 ----
    py_files = [os.path.join(dp, fn) for dp, _, fns in os.walk(root)
                for fn in fns if fn.endswith(".py")]
    for path in py_files:
        with open(path, encoding="utf-8") as fh:
            ast.parse(fh.read(), filename=path)            # 语法错会在这里抛 SyntaxError
    print(f"[语法] ast.parse 通过: {sorted(os.path.basename(p) for p in py_files)}")

    # ---- 4) 行为自检：不装pytest也直接把 test_* 跑一遍 ----
    ns = {"__file__": os.path.join(root, "tests", "test_main.py"), "__name__": "test_main"}
    src_main = os.path.join(root, "src", "main.py")
    with open(src_main, encoding="utf-8") as fh:
        compile(fh.read(), src_main, "exec")               # 确保可导入
    test_path = os.path.join(root, "tests", "test_main.py")
    with open(test_path, encoding="utf-8") as fh:
        code = compile(fh.read(), test_path, "exec")
    eval(code, ns)                                         # noqa: S307 - 受控的临时目录代码
    ran = [name for name in ns if name.startswith("test_")]
    for name in sorted(ran):
        ns[name]()
    assert len(ran) >= 3, "工单要求至少3条断言用例"
    print(f"[测试] {sorted(ran)} 全部通过（pytest 口径同）")

    # ---- 5) 配置外置自检：settings.yaml 可读（PyYAML 缺失则降级为文本检查） ----
    cfg = os.path.join(root, "config", "settings.yaml")
    try:
        import yaml
        with open(cfg, encoding="utf-8") as fh:
            conf = yaml.safe_load(fh)
        assert conf["quality"]["min_score"] == 85
        print(f"[配置] YAML 解析成功: min_score={conf['quality']['min_score']}")
    except ImportError:
        assert "min_score" in open(cfg, encoding="utf-8").read()
        print("[配置] 未装 PyYAML，降级为文本存在性检查")

    # ---- 6) 不污染仓库：产物必须全在临时目录 ----
    assert os.path.abspath(root).startswith(os.path.abspath(os.sep + "tmp")) or \
        "temp" in os.path.abspath(root), "模板必须生成在临时目录"
    shutil.rmtree(root)
    print(f"[清理] 已删除临时工程 {root}（仓库零残留）")
    print("P1.2 模板生成器：生成→结构→语法→测试→配置 五级自检通过")


# ======================================================================
# P2.1 Pandas 数据清洗管道
# ======================================================================
def p21(src="W03_raw.csv", out_csv=None):
    """工单P2.1 七步管道参考：每步(操作/行数/Δ/缺失)全程留痕，按设备分组插值，质量评分断言。"""
    import pandas as pd

    path = _find_data(src)
    audit, rows_seen = [], []

    def note(step, name, df, extra=""):
        """每步留痕：操作名 + 行数 + 与上一步的Δ + 剩余缺失单元格（工单P2.1 A层全程可追溯）。"""
        prev = rows_seen[-1] if rows_seen else len(df)
        rows_seen.append(len(df))
        audit.append(f"[{step}/7] {name:<10} 行数={len(df):>5} Δ={len(df) - prev:>+5} "
                     f"缺失单元格={int(df.isna().sum().sum()):>4} {extra}")

    df = pd.read_csv(path)
    note(1, "加载检查", df, f"列={list(df.columns)}")

    # ---- 2) 类型转换：脏字符串→NaN（coerce 不炸管道） ----
    df["temp"] = pd.to_numeric(df["temp"], errors="coerce")
    note(2, "类型转换", df, "temp→float(coerce)")

    # ---- 3) 时间戳统一：三种格式各自解析后 combine_first 补洞 ----
    parts = [pd.to_datetime(df["ts"], format=fmt, errors="coerce")
             for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%Y%m%d%H%M%S")]
    ts = parts[0]
    for p in parts[1:]:
        ts = ts.combine_first(p)
    bad_ts = int(ts.isna().sum())
    df = df.assign(ts=ts).sort_values(["device_id", "ts"], kind="stable").reset_index(drop=True)
    note(3, "时间统一", df, f"三格式归一, 解析失败={bad_ts}")

    # ---- 4) 去重（先于离群检测：重复行会把IQR护栏带偏，工单B07清洗顺序） ----
    df = df.drop_duplicates(subset=["device_id", "ts"], keep="first")
    note(4, "去重", df, "按(device_id,ts)语义去重")

    # ---- 5) 缺失插补：组内线性插值 + 组内首尾回填；跨设备不借值（工单B02决策） ----
    missing = int(df["temp"].isna().sum())
    df["temp_missing"] = df["temp"].isna().astype(int)          # 缺失本身是信息（工单B02进阶）
    df["temp"] = (df.groupby("device_id")["temp"]
                    .transform(lambda s: s.interpolate().bfill().ffill()))
    note(5, "缺失插补", df, f"temp缺失{missing}→按设备分组线性插值+组内首尾回填, "
                           f"残留={int(df['temp'].isna().sum())}")

    # ---- 6) 异常剔除：统计(IQR)∧业务(>120℃)双闸门，工单B05/B06 ----
    q1, q3 = df["temp"].quantile([.25, .75])
    iqr = q3 - q1
    stat_mask = (df["temp"] < q1 - 1.5 * iqr) | (df["temp"] > q3 + 1.5 * iqr)
    biz_mask = df["temp"] > 120
    hit_mask = stat_mask | biz_mask
    both = int((stat_mask & biz_mask).sum())
    df = df[~hit_mask].copy()
    note(6, "异常剔除", df,
         f"IQR界=[{q1 - 1.5 * iqr:.1f},{q3 + 1.5 * iqr:.1f}] 业务>120℃ "
         f"共剔{int(hit_mask.sum())}行(统计∧业务双确认={both})")

    # ---- 7) 验证 + 输出 ----
    assert int(df["temp"].isna().sum()) == 0, "插补后仍有缺失"
    assert df.groupby("device_id")["ts"].apply(lambda s: s.is_monotonic_increasing).all(), \
        "设备内时间轴未递增"
    dup_left = int(df.duplicated(subset=["device_id", "ts"]).sum())
    assert dup_left == 0, "去重后仍有重复"
    out = out_csv or os.path.join(_tmp_dir("p21"), "clean.csv")
    df.to_csv(out, index=False)
    note(7, "输出落盘", df, f"→ {out}")

    # ---- 质量评分（口径文档化：完整性40 + 合规性30 + 唯一性20 + 及时性10） ----
    score = (40 * (1 - df.isna().mean().mean())
             + 30 * df["temp"].between(20, 120).mean()
             + 20 * df["device_id"].str.match(r"DEV-\d{2}").mean()
             + 10 * (1 - dup_left / max(len(df), 1)))
    print("\n".join(audit))
    print(f"清洗后 {len(df)} 行（原始 {rows_seen[0]} 行）| 质量评分 {score:.1f} "
          f"(D≥85 / C≥88 / B≥90)")
    assert score >= 85, f"质量评分 {score:.1f} 未达及格线85"
    print(f"  ✓ 及格(D≥85)达标 | 良好(C≥88){'达标' if score >= 88 else '未达标'} | "
          f"优秀(B≥90){'达标' if score >= 90 else '未达标'}")
    print(f"P2.1 管道留痕 {len(audit)} 步，评分 {score:.1f} 通过断言")


# ======================================================================
# P2.2 NumPy 特征提取
# ======================================================================
def p22(n_normal=500, n_fault=500, length=1000, fs=100):
    """工单P2.2 21维特征矩阵（全向量化）；dom_freq/f2/f3=主峰与第2、3峰**频率**；含有限性+可分性断言。"""
    import time

    import numpy as np

    # ---------- 合成信号：正常(8Hz载频) / 轴承磨损(叠加25Hz调制) ----------
    rng = np.random.RandomState(42)
    t = np.arange(length) / fs
    labels = np.r_[np.zeros(n_normal, dtype=int), np.ones(n_fault, dtype=int)]
    sigs = np.tile(0.5 + 0.1 * np.sin(2 * np.pi * 8 * t), (len(labels), 1))
    sigs += rng.normal(0, 0.02, sigs.shape)                  # 本底噪声
    sigs[labels == 1] += 0.06 * np.sin(2 * np.pi * 25 * t)   # 故障特征频率

    def feature_matrix(signals, fs=100):
        """(N,L) → (N,21)：一次FFT+广播算完所有特征，禁止逐样本Python循环。"""
        x = np.atleast_2d(np.asarray(signals, dtype=float))
        n, m = x.shape
        fr = np.fft.rfftfreq(m, 1 / fs)
        amp = np.abs(np.fft.rfft(x, axis=1)) * 2 / m          # 单边幅值谱
        mean, std = x.mean(1), x.std(1)
        rms = np.sqrt((x ** 2).mean(1))
        absx, absmean = np.abs(x), np.abs(x).mean(1)
        # ---- 谱峰提取：局部极大值打分 → 每行取前3峰（频率+幅值） ----
        is_peak = np.zeros(amp.shape, dtype=bool)
        is_peak[:, 1:-1] = (amp[:, 1:-1] > amp[:, :-2]) & (amp[:, 1:-1] >= amp[:, 2:])
        score = np.where(is_peak, amp, -np.inf)
        cand = np.argpartition(-score, 2, axis=1)[:, :3]      # 只挑3个，避免全排序
        order = np.argsort(-np.take_along_axis(score, cand, 1), axis=1)
        order = np.take_along_axis(cand, order, 1)
        pk_freq = np.take_along_axis(np.broadcast_to(fr, amp.shape), order, 1)
        # ---- 频域派生量 ----
        total = amp.sum(1)
        centroid = (fr * amp).sum(1) / total                        # 频域质心
        spec_var = (amp * (fr[None, :] - centroid[:, None]) ** 2).sum(1) / total  # 频域方差
        hi = np.where(amp > amp.max(1, keepdims=True) / 2, fr[None, :], np.nan)
        bandwidth = np.nanmax(hi, axis=1) - np.nanmin(hi, axis=1)   # 半功率带宽
        p = absx / absx.sum(1, keepdims=True)
        cols = {
            "mean": mean, "std": std, "max": absx.max(1), "ptp": np.ptp(x, axis=1),
            "rms": rms, "var": x.var(1), "abs_mean": absmean,
            "crest": absx.max(1) / rms,
            "kurtosis": ((x - mean[:, None]) ** 4).mean(1) / std ** 4 - 3,
            "clearance": absx.max(1) / (np.sqrt(absx).mean(1) ** 2),
            "skewness": ((x - mean[:, None]) ** 3).mean(1) / std ** 3,
            "cv": std / np.abs(mean), "shape": rms / absmean,
            "dom_freq": pk_freq[:, 0], "f2": pk_freq[:, 1], "f3": pk_freq[:, 2],
            "spec_energy": (amp ** 2).sum(1), "spec_centroid": centroid,
            "spec_var": spec_var, "bandwidth": bandwidth,
            "entropy": -(p * np.log(p + 1e-12)).sum(1),
        }
        return np.column_stack(list(cols.values())), list(cols)

    t0 = time.perf_counter()
    X, names = feature_matrix(sigs, fs)
    ms = (time.perf_counter() - t0) * 1000
    sd = X.std(0)
    flat = sd < 1e-12                                   # 零方差列（如本例 dom_freq 恒为8Hz）
    Z = (X - X.mean(0)) / np.where(flat, 1.0, sd)       # 常数列强制保留为0，不做 0/0

    # ================= 自检断言 =================
    assert X.shape == (len(labels), 21), f"特征矩阵形状异常 {X.shape}"
    assert np.isfinite(X).all(), "特征矩阵含 NaN/Inf"
    assert X.shape == (len(labels), 21), f"特征矩阵形状异常 {X.shape}"
    assert np.isfinite(X).all(), "特征矩阵含 NaN/Inf"
    # 相干采样的单音合成信号里，主频与半功率带宽是"结构常量"（两类都相同）→
    # 这两列零方差属预期，标准化时必须跳过，否则 0/0 产生 NaN；它们也不承担可分性。
    EXPECT_FLAT = {"dom_freq", "bandwidth"}
    assert set(np.where(flat)[0]) == {names.index(n) for n in EXPECT_FLAT}, \
        f"零方差列与预期不符: {[names[i] for i in np.where(flat)[0]]}"
    nz = ~flat
    assert np.abs(Z.std(0)[nz] - 1).max() < 1e-6 and abs(Z.mean(0)).max() < 1e-6, "标准化失真"
    i2, i3 = names.index("f2"), names.index("f3")
    # f2/f3 语义：故障类的第2峰应落在 25Hz 特征频率上（±1Hz），而不是"幅值排序"
    near25 = np.abs(X[np.ix_(labels == 1, [i2, i3])] - 25.0).min(1) < 1.0
    assert np.median(X[labels == 0, names.index("dom_freq")]) == 8.0, "正常类主频应为8Hz"
    assert near25.mean() >= 0.95, f"故障类前3峰含25Hz的比例仅 {near25.mean():.0%}"
    # 可分性：两类特征的 |t| 统计量 + 主导特征与标签的相关系数
    a, b = X[labels == 0], X[labels == 1]
    se = np.sqrt(a.var(0, ddof=1) / len(a) + b.var(0, ddof=1) / len(b))
    tstat = np.abs((b.mean(0) - a.mean(0)) / np.where(se == 0, np.inf, se))
    best = int(np.argmax(tstat))
    corr = np.zeros(X.shape[1])                           # 常数列不参与相关系数（否则 0/0 出 NaN）
    nzf = ~flat
    corr[nzf] = np.abs(np.corrcoef(X[:, nzf].T, labels)[:-1, -1])
    assert tstat[best] >= 8.0, f"最优可分特征 |t|={tstat[best]:.1f} 太小"
    assert corr.max() >= 0.5, f"主导特征与标签相关性 {corr.max():.2f} 不足"
    assert ms < 250, f"向量化实现退化？{len(labels)}样本耗时 {ms:.0f}ms"

    top = np.argsort(-tstat)[:5]
    print(f"特征矩阵 {X.shape} | 特征名 {names}")
    print(f"向量化计时 {ms:.1f}ms / {len(labels)}样本×{length}点 "
          f"(工单口径 <100ms{'达标' if ms < 100 else '未达标(本机阈值250ms兜底)'})")
    print("可分性Top5 |t|: " + ", ".join(f"{names[i]}={tstat[i]:.1f}" for i in top))
    print(f"  ✓ 全有限 | ✓ 标准化(均值0方差1, 零方差列{int(flat.sum())}个已识别跳过) "
          f"| ✓ f2/f3=第2/3峰频率(故障类25Hz命中 "
          f"{near25.mean():.0%}) | ✓ 最大|t|={tstat[best]:.1f}({names[best]}) "
          f"最大|r|={corr.max():.2f}")
    print("P2.2 特征工厂自检通过")


# ======================================================================
# P3 产线KPI仪表盘 + 四段式日报
# ======================================================================
def p33(n_rows=2000, report_path=None):
    """工单P3 参考实现：5个KPI(无streamlit) + Plotly三图 + 四段式日报HTML（生产概览/详细分析/异常识别/数据附表）。"""
    import datetime
    import time

    import numpy as np
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as pgo      # 仪表盘用 go.Indicator（px 里没有 indicator）

    t0 = time.perf_counter()

    # ---------- 数据层（= starter 的 load_data，去掉 st.cache_data） ----------
    rng = np.random.RandomState(2026)
    ts = pd.date_range("2026-04-01", periods=n_rows, freq="30min")
    df = pd.DataFrame({"ts": ts, "device_id": rng.choice(DEVICES, n_rows),
                       "output": rng.poisson(50, n_rows)})
    df["ok_qty"] = (df["output"] * rng.uniform(0.88, 0.99, n_rows)).astype(int)
    df["yield"] = (df["ok_qty"] / df["output"].replace(0, np.nan)).clip(upper=1.0)
    df["temp"] = rng.uniform(45, 95, n_rows)
    df["vib"] = rng.uniform(1, 6, n_rows)

    # ---------- TODO-1 侧栏筛选（等价实现：日期范围 + 设备多选） ----------
    day = df["ts"].dt.date
    today = max(day)
    df["date"] = day
    df["shift"] = pd.cut(df["ts"].dt.hour, [-1, 8, 16, 24],
                         labels=["白班(0-8h)", "中班(8-16h)", "夜班(16-24h)"])
    sel_devs = DEVICES                                 # multiselect 全选口径
    view = df[df["device_id"].isin(sel_devs)]

    # ---------- TODO-2 五个KPI ----------
    alarms_today = view[(view["date"] == today) & (view["vib"] > 4.5)]
    online = sorted(set(view[view["date"] == today]["device_id"]))
    target_daily = 5000
    kpis = {
        "总产量": int(view["output"].sum()),
        "平均良率": round(float(view["yield"].mean()) * 100, 2),          # %
        "设备在线数": f"{len(online)}/{df['device_id'].nunique()}",
        "今日告警数": int(len(alarms_today)),
        "效率对标": round(float(view[view["date"] == today]["output"].sum())
                          / target_daily * 100, 1),                       # %
    }
    for key, val in kpis.items():
        assert val is not None, f"KPI {key} 为空"
        if isinstance(val, float):
            assert np.isfinite(val), f"KPI {key} 非有限值: {val}"
        if isinstance(val, (int, float)):
            assert val >= 0, f"KPI {key}={val} 不应为负"
    assert len(kpis) == 5, "工单要求5个KPI"
    assert kpis["总产量"] > 0 and 0 < kpis["平均良率"] <= 100, "产量/良率 KPI 失真"
    assert int(kpis["设备在线数"].split("/")[0]) >= 1, "无在线设备"
    assert kpis["今日告警数"] >= 1, "异常识别段无内容"
    assert 0 < kpis["效率对标"] <= 200, "效率对标应在 (0,200]%"
    print("KPI: " + " | ".join(f"{k}={v}" for k, v in kpis.items()))

    # ---------- TODO-3/4/5 Plotly 三图（只构建不显示） ----------
    daily = view.groupby("date", as_index=False)["output"].sum().rename(
        columns={"date": "day"})
    daily["day"] = daily["day"].astype(str)
    fig_line = px.line(daily, x="day", y="output", title="产量趋势",
                       labels={"output": "日产量", "day": "日期"})
    dev_tab = (view.groupby("device_id")
               .agg(产量=("output", "sum"), 平均良率=("yield", "mean"),
                    平均振动=("vib", "mean"), 平均温度=("temp", "mean"))
               .round(3).reset_index())
    fig_bar = px.bar(dev_tab, x="device_id", y="产量", title="设备产量对比")
    fig_gauge = pgo.Figure(pgo.Indicator(
        mode="gauge+number", value=float(kpis["平均良率"]),
        number={"suffix": "%"},
        title={"text": "平均良率"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2c7be5"},
               "steps": [{"range": [0, 90], "color": "#f8d9da"},
                         {"range": [90, 100], "color": "#d4edda"}]}))
    for name, fig in (("line", fig_line), ("bar", fig_bar), ("indicator", fig_gauge)):
        assert len(fig.data) >= 1, f"{name} 图为空"
        assert fig.to_html(full_html=False, include_plotlyjs=False), f"{name} 渲染失败"
    div_line = fig_line.to_html(full_html=False, include_plotlyjs=False)
    div_bar = fig_bar.to_html(full_html=False, include_plotlyjs=False)
    div_gauge = fig_gauge.to_html(full_html=False, include_plotlyjs=False)
    print(f"Plotly figure: px.line({len(daily)}点) / px.bar({len(dev_tab)}设备) / "
          f"go.Indicator(仪表盘) —— 仅构建，不启动浏览器")

    # ---------- 异常识别：超阈值记录 + 原因建议模板（工单P3.2-3） ----------
    def reason(row):
        if row["vib"] > 4.5 and row["temp"] > 90:
            return "振动超限+温度超限 → 轴承磨损并发过热；建议：停机测温并安排更换", 3
        if row["vib"] > 4.5:
            return "振动>4.5mm/s → 不平衡/轴承早期磨损；建议：加测点复采并排产点检", 2
        return "温度>90℃ → 冷却不足/负载过高；建议：查冷却泵与风扇", 2

    bad = df[((df["date"] == today) & (df["vib"] > 4.5)) | (df["temp"] > 90)].copy()
    advice = bad.apply(reason, axis=1)
    bad["处置建议"] = [a for a, _ in advice]
    bad["等级"] = [lv for _, lv in advice]
    bad_top = bad.sort_values(["等级", "vib"], ascending=False).head(20)
    shift_tab = (view.groupby("shift", observed=True)
                 .agg(产量=("output", "sum"), 平均良率=("yield", "mean")).round(3).reset_index())

    # ---------- PDF 可选依赖探测（缺失即降级并在报尾注明，不影响自检） ----------
    try:
        import reportlab                             # noqa: F401
        pdf_note = " | reportlab可用：可按02包w10字体方案转PDF"
    except ImportError:
        pdf_note = " | reportlab未安装：本次仅出HTML（离线降级，PDF复用02包w10字体方案）"

    # ---------- 四段式HTML（模板与数据分离：Jinja2 渲染；无Jinja2则同键降级） ----------
    today_output = int(view[view["date"] == today]["output"].sum())
    ctx = {
        "title_date": str(today),
        "kpi_total": f"{kpis['总产量']:,}",
        "kpi_yield": kpis["平均良率"],
        "kpi_online": kpis["设备在线数"],
        "kpi_alarm": kpis["今日告警数"],
        "kpi_bench": kpis["效率对标"],
        "range_txt": f"{df['ts'].min():%Y-%m-%d} ~ {df['ts'].max():%Y-%m-%d}（{len(df):,} 条）",
        "dev_rows": dev_tab.to_html(classes="tbl", index=False, border=1),
        "shift_rows": shift_tab.to_html(classes="tbl", index=False, border=1),
        "alarm_rows": bad_top.drop(columns=["等级"]).to_html(classes="tbl", index=False, border=1),
        "alarm_n": len(bad_top),
        "appendix": df.tail(50).to_html(classes="tbl", index=False, border=1),
        "ratio": kpis["效率对标"],
        "gap": max(0, target_daily - today_output),
        "div_line": div_line, "div_bar": div_bar, "div_gauge": div_gauge,
        "stamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pdf_note": pdf_note,
    }
    TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>每日生产分析报告</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
<style>
body { font-family: sans-serif; margin: 32px; line-height: 1.6; }
h1 { color: #1a3c5e; border-bottom: 3px solid #2c7be5; padding-bottom: 8px; }
h2 { color: #2c7be5; margin-top: 26px; }
.tbl { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
.tbl th, .tbl td { border: 1px solid #dee2e6; padding: 8px; }
.tbl th { background: #e9ecef; }
.tbl tr:nth-child(even) { background: #f8f9fa; }
.progress { width: 100%; height: 22px; background: #e9ecef; border-radius: 11px; overflow: hidden; }
.fill { height: 100%; background: #28a745; }
.kpi { display:inline-block; min-width:170px; margin:6px 10px 6px 0; padding:10px 14px;
       border-left:4px solid #2c7be5; background:#f4f8fd; }
</style></head><body>
<h1>每日生产分析报告 {{ title_date }}</h1>
<h2>1. 生产概览</h2>
<div class="kpi">总产量 <b>{{ kpi_total }}</b></div>
<div class="kpi">平均良率 <b>{{ kpi_yield }}%</b></div>
<div class="kpi">设备在线数 <b>{{ kpi_online }}</b></div>
<div class="kpi">今日告警数 <b>{{ kpi_alarm }}</b></div>
<div class="kpi">效率对标 <b>{{ kpi_bench }}%</b></div>
<p>数据范围 {{ range_txt }}</p>
<h3>良率指标卡（Plotly px.indicator）</h3>{{ div_gauge }}
<h2>2. 详细分析</h2>
<h3>2.1 设备对比</h3>{{ dev_rows }}
<h3>2.2 班次对比</h3>{{ shift_rows }}
<h3>2.3 趋势与分布（px.line / px.bar）</h3>{{ div_line }}{{ div_bar }}
<h2>3. 异常识别</h2>
<p>今日超阈值记录 {{ alarm_n }} 条（vib&gt;4.5mm/s 或 temp&gt;90℃），按等级排序并给出原因与处置建议模板。</p>
{{ alarm_rows }}
<h2>4. 数据附表（最近50条）</h2>
{{ appendix }}
<h2>5. 效率对标</h2>
<p>今日实际 / 日目标 5,000 = <b>{{ ratio }}%</b>｜缺口 {{ gap }} 件</p>
<div class="progress"><div class="fill" style="width: {{ ratio }}%"></div></div>
<hr><p style="color:#6c757d;font-size:.9em">生成时间: {{ stamp }}
 | 数据来源: 合成产线数据 (RandomState=2026){{ pdf_note }}
 | Plotly图为交互div，离线打开需 plotly.js（已置CDN script，无外网时表格数据仍完整可读）</p>
</body></html>"""
    try:
        from jinja2 import Template
        html = Template(TEMPLATE, autoescape=False).render(**ctx)
        renderer = "Jinja2"
    except ImportError:                       # 离线兜底：占位符即 {{ 键名 }}，逐个替换
        html = TEMPLATE
        for key, val in ctx.items():
            html = html.replace("{{ " + key + " }}", str(val))
        renderer = "str.replace(无Jinja2)"
    assert "{{ " not in html, "有占位符未被数据填充（模板变量名与数据键不一致）"

    # ---------- 落盘：仓库既有 daily_report.html 才就地更新，否则写临时目录 ----------
    if report_path is None:
        for cand in (os.path.join(os.getcwd(), "daily_report.html"),
                     os.path.join(COURSE_ROOT, "daily_report.html")):
            if os.path.exists(cand):
                report_path = cand
                break
        else:
            report_path = os.path.join(_tmp_dir("p33"), "daily_report.html")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    size = os.path.getsize(report_path)

    # ---------- 自检断言 ----------
    assert size > 6000, f"日报过小 {size}B"
    for heading in ("生产概览", "详细分析", "异常识别", "数据附表"):
        assert heading in html, f"四段式缺段落标题：{heading}"
    assert html.count("plotly-graph-div") >= 3, "三张Plotly图未落进HTML"
    elapsed = time.perf_counter() - t0
    assert elapsed < 120, f"日报生成超工单口径2分钟：{elapsed:.1f}s"
    print(f"日报渲染器={renderer} 字节={size:,} 生成耗时={elapsed:.2f}s(工单口径<2min)")
    print(f"[落盘] {report_path}（四段式标题 1.生产概览 / 2.详细分析 / 3.异常识别 / 4.数据附表 + 5.效率对标）")
    print("P3 参考实现：5 KPI + 3 Plotly图 + 四段式日报 自检通过")


# ======================================================================
# P4.1 多源工业数据采集（三线程）
# ======================================================================
def p41(rounds=8, batch=12, db_path=None):
    """工单P4.1 三线程采集参考：Modbus采集+MQTT订阅+处理入库，含退避重试/去重/告警/批量入库/采集率断言。

    离线兜底：未装 pymodbus 用进程内PLC模拟器（同5寄存器÷10布局）；未装 paho-mqtt 用本地
    JSON报文发生器走同一条 device/+/status 主题契约。协议层可插拔，三线程骨架完全一致。
    """
    import json
    import os
    import queue
    import sqlite3
    import threading
    import time

    import numpy as np

    NAMES = ["temp_c", "press_mpa", "vib_mm_s", "rpm", "status"]     # 寄存器语义（线上序）
    KEYS = ["temp", "press", "vib", "rpm", "status"]                 # 入库列名（内部统一口径）
    PLCS = [("127.0.0.1", 5020), ("127.0.0.1", 5021), ("127.0.0.1", 5022)]
    POLL = 0.30                 # 演示节拍（工单口径0.5s×3台；此处缩拍以在数秒内跑完多轮）
    LADDER = [1, 2, 4]          # 退避重试秒数：1s→2s→4s 封顶
    MAX_TRIES = 4               # 每轮每台最多4次尝试（3次退避后仍失败 → 死信）
    SCALE = 0.1                 # 演示时间压缩系数（真实运行置 1.0）
    FLUSH_SECS = 1.2            # 工单口径"每50条或每5秒"→演示口径 12条/1.2s（等比缩拍）
    ALARM_VIB = 4.5
    DEDUP_KEY = 3               # (source, ts) 中 ts 的取整位数
    REAL_PLC = os.environ.get("SOL_P41_REAL") == "1"   # 真机链路开关（默认走离线模拟器）

    try:
        from pymodbus.client import ModbusTcpClient
        modbus_mode = ("pymodbus(真机链路)" if REAL_PLC
                       else "内置PLC模拟器(离线兜底；pymodbus 已装，需 SOL_P41_REAL=1 才走真机)")
    except ImportError:
        ModbusTcpClient, modbus_mode = None, "内置PLC模拟器(离线兜底)"
    try:
        import paho.mqtt.client as mqtt
        mqtt_mode = "paho-mqtt(broker)"
    except ImportError:
        mqtt, mqtt_mode = None, "本地JSON报文(离线兜底)"

    class SimResp:
        """与 pymodbus 响应对象同形：.registers + .isError()。"""

        def __init__(self, registers):
            self.registers = registers

        @staticmethod
        def isError():
            return False

    class SimLink:
        """离线兜底 PLC：read_holding_registers() 返回 物理值×10 的寄存器；可按轮次脚本化掉线。

        FAULT_PLAN = {端口: {轮次: 连续拒绝的尝试次数}}；99 = 本轮彻底失联（走满退避链后进死信）。
        2号PLC(5021) 正是工单里那个"戏精"设备：第3轮瞬时掉线（重试即恢复）、第5轮整轮失联。
        """
        FAULT_PLAN = {5021: {3: 1, 5: 99}}
        ALARM_ROUND = {5022: 4}                # 该端口该轮次产出 4.8mm/s 超限样本（触发告警）

        def __init__(self, host, port):
            self.host, self.port = host, port
            self.reject, self.tick, self.rnd = 0, 0, 0

        def start_round(self, rnd):
            self.rnd = rnd
            self.reject = self.FAULT_PLAN.get(self.port, {}).get(rnd, 0)

        def read_holding_registers(self, address=0, count=5):
            if self.reject > 0:
                self.reject -= 1
                return None                          # 等价于超时/无响应
            self.tick += 1
            wobble = 0.4 * (1 if self.tick % 2 else -1)
            vib = 4.8 if self.ALARM_ROUND.get(self.port) == self.rnd \
                else round(2.6 + 0.3 * np.sin(self.tick / 3.0), 2)
            phys = [56.3 + wobble, 4.5, vib, 1480.0, 1]        # temp/press/vib/rpm/status
            return SimResp([int(round(v * 10)) for v in phys[:count]])    # ×10 上送

    class RealLink(SimLink):
        """pymodbus 版：与模拟器同一 start_round/read 接口，读失败一律表达为 None。"""

        def __init__(self, host, port):
            super().__init__(host, port)
            self.client = ModbusTcpClient(host=host, port=port)
            self.connected = bool(self.client.connect())

        def read_holding_registers(self, address=0, count=5):
            try:                                     # pymodbus 3.x 要求关键字参数
                rr = self.client.read_holding_registers(address=address, count=count)
            except Exception:                        # pylint: disable=broad-except
                return None
            if rr is None or getattr(rr, "isError", lambda: False)():
                return None
            return rr

    q = queue.Queue(maxsize=10000)                     # 背压：满则 put 超时并丢弃计数
    stop = threading.Event()

    def make_link(host, port):
        """默认用内置模拟器：它的故障是脚本化的（第3轮瞬时掉线、第5轮整轮失联），
        离线也能取证；真机链路由 SOL_P41_REAL=1 显式开启，且连不上就自动回落。
        """
        if ModbusTcpClient is not None and REAL_PLC:
            link = RealLink(host, port)
            if link.connected:
                return link
            print("    · PLC@%d 真机连不上 → 回落内置模拟器" % port)
        return SimLink(host, port)

    links = [make_link(h, p) for h, p in PLCS]
    stat = {"ok": 0, "fail": 0, "retry": 0, "dead": 0, "put": 0, "drop": 0}
    lock = threading.Lock()

    def bump(key, n=1):
        with lock:
            stat[key] += n

    class ModbusCollector(threading.Thread):
        """线程1：0.5s(演示缩拍)轮询三台，读5寄存器÷10还原，失败走 1s→2s→4s 退避。"""

        def __init__(self):
            super().__init__(daemon=True, name="Modbus")

        def read_with_retry(self, link, rnd):
            """一次采样 = 最多 MAX_TRIES 次尝试；失败按 1s→2s→4s 封顶退避（演示×SCALE）。"""
            link.start_round(rnd)
            for attempt in range(1, MAX_TRIES + 1):
                resp = link.read_holding_registers(address=0, count=5)   # 关键字参数口径
                if resp is not None and getattr(resp, "registers", None):
                    if attempt > 1:
                        bump("retry")
                        ladder = "→".join(
                            str(LADDER[min(i, len(LADDER) - 1)]) for i in range(attempt - 1))
                        print(f"    ↳ PLC@{link.port} 第{attempt}次尝试成功"
                              f"（已退避 {ladder}s，重连后继续采集）")
                    row = {k: (v / 10 if k != "status" else v)      # ÷10 还原物理值
                           for k, v in zip(KEYS, resp.registers)}
                    row.update(source=f"plc@{link.port}", ts=time.time())
                    return row
                if attempt == MAX_TRIES:
                    break
                delay = LADDER[min(attempt - 1, len(LADDER) - 1)]
                print(f"    ↳ PLC@{link.port} 第{rnd}轮第{attempt}次读失败 → 退避 {delay}s"
                      f"（演示×{SCALE}={delay * SCALE:.1f}s）")
                time.sleep(delay * SCALE)
            return None

        def run(self):
            for rnd in range(1, rounds + 1):
                if stop.is_set():
                    break
                for link in links:
                    row = self.read_with_retry(link, rnd)
                    if row is None:
                        bump("fail")                        # 本轮该链路计一次失败
                        bump("dead")                        # 走满退避链 → 同时计一次死信
                        print(f"    ⚠ PLC@{link.port} 第{rnd}轮失联（死信计数，不阻塞其他台）")
                    else:
                        bump("ok")
                        try:
                            q.put(row, timeout=1)
                            bump("put")
                        except queue.Full:
                            bump("drop")
                        if rnd == 6 and link.port == 5020:      # 重连后消息双发（幂等演示）
                            q.put(dict(row), timeout=1)
                            bump("put")
                time.sleep(POLL)

    class MQTTSubscriber(threading.Thread):
        """线程2：订阅 device/+/status；无 paho 时本地按同契约生成JSON状态报文。"""

        def __init__(self):
            super().__init__(daemon=True, name="MQTT")

        def on_message(self, topic, payload):
            try:
                data = json.loads(payload)
            except (TypeError, ValueError):
                bump("drop")
                return
            row = {"source": f"mqtt@{data['device_id']}", "ts": data["ts"],
                   "status": data["status"], "temp": data.get("temp")}
            try:
                q.put(row, timeout=1)
                bump("put")
            except queue.Full:
                bump("drop")

        def run(self):
            if mqtt is not None:                      # 真机分支
                client = mqtt.Client()
                client.on_message = lambda _c, _u, m: self.on_message(m.topic, m.payload)
                try:
                    client.connect("127.0.0.1", 1883, 2)
                    client.subscribe("device/+/status", qos=0)
                    client.loop_start()
                    while not stop.is_set():
                        time.sleep(0.1)
                    client.loop_stop()
                except Exception:                     # pylint: disable=broad-except
                    print("    ⚠ MQTT broker 不可达 → 转本地报文生成")
                    self.offline_loop()
            else:
                self.offline_loop()

        def offline_loop(self):
            i = 0
            while not stop.is_set():
                i += 1
                dev = DEVICES[i % len(DEVICES)]
                topic = f"device/{dev.lower()}/status"       # 主题契约 device/+/status
                payload = json.dumps({"device_id": dev, "ts": time.time(),
                                      "status": "运行" if i % 5 else "停止",
                                      "temp": round(58.0 + i * 0.1, 2)})
                self.on_message(topic, payload)
                time.sleep(0.35)

    class DataProcessor(threading.Thread):
        """线程3：消费队列 → (source,ts)去重 → 振动>4.5告警 → 每20条/1.2s 批量入库。"""

        def __init__(self, db):
            super().__init__(daemon=False, name="Proc")
            self.db, self.batch = db, batch
            self.buf, self.seen = [], set()
            self.dup = self.alarms = self.rows = 0
            self.flushes = []

        def run(self):
            con = sqlite3.connect(self.db)
            con.execute("CREATE TABLE IF NOT EXISTS records("
                        "source TEXT, ts REAL, temp REAL, vib REAL, status TEXT)")
            last_flush = time.time()
            while True:
                try:
                    row = q.get(timeout=0.3)
                except queue.Empty:
                    if stop.is_set() and q.empty():
                        break
                    if time.time() - last_flush >= FLUSH_SECS and self.buf:
                        self.flush(con, "按时")
                        last_flush = time.time()
                    continue
                if row is None:                       # 停机哨兵
                    break
                key = (row["source"], round(row["ts"], DEDUP_KEY))
                if key in self.seen:                  # 幂等去重
                    self.dup += 1
                    continue
                self.seen.add(key)
                vib = row.get("vib")
                if vib is not None and vib > ALARM_VIB:
                    self.alarms += 1
                    print(f"    🚨 告警 {row['source']} 振动 {vib} > {ALARM_VIB}mm/s")
                self.buf.append((row["source"], row["ts"], row.get("temp"), vib,
                                 str(row.get("status"))))
                if len(self.buf) >= self.batch:       # 门限1：攒够 N 条
                    self.flush(con, "攒批")
                    last_flush = time.time()
                elif time.time() - last_flush >= FLUSH_SECS:   # 门限2：超过 T 秒（未满批也落）
                    self.flush(con, "按时")
                    last_flush = time.time()
            self.flush(con, "收尾")                   # 无论从哨兵还是"停机且队列空"退出都兜底落库
            con.commit()
            self.rows = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            con.close()
            stop.set()

        def flush(self, con, why):
            if not self.buf:
                return
            con.executemany("INSERT INTO records VALUES(?,?,?,?,?)", self.buf)
            con.commit()
            self.flushes.append((why, len(self.buf)))
            self.buf.clear()

    db_path = db_path or os.path.join(_tmp_dir("p41"), "buffer.db")
    assert COURSE_ROOT not in os.path.abspath(db_path), "演示库禁止写入仓库"

    proc = DataProcessor(db_path)
    t_start = time.perf_counter()
    collector, mqtt_thread = ModbusCollector(), MQTTSubscriber()
    collector.start(); mqtt_thread.start(); proc.start()
    print(f"协议层: Modbus={modbus_mode} | MQTT={mqtt_mode} | 轮次={rounds} "
          f"节拍={POLL}s 退避={LADDER}s(×{SCALE}演示) 批量={batch}条/{FLUSH_SECS}s")
    print(f"寄存器契约(0起5字, ×10上送): {'/'.join(NAMES)} → 入库列 {'/'.join(KEYS)}")
    collector.join(timeout=20)
    time.sleep(FLUSH_SECS + 0.3)      # 制造"数据变稀"窗口：让"按时"分支与"攒批"分支都被演示到
    stop.set()
    mqtt_thread.join(timeout=5)
    q.put(None)                                       # 哨兵：让处理线程收尾落库
    proc.join(timeout=20)
    wall = time.perf_counter() - t_start

    expected = rounds * len(PLCS)
    rate = stat["ok"] / max(stat["ok"] + stat["fail"], 1)
    enqueued = stat["put"]
    print(f"  采集: 应采{expected} 成功{stat['ok']} 失败{stat['fail']} "
          f"重试恢复{stat['retry']} 死信{stat['dead']} | 入队{enqueued} 背压丢弃{stat['drop']}")
    print(f"  处理: 去重丢弃{proc.dup} 告警{proc.alarms} 入库{proc.rows} "
          f"批量提交{proc.flushes} 残留buf={len(proc.buf)}")
    print(f"  采集率: {stat['ok']}/{expected} = {rate:.1%} (工单目标≥95%) | 运行{wall:.2f}s")

    assert rate >= 0.95, f"采集率 {rate:.1%} < 95%"
    assert stat["retry"] >= 1, "退避重试链路未被触发"
    assert stat["dead"] >= 1, "未演练彻底失联（死信计数为0）"
    assert proc.dup >= 1, "去重未生效（双发消息未被拦截）"
    assert proc.alarms >= 1, "振动>4.5 告警未触发"
    assert len(proc.flushes) >= 2, "批量入库未演示（攒批+按时/收尾至少两次）"
    assert len({why for why, _ in proc.flushes}) >= 2, \
        f"双门限未同时演示：{sorted({why for why, _ in proc.flushes})}"
    assert len(proc.buf) == 0, "停机时仍有未落库数据"
    # 对账恒等式（工程化要求2）：入队 = 入库 + 去重丢弃 + 在途(0)
    assert enqueued == proc.rows + proc.dup + len(proc.buf), \
        f"对账不平: 入队{enqueued} ≠ 入库{proc.rows}+去重{proc.dup}+在途{len(proc.buf)}"
    assert expected == stat["ok"] + stat["fail"], "应采/成功/失败三数不咬合"
    assert wall < 9.0, f"演示超时 {wall:.1f}s（退避链已按×{SCALE}缩拍，正常应≈5s）"
    print("P4.1 三线程采集：退避重试/幂等去重/超限告警/批量入库/对账恒等式 全部通过")


# ======================================================================
# P5 产线数据仓库与 ORM
# ======================================================================
def p55(n_records=500, db_path=None):
    """工单P5 参考实现：四表ER+联合索引+种子数据+4a/4b/4c+A层窗口函数环比(SQL/ORM双实现)+索引前后对比。"""
    import datetime
    import random
    import time
    from contextlib import contextmanager

    from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                            String, create_engine, func, text)
    try:                                        # 2.0/1.4 写法优先，1.3 回退
        from sqlalchemy.orm import declarative_base
    except ImportError:
        from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import Session, relationship

    Base = declarative_base()

    class Device(Base):
        __tablename__ = "devices"
        id = Column(Integer, primary_key=True)
        code = Column(String(16), unique=True, nullable=False)
        name = Column(String(64))
        area = Column(String(32))
        points = relationship("SensorPoint", back_populates="device",
                              cascade="all, delete-orphan")
        alarms = relationship("AlarmEvent", back_populates="device")

    class SensorPoint(Base):
        __tablename__ = "sensor_points"
        id = Column(Integer, primary_key=True)
        device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
        metric = Column(String(16))                  # vib / temp
        unit = Column(String(8))
        device = relationship("Device", back_populates="points")

    class Record(Base):
        __tablename__ = "records"
        id = Column(Integer, primary_key=True)
        device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
        point_id = Column(Integer, ForeignKey("sensor_points.id"), nullable=False)
        ts = Column(DateTime, nullable=False)
        vib = Column(Float)
        temp = Column(Float)
        # 联合索引 idx(device_id, ts) 故意留到 optimize() 里显式建，好做前后对比

    class AlarmEvent(Base):
        __tablename__ = "alarms"
        id = Column(Integer, primary_key=True)
        device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
        ts = Column(DateTime, nullable=False)
        level = Column(Integer, default=2)
        message = Column(String(128))
        resolved = Column(Boolean, default=False)
        device = relationship("Device", back_populates="alarms")

    @contextmanager
    def session_of(engine):                          # SQLAlchemy 1.3 无 Session 上下文协议
        ses = Session(engine)
        try:
            yield ses
        finally:
            ses.close()

    db_path = db_path or os.path.join(_tmp_dir("p55"), "warehouse.db")
    assert COURSE_ROOT not in os.path.abspath(db_path), "禁止写仓库内的 warehouse.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    tables = sorted(t.name for t in Base.metadata.sorted_tables)
    print(f"[ER] 四表={tables} 外键=records→devices/sensor_points, alarms→devices")

    # ---- 种子数据：3设备 × 2测点 + 500记录，告警≈5% ----
    T0 = datetime.datetime(2026, 4, 1, 0, 0)
    random.seed(1)
    with session_of(engine) as s:
        devs = [Device(code=f"DEV-0{i}", name=n, area="A线")
                for i, n in enumerate(["空压机", "冷却泵", "离心机"], 1)]
        s.add_all(devs)
        s.flush()
        points = []
        for d in devs:
            points += [SensorPoint(device_id=d.id, metric="vib", unit="mm/s"),
                       SensorPoint(device_id=d.id, metric="temp", unit="℃")]
        s.add_all(points)
        s.flush()
        vib_ids = {d.id: [p.id for p in points if p.device_id == d.id and p.metric == "vib"][0]
                   for d in devs}
        alarm_idx = set(random.sample(range(n_records), max(1, int(n_records * 0.05))))
        rows = []
        for i in range(n_records):
            d = devs[i % len(devs)]
            rows.append(dict(device_id=d.id, point_id=vib_ids[d.id],
                             ts=T0 + datetime.timedelta(minutes=3 * i),
                             vib=round(random.uniform(4.55, 6.0) if i in alarm_idx
                                       else random.uniform(1.0, 4.2), 3),
                             temp=round(random.uniform(45, 95), 2)))
        s.bulk_insert_mappings(Record, rows)         # 工程化要求3：禁循环单条 add
        s.commit()
        alarm_rows = [r for r in rows if round(r["vib"], 3) > 4.5]
        s.bulk_insert_mappings(
            AlarmEvent, [dict(device_id=r["device_id"], ts=r["ts"], level=2,
                              message=f"振动超限 {r['vib']}mm/s", resolved=False)
                         for r in alarm_rows])
        s.commit()
        n_dev, n_pt = s.query(Device).count(), s.query(SensorPoint).count()
        n_rec, n_al = s.query(Record).count(), s.query(AlarmEvent).count()
    share = n_al / n_rec
    print(f"[种子] 设备{n_dev} × 测点{n_pt} | 记录{n_rec} | 告警{n_al} 占比{share:.1%}")
    assert (n_dev, n_pt, n_rec) == (3, 6, n_records), "种子数据规模不符工单要求"
    assert abs(share - 0.05) < 0.005, f"告警占比 {share:.1%} 偏离 5% 口径"

    # ---- 查询 4a/4b/4c ----
    with session_of(engine) as s:
        q4a = (s.query(Device.code, func.round(func.avg(Record.vib), 3))
                .join(Record, Record.device_id == Device.id)
                .group_by(Device.code).order_by(Device.code).all())
        q4b = (s.query(Device.code, func.count(AlarmEvent.id).label("n"))
                .join(AlarmEvent, AlarmEvent.device_id == Device.id)
                .group_by(Device.code).order_by(func.count(AlarmEvent.id).desc())
                .limit(3).all())
        hour = func.strftime("%Y-%m-%d %H", Record.ts)
        q4c = (s.query(hour.label("hour"), func.count(Record.id))
                .group_by("hour").order_by("hour").all())
        hourly_counts = [c for _, c in q4c]
        q1_avg = dict(q4a)
        # 4a 交叉验证：与SQL聚合逐设备比对
        for code, avg in q4a:
            direct = s.query(func.avg(Record.vib)).join(Device, Device.id == Record.device_id)\
                .filter(Device.code == code).scalar()
            assert abs(direct - avg) < 1e-3, f"{code} 平均振动不一致"
        print(f"  4a 各设备平均vib: {q4a}")
        print(f"  4b 告警Top3设备: {q4b}")
        print(f"  4c 按小时聚合(前3小时): {q4c[:3]} … 共{len(q4c)}个小时桶")

    assert sum(hourly_counts) == n_rec, "小时聚合总数 ≠ 记录总数"
    assert len(q4b) == 3 and q4b[0][1] >= q4b[-1][1], "告警Top3 排序异常"
    assert set(q1_avg) == {"DEV-01", "DEV-02", "DEV-03"}, "4a 设备覆盖不全"

    # ---- A层：窗口函数按小时聚合 + 环比（SQL 与 ORM 双实现） ----
    sql_cte = text("""
        WITH h AS (
            SELECT strftime('%Y-%m-%d %H', ts) AS hour, COUNT(*) AS cnt,
                   ROUND(AVG(vib), 3) AS avg_vib
            FROM records GROUP BY hour)
        SELECT hour, cnt, avg_vib,
               LAG(cnt)  OVER (ORDER BY hour) AS prev_cnt,
               ROUND(1.0 * cnt / NULLIF(LAG(cnt) OVER (ORDER BY hour), 0) - 1, 4) AS mom_ratio
        FROM h ORDER BY hour LIMIT 5""")
    with engine.connect() as conn:
        sql_rows = conn.execute(sql_cte).fetchall()
    with session_of(engine) as s:
        sub = (s.query(hour.label("hour"),
                       func.count(Record.id).label("cnt"),
                       func.round(func.avg(Record.vib), 3).label("avg_vib"))
               .group_by(hour).subquery())
        lag = func.lag(sub.c.cnt, 1).over(order_by=sub.c.hour)
        orm_rows = (s.query(sub.c.hour, sub.c.cnt, sub.c.avg_vib, lag.label("prev_cnt"),
                            func.round(1.0 * sub.c.cnt / func.nullif(lag, 0) - 1, 4)
                            .label("mom_ratio"))
                    .order_by(sub.c.hour).limit(5).all())
    print("  A层窗口函数 环比(SQL):", [tuple(r) for r in sql_rows[:3]])
    print("  A层窗口函数 环比(ORM):", [tuple(r) for r in orm_rows[:3]])
    assert [tuple(r) for r in sql_rows] == [tuple(r) for r in orm_rows], "SQL与ORM两解结果不一致"
    assert all(r[0] for r in orm_rows) and len(sql_rows) == 5, "窗口函数环比无输出"

    # ---- 索引优化：EXPLAIN QUERY PLAN + 前后耗时对比 ----
    probe = ("SELECT COUNT(*) FROM records WHERE device_id = :d AND ts BETWEEN :a AND :b")
    with engine.connect() as conn:      # 绑定值必须取真实 device_id，否则探测查不到任何行
        real_dev = conn.execute(text("SELECT device_id FROM records LIMIT 1")).scalar()
    assert real_dev, "records 里没有设备号，索引探测无从做起"
    d1 = {"d": real_dev, "a": T0, "b": T0 + datetime.timedelta(hours=6)}   # 绑定参数（勿写成元组解包）

    def timed(repeat=300):
        with engine.connect() as conn:
            t0 = time.perf_counter()
            for _ in range(repeat):
                conn.execute(text(probe), d1).fetchall()
            return (time.perf_counter() - t0) / repeat * 1000

    def plan():
        with engine.connect() as conn:
            return conn.execute(text("EXPLAIN QUERY PLAN " + probe), d1).fetchall()

    with engine.connect() as conn:                 # 先取无索引基线
        p_before = plan()
    t_before = timed()
    # DDL/ANALYZE 必须显式 commit：SQLAlchemy 2.0 的连接关闭即回滚，
    # 未提交时新建连接（plan/timed）看不到索引，EXPLAIN 永远是 SCAN。
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX idx_records_dev_ts ON records(device_id, ts)"))
        conn.commit()
    with engine.connect() as conn:
        conn.execute(text("ANALYZE"))
        conn.commit()
    p_after = plan()
    t_after = timed()
    txt_before = " ; ".join(r[-1] for r in p_before)
    txt_after = " ; ".join(r[-1] for r in p_after)
    speedup = t_before / max(t_after, 1e-9)
    print(f"  EXPLAIN 前: {txt_before}")
    print(f"  EXPLAIN 后: {txt_after}")
    print(f"  耗时 前{t_before:.3f}ms → 后{t_after:.3f}ms（{speedup:.2f}×）"
          f"｜{n_records}行量级 B+树层数≈2，收益不显著属正常（工单要求：写进报告，不谎报提速）")
    assert "SCAN" in txt_before or "USE TEMP" in txt_before, "索引前计划应含全表扫描"
    assert "SEARCH" in txt_after and "idx_records_dev_ts" in txt_after, "索引未被使用"
    assert t_after > 0, "索引后查询未执行"
    # N+1 规避：relationship 用 joinedload 一次取全
    from sqlalchemy.orm import joinedload
    with session_of(engine) as s:
        devs = s.query(Device).options(joinedload(Device.points),
                                       joinedload(Device.alarms)).all()
        s.expire_all()
        t0 = time.perf_counter()
        sizes = [(d.code, len(d.points), len(d.alarms)) for d in devs]
        lazy_ms = (time.perf_counter() - t0) * 1000
    print(f"  预加载(joinedload)取 设备→测点/告警: {sizes} 遍历{lazy_ms:.2f}ms（N+1已规避）")
    assert all(p == 2 for _, p, _ in sizes), "每设备应有2个测点"
    print(f"[落盘] {db_path}")
    print("P5 四表仓库：ER/种子/4a-4b-4c/窗口环比双实现/索引EXPLAIN 自检通过")


# ======================================================================
# P6 故障诊断模型与部署
# ======================================================================
def p66(save_to=None):
    """工单P6 参考实现：五步流 + LR/RF/GradientBoosting 三模型对比(F1/训练耗时/可解释性)
    + GridSearchCV调参留痕 + 混淆矩阵/分类报告 + F1≥0.80断言 + joblib落盘（默认临时目录）。

    老师要产出真实提交物时：``p66(save_to=MODEL_FILE)``（即 model_v1.joblib）。
    """
    import time

    import joblib
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                                 f1_score)
    from sklearn.model_selection import GridSearchCV, cross_val_score, train_test_split

    # ---------- 1) 数据：P2.2 特征口径的合成诊断集（两类×30维，固定种子可复现） ----------
    rng = np.random.RandomState(7)
    informative = np.arange(2, 8)                          # 第2~7维是真正带故障信息的特征
    X = rng.normal(0, 1, (400, 30))
    y = rng.binomial(1, .5, 400)
    fault = y == 1
    X[np.ix_(fault, informative)] += rng.uniform(          # 故障类在 informative 维上整体抬升
        1.0, 1.8, size=(int(fault.sum()), informative.size))
    Xtr, Xte, ytr, yte = train_test_split(X, y, stratify=y, random_state=42,
                                          test_size=0.25)

    # ---------- 2) 训练三模型并计时（A层对比） ----------
    cands = {
        "LogisticRegression": (LogisticRegression(max_iter=2000, random_state=42),
                               "系数即归因（可解释性最好）"),
        "RandomForest": (RandomForestClassifier(n_estimators=300, random_state=42),
                         "特征重要度+OOB（可解释性中）"),
        "GradientBoosting": (GradientBoostingClassifier(n_estimators=200, random_state=42),
                             "逐步拟合，重要度可用但最难讲清"),
    }
    rows, fitted = [], {}
    print("模型对比（训练耗时 / 交叉验证F1 / 测试集F1）:")
    for name, (model, why) in cands.items():
        t0 = time.perf_counter()
        model.fit(Xtr, ytr)
        fit_s = time.perf_counter() - t0
        cv = cross_val_score(model, Xtr, ytr, cv=5, scoring="f1_weighted").mean()
        pred = model.predict(Xte)
        f1w = f1_score(yte, pred, average="weighted")
        f1_1 = f1_score(yte, pred)
        rows.append((name, fit_s, cv, f1w, f1_1, why))
        fitted[name] = model
        print(f"  {name:<20} 训练{fit_s*1000:7.1f}ms  CV-F1 {cv:.3f}  "
              f"测试F1(w) {f1w:.3f}  F1(故障类) {f1_1:.3f}  {why}")

    # ---------- 3) GridSearchCV 调参留痕 ----------
    gs = GridSearchCV(RandomForestClassifier(random_state=42),
                      {"n_estimators": [100, 200], "max_depth": [6, 12, None]},
                      cv=3, scoring="f1_weighted", n_jobs=-1)
    t0 = time.perf_counter()
    gs.fit(Xtr, ytr)
    gs_s = time.perf_counter() - t0
    print(f"GridSearchCV: 6组合×3折 耗时{gs_s:.2f}s 基线CV-F1 {gs.cv_results_['mean_test_score'][0]:.3f}"
          f" → best {gs.best_score_:.3f} @ {gs.best_params_}")

    # ---------- 4) 选定最终模型：调优后的RF，与基线取优 ----------
    tuned = gs.best_estimator_
    best_name, best_model, best_f1 = "RandomForest(tuned)", tuned, f1_score(
        yte, tuned.predict(Xte), average="weighted")
    base_name, base_model, base_f1 = "RandomForest", fitted["RandomForest"], rows[1][3]
    chosen = (best_name, best_model, best_f1) if best_f1 >= base_f1 \
        else (base_name, base_model, base_f1)
    best_name, best_model, best_f1 = chosen
    pred = best_model.predict(Xte)

    # ---------- 5) 评估报告：混淆矩阵 + classification_report + 可解释性 ----------
    cm = confusion_matrix(yte, pred)
    print(f"最终模型={best_name}  F1(w)={best_f1:.3f}  acc={accuracy_score(yte, pred):.3f}")
    print("混淆矩阵 [[TN FP],[FN TP]] =", cm.tolist())
    print(classification_report(yte, pred, target_names=["正常0", "故障1"]).rstrip())
    imp = getattr(best_model, "feature_importances_", None)
    if imp is None:
        imp = np.abs(best_model.coef_[0])
    top3 = np.argsort(-imp)[:3]
    hits = len(set(top3.tolist()) & set(informative.tolist()))
    print(f"可解释性 Top3特征={top3.tolist()} 重要度={np.round(imp[top3], 3).tolist()} "
          f"命中真实故障特征 {hits}/3")

    # ---------- 6) 落盘（默认临时目录，避免覆盖仓库里的 model_v1.joblib） ----------
    target = save_to or os.path.join(_tmp_dir("p66"), MODEL_FILE)
    joblib.dump(best_model, target, compress=3)
    reloaded = joblib.load(target)
    assert np.array_equal(reloaded.predict(Xte), pred), "落盘模型与内存模型预测不一致"
    assert not np.array_equal(cm[0], np.zeros(cm.shape[1])), "混淆矩阵退化"

    # ---------- 自检断言 ----------
    assert cm.shape == (2, 2) and cm.sum() == len(yte), "混淆矩阵行数与测试集不符"
    assert best_f1 >= 0.80, f"F1 {best_f1:.3f} 未达工单门槛 0.80"
    assert all(r[3] >= 0.75 for r in rows), "存在模型严重掉线（对比失真）"
    assert hits >= 1, "可解释性未指向真实故障特征，结论不可讲"
    assert os.path.getsize(target) > 1000, "模型文件过小，落盘可疑"
    assert 0 < gs_s < 120, "调参耗时异常"
    print(f"[落盘] 模型 {target}（{os.path.getsize(target):,}B）；"
          f"要写真实提交物请调用 p66(save_to=MODEL_FILE)")
    print("P6 三模型对比+调参+混淆矩阵+F1≥0.80+落盘回读 自检通过")


# ======================================================================
# P7：多引擎平台无法塞进单文件 —— 驱动 教师参考/p77_smart_ops/ 的端到端闸门
# ======================================================================
def p77(timeout=520):
    """工单P7 参考实现：五库(关系/时序/图/向量/KV)+F1门禁+HTTP服务 端到端自检

    P6 之前每个工单都能压成一个函数；P7 是**跨引擎平台**（Litestar/granian +
    SQLAlchemy/DuckDB/Kùzu/Chroma/redis + ReAct 智能体），单文件版会退化成玩具，
    所以原厂完成态就是同目录的 `p77_smart_ops/` 包。本格不重写逻辑，只做一件事：
    驱动它的 `verify.sh`，把工单四层闸门逐条落到真实断言上——

        [1/6]~[5/6]  关系/时序/图/向量/模型 = C层「五库段全绿」
        [6/6]        granian+Litestar 四路由 + MISS→HIT + 404/400 兜底 = D层
        ALL PASS     = B层；末尾两条拓展留痕(召回对比 / 压测脚本) = A层

    诚实口径：litestar/granian 未安装时 verify.sh 会把该项判 ✗，本函数随之抛
    AssertionError（而不是"跳过即通过"）；缺 redis 时 KV 自动回退离线 TTL-KV，
    服务段仍应全绿。
    """
    import subprocess

    pkg = os.path.join(MODULE_DIR, "p77_smart_ops")
    script = os.path.join(pkg, "verify.sh")
    assert os.path.exists(script), "缺 p77_smart_ops/verify.sh，P7 无从验收"
    print("[P7] 驱动 %s（首跑含 Chroma/Kùzu 播种，约 1~3 分钟）" % os.path.relpath(script, COURSE_ROOT))
    r = subprocess.run(["bash", "verify.sh"], cwd=pkg, capture_output=True,
                       timeout=timeout, env=dict(os.environ, PY=sys.executable))
    out = (r.stdout or b"").decode("utf-8", "ignore")
    err = (r.stderr or b"").decode("utf-8", "ignore")
    marks = [l.strip() for l in out.splitlines() if l.strip().startswith(("✓", "✗", "["))]
    for line in marks:
        print("   ", line[:120])
    if r.returncode != 0 and err.strip():
        print("   [stderr]", err.strip().splitlines()[-1][:200])
    assert r.returncode == 0, "verify.sh 存在失败项（见上方 ✗），P7 未达交付口径"
    assert "ALL PASS" in out, "verify.sh 未输出 ALL PASS，闸门不完整"
    assert sum(l.startswith("✓") for l in marks) >= 18, "闸门条目过少，疑被跳过"
    print("P7 五库+F1门禁+四路由+智能体取证+404/400兜底 端到端 ALL PASS")


# ======================================================================
# CLI
# ======================================================================
TASKS = {"p11": p11, "p12": p12, "p21": p21, "p22": p22,
         "p33": p33, "p41": p41, "p55": p55, "p66": p66, "p77": p77}


def _run(names):
    import time
    import traceback

    failed = []
    for name in names:
        fn = TASKS[name]
        t0 = time.perf_counter()
        head = (fn.__doc__ or "").strip().splitlines()[0]
        print("=" * 72)
        print(f"▶ {name}｜{head}")
        print("-" * 72)
        try:
            fn()
            print(f"PASS {name} ({time.perf_counter() - t0:.1f}s)")
        except Exception as exc:                      # pylint: disable=broad-except
            traceback.print_exc()
            print(f"FAIL {name} ({exc.__class__.__name__}: {exc}) "
                  f"[{time.perf_counter() - t0:.1f}s]")
            failed.append(name)
    print("=" * 72)
    print(f"教师参考自检汇总: {len(names) - len(failed)}/{len(names)} PASS"
          + (" —— 全部通过 ✓" if not failed else f" —— 失败: {', '.join(failed)}"))
    return 1 if failed else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if argv[0] == "all":
        sys.exit(_run(list(TASKS)))
    unknown = [a for a in argv if a not in TASKS]
    if unknown:
        print(f"未知工单号 {unknown}；可选: all / {' '.join(TASKS)}")
        sys.exit(2)
    sys.exit(_run(argv))
