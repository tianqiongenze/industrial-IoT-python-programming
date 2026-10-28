# -*- coding: utf-8 -*-
"""tests 包：按工单 P1.1 分层表四行组织用例（及格D/良好C/优秀B/超优A）。

test_tier_d/c/b/a.py 逐档验收"工单要求 → 真实测量数字 → 判定"，课堂跟做
阶梯作为"保底自检（不计入工单档位）"在 test_tier_d.py 里单独留痕。
pytest 自动发现 test_*.py / test_*；每个测试函数都有 docstring，
使 docs/03 声明的"注释补全"达标线可被 stylecheck 真实度量。
"""
