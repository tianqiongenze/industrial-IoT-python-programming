# pump-ops

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
