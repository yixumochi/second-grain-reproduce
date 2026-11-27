#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash run_repair_v2.sh --export-only
