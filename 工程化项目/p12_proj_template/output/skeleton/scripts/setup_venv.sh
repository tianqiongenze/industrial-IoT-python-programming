#!/usr/bin/env bash
# C 层：venv + 依赖 + 仓库 三连（课堂逐条执行；本项目 pytest 不执行本脚本，只校验其内容）
set -euo pipefail
python -m venv venv
source venv/bin/activate          # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest
git init
git add .
git commit -m "feat: 初始化标准工程模板"
