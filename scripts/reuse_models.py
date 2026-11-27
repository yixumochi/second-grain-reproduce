from pathlib import Path
import sys,os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.io_utils import ROOT,read,sha
previous=Path(sys.argv[1])
for m in read(ROOT/'configs/models.json')['models']:
    target=ROOT/m['location'];source=previous/m['location']
    if target.exists():print('Present:',target.name);continue
    if source.is_file() and source.stat().st_size==m['bytes'] and sha(source)==m['sha256']:
        target.parent.mkdir(exist_ok=True,parents=True);target.symlink_to(source)
        print('Reused verified checkpoint:',target.name)
    else:print('Checkpoint not yet available:',target.name)
