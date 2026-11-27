"""Portable review archives: no environments, credentials, weights or raw gallery."""
from pathlib import Path
import sys,json,tarfile,argparse,datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.io_utils import ROOT,read
p=argparse.ArgumentParser();p.add_argument('--all-in-one',action='store_true');p.add_argument('--ids',nargs='+');a=p.parse_args()
out=ROOT/'outputs';summary=read(out/'batch_summary.json');items=list(summary['records'].items())
if a.ids:items=[item for item in items if item[0] in a.ids]
size=len(items) if a.all_in_one else 100;size=max(1,size)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
dest=ROOT/'exports';dest.mkdir(exist_ok=True)
for offset in range(0,len(items),size):
    part=items[offset:offset+size];name=dest/f'timber_review_{stamp}_{offset//size+1:02d}.tar.gz'
    with tarfile.open(name,'w:gz',compresslevel=3) as archive:
        for leaf in ['index.html','batch_summary.json']:archive.add(out/leaf,arcname='outputs/'+leaf)
        for listing,item in part:
            folder=(out/item['report']).parent
            for file in sorted(folder.rglob('*')):
                if not file.is_file() or file.name in ['predictions.npz','job.json'] or '__pycache__' in file.parts:continue
                archive.add(file,arcname='outputs/'+file.relative_to(out).as_posix())
    print('Download:',name,'MiB:',round(name.stat().st_size/1024**2,1))
print('Extract all parts into the SAME directory; then open outputs/index.html. Parts intentionally share the index. Original gallery remains in the upload package; dense intermediate is excluded.')
