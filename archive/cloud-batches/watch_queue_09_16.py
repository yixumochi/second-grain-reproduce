"""Read-only auto-follow monitor. Ctrl+C does not signal the background queue."""
from pathlib import Path
import argparse, datetime, json, os, time

ROOT = Path(__file__).resolve().parent

def process_matches(pid):
    """Verify the queue command, avoiding a recycled PID being reported as live."""
    if not isinstance(pid, int) or pid <= 0: return False
    try:
        raw = Path(f'/proc/{pid}/cmdline').read_bytes()
        return any(x.endswith(b'queue_09_16.py') for x in raw.split(b'\0'))
    except FileNotFoundError: return False
    except PermissionError: return None

def render(state):
    live = process_matches(state.get('pid'))
    lines = ['TIMBER 09-16 | ' + datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
             'Queue: ' + state['status'] + ' | process present: ' + str(live),
             'Batches finished/skipped: ' + str(len(state.get('batches', []))) + '/8',
             'Current batch: ' + str(state.get('current_batch'))]
    p = state.get('progress') or {}
    if p:
        lines += [f"Completed listings in recent log: {p.get('completed_listings', '?')}/{state.get('batch_listing_count', '?')} | last listing: {p.get('current_listing')}",
                  'Queue heartbeat: ' + str(state.get('heartbeat_utc')) + ' (not proof of model progress)']
    log = Path(state['current_log']) if state.get('current_log') else None
    if log and log.is_file():
        with log.open('rb') as f:
            f.seek(max(0, log.stat().st_size-12000))
            recent = f.read().decode('utf-8', errors='replace').splitlines()[-14:]
        lines += ['Log idle: %.0f seconds | %s' % (max(0,time.time()-log.stat().st_mtime), log), '', *recent]
    if state.get('error'): lines += ['', 'ERROR: ' + state['error']]
    if state['status'] == 'RUNNING' and live is False:
        lines += ['', 'QUEUE PROCESS IS ABSENT. RUNNING may be stale; inspect logs before restarting.']
    lines += ['', 'Ctrl+C exits this viewer only. The GPU instance must remain running.']
    return '\n'.join(lines), live

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    path = ROOT/'batch-evidence-v3/state/queue_09_16_status.json'
    try:
        while True:
            if not path.exists():
                print('No queue status yet. Startup may still be checking inputs; inspect the launcher LOG.', flush=True)
                return
            state = json.loads(path.read_text(encoding='utf-8'))
            display, live = render(state)
            print(('\033[2J\033[H' if not args.once else '') + display, flush=True)
            if args.once or state['status'] != 'RUNNING' or live is False: return
            time.sleep(5)
    except KeyboardInterrupt: print('\nViewer stopped. No background process was signaled.')

if __name__ == '__main__': main()
