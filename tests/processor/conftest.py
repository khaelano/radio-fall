import sys
from pathlib import Path

PROCESSOR_ROOT = Path(__file__).parents[2] / "src" / "processor"
sys.path.insert(0, str(PROCESSOR_ROOT))
