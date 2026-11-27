"""Safe offline replacement for the original hard-coded PASS/commit script.

Recompute and verify the frozen case. This entry point never commits a live
transaction, changes original pointers, or claims a new Karamba result.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from timber_baseline.replay import main

if __name__ == '__main__':
    sys.exit(main())
