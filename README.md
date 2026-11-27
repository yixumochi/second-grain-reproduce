# Second Grain

## 1. Project overview

Second Grain follows reclaimed timber from seller photographs to a saved allocation and a preliminary structural study. The public site presents that record. This repository holds the code that replays the allocation and screens photographs.

[![A timber shelter with a cutaway frame, weathered cladding, and a slatted roof](https://yixumochi.github.io/second-grain-timber/showcase/assets/narrative/allocation-shelter-cover.webp)](https://yixumochi.github.io/second-grain-timber/showcase/)

### Quick Start

[Open the research site](#2-published-record) · [Replay the allocation](#offline-allocation) · [Screen three specimens](#photograph-screening) · [Run the public example](#6-reproduction)

[Open the project website](https://yixumochi.github.io/second-grain-timber/showcase/) · [Material AI](https://yixumochi.github.io/second-grain-timber/showcase/#material-workflow) · [Design Agent](https://yixumochi.github.io/second-grain-timber/showcase/#design-workflow) · [Case studies](https://yixumochi.github.io/second-grain-timber/showcase/#cases)

## 2. Published record

**Quick Start.** Open the site and use the chapter navigation. The pages show saved records. Opening them does not run SAM2, VGGT, or the allocator.

| Chapter | Where to start |
| --- | --- |
| Index | [Research overview](https://yixumochi.github.io/second-grain-timber/showcase/#overview) |
| Material AI | [Specimen photographs, masks, and point support](https://yixumochi.github.io/second-grain-timber/showcase/#material-workflow) |
| Design Agent | [Saved allocation and geometry](https://yixumochi.github.io/second-grain-timber/showcase/#design-workflow) |
| Case studies | [Individual cases](https://yixumochi.github.io/second-grain-timber/showcase/#cases) |

## 3. Research outputs

### Offline allocation

**Quick Start.** From a checkout, run `python baseline/run.py` and read `baseline/results/baseline/verification.json`. [Run it](#6-reproduction)

The baseline replays one saved backing revision from the inventory, allocation, member geometry, and assembly records stored in `baseline/case/`. It uses the Python standard library. A passing run reports 15 added members from 10 stock sources. Engineering approval stays `UNKNOWN`. The script does not launch Rhino, Grasshopper, Karamba, or a language model. [Baseline notes](baseline/README.md)

### Photograph screening

**Quick Start.** After the GPU setup in the reproduction guide, run `bash run_test.sh`. It screens listings 117692, 120235, and 111575. [Reproduction guide](docs/reproduction.md)

Those three photograph sets are already in `data/all/`. The route is SAM2 masks, VGGT geometry, line detection, a CPU surface estimate, and a conditional grade hypothesis. The saved audit records every formal grade as unknown. The full set of 762 listings and 2,161 images is not in this repository. [Methods and sources](METHODS_AND_SOURCES.md)

## 4. Reading order

Start on the site, then replay the allocation, then screen the three specimens. Use the full photograph batch only when you have the local archive and a CUDA GPU. [Published record](#2-published-record) · [Public example](#6-reproduction)

## 5. Repository layout

| Location | Contents |
| --- | --- |
| [baseline/](baseline/README.md) | Offline allocation replay, its saved inputs, and the verification result. |
| [src/](src/), [scripts/](scripts/), [vendor/](vendor/), [configs/](configs/) | Photograph screening, pinned SAM2, VGGT, and DeepLSD snapshots, and model checksums. |
| [data/all/](data/all/) | Photographs for listings 117692, 120235, and 111575. |
| [data/download_data.py](data/download_data.py) | Checker for the full photo archive. No public archive URL is set. |
| [docs/reproduction.md](docs/reproduction.md) | Setup, weights, the three-specimen run, and the full batch. |
| [licenses/](licenses/) | SAM2, VGGT, DeepLSD, and DiffCheck notices. |
| [audit/](audit/) | Saved dataset and CPU regression records. |

## 6. Reproduction

**Quick Start.** With Git and Python 3.10 or newer, clone the repository and replay the allocation. The example uses only the Python standard library.

```sh
git clone https://github.com/yixumochi/second-grain-reproduce.git
cd second-grain-reproduce
python baseline/run.py
```

A passing run writes `baseline/results/baseline/verification.json` and returns exit code 0. For the three-specimen GPU screen, model weights, and the unpublished full photograph set, see the [reproduction guide](docs/reproduction.md).
