# P2.1 清洗管道 · 工程化示范项目

## 目录结构（TOGAF四域落地）
```
engineering_demo_p21/
├── src/cleaning/     ← 应用架构：loader/cleaner 模块（单一职责）
├── config/rules.yaml ← 技术架构：清洗规则外置（改规则不改代码）
├── tests/            ← GB/T 15532：pytest 用例（正常/边界/异常）
├── docs/             ← 文档（GB/T 8567）
├── data/             ← 数据架构：原始数据与产出
├── run.py            ← 唯一入口
└── requirements.txt  ← 依赖锁定
```

## 一键运行
```bash
conda activate pp03
pip install -r requirements.txt
python run.py          # 完整管道+质量评分
python -m pytest tests/ -v   # 单元测试
```

## 工程化检查单（对照）
- [x] 多文件分层（loader/cleaner/report 分离）
- [x] 规则配置外置（rules.yaml）
- [x] 单元测试 ≥5（正常/边界/异常）
- [x] 审计留痕（pipe.audit 台账）
- [x] 依赖锁定 requirements.txt
