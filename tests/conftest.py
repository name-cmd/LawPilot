"""pytest 公共配置：将项目根目录加入 sys.path，测试可 `from src.…` 导入。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
