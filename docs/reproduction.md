# Reproduce Second Grain

The public repository contains the offline allocation baseline, the photograph-screening source, and three specimen photograph sets. The routes below state where each run starts and what it checks.

| Route | Input | Output and verified scope |
| --- | --- | --- |
| Replay the allocation | This checkout and Python 3.10 or newer | `baseline/results/baseline/verification.json`. A local run returned exit code 0, with 15 added members from 10 stock sources. Engineering approval remains `UNKNOWN`. |
| Screen three specimens | CUDA PyTorch, downloaded SAM2 and VGGT weights, and the three photograph sets in `data/all/` | Per-listing records under `outputs/`. Listings 117692, 120235, and 111575. |
| Screen the full set | The same GPU setup plus the local 762-listing archive | A new `outputs/` tree. The earlier 29 GB evidence bundle is not distributed. The 762-listing GPU pass was not recorded as a completed run. |

## Replay the allocation

From the repository root:

```sh
python baseline/run.py
```

Read `baseline/results/baseline/verification.json`. Exit code 0 means the offline checks passed. The baseline does not run Rhino, Grasshopper, Karamba, or a language model. [Baseline notes](../baseline/README.md)

## Install the screening environment

Install a CUDA build of PyTorch and torchvision from the official PyTorch index. Then:

```sh
pip install -r requirements.txt
bash setup.sh
```

`setup.sh` creates a local virtual environment and leaves the installed PyTorch unchanged. An existing environment can be reused by setting `TIMBER_REUSE_ROOT` to its checkout before running `setup.sh`.

## Download model weights

Weights are not in this repository. The script downloads the pinned SAM2.1 Hiera Tiny and VGGT-1B checkpoints, about 4.8 GiB, and checks the SHA-256 values in `configs/models.json`.

```sh
bash download_models.sh
```

If a file returns 401 or 403, accept the model terms on its official page and set `HF_TOKEN` in the shell. The token is not written into the repository. DeepLSD is optional. If its download fails, line detection uses OpenCV LSD and the run records that fallback.

Pinned revisions:

- SAM2 `2b90b9f5ceec907a1c18123530e92e794ad901a4`
- VGGT `a288dd0f14786c93483e45524328726ab7b1b4ce`
- DeepLSD `f7d9d6258c0cd25d4f6eea882853565403d289be`

`vendor/` holds the snapshots imported by the runner. `vendor_manifest.json` is checked before a batch starts.

## Screen three specimens

`data/all/117692`, `data/all/120235`, and `data/all/111575` are already in the repository.

```sh
bash run_test.sh
```

This needs a CUDA GPU. Allow several minutes and keep more than 8 GiB free. Finished listings are written under `outputs/` and are not committed.

## Full photographs

The full set is 762 listings and 2,161 images, 8,270,554,923 bytes. `METHODS_AND_SOURCES.md` states that the package does not grant a license to redistribute those seller photographs, so they are not on GitHub or Zenodo.

A local zip is at `E:\second-grain\photo-archive\second-grain-photos.zip` on the machine that packed this repository. Its SHA-256 is in `data/SHA256SUMS`. Check it without extracting:

```sh
python data/download_data.py --check --archive /path/to/second-grain-photos.zip
```

`python data/download_data.py` with no arguments stops, because no public URL is set. Omit `--check` to extract a verified zip into `data/all/`.

## Full batch

```sh
bash run_all.sh
```

Listings that already have a matching input, source, and config record are skipped. One listing failing does not stop the queue. The run stops when free disk drops below 8 GiB. A full pass can take many hours and can write tens of gigabytes under `outputs/`.

`QUEUE_*_README.md` and `PILOT_FIRST.md` are notes from an earlier machine-specific upload. They are not the entry point.

## Licenses

Third-party terms are in `licenses/`. SAM2 is Apache-2.0, DeepLSD is MIT, and the VGGT source snapshot uses the VGGT License. The DiffCheck GPL-3.0 notice is kept with the source record; this batch does not run DiffCheck. Review the VGGT model card before downloading weights. This repository does not relicense the seller photographs.
