import sys
from pathlib import Path

# The code under test imports itself (qicklab.*, tests.*) from the repo root.
REPO = str(Path(__file__).resolve().parents[1])
if REPO not in sys.path:
    sys.path.insert(0, REPO)
