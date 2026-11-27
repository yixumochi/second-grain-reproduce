# Second Grain reproduction

Screen reclaimed-timber photographs, then replay a saved allocation offline.

The screening route is original photographs, SAM2 masks, VGGT geometry, line detection, a CPU surface estimate, and a conditional grade hypothesis. It does not train a model. It does not claim that all 762 listings have been run on a GPU. A formal grade can remain unknown. `audit/dataset_qa.json` records `all_formal_grades_unknown: true`.

The published reading of the work is the site, not this repository:

https://yixumochi.github.io/second-grain-timber/

## Install

The CPU baseline needs Python 3.10 or newer and the standard library only.

The GPU screening path needs a CUDA build of PyTorch and torchvision, installed from the official PyTorch index for your machine. Then:

```bash
pip install -r requirements.txt
bash setup.sh
```

`setup.sh` creates a local virtual environment and does not change the installed PyTorch. Model weights are not part of that step.

## CPU baseline

This replay needs no download and no GPU. From `baseline/`:

```bash
cd baseline
python run.py
```

Read `baseline/results/baseline/verification.json`. An exit code of 0 means the offline checks passed. That is not a structural-capacity result: the baseline does not run Rhino, Grasshopper, Karamba, or a language model. Details are in `baseline/README.md`.

## Three specimens

`data/all/117692`, `data/all/120235`, and `data/all/111575` are already in this repository. After `setup.sh` and `download_models.sh`:

```bash
bash run_test.sh
```

This needs a CUDA GPU. The packaged script runs SAM2, VGGT, line detection, the surface estimate, and the grade hypothesis on these three listings only. Allow several minutes and keep more than 8 GiB free. A finished listing is written under `outputs/` and is not committed.

## Full photographs

The full set is 762 listings and 2,161 images, 8,270,554,923 bytes. It is not in this repository.

Those photographs are seller images from a dataset the project already held. `METHODS_AND_SOURCES.md` states that the package does not grant a license to redistribute them. They are therefore not uploaded to Zenodo or GitHub. `data/download_data.py` stops before transferring anything until a public archive URL exists.

The three specimens above are enough for `run_test.sh`.

## Model weights

Weights are not in this repository. `download_models.sh` fetches the pinned SAM2.1 Hiera Tiny and VGGT-1B checkpoints from their official URLs and checks the SHA-256 values in `configs/models.json`. Together they are about 4.8 GiB.

```bash
bash download_models.sh
```

If a file returns 401 or 403, accept the model terms on its official page and set `HF_TOKEN` in the shell. The token is not written into the repository. DeepLSD is optional. If its download fails, line detection falls back to OpenCV LSD and the run records that fallback.

Pinned code revisions, not copies of the upstream git histories, are:

- SAM2 `2b90b9f5ceec907a1c18123530e92e794ad901a4`
- VGGT `a288dd0f14786c93483e45524328726ab7b1b4ce`
- DeepLSD `f7d9d6258c0cd25d4f6eea882853565403d289be`

The small trees under `vendor/` are the snapshots this runner imports. `vendor_manifest.json` is checked before a batch starts.

## Full batch

```bash
bash run_all.sh
```

Listings that already have a matching input, source, and config record are skipped. One listing failing does not stop the queue. The run stops when free disk drops below 8 GiB. A full pass can take many hours and can write tens of gigabytes under `outputs/`.

The previously saved batch evidence, about 29 GB, is not distributed. Regenerate it with `run_all.sh`. The full 762-listing GPU pass was not recorded as a completed run on the machine that packed this code.

`QUEUE_*_README.md` and `PILOT_FIRST.md` are notes from an earlier machine-specific upload. They are not the entry point.

## Published record

The website shows saved research records. Opening it does not run SAM2, VGGT, or the allocator:

https://yixumochi.github.io/second-grain-timber/

## Licenses

Third-party terms are in `licenses/`: SAM2 is Apache-2.0, DeepLSD is MIT, and the VGGT source snapshot uses the VGGT License. DiffCheck's GPL-3.0 notice is kept because it was part of the source record; this batch does not run DiffCheck. Review the VGGT model card before downloading weights. The seller photographs are not relicensed by this repository.
