"""Run the controlled change experiment with Python 3.10+."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent/'src'))
from timber_baseline.change_experiment import main
if __name__ == '__main__':
    sys.exit(main())
