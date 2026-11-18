import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent

for percorso in (RADICE, TESTS):
    if str(percorso) not in sys.path:
        sys.path.insert(0, str(percorso))
