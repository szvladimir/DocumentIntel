import sys
from pathlib import Path

# Ensure repository root is on sys.path for imports like `app` during tests
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
