"""Run with Python 3.10+; the baseline needs only the standard library."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from timber_baseline.replay import main

if __name__ == '__main__':
    sys.exit(main())
