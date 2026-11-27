"""Explicit, hash-checked checkpoint transfer; never imported by the runner."""
from pathlib import Path
import sys,argparse,time,os,urllib.request,urllib.error
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.io_utils import *
p=argparse.ArgumentParser();p.add_argument('--accept-downloads',action='store_true');a=p.parse_args()
models=read(ROOT/'configs/models.json')['models']
class NoTokenAcrossHosts(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,request,fp,code,msg,headers,url):
  redirected=super().redirect_request(request,fp,code,msg,headers,url)
  if redirected and urlsplit(url).netloc!=urlsplit(request.full_url).netloc:redirected.remove_header('Authorization')
  return redirected
opener=urllib.request.build_opener(NoTokenAcrossHosts())
print('Required pretrained checkpoint bytes:',sum(m['bytes'] for m in models),'(~4.83 GiB); model files are excluded from this package.',flush=True)
if not a.accept_downloads:raise SystemExit('No download started. Review MODEL_MANIFEST.md, then pass --accept-downloads.')
for model in models:
 location=Path(model['location'])
 if location.is_absolute() or '..' in location.parts:raise ValueError('Invalid checkpoint location')
 target=ROOT/location;target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():
  if target.stat().st_size==model['bytes'] and sha(target)==model['sha256']:print('Verified existing',target.name,flush=True);continue
  raise SystemExit('Existing checkpoint failed hash validation; inspect it before replacement: '+model['location'])
 part=target.with_suffix(target.suffix+'.part');deadline=time.monotonic()+1800
 for attempt in range(3):
  offset=part.stat().st_size if part.exists() else 0
  if offset==model['bytes']:break
  headers={'User-Agent':'reclaimed-timber-research-demo','Range':f'bytes={offset}-'}
  token=os.environ.get('HF_TOKEN')
  if token and 'huggingface.co' in model['url']:headers['Authorization']='Bearer '+token
  try:
   with opener.open(urllib.request.Request(model['url'],headers=headers),timeout=30) as response:
    resumed=response.status==206
    if resumed and not response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-'):raise RuntimeError('Unexpected resume range; partial file preserved')
    # Servers ignoring Range require a clean overwrite of this .part only, not inputs.
    with part.open('ab' if resumed else 'wb') as stream:
     while True:
      if time.monotonic()>deadline:raise TimeoutError('30 minute model transfer deadline')
      chunk=response.read(1024*1024)
      if not chunk:break
      stream.write(chunk)
   if part.stat().st_size==model['bytes']:break
  except urllib.error.HTTPError as e:
   if e.code in [401,403]:raise SystemExit('Authorization/license access required for '+model['name']+'. Accept access terms on its official Hugging Face page if required, then supply HF_TOKEN in your shell. Token is never written to outputs.')
   print(model['name'],'HTTP',e.code,'attempt',attempt+1,flush=True)
  except (OSError,TimeoutError) as e:print(model['name'],type(e).__name__,'attempt',attempt+1,'partial bytes',part.stat().st_size if part.exists() else 0,flush=True)
  if time.monotonic()>deadline:break
 if not part.exists() or part.stat().st_size!=model['bytes'] or sha(part)!=model['sha256']:raise SystemExit('Download incomplete/hash mismatch; finite retry exhausted. .part retained. No model run started.')
 part.replace(target);print('Checkpoint verified:',model['name'],flush=True)
