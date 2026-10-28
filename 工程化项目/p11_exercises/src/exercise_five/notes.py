# -*- coding: utf-8 -*-
"""《迁移笔记》生成器（超优(A)层交付物，由项目维护而非手写快照）。

笔记内容来自真实实现（core.py 的函数/类与工单知识四要素 B01~B06），
每次 `python run.py` 重新渲染并落盘 docs/09-C转Python迁移笔记.md，
保证"文档↔代码"不脱节（GB/T 8567 文档编制 + 配置管理基线思想）。
完整性口径（audit()实测）：条目 ≥10、逐题常见错误覆盖五题、
含"P1.2 标准工程布局"映射章节——对应工单超优(A)行《迁移笔记》。
"""
import random
import re

ENTRY_COUNT_REQUIRED = 10
QUESTION_ORDER = ("题1", "题2", "题3", "题4", "题5")
#: A 层笔记必须出现的完整性章节（audit() 按名实测，缺一即不完整）
REQUIRED_SECTIONS = ("逐题常见错误", "P1.2 标准工程布局")

#: 笔记条目：编号 / 主题 / C 侧写法 / Python 侧写法 / 本项目落点 / 误区
ENTRIES = [
    ("声明与赋值", "int x = 5;", "x = 5  # 赋值即声明即初始化",
     "core.to_number()", "类型贴在值上，不是贴在变量上；换类型合法"),
    ("大括号与缩进", "if (d < 0) { return; }", "if d < 0:\n        return None",
     "core.solve_quadratic()", "4 空格统一禁 Tab；块结束没有 } 收尾"),
    ("printf 与 f-string", 'printf("%.2f", f)', 'f"%.2f" % f / format()',
     "exercises.exercise1()", "报告里所有格式化都走 str 格式化，不拼字符串"),
    ("数组与列表", "int a[10]; a[0]=1", "a = [0] * 10; a.append(1)",
     "selfcheck._bulk()", "列表动态扩容，无需 malloc 预分配"),
    ("结构体与类", "struct Device { char id[8]; };", "class Device: ...",
     "core.Device", "struct+配套函数 = 数据与行为一体的类"),
    ("函数指针与方法", "void start(struct Device *d)", "def start(self)",
     "core.Device.start()", "Python 少传一层指针，self 就是那个指针"),
    ("继承与扩展", "无内建继承（手工塞结构体）", "class PLC(Device)",
     "core.PLC", "子类新增 scan_ms、覆盖 start()，超集语义"),
    ("引用语义", "b = a 拷贝整个数组", "b = a 只复制引用",
     "tests/test_tier_d.py::test_tier_d_reference_versus_copy_difference",
     "改 b 会动 a；要断引用用 copy.deepcopy()"),
    ("错误码与异常", "if (read() < 0) return -1;", "try/except FileNotFoundError",
     "core.safe_read()", "错误在最外层一处接住，主逻辑不掺错误分支"),
    ("返回码类型", "返回 -1 表错（歧义）", "抛带上下文的自定义异常",
     "core.ExerciseError", "异常携带题号与参数，排错不用猜"),
    ("哈希表选型", "自己写 hash + 开放定址", "dict 键值 O(1)",
     "core.Registry", "设备 ID 键必须归一化类型，否则查不到"),
    ("头文件与模块", "#include \"device.h\"", "from . import core",
     "src/exercise_five/exercises.py", "src 布局 + 包内相对导入防命名冲突"),
    ("宏常量", "#define WARN 80", "配置文件 + dataclass 常量",
     "config.Settings", "阈值外置 YAML，改配置不改代码"),
    ("内存回收", "malloc/free 成对", "引用计数 + GC",
     "io_utils.write_text()", "临时文件必用 finally 清理，不靠 free 直觉"),
    ("浮点数值稳定性", "double 公式照抄教科书", "稳定式 q=-(b+sign(b)√d)/2",
     "core.solve_quadratic()", "b=-1e6、c=1 时朴素求根公式小根误差≈1e-6"),
]

#: 逐题常见错误与防线（题号 / 学生最常犯的错 / 本项目可核对的防线）
QUESTION_PITFALLS = [
    ("题1", "只换算华氏度，漏掉开尔文（工单要求两个结果都返回）",
     "`core.convert_temperature()` 返回二元组；内置断言锁定 ℉/K 成对"),
    ("题2", "Δ<0 时崩溃或硬塞复数；照抄教科书公式遇 b=-1e6 灾难性抵消",
     "`core.solve_quadratic()` 无实根返回 None + 稳定式 q，韦达/残差实测"),
    ("题3", "YAML 把 `01` 读成整数 1，键类型不一致导致删除静默失效",
     "ID 全链路 `normalize_id()` 归一化；删除未生效直接抛错判 FAIL"),
    ("题4", "子类只加 `scan_ms` 属性，忘了覆盖 `start()`（文案仍是基类）",
     "`core.PLC.start()` 覆盖 + `scan()` 逐轮输出，断言基类/子类文案不同"),
    ("题5", "先 `exists()` 预判再读（竞态），或裸 `except:` 把错误吞掉",
     "`core.safe_read()` try/except 逐类兜错，返回约定标记不崩溃"),
]

#: 本项目目录 ↔ P1.2 讲授的标准 Python 工程化布局的映射
P12_LAYOUT_MAP = [
    ("run.py", "唯一入口", "P1.2 骨架同款：`python run.py` 一键起跑"),
    ("config/rules.yaml", "规则外置", "P1.2 `config/` 目录：改配置不改代码"),
    ("src/exercise_five/", "src 布局业务包", "P1.2 `src/<包名>/`：逻辑与入口分离"),
    ("tests/", "分层验收测试", "P1.2 `tests/` 目录：一档一文件 + 端到端"),
    ("docs/01~09", "过程文档链", "P1.2 文档基线：与代码同 PR 更新"),
    ("output/", "确定性生成物", "P1.2 忽略口径：可重复生成、不进评审"),
]


def _explain_pick(seed):
    """A 层"挑 1 条向全班讲解"：用配置里的 seed 做确定性抽签。"""
    return random.Random(int(seed)).choice(["题1", "题2", "题3", "题4", "题5"])


def render(cfg, style, notes_stats):
    """渲染笔记正文（无时间戳：两次运行字节级一致，可进基线）。"""
    lines = ["# 09 C→Python 迁移笔记（超优 A 层交付物）", "",
             "> 项目：Python 五题闯关（工单 P1.1）　编制方式：由 "
             "`src/exercise_five/notes.py` 随 `python run.py` 自动生成",
             "> 达标线：A 层要求 ≥%d 条（本文件实测 %d 条）；完整性另按"
             "「逐题常见错误覆盖 5/5」+「P1.2 标准工程布局」章节实测"
             % (ENTRY_COUNT_REQUIRED, len(ENTRIES)),
             "> 用法：每条=C 侧写法 → Python 侧写法 → 本项目落点 → 误区",
             "", "## 一、迁移条目表", "",
             "| # | 主题 | C 语言 | Python | 本项目落点 | 误区/要点 |",
             "|---|---|---|---|---|---|"]
    for idx, (topic, c_side, py_side, where, pitfall) in enumerate(ENTRIES, 1):
        lines.append("| %d | %s | `%s` | `%s` | `%s` | %s |"
                     % (idx, topic, c_side.replace("\n", "  <br>  "),
                        py_side.replace("\n", "  <br>  "), where, pitfall))
    lines += ["", "## 二、五题对照速查", "",
              "| 题 | 工单要求 | Python 关键语法 | 实现位置 |", "|---|---|---|---|",
              "| 题1 | ℃→℉/K 两个结果都返回 | 元组返回、f-string/格式化 |"
              " `core.convert_temperature()` |",
              "| 题2 | 含无实根分支 | 判别式三分支、math.sqrt |"
              " `core.solve_quadratic()` |",
              "| 题3 | 字典增删改查 | dict O(1)、pop 真删 | `core.Registry` |",
              "| 题4 | Device+PLC（含 scan） | 继承/super/方法覆盖 |"
              " `core.Device` `core.PLC` |",
              "| 题5 | 异常保护读文件 | try/except 多分支 | `core.safe_read()` |",
              "", "## 三、决策矩阵（题3 容器选型·已填写）", "",
              "| 需求 | list | dict | 元组 | 结论 |",
              "|---|---|---|---|---|",
              "| 按 ID 查设备 | O(n) 遍历 | O(1) 哈希 | O(n) 遍历 | **选 dict** |",
              "| 保持录入顺序 | 天然保序 | 3.7+ 保序 | 天然保序 | dict 也可 |",
              "| ID 不可变 | 可变 | 键需可哈希 | 不可变 | 键用零填充字符串 |",
              "", "## 四、避坑清单（工单原文 ↔ 本项目防线）", "",
              "1. 缩进混用 Tab/空格 → `stylecheck` 的 E101 规则实测拦截；",
              "2. `=` 与 `==` 混用 → 语法层报错，无静默路径；",
              "3. dict 遍历时修改自身 → `Registry` 先取 `ids()` 快照再操作；",
              "4. `input()` 返回 str 忘转换 → 所有入参先过 `to_number()`；",
              "5. 以为 `=` 是拷贝 → 见上表「引用语义」一行，测试已锁定。",
              "", "## 五、规范与工具实测（与 output/report.txt 同源）", "",
              "- 内置 PEP 8 子集自检得分：**%.1f%%**（检查项 %d，违规 %d）"
              % (style["score"], style["total"], style["total"] -
                 style["passed"]),
              "- pylint/flake8/black/pre-commit 是否可用：见 output/report.txt"
              "「工具链探测」一节；工具缺失时直说不可用，绝不编造评分；",
              "- A 层讲解抽签（seed=%s）：本轮讲 **%s**；"
              % (cfg.seed, notes_stats["explain"]),
              "", "## 六、逐题常见错误与防线（超优(A)完整性口径）", "",
              "| 题号 | 学生常见错误 | 本项目防线 |", "|---|---|---|"]
    for number, pitfall, guard in QUESTION_PITFALLS:
        lines.append("| %s | %s | %s |" % (number, pitfall, guard))
    lines += ["", "## 七、与 P1.2 标准工程布局的映射", "",
              "| 本项目目录 | 角色 | 对应 P1.2 标准工程布局讲法 |",
              "|---|---|---|"]
    lines += ["| %s | %s | %s |" % row for row in P12_LAYOUT_MAP]
    lines += ["", "## 八、自查口令", "",
              "```bash", "python run.py --tier A     # 分层达标线",
              "python -m pytest -q -p no:cacheprovider   # 全量回归", "```", ""]
    return "\n".join(lines)


def count_entries(text):
    """实测条目数：只统计正文表格里的编号行（防止文档虚标）。"""
    return len(re.findall(r"^\| \d+ \| ", text, re.M))


def audit(text):
    """迁移笔记完整性实测：条数 + 逐题常见错误覆盖 + 必备章节（全按文本数）。"""
    covered = sum(1 for number in QUESTION_ORDER
                  if re.search(r"^\| %s \|" % number, text, re.M))
    found = sum(1 for section in REQUIRED_SECTIONS if section in text)
    return {"entries": count_entries(text),
            "questions_covered": covered,
            "questions_total": len(QUESTION_ORDER),
            "sections_found": found,
            "sections_total": len(REQUIRED_SECTIONS),
            "sections_complete": found == len(REQUIRED_SECTIONS)}


def write(cfg, style, path):
    """渲染并返回 (文本, 统计信息)；落盘由 pipeline 负责。"""
    stats = {"entries": len(ENTRIES), "explain": _explain_pick(cfg.seed),
             "seed": cfg.seed, "required": ENTRY_COUNT_REQUIRED}
    text = render(cfg, style, stats)
    stats["verified_entries"] = count_entries(text)
    stats["path"] = path
    stats["pass"] = stats["verified_entries"] >= ENTRY_COUNT_REQUIRED
    stats.update(audit(text))
    stats["complete"] = (stats["pass"] and stats["questions_covered"]
                         == len(QUESTION_ORDER) and stats["sections_complete"])
    return text, stats
