import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))
