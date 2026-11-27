"""Sequential, restartable all-gallery runner. Never downloads or modifies inputs."""
from pathlib import Path
import argparse,sys,os,time,subprocess,signal,shutil,datetime,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageOps
from src.io_utils import ROOT,read,save,sha,digest,verify_files,files,environment
from src.grade import evaluate
from src import report

def stage(job,name,seconds):
    folder=Path(job['run_dir'])/name;folder.mkdir(exist_ok=True);stamp=folder/'stage.json'
    sig=digest(dict(key=job['run_key'],stage=name,force_lsd=job.get('force_lsd',False)))
    if stamp.exists():
        old=read(stamp)
        if old.get('signature')==sig and old.get('status')=='COMPLETE' and verify_files(folder,old['files']):
            return dict(status='COMPLETE',detail='Verified cached output')
    spec=dict(job,stage=name,output=str(folder));save(folder/'job.json',spec)
    start=time.monotonic();print(job['record']['listing_id'],name,'START',flush=True)
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        child=subprocess.Popen([sys.executable,'-u',str(ROOT/'src/worker.py'),str(folder/'job.json')],cwd=ROOT,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
        try:code=child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            if os.name!='nt':os.killpg(child.pid,signal.SIGTERM)
            else:child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name!='nt':os.killpg(child.pid,signal.SIGKILL)
                else:child.kill()
                child.wait(timeout=10)
            code=124
    elapsed=time.monotonic()-start
    if code:
        result=dict(status='TIMEOUT' if code==124 else 'FAILED',exit_code=code,seconds=elapsed,detail=name+'/worker.log')
    else:
        inventory=files(folder)
        for key in ['predictions.npz','job.json','worker.log']:inventory.pop(key,None)
        result=dict(status='COMPLETE',seconds=elapsed,detail='Fresh computation',signature=sig,files=inventory)
    save(stamp,result);print(job['record']['listing_id'],name,result['status'],f'{elapsed:.1f}s',flush=True)
    return {k:v for k,v in result.items() if k not in ['files','signature']}

def reuse_masks(job):
    cache=ROOT/'cache_masks'/job['record']['listing_id'];meta=cache/'manifest.json'
    if not meta.exists():return False
    m=read(meta)
    if m['source_images']!=[x['sha256'] for x in job['record']['images']] or m['sam2_config']!=job['config']['sam2']:return False
    if not all(sha(cache/f['path'])==f['sha256'] for f in m['files']):return False
    dst=Path(job['run_dir'])/'sam2';dst.mkdir(exist_ok=True)
    for f in m['files']:shutil.copy2(cache/f['path'],dst/f['path'])
    save(dst/'reused_manifest.json',m);return True

def preflight():
    import cv2,numpy,scipy,torch,torchvision,hydra,omegaconf,safetensors,iopath,einops
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable in this interpreter; use the existing .envs/vision_gpu/bin/python without resolving its symlink')
    if torch.cuda.get_device_capability()[0]<8:raise RuntimeError('Use this package on RTX4090D, not V100S')
    from src.io_utils import checked_model
    cfg=read(ROOT/'configs/batch.json')
    # Revalidate full checkpoint hashes once per batch invocation. Workers reuse
    # the identity only while resolved file path, byte size and mtime remain equal.
    save(ROOT/'.runtime/verified_models.json',{})
    for name in ['SAM2.1 Hiera Tiny','VGGT-1B']:checked_model(cfg,name)
    print('Preflight OK:',sys.executable,torch.cuda.get_device_name(0),torch.__version__,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--all',action='store_true');p.add_argument('--ids',nargs='+')
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--preflight',action='store_true')
    p.add_argument('--retry-failed',action='store_true');p.add_argument('--keep-dense',action='store_true')
    p.add_argument('--limit',type=int);p.add_argument('--output',default='outputs');args=p.parse_args()
    if args.preflight:preflight();return
    if not args.all and not args.ids:p.error('Choose --all or --ids 117692 120235 111575')
    cfg=read(ROOT/'configs/batch.json');records=read(ROOT/'data/all_manifest.json')['records']
    ids=set(args.ids or []);known={r['listing_id'] for r in records}
    if ids-known:p.error('Unknown listing IDs: '+','.join(ids-known))
    chosen=[r for r in records if args.all or r['listing_id'] in ids]
    if args.limit:chosen=chosen[:args.limit]
    out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
    lock=out/'.batch.lock'
    try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    except FileExistsError:raise SystemExit('Batch lock exists. Do not start a second batch. After verifying the recorded PID has stopped, remove only outputs/.batch.lock.')
    with os.fdopen(fd,'w') as f:f.write(str(os.getpid()))
    try:
        if not args.prepare_only:preflight()
        results=read(out/'batch_summary.json')['records'] if (out/'batch_summary.json').exists() else {}
        # Hash our adapter code plus the frozen upstream source inventory; changes create new run directories.
        code={str(x.relative_to(ROOT)):sha(x) for sub in ['src','configs','scripts','assets'] for x in sorted((ROOT/sub).rglob('*')) if x.is_file() and '__pycache__' not in x.parts}
        code['vendor_manifest']=sha(ROOT/'vendor_manifest.json')
        # Verify frozen vendored source once, not 762 times.
        vendor=read(ROOT/'vendor_manifest.json')
        if not verify_files(ROOT,vendor):raise RuntimeError('Vendored source changed; preserve audit and rebuild package signature')
        for record in chosen:
            start=time.monotonic();listing_id=record['listing_id'];key=digest(dict(inputs=record,config=cfg,code=code))[:16]
            folder=out/'runs'/listing_id/key;folder.mkdir(parents=True,exist_ok=True)
            runfile=folder/'run.json';previous=read(runfile) if runfile.exists() else None
            if previous and previous['status'] in ['COMPLETE_RESEARCH_OUTPUT','PARTIAL_RESEARCH_OUTPUT','FAILED']:
                if previous['status']=='COMPLETE_RESEARCH_OUTPUT' or not args.retry_failed:
                    inventory=previous.get('output_hashes',{})
                    if inventory and verify_files(folder,inventory):
                        print(listing_id,'SKIP verified existing',previous['status'],flush=True);continue
                    print(listing_id,'Previous output incomplete/changed; checking individual stage caches',flush=True)
            if shutil.disk_usage(out).free<8*1024**3:print('STOP: less than 8 GiB free. Completed outputs preserved.',flush=True);break
            run=dict(listing_id=listing_id,run_key=key,status='RUNNING',stages={},environment=environment(),
                grade_is_hypothesis_only=True,formal_grade='UNKNOWN',structural_verification='NOT_RUN')
            grade=evaluate(record);save(folder/'grade_hypothesis.json',grade);save(folder/'input.json',record)
            try:
                images=[];preview=folder/'previews';preview.mkdir(exist_ok=True)
                for i,im in enumerate(record['images'],1):
                    source=ROOT/'data'/im['path']
                    if sha(source)!=im['sha256']:raise ValueError('Original image hash mismatch: '+im['path'])
                    images.append(str(source));thumb=ImageOps.exif_transpose(Image.open(source)).convert('RGB');thumb.thumbnail((1000,1000));thumb.save(preview/f'{i:02d}.jpg',quality=85)
                run['stages']['input']=dict(status='COMPLETE',detail='Full gallery and source hashes verified')
                prepared=folder/'prepared';prepared.mkdir(exist_ok=True)
                save(prepared/'inputs.json',dict(listing_id=listing_id,nominal_dimensions=record.get('nominal_dimensions') or {},
                    images=[dict(copy_path=os.path.relpath(path,prepared),sha256=im['sha256']) for path,im in zip(images,record['images'])]))
                job=dict(record=record,config=dict(cfg,listing_id=listing_id),images=images,run_key=key,
                    run_dir=str(folder),prepared=str(prepared),masks=[str(folder/f'sam2/{i:02d}_mask.png') for i in range(1,len(images)+1)],vggt=str(folder/'vggt'))
                if args.prepare_only:run['status']='PREPARED_NOT_RUN'
                else:
                    if reuse_masks(job):run['stages']['sam2']=dict(status='COMPLETE',detail='Reused SHA-bound existing automatic masks')
                    else:run['stages']['sam2']=stage(job,'sam2',cfg['timeouts_seconds']['sam2'])
                    if run['stages']['sam2']['status']=='COMPLETE':
                        run['stages']['lines']=stage(job,'lines',cfg['timeouts_seconds']['lines'])
                        if run['stages']['lines']['status']!='COMPLETE':run['stages']['lines']=stage(dict(job,force_lsd=True),'lines',45)
                        if len(images)>1:
                            # If partial surface output must be retried after dense cleanup, regenerate only VGGT.
                            if args.retry_failed and (folder/'vggt/stage.json').exists() and not (folder/'vggt/predictions.npz').exists() and not (folder/'surface/surface_fit.json').exists():
                                (folder/'vggt/stage.json').rename(folder/'vggt/stage_before_dense_regeneration.json')
                            run['stages']['vggt']=stage(job,'vggt',cfg['timeouts_seconds']['vggt'])
                            if run['stages']['vggt']['status']=='COMPLETE':run['stages']['surface']=stage(job,'surface',cfg['timeouts_seconds']['surface'])
                        else:run['stages']['vggt']=dict(status='SINGLE_VIEW_2D_ONLY',detail='No multi-view geometry claim')
                    run['status']='COMPLETE_RESEARCH_OUTPUT' if all(run['stages'].get(s,{}).get('status')=='COMPLETE' for s in ['sam2','lines','vggt','surface']) else 'PARTIAL_RESEARCH_OUTPUT'
                    if not args.keep_dense and run['stages'].get('surface',{}).get('status')=='COMPLETE':
                        # The only deleted file is this new run's explicitly transient intermediate.
                        dense=folder/'vggt/predictions.npz'
                        if dense.exists():dense.unlink()
                        run['dense_predictions']='TRANSIENT_REMOVED_AFTER_DERIVED_OUTPUTS; use --keep-dense before first run to retain'
            except Exception as e:
                run['status']='FAILED';run['failure']=dict(type=type(e).__name__,message=str(e));print(listing_id,str(e),flush=True)
            grade['cv_evidence']=dict(stages={k:v['status'] for k,v in run['stages'].items()},
                supports=['visible-pixel candidate selection','estimated geometry / appearance where available'],
                does_not_establish=['good condition','decay absence','species','grade','strength','same physical piece'])
            if (folder/'surface/surface_fit.json').exists():
                fit=read(folder/'surface/surface_fit.json')
                grade['cv_evidence'].update(estimated_patches=fit['estimated_patches'],supported_points=fit['supported_points'],
                    same_piece_confirmed=fit['same_physical_piece_confirmed'],head_disagreement_median_fraction=fit['head_disagreement_median_fraction'],
                    seller_dimension_disagreement=fit['nominal_length_scale_scenario'])
            save(folder/'grade_hypothesis.json',grade)
            run['seconds']=time.monotonic()-start;run['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(runfile,run)
            try:report.listing(record,folder,run)
            except Exception as e:run['report_error']=str(e);save(runfile,run)
            inventory=files(folder)
            inventory={k:v for k,v in inventory.items() if k!='run.json' and not k.endswith(('predictions.npz','job.json','worker.log'))}
            run['output_hashes']=inventory;save(runfile,run)
            results[listing_id]=dict(status=run['status'],report=(folder/'review.html').relative_to(out).as_posix(),
                grade_status=grade['status'],hypotheses=[c['grade'] for c in grade['conditional_candidates']],seconds=run['seconds'])
            report.index(out,records,results);print(listing_id,run['status'],f'{run["seconds"]:.1f}s',flush=True)
        report.index(out,records,results)
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':main()
