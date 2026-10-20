# -*- coding: utf-8 -*-
"""标准工程模板：表驱动 + 原子生成 + 生成后自检。"""
import os

README = """# {name}

## 一、跑起来
```bash
pip install -r requirements.txt
python run.py
python -m pytest -q
```

## 二、目录
- src/（包代码，按层拆 module）
- tests/（pytest，正常/边界/异常三档）
- docs/（过程文档）
- config/（YAML，规则外置）

## 三、提交历史
- 分支 main 保护；提交信息 feat:/fix:/docs:/test:
"""

GITIGNORE = """__pycache__/
*.py[cod]
.pytest_cache/
.venv/
output/*.log
"""


def file_templates(name, deps):
    """返回 {相对路径: 内容}（表驱动，新增文件只需加一行）。"""
    return {
        "README.md": README.format(name=name),
        ".gitignore": GITIGNORE,
        "requirements.txt": "\n".join(["# %s 依赖" % name] + list(deps)) + "\n",
        "src/__init__.py": '"""%s 实现包。"""\n__version__ = "1.0.0"\n' % name,
        "tests/__init__.py": "",
        "run.py": "print('hello %s')\n" % name,
    }


def ensure(root, files):
    """原子生成；已存在则不覆盖（防误覆盖）。"""
    made, kept = [], []
    for rel, content in files.items():
        path = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if os.path.exists(path):
            kept.append(rel)
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        made.append(rel)
    return made, kept


def verify(root, files):
    """生成后自检：必须文件都在、无空目录、无 .pyc。"""
    missing = [rel for rel in files
               if not os.path.exists(os.path.join(root, rel.replace("/", os.sep)))]
    empty_dirs, junk = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath == root or "__pycache__" in dirpath:
            continue
        if not filenames and not dirnames:
            empty_dirs.append(os.path.relpath(dirpath, root))
        junk += [f for f in filenames if f.endswith(".pyc")]
    return {"missing": missing, "empty_dirs": empty_dirs, "junk": junk}
