# -*- coding: utf-8 -*-
"""P1.2 标准工程模板生成器 —— 运行后生成完整项目骨架
用法: python W02_template.py [项目名]
生成后: cd 项目名 && git init && pytest
"""
import os
import sys

FILES = {
    "src/main.py": '"""主程序入口"""\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
    "src/utils.py": '"""工具函数"""\n',
    "tests/test_main.py": ('"""单元测试: pytest自动发现test_开头函数"""\n'
                           "from src.main import main\n\n\n"
                           "def test_main_runs():\n    assert main() is None\n"),  # noqa: E501
    "config/settings.yaml": "db_path: data/warehouse.db\npoll_interval: 0.5\n",
    "README.md": ("# {name}\n\n## 快速开始\n```bash\n"
                  "python -m venv venv && source venv/bin/activate\n"
                  "pip install -r requirements.txt\npytest\n```\n"),  # noqa: E501
    "requirements.txt": "pandas>=1.5\nnumpy>=1.21\n",
    ".gitignore": "venv/\n__pycache__/\n*.pyc\n.DS_Store\ndata/*.db\n",
    ".pycharm/settings.json": '{"python.formatting.provider": "black",\n "python.linting.enabled": true}\n',
}


def build(name):
    for rel, content in FILES.items():
        path = os.path.join(name, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.replace("{name}", name))
        print("创建", path)
    print(f"""
模板已生成 → {name}/
下一步(逐条执行, 记录到工单):
  1. cd {name} && git init
  2. git add . && git commit -m "feat: 初始化标准工程模板"
  3. git branch dev && git checkout dev        # 开发分支
  4. pip install pytest pylint && pytest       # 测试通过
  5. pylint src/ --fail-under=8.5              # 评分≥8.5(工单截图)
""")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "industrial_project")
