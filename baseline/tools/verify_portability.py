"""Relocate the package and deny all file reads outside it and Python's runtime."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

GUARD = r'''
import os,pathlib,runpy,sys
root=pathlib.Path(sys.argv[1]).resolve()
os.chdir(root)
allowed=[root,pathlib.Path(sys.base_prefix).resolve(),pathlib.Path(sys.prefix).resolve()]
opened=[]
def check(event,args):
    if event!='open' or not isinstance(args[0],(str,bytes,os.PathLike)):return
    p=pathlib.Path(os.fsdecode(args[0])).resolve()
    if not any(p.is_relative_to(base) for base in allowed):
        raise PermissionError('OUTSIDE_RELOCATED_PACKAGE:'+str(p))
    opened.append(str(p))
sys.addaudithook(check)
sys.dont_write_bytecode=True
sys.argv=[str(root/'run.py')]
try:
    runpy.run_path(str(root/'run.py'),run_name='__main__')
except SystemExit as exc:
    if exc.code:raise
import json
(root/'read-audit.json').write_text(json.dumps({'opened_files':sorted(set(opened)),
    'allowed_roots':[str(p) for p in allowed]},indent=2),encoding='utf-8')
'''

def main():
    target = ROOT.parent / 'timber-baseline-relocated-check'
    if target.exists():
        raise RuntimeError('Relocation target already exists; choose a new target to preserve evidence.')
    target.mkdir()
    for name in ['case', 'original-code', 'src']:
        shutil.copytree(ROOT / name, target / name, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'run.py', target / 'run.py')
    run = subprocess.run([sys.executable,'-I','-c',GUARD,str(target)],
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    baseline = ROOT / 'results' / 'baseline' / 'verification.json'
    relocated = target / 'results' / 'baseline' / 'verification.json'
    audit_file = target / 'read-audit.json'
    identical = relocated.exists() and baseline.read_bytes() == relocated.read_bytes()
    report = {'relocated_directory':str(target), 'exit_code':run.returncode,
              'original_project_reads_allowed':False,
              'same_verification_bytes':identical,
              'read_audit_completed':audit_file.exists(),
              'stdout':run.stdout,'stderr':run.stderr}
    (ROOT / 'results' / 'portability.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if run.returncode==0 and identical and audit_file.exists() else 1

if __name__ == '__main__':
    sys.exit(main())
