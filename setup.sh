#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .runtime logs models outputs
REUSE="${TIMBER_REUSE_ROOT:-}"
if [[ -n "$REUSE" && -x "$REUSE/.envs/vision_gpu/bin/python" ]]; then
  PY="$REUSE/.envs/vision_gpu/bin/python"
  echo "Reusing verified GPU environment: $PY"
elif [[ -x .envs/vision_gpu/bin/python ]]; then
  PY="$PWD/.envs/vision_gpu/bin/python"
else
  python -c 'import torch,torchvision; print("Platform:",torch.__version__,torchvision.__version__)'
  python -m venv --system-site-packages .envs/vision_gpu
  PY="$PWD/.envs/vision_gpu/bin/python"
fi
# Never resolve the venv executable symlink: doing that bypasses site-packages.
printf '%s\n' "$PY" > .runtime/vision_python
"$PY" - <<'PY'
import json,torch,torchvision,sys
from pathlib import Path
Path('.runtime/platform_before.json').write_text(json.dumps(dict(python=sys.version,torch=torch.__version__,torchvision=torchvision.__version__)))
PY
if ! "$PY" -c 'import cv2,numpy,scipy,PIL,einops,omegaconf,hydra,safetensors,iopath,tqdm,yaml'; then
  # Preserve platform Torch by explicit installed-version constraints.
  "$PY" - <<'PY'
import torch,torchvision
from pathlib import Path
Path('.runtime/platform_constraints.txt').write_text(f'torch=={torch.__version__}\ntorchvision=={torchvision.__version__}\n')
PY
  timeout --kill-after=10s 600s "$PY" -m pip install --timeout 25 --retries 2 -c .runtime/platform_constraints.txt -r requirements/vision_gpu.txt
fi
# Optional CPU line extraction dependency. No custom CUDA/gsplat build.
if ! "$PY" -c 'import pytlsd' >/dev/null 2>&1; then
  timeout --kill-after=5s 120s "$PY" -m pip install --only-binary=:all: --timeout 20 --retries 1 pytlsd==0.0.2 || echo 'DeepLSD optional dependency unavailable; OpenCV LSD fallback will be recorded.'
fi
if [[ -n "$REUSE" ]]; then
  "$PY" scripts/reuse_models.py "$REUSE"
fi
"$PY" - <<'PY'
import json,torch,torchvision,sys
from pathlib import Path
old=json.loads(Path('.runtime/platform_before.json').read_text())
assert old==dict(python=sys.version,torch=torch.__version__,torchvision=torchvision.__version__),'Platform changed unexpectedly'
print('Platform Python/Torch/torchvision preserved. No training or CUDA compilation.')
PY
echo 'Setup complete. If model weights are missing, run: bash download_models.sh'
echo 'Then: bash run_test.sh   OR   bash run_all.sh'
