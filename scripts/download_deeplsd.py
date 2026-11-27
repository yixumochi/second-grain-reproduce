from pathlib import Path
import sys,time,urllib.request,os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.io_utils import ROOT,sha
target=ROOT/'models/deeplsd_md.tar';expected='56e9bae263977caa289ae49802987a67d4f00f376ae7e542176c8ae0a6cc2083'
if target.is_file():
    if sha(target)==expected:print('Verified existing DeepLSD');sys.exit(0)
    raise SystemExit('DeepLSD hash mismatch; existing file preserved')
partial=target.with_suffix('.tar.part');deadline=time.monotonic()+180
for attempt in range(2):
    try:
        offset=partial.stat().st_size if partial.exists() else 0
        request=urllib.request.Request('https://cvg-data.inf.ethz.ch/DeepLSD/deeplsd_md.tar',headers={'Range':f'bytes={offset}-'})
        with urllib.request.urlopen(request,timeout=20) as response:
            resumed=response.status==206
            if resumed and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise RuntimeError('Unexpected range')
            with partial.open('ab' if resumed else 'wb') as out:
                while True:
                    if time.monotonic()>deadline:raise TimeoutError('Optional model deadline')
                    data=response.read(1024*1024)
                    if not data:break
                    out.write(data)
        if sha(partial)==expected:os.replace(partial,target);print('DeepLSD verified');break
    except Exception as e:print('DeepLSD attempt',attempt+1,type(e).__name__)
    if time.monotonic()>deadline:break
else:raise SystemExit('Optional DeepLSD download incomplete; partial retained')
if not target.exists():raise SystemExit('Optional download stopped; OpenCV LSD will be used')
