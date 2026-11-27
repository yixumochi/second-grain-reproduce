#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
# Deliberately fixed small selection. This wrapper never accepts --all.
# Keep dense outputs for these five only, so first-run failures can be diagnosed.
bash scripts/python.sh -u scripts/run_batch.py --ids 117692 120235 111575 117165 115685 --keep-dense 2>&1 | tee logs/pilot_console.log
bash scripts/python.sh check_pilot.py
echo 'Pilot stopped. Review and export results before starting any full batch.'
