"""User-authorized eight-batch queue. Standard library only; no setup/download."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, time, zipfile

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'batch-evidence-v3'
BATCHES = ['09', '10', '11', '12', '13', '14', '15', '16']
MIN_FREE = 20 * 2**30

def progress(log):
    """Read at most 256 KiB. Log activity and queue heartbeat are separate facts."""
    if not log.exists(): return dict(log_tail=[], current_listing=None, completed_listings=0)
    with log.open('rb') as f:
        f.seek(max(0, log.stat().st_size - 256 * 1024))
        lines = f.read().decode('utf-8', errors='replace').splitlines()
    starts = [m.group(1) for line in lines if (m := re.match(r'^LISTING (\S+) upright inputs ', line))]
    finished = {m.group(1) for line in lines if (m := re.match(r'^(\S+) (?:READY_FOR_VISUAL_REVIEW|PARTIAL_REVIEW_OUTPUT|FAILED_CONTINUED)$', line))}
    return dict(log_tail=lines[-10:], current_listing=starts[-1] if starts else None,
                completed_listings=len(finished), completed_count_scope='recent_log_window',
                log_bytes=log.stat().st_size, log_last_modified_utc=datetime.datetime.fromtimestamp(log.stat().st_mtime, datetime.timezone.utc).isoformat(),
                log_idle_seconds=round(max(0, time.time()-log.stat().st_mtime), 1))

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def stamp(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def save(p, value):
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(tmp, p)
def space(extra=0):
    free = shutil.disk_usage(ROOT).free
    if free < MIN_FREE + extra:
        raise RuntimeError(f'Insufficient disk: {free/2**30:.1f} GiB free; need {(MIN_FREE+extra)/2**30:.1f} GiB. Nothing deleted.')
def plan(bid): return read(APP / f'plans/batch_{bid}.json')
def completed(bid):
    pointer = APP / f'state/latest_batch_{bid}.json'
    if not pointer.exists(): return False
    out = Path(read(pointer)['output']).resolve()
    if not out.is_relative_to((APP / 'outputs').resolve()): raise ValueError('Output outside owned directory')
    state = read(out / 'batch_summary.json')
    if state.get('status') != 'BATCH_COMPLETE_REVIEW_REQUIRED':
        raise RuntimeError(f'Batch {bid} has an incomplete prior snapshot. Inspect before queueing; no retry requested.')
    expected = set(plan(bid)['listing_ids'])
    rows = state.get('results', {})
    if set(rows) != expected or any(r.get('status') != 'READY_FOR_VISUAL_REVIEW' for r in rows.values()):
        raise RuntimeError(f'Batch {bid} has missing/failed listings. Inspect logs; queue stops without retry.')
    for lid, row in rows.items():
        if any(s.get('status') not in ('COMPLETE', 'NOT_RUN_SINGLE_VIEW') for s in row.get('stages', {}).values()):
            raise RuntimeError(f'Batch {bid}, listing {lid}: failed stage; queue stops.')
    return True

def prepare(bid):
    if completed(bid):
        print(f'{bid}: completed snapshot found; will SKIP, no new inference.', flush=True)
        return
    missing = []
    for record in plan(bid)['records']:
        for im in record['images']:
            rel = Path(im['path'])
            if rel.is_absolute() or '..' in rel.parts: raise ValueError('Unsafe image path')
            candidates = [ROOT / 'data' / rel, APP / f'incoming/batch_{bid}' / rel]
            valid = False
            for dest in candidates:
                if dest.exists():
                    if dest.stat().st_size != im['bytes'] or sha(dest) != im['sha256']:
                        raise RuntimeError('Existing input differs; will not overwrite: ' + str(dest))
                    valid = True
                    break
            if not valid: missing.append((im, candidates[1]))
    if not missing:
        print(f'{bid}: all existing images verified.', flush=True)
        return
    archives = [ROOT.parent / f'timber-batch-{bid}-v3.zip', ROOT / f'timber-batch-{bid}-v3.zip']
    archive = next((p for p in archives if p.is_file()), None)
    if archive is None: raise FileNotFoundError(f'Upload timber-batch-{bid}-v3.zip to {ROOT.parent}. No model started.')
    space(sum(im['bytes'] for im, _ in missing))
    with zipfile.ZipFile(archive) as z:
        for im, dest in missing:
            # Only exact manifest-named image entries are read, never arbitrary ZIP paths.
            member = f'timber-full-batch-4090d/batch-evidence-v3/incoming/batch_{bid}/{im["path"]}'
            info = z.getinfo(member)
            if info.file_size != im['bytes']: raise ValueError('ZIP image size mismatch: ' + member)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + '.queue09-16.part')
            with z.open(info) as src, tmp.open('wb') as target: shutil.copyfileobj(src, target)
            if sha(tmp) != im['sha256']: raise ValueError('ZIP image hash mismatch: ' + member)
            if dest.exists(): raise RuntimeError('Input appeared concurrently; no overwrite: ' + str(dest))
            tmp.rename(dest)
    print(f'{bid}: extracted and hash-verified {len(missing)} images.', flush=True)

def queue(lock_factory):
    state_dir = APP / 'state'
    state_dir.mkdir(exist_ok=True)
    with (state_dir / 'queue_09_16.lock').open('a+') as queue_lock, (state_dir / 'queue_04_08.lock').open('a+') as prior_queue:
        lock_factory(queue_lock)
        # Keep the old queue excluded for the entire new queue, including preflight.
        lock_factory(prior_queue)
        with (state_dir / 'batch_runner.lock').open('a+') as existing:
            lock_factory(existing)  # Probe only; child batch runner takes this lock itself.
        for bid in BATCHES: prepare(bid)
        if ARGS.prepare:
            print('READY: fixed batches 09-16. No model has been started by this preflight.', flush=True)
            return
        log_dir = ROOT / 'logs'
        log_dir.mkdir(exist_ok=True)
        status_path = state_dir / 'queue_09_16_status.json'
        state = dict(queue=BATCHES, status='RUNNING', pid=os.getpid(), started_utc=stamp(), batches=[],
                     no_automatic_retry=True, no_setup_or_download=True, quality_approved=False)
        save(status_path, state)
        try:
            for bid in BATCHES:
                if completed(bid):
                    state['batches'].append(dict(batch=bid, status='SKIPPED_EXISTING_COMPLETE'))
                    save(status_path, state)
                    continue
                space()
                log = log_dir / f'queue_batch_{bid}_{stamp()}.log'
                state.update(current_batch=bid, current_log=str(log), batch_listing_count=len(plan(bid)['listing_ids']),
                             child_pid=None, progress=None)
                save(status_path, state)
                print(f'START batch {bid}; log: {log}', flush=True)
                with log.open('wb') as output:
                    child = subprocess.Popen(['bash', str(ROOT / 'run_batch_v31.sh'), bid], cwd=ROOT,
                                             stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
                    state['child_pid'] = child.pid
                    while True:
                        code = child.poll()
                        state.update(heartbeat_utc=stamp(), progress=progress(log))
                        save(status_path, state)
                        if code is not None: break
                        time.sleep(5)
                state['child_exit_code'] = code
                if code:
                    raise RuntimeError(f'Batch {bid} exited {code}. See {log}; later batches NOT started.')
                if not completed(bid): raise RuntimeError(f'Batch {bid} did not publish completed output.')
                state['batches'].append(dict(batch=bid, status='EXECUTION_COMPLETE_QUALITY_UNREVIEWED', log=str(log)))
                save(status_path, state)
                print(f'COMPLETE batch {bid}; compact report generated by original runner.', flush=True)
            state.update(status='FINISHED_09_16_REVIEW_REQUIRED', finished_utc=stamp(), current_batch=None, child_pid=None)
            save(status_path, state)
            print('FINISHED: 09-16 only. No further batch will start. Preserve raw cache; review reports after return.', flush=True)
        except BaseException as error:
            state.update(status='STOPPED_ERROR', error=str(error), finished_utc=stamp())
            save(status_path, state)
            raise

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--prepare', action='store_true')
    ARGS = p.parse_args()
    if os.name != 'posix': raise SystemExit('Run manually on the existing Linux GPU machine.')
    import fcntl
    def lock(file):
        try: fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another batch/queue is active. No process or lock file removed.')
    try: queue(lock)
    except Exception as error: raise SystemExit(type(error).__name__ + ': ' + str(error))
