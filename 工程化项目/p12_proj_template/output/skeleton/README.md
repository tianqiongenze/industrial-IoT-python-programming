# pump-ops

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
