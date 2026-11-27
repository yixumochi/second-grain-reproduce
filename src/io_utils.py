from pathlib import Path
import hashlib,json,os,sys,platform,importlib.metadata
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');os.replace(temp,p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def package_path(value):
 p=(ROOT/value).resolve()
 if not p.is_relative_to(ROOT):raise ValueError('Package-relative input path escapes package: '+str(value))
 return p
def files(root):return {p.relative_to(root).as_posix():sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file() and p.name!='stage.json' and '__pycache__' not in p.parts}
def verify_files(root,record):return bool(record) and all((root/p).is_file() and sha(root/p)==h for p,h in record.items())
def environment():
 packages={}
 for name in ['numpy','scipy','Pillow','opencv-python','torch','torchvision','safetensors','huggingface-hub','diffcheck']:
  try:packages[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:pass
 return dict(python=platform.python_version(),platform=platform.platform(),packages=packages)
def checked_model(cfg,name):
 m=next(m for m in read(package_path(cfg['models']))['models'] if m['name']==name)
 location=Path(m['location'])
 if location.is_absolute() or '..' in location.parts:raise ValueError('Invalid checkpoint path')
 # A setup-created link may reuse an existing external weight. Identity is still
 # established by exact byte count and full SHA-256, never just by path.
 p=ROOT/location
 if not p.exists():raise RuntimeError('FAILED_MODEL: missing '+m['location']+'; explicitly run scripts/download_models.py --accept-downloads first. No automatic download during validation.')
 stat=p.stat();identity=dict(path=str(p.resolve()),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=m['sha256'])
 validation=ROOT/'.runtime/verified_models.json'
 cache=read(validation) if validation.exists() else {}
 if cache.get(name)!=identity:
  if stat.st_size!=m['bytes'] or sha(p)!=m['sha256']:raise RuntimeError('FAILED_MODEL: checkpoint hash mismatch '+m['location'])
  cache[name]=identity;save(validation,cache)
 return p,m
