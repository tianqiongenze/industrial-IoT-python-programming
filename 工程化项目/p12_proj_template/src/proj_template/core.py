# -*- coding: utf-8 -*-
"""标准工程模板：表驱动 + 原子生成 + 生成后自检 + 分层闸门事实。

生成物覆盖工单 P1.2 四层达标线（全部是**真实文件**，不是文档里的话术）：
  D 学徒   —— 结构完整可运行：src/ + tests/ + config/ + scripts/ + run.py + src/main.py
  C 操作员 —— scripts/setup_venv.sh 一键还原 venv，.gitignore 屏蔽 venv/（仓库就绪）
  B 组长   —— requirements.txt / requirements-dev.txt 双清单（-r 引用 + 钉版本下限）
              + scripts/git_dev_branch.sh 的 dev 分支与 --no-ff 合并
  A 师傅   —— .pre-commit-config.yaml 规范闸门（按配置声明 black/flake8 等 local hook）
              工具在**本机能否导入**由 env_probe 探测，报告如实标注，绝不谎报"已执行"。

铁律：本模块零外部命令——绝不执行 git / venv / pip / black / flake8 等任何子进程。
唯一的"真跑"是 skeleton_smoke()：在本进程内 import 生成骨架并调用它的入口与自带 test_
函数（不起子进程、不写 .pyc、模块名用完即归还），因为"骨架可运行"这句话必须有真凭据。
"""
import ast
import os
import re

README = """# {name}

> 由 03-P1.2 标准工程模板生成器产出（改配置不改代码：阈值与清单见 config/）。

## 一、跑起来（C 层：venv + 依赖 + 仓库）
```bash
bash scripts/setup_venv.sh      # 建 venv、装依赖、初始化仓库
python run.py
python -m pytest -q
```

## 二、目录
- src/（包代码，main.py 为入口，pyproject 的 [project.scripts] 指向 src.main:main）
- tests/（pytest，正常/边界/异常三档）
- config/（settings.yaml，配置外置）
- scripts/（venv 还原与 dev 分支命令，逐条可抄）
- docs/（过程文档，按需补）

## 三、规范闸门与分支（A/B 层）
- pre-commit 钩子：`pre-commit install` 后 commit 前自动跑 black + flake8
- 分支：main 保护，开发走 dev，合并用 `bash scripts/git_dev_branch.sh`
- 提交信息：feat:/fix:/docs:/test: 前缀，一个功能一个 commit
"""

GITIGNORE = """venv/
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
output/*.log
data/*.db
.DS_Store
"""

MAIN_PY = '''"""主程序入口（pyproject [project.scripts] 指向 src.main:main）。"""


def main():
    print("{name} 骨架可运行：入口 src/main.py:main 解析成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

UTILS_PY = '''"""工具函数。"""


def celsius_to_fahrenheit(c: float) -> float:
    return c * 9 / 5 + 32
'''

TEST_MAIN = '''"""单元测试：pytest 自动发现 test_ 开头函数（正常/边界/异常三档）。"""
from src.main import main
from src.utils import celsius_to_fahrenheit


def test_main_runs():
    assert main() == 0


def test_convert():
    assert celsius_to_fahrenheit(100) == 212


def test_convert_boundary_zero():
    assert celsius_to_fahrenheit(0) == 32
'''

SETTINGS_YAML = """db_path: data/warehouse.db
poll_interval: 0.5
unit: c
"""

SCRIPT_VENV = """#!/usr/bin/env bash
# C 层：venv + 依赖 + 仓库 三连（课堂逐条执行；本项目 pytest 不执行本脚本，只校验其内容）
set -euo pipefail
python -m venv venv
source venv/bin/activate          # Windows PowerShell: venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest
git init
git add .
git commit -m "feat: 初始化标准工程模板"
"""

SCRIPT_BRANCH = """#!/usr/bin/env bash
# B 层：dev 分支规范合并（main 保护，合并保留分支拓扑留痕；本项目 pytest 不执行本脚本）
set -euo pipefail
git branch dev
git checkout dev
# 在 dev 上小步提交：一个功能一个 commit，前缀 feat:/fix:/docs:/test:
git commit -m "feat: 第一个功能"
git checkout main
git merge --no-ff dev -m "merge: feat(P1.2) 标准工程模板并入 main"
"""

#: 每个规范工具对应的 local hook entry（未在表内的工具退化为 "<tool> ."）
LINT_ENTRY = {
    "black": "black .",
    "flake8": "flake8 src tests --max-line-length=100",
    "isort": "isort src tests",
    "ruff": "ruff check src tests",
    "pylint": "pylint src --fail-under=8.5",
}

DEFAULT_DEV_DEPS = ("pytest>=8.0", "black>=23.0", "flake8>=6.0", "pre-commit>=3.0")
DEFAULT_LINT_TOOLS = ("black", "flake8")
REQUIRED_DIRS = ("src", "tests", "config", "scripts")

RUNTIME_REQ = "requirements.txt"
DEV_REQ = "requirements-dev.txt"
PRECOMMIT = ".pre-commit-config.yaml"
GITIGNORE_NAME = ".gitignore"
VENV_SCRIPT = "scripts/setup_venv.sh"
BRANCH_SCRIPT = "scripts/git_dev_branch.sh"


def pre_commit_text(lint_tools=DEFAULT_LINT_TOOLS):
    """A 层钩子文件内容：工具清单来自配置（改配置不改代码）。"""
    lines = [
        "# A 层：commit 前自动执行规范闸门（repo: local，离线可用，不联网拉远程仓库）",
        "# 装钩子：pip install -r requirements-dev.txt && pre-commit install",
        "# 全量手动：pre-commit run --all-files",
        "repos:",
        "  - repo: local",
        "    hooks:",
    ]
    for tool in lint_tools:
        entry = LINT_ENTRY.get(tool, "%s ." % tool)
        lines += ["      - id: %s" % tool,
                  "        name: %s" % tool,
                  "        entry: %s" % entry,
                  "        language: system",
                  "        types: [python]"]
    return "\n".join(lines) + "\n"


def requirements_text(name, deps):
    """运行依赖清单（B 层要求逐行钉版本下限，闸门按内容判定）。"""
    return "\n".join(["# %s 运行依赖（每行钉版本下限 >= 或 ==）" % name]
                     + [str(d) for d in deps]) + "\n"


def requirements_dev_text(dev_deps=DEFAULT_DEV_DEPS):
    """开发依赖清单：-r 引用运行依赖，避免两份真源。"""
    return "\n".join(["# B 层：开发依赖可还原（一行 pip 装齐；运行依赖用 -r 引用，不重复真源）",
                      "-r requirements.txt"] + [str(d) for d in dev_deps]) + "\n"


def pyproject_text(name, python_version=">=3.10"):
    """包元数据：[project.scripts] 必须指向生成树里真实存在的 模块:函数。"""
    return (
        '[build-system]\n'
        'requires = ["setuptools>=61"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '\n'
        '[project]\n'
        'name = "%s"\n'
        'version = "0.1.0"\n'
        'description = "%s —— 标准工程模板生成骨架（03-P1.2）"\n'
        'requires-python = "%s"\n'
        'dependencies = []\n'
        '\n'
        '[project.optional-dependencies]\n'
        'dev = ["pytest>=8.0"]\n'
        '\n'
        '[project.scripts]\n'
        '%s = "src.main:main"\n'
        '\n'
        '[tool.setuptools.packages.find]\n'
        'where = ["."]\n'
        'include = ["src*"]\n'
        '\n'
        '[tool.pytest.ini_options]\n'
        'testpaths = ["tests"]\n'
        'pythonpath = [".", "src"]\n'
        'addopts = "-q --tb=short"\n'
    ) % (name, name, python_version, name)


def file_templates(name, deps, dev_deps=DEFAULT_DEV_DEPS, lint_tools=DEFAULT_LINT_TOOLS,
                   python_version=">=3.10", pre_commit=True):
    """返回 {相对路径: 内容}（表驱动，新增文件只需加一行）。

    pre_commit=False 时不产出 A 层钩子文件（配置驱动，A 层闸门随即判不达标）。
    """
    files = {
        "README.md": README.format(name=name),
        GITIGNORE_NAME: GITIGNORE,
        RUNTIME_REQ: requirements_text(name, deps),
        DEV_REQ: requirements_dev_text(dev_deps),
        "pyproject.toml": pyproject_text(name, python_version),
        VENV_SCRIPT: SCRIPT_VENV,
        BRANCH_SCRIPT: SCRIPT_BRANCH,
        "run.py": ('"""生成骨架的唯一入口：把项目根加入 sys.path 后调用 src.main:main。"""\n'
                   "import os\nimport sys\n\n"
                   "ROOT = os.path.dirname(os.path.abspath(__file__))\n"
                   "sys.path.insert(0, ROOT)\n\n"
                   "from src.main import main\n\n"
                   'if __name__ == "__main__":\n'
                   "    raise SystemExit(main())\n"),
        "src/__init__.py": '"""%s 实现包。"""\n__version__ = "1.0.0"\n' % name,
        "src/main.py": MAIN_PY.format(name=name),
        "src/utils.py": UTILS_PY,
        "tests/__init__.py": "",
        "tests/test_main.py": TEST_MAIN,
        "config/settings.yaml": SETTINGS_YAML,
    }
    if pre_commit:
        files[PRECOMMIT] = pre_commit_text(lint_tools)
    return files


def _path(root, rel):
    return os.path.join(root, rel.replace("/", os.sep))


def ensure(root, files, overwrite=False):
    """原子生成。

    overwrite=False：已存在即跳过（防误覆盖，保留手改）；
    overwrite=True ：内容不一致才重写（生成物归模板所有，保证生成树与模板同步）。
    返回 (写入清单, 保留清单)。
    """
    made, kept = [], []
    for rel, content in files.items():
        path = _path(root, rel)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if os.path.exists(path):
            if overwrite and _read(path) != content:
                _write(path, content)
                made.append(rel)
            else:
                kept.append(rel)
            continue
        _write(path, content)
        made.append(rel)
    return made, kept


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def inventory(root, files):
    """生成物盘点：{相对路径: 字节数}（文件不存在记 None）——报告的清单证据。"""
    out = {}
    for rel in sorted(files):
        path = _path(root, rel)
        out[rel] = os.path.getsize(path) if os.path.exists(path) else None
    return out


def verify(root, files):
    """生成后自检：必须文件都在、无空目录、无 .pyc、无模板外的野文件。"""
    missing = [rel for rel in sorted(files) if not os.path.exists(_path(root, rel))]
    empty_dirs, junk, unexpected = [], [], []
    rel_set = set(files)
    for dirpath, dirnames, filenames in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        if dirpath != root and not filenames and not dirnames:
            empty_dirs.append(os.path.relpath(dirpath, root))
        for f in filenames:
            rel = os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/")
            if f.endswith(".pyc"):
                junk.append(rel)                      # 编译产物混进交付物 = 不干净
            elif rel not in rel_set:
                unexpected.append(rel)                # 模板给不出来的文件
    return {"missing": missing, "empty_dirs": sorted(empty_dirs),
            "junk": sorted(junk), "unexpected": sorted(unexpected)}


def dep_lines(text):
    """依赖清单有效行：去注释、去空行（-r 引用行保留，供 -r 检查）。"""
    return [x.strip() for x in text.splitlines()
            if x.strip() and not x.strip().startswith("#")]


def pinned(lines):
    """(有效依赖行数, 其中钉了 >=/== 的行数)——B 层"依赖可还原"的量化口径。"""
    pk = [x for x in lines if not x.startswith("-r")]
    ok = [x for x in pk if (">=" in x or "==" in x)]
    return len(pk), len(ok)


def hook_ids(text):
    """从 .pre-commit-config.yaml 文本里取出声明的 hook id（不执行 pre-commit）。"""
    return re.findall(r"^\s*-\s*id:\s*([A-Za-z0-9_.-]+)", text, re.M)


def hook_entries(text):
    """{hook id: entry 命令行}（纯文本解析）——用来证明"配置里真的写了怎么跑"。"""
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^-\s*id:\s*([A-Za-z0-9_.-]+)$", s)
        if m:
            cur = m.group(1)
            out[cur] = ""
            continue
        if cur is not None and s.startswith("entry:"):
            out[cur] = s.partition(":")[2].strip()
    return out


def req_names(lines):
    """依赖行的包名（去掉版本约束与 -r 引用行）——查重复真源用。"""
    out = []
    for x in lines:
        if x.startswith("-r"):
            continue
        out.append(re.split(r"[<>=!~;\[]", x)[0].strip().lower())
    return out


def scripts_text(text):
    """[project.scripts] 段里的 目标 = "模块:属性" 映射（纯文本解析，不安装不执行）。"""
    out = []
    in_sec = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_sec = s == "[project.scripts]"
            continue
        if in_sec and s and not s.startswith("#") and "=" in s:
            _, _, val = s.partition("=")
            out.append(val.strip().strip(chr(34)))
    return out


def find_module_file(root, module, extra_bases=()):
    """在 root（及额外基目录，如 src/）里定位 dotted module 对应的源文件；找不到返回 ''。"""
    rel = module.replace(".", os.sep)
    for base in (root,) + tuple(extra_bases):
        for cand in (os.path.join(base, rel + ".py"),
                     os.path.join(base, rel, "__init__.py")):
            if os.path.exists(cand):
                return cand
    return ""


def defines_attr(path, attr):
    """AST 判断模块里是否定义了该顶层属性（def/class/赋值）——不 import、不执行。"""
    try:
        tree = ast.parse(_read(path))
    except (SyntaxError, ValueError, OSError):
        return False
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == attr:
                return True
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == attr for t in node.targets):
                return True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == attr:
                return True
    return False


def resolve_scripts(root, text, extra_bases=()):
    """校验 [project.scripts] 每个 "模块:属性" 目标在树里是否真实可解析。

    返回 [{target, module, attr, file, resolves, reason}]；只做定位 + AST 检查，
    不 pip install、不执行入口，因此测试永远不会碰 git/venv。
    """
    out = []
    for target in scripts_text(text):
        module, _, attr = target.partition(":")
        rec = {"target": target, "module": module, "attr": attr, "file": "",
               "resolves": False, "reason": ""}
        if not module or not attr:
            rec["reason"] = "目标写法非法（应为 模块:属性）"
            out.append(rec)
            continue
        path = find_module_file(root, module, extra_bases)
        if not path:
            rec["reason"] = "模块文件不存在"
            out.append(rec)
            continue
        rec["file"] = os.path.relpath(path, root).replace(os.sep, "/")
        if defines_attr(path, attr):
            rec["resolves"] = True
        else:
            rec["reason"] = "模块存在但未定义属性 %s" % attr
        out.append(rec)
    return out


def layer_facts(root, files, lint_tools=DEFAULT_LINT_TOOLS):
    """读生成物本体得出 D/C/B/A 分层闸门事实（只读内容，绝不执行 git/venv/pip/工具）。"""
    def text_of(rel):
        p = _path(root, rel)
        return _read(p) if os.path.exists(p) else ""

    dirs = [d for d in REQUIRED_DIRS if os.path.isdir(_path(root, d))]
    gi = text_of(GITIGNORE_NAME).splitlines()
    venv = text_of(VENV_SCRIPT)
    branch = text_of(BRANCH_SCRIPT)
    rt = dep_lines(text_of(RUNTIME_REQ))
    dev = dep_lines(text_of(DEV_REQ))
    pc = text_of(PRECOMMIT)
    hooks = hook_ids(pc)
    entries = hook_entries(pc)
    pp = text_of("pyproject.toml")
    skel_tests = text_of("tests/test_main.py")
    readme = text_of("README.md")
    eps = resolve_scripts(root, text_of("pyproject.toml"))
    runtime_pin = pinned(rt)
    dev_pin = pinned(dev)
    dupes = sorted(set(req_names(rt)) & set(req_names(dev)))
    return {
        "dirs_present": len(dirs), "dirs_total": len(REQUIRED_DIRS),
        "dirs_missing": [d for d in REQUIRED_DIRS if d not in dirs],
        "entry_total": len(eps),
        "entry_resolved": sum(1 for e in eps if e["resolves"]),
        "entry_failed": [e["target"] for e in eps if not e["resolves"]],
        "gitignore_venv": any(x.strip() in ("venv/", "/venv") for x in gi),
        "venv_cmd": "python -m venv venv" in venv,
        "venv_pip_restore": "pip install -r requirements.txt" in venv,
        "git_init": "git init" in venv,
        "runtime_dep_total": runtime_pin[0], "runtime_dep_pinned": runtime_pin[1],
        "dev_dep_total": dev_pin[0], "dev_dep_pinned": dev_pin[1],
        "dev_ref_runtime": "-r requirements.txt" in dev,
        "dev_branch": "git branch dev" in branch,
        "dev_checkout": "git checkout dev" in branch,
        "no_ff_merge": "--no-ff" in branch,
        "pre_commit_declared": PRECOMMIT in files,
        "hook_declared": hooks,
        "hook_missing": [t for t in lint_tools if t not in hooks],
        # 工单四档原文里额外要求取证的项目（课堂闸门不看这些）
        "readme_declared": "README.md" in files,
        "readme_bytes": len(readme.encode("utf-8")),
        "readme_titled": bool(readme.strip()) and readme.splitlines()[0].startswith("# "),
        "git_repo_seq": all(c in venv for c in ("git init", "git add .", "git commit -m")),
        "venv_activate": "source venv/bin/activate" in venv,
        "pytest_cfg_declared": "[tool.pytest.ini_options]" in pp
                               and 'testpaths = ["tests"]' in pp,
        "generated_tests": len(re.findall(r"^def test_", skel_tests, re.M)),
        "hook_with_entry": sum(1 for v in entries.values() if v),
        "fail_under_declared": any("--fail-under" in v for v in entries.values()),
        "dep_dupes": dupes,
        "ci_workflows": _ci_workflows(root),
    }


def _ci_workflows(root):
    """生成树里 .github/workflows/ 下的 yml/yaml 清单（工单超优行的『CI 或钩子』要如实区分）。"""
    base = _path(root, ".github/workflows")
    if not os.path.isdir(base):
        return []
    return sorted(f for f in os.listdir(base) if f.endswith((".yml", ".yaml")))


def structure_ok(facts, rep):
    """目录齐备 + 模板文件全落盘 + 无空目录 + 无 .pyc（课堂 D/C 与工单 D 共用这一条口径）。"""
    return bool(facts["dirs_present"] == facts["dirs_total"] and not rep["missing"]
                and not rep["empty_dirs"] and not rep["junk"])


def layer_gates(facts, rep, lint_tools=DEFAULT_LINT_TOOLS):
    """由事实推导 D/C/B/A 达标（每层都可被单条配置改动翻掉）。"""
    # 注：unexpected（模板外的野文件）只写进报告与自检行，不参与 D 判定——
    # 它可能是浏览目录时系统自动生成的 .DS_Store，用它翻闸门会造成无谓抖动。
    tiers = {
        "D": (structure_ok(facts, rep) and facts["entry_total"] > 0
              and facts["entry_resolved"] == facts["entry_total"]),
        "C": (structure_ok(facts, rep) and facts["gitignore_venv"] and facts["venv_cmd"]
              and facts["venv_pip_restore"] and facts["git_init"]),
        "B": (facts["dev_ref_runtime"] and facts["dev_dep_total"] > 0
              and facts["dev_dep_pinned"] == facts["dev_dep_total"]
              and facts["runtime_dep_total"] > 0
              and facts["runtime_dep_pinned"] == facts["runtime_dep_total"]
              and facts["dev_branch"] and facts["dev_checkout"]
              and facts["no_ff_merge"]),
        "A": (facts["pre_commit_declared"] and bool(facts["hook_declared"])
              and not facts["hook_missing"]),
    }
    return tiers


#: 工单《P1.2 标准 Python 工程模板 · 验收标准》四行原文（逐字照抄，作为对照节的单一口径来源）。
#: 它与上面的课堂四档**不同轴**：工单良好(C)「检查工具配置生效；pytest通过」在 layer_gates
#: 里没有对应门禁（课堂 A 只判钩子文件是否声明齐、课堂里没有一处跑过生成骨架的测试），
#: 所以这两条只由下面的 workorder_gates 取证。
WO_ROW = {
    "D": "conda环境激活可用+仓库初始化+结构完整+README",
    "C": "检查工具配置生效；pytest通过",
    "B": "依赖可还原（requirements完整）；dev分支规范合并",
    "A": "优秀+GitHub Actions CI或pre-commit钩子",
}

#: 生成骨架时在流水线进程内临时占用的模块名（用完原样归还）
SKEL_MODULES = ("src", "src.main", "src.utils", "tests", "tests.test_main")


def conda_env():
    """当前跑本流水线的解释器是否位于 conda 环境目录（只读 sys.prefix，不执行任何命令）。"""
    import sys
    prefix = sys.prefix.replace(os.sep, "/")
    return {"executable": sys.executable, "prefix": prefix,
            "in_conda_envs": "/envs/" in prefix}


def skeleton_smoke(root):
    """把生成骨架**真的加载一次**：导入 src.main 调 main()，再逐个调用它自带的 test_ 函数。

    口径边界（不夸大）：进程内直接调用，不起子进程、不跑 pytest 命令行、不写 .pyc；
    退出时把 sys.path / sys.modules / sys.dont_write_bytecode 还原成进来时的样子。
    """
    import importlib
    import io
    import sys
    from contextlib import redirect_stdout

    out = {"imported": False, "entry_returned": None, "entry_spoke": False,
           "tests_found": 0, "tests_passed": [], "tests_failed": [], "error": ""}
    saved_path, saved_dwb = list(sys.path), sys.dont_write_bytecode
    saved_mods = {k: sys.modules.get(k) for k in SKEL_MODULES}
    for key in SKEL_MODULES:
        sys.modules.pop(key, None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, root)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            main_mod = importlib.import_module("src.main")
            out["imported"] = True
            out["entry_returned"] = main_mod.main()
            tm = importlib.import_module("tests.test_main")
        names = sorted(n for n in dir(tm) if n.startswith("test_"))
        out["tests_found"] = len(names)
        for n in names:
            try:
                with redirect_stdout(buf):
                    getattr(tm, n)()
            except Exception as exc:
                out["tests_failed"].append(
                    {"name": n, "reason": "%s: %s" % (type(exc).__name__, exc)})
            else:
                out["tests_passed"].append(n)
        out["entry_spoke"] = bool(buf.getvalue().strip())
    except Exception as exc:
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_dwb
        for k, v in saved_mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return out


def workorder_gates(facts, rep, smoke, conda):
    """按工单四行原文逐条取证。与 layer_gates 各判各的，互不覆写。

    诚实红线：只要一档还剩"本机取不了证"的子项（要真开 shell 激活、真联网 pip、真触发 git
    钩子），这一档就只写"本节取证项 通过"而不写"达标"，并把子项名字原样列进 wo_ext。
    """
    structure = structure_ok(facts, rep)
    dep_ok = (facts["runtime_dep_total"] > 0
              and facts["runtime_dep_pinned"] == facts["runtime_dep_total"]
              and facts["dev_dep_total"] > 0
              and facts["dev_dep_pinned"] == facts["dev_dep_total"]
              and facts["dev_ref_runtime"] and not facts["dep_dupes"])
    branch_ok = (facts["dev_branch"] and facts["dev_checkout"] and facts["no_ff_merge"])
    hooks_ok = bool(facts["hook_declared"]) and not facts["hook_missing"]
    entry_ok = facts["hook_with_entry"] == len(facts["hook_declared"]) > 0
    run_ok = (smoke["imported"] and smoke["entry_returned"] == 0 and not smoke["tests_failed"]
              and smoke["tests_found"] > 0
              and facts["pytest_cfg_declared"]
              and facts["generated_tests"] == smoke["tests_found"])
    wo_b = bool(dep_ok and branch_ok)
    wo = {
        "D": bool(structure and facts["readme_declared"] and facts["readme_titled"]
                  and facts["git_repo_seq"] and facts["venv_activate"]),
        "C": bool(hooks_ok and entry_ok and run_ok),
        "B": wo_b,
        # 工单超优行原文是"优秀+…"，所以 B 档的实测项是 A 档的前置条件
        "A": bool(wo_b and facts["pre_commit_declared"] and hooks_ok),
    }
    wo_ext = {
        "D": ["conda activate 后 python -V 的课堂截图：本节只读出解释器确实在 conda 环境目录"
              "（%s），不在 shell 里执行激活" % conda["executable"]],
        "C": ["pre-commit run --all-files 实跑（工具能否导入见「规范闸门环境探测」节）",
              "用 pytest 命令行跑一遍生成骨架（本节只在进程内直接调用它自带的 test_ 函数）"],
        "B": ["pip install -r requirements.txt 实装（课程解释器离线，不联网）",
              "在真实 git 仓库里跑一次 dev → main 的 --no-ff 合并"],
        "A": ["GitHub Actions CI 未产出（工单原文是『CI 或 pre-commit 钩子』，本项目取后一支）",
              "pre-commit install 后由 git 在 commit 前真拦截"],
    }
    if not facts["fail_under_declared"]:
        wo_ext["C"].append("pylint 评分截图（工单提交物要求 ≥8.5/10）：本次 lint_tools 未含 "
                           "pylint，故 --fail-under=8.5 的 entry 未生成；把它加进 lint_tools "
                           "并在装有 pylint 的机器上运行即得该截图")
    return wo, wo_ext
