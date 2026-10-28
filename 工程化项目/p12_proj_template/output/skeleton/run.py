"""生成骨架的唯一入口：把项目根加入 sys.path 后调用 src.main:main。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.main import main

if __name__ == "__main__":
    raise SystemExit(main())
