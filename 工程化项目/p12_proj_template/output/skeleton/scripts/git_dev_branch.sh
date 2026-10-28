#!/usr/bin/env bash
# B 层：dev 分支规范合并（main 保护，合并保留分支拓扑留痕；本项目 pytest 不执行本脚本）
set -euo pipefail
git branch dev
git checkout dev
# 在 dev 上小步提交：一个功能一个 commit，前缀 feat:/fix:/docs:/test:
git commit -m "feat: 第一个功能"
git checkout main
git merge --no-ff dev -m "merge: feat(P1.2) 标准工程模板并入 main"
