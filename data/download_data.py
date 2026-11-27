#!/usr/bin/env python3
"""Download the full photo archive into data/all and verify it.

The seller photographs are not licensed for public redistribution, so
ZENODO_URL stays empty and a normal run stops before any transfer.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ALL = ROOT / "data" / "all"
SUMS = Path(__file__).resolve().parent / "SHA256SUMS"
ARCHIVE_NAME = "second-grain-photos.zip"

# Set this to a Zenodo direct-download URL only after the photographs may be redistributed.
ZENODO_URL = ""

EXPECTED_LISTINGS = 762
EXPECTED_IMAGES = 2161
EXPECTED_IMAGE_BYTES = 8270554923
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha() -> str:
    if not SUMS.is_file():
        raise SystemExit(f"Missing {SUMS}")
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        if name.strip() == ARCHIVE_NAME:
            return digest
    raise SystemExit(f"{ARCHIVE_NAME} is missing from {SUMS.name}")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "second-grain-reproduce"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        status = getattr(response, "status", 200)
        append = offset > 0 and status == 206
        with partial.open("ab" if append else "wb") as out:
            if offset and not append:
                out.seek(0)
                out.truncate()
            while chunk := response.read(4 * 1024 * 1024):
                out.write(chunk)
    partial.replace(dest)


def safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = []
    for info in archive.infolist():
        parts = Path(info.filename).parts
        if info.filename.startswith(("/", "\\")) or ".." in parts:
            raise SystemExit(f"Refusing unsafe zip entry: {info.filename}")
        members.append(info)
    return members


def verify_zip(archive: zipfile.ZipFile) -> None:
    listings = set()
    images = 0
    total = 0
    for info in safe_members(archive):
        if info.is_dir():
            continue
        path = Path(info.filename)
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if len(path.parts) < 2:
            raise SystemExit(f"Image is not inside a listing directory: {info.filename}")
        listings.add(path.parts[0])
        images += 1
        total += info.file_size
    if len(listings) != EXPECTED_LISTINGS or images != EXPECTED_IMAGES or total != EXPECTED_IMAGE_BYTES:
        raise SystemExit(
            "Photo archive check failed: "
            f"listings={len(listings)} images={images} bytes={total}. "
            f"Expected {EXPECTED_LISTINGS} listings, {EXPECTED_IMAGES} images, "
            f"{EXPECTED_IMAGE_BYTES} bytes."
        )


def extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as handle:
        verify_zip(handle)
        handle.extractall(dest)


def verify_tree(root: Path) -> None:
    listings = [path for path in root.iterdir() if path.is_dir()]
    images = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    total = sum(path.stat().st_size for path in images)
    if len(listings) != EXPECTED_LISTINGS or len(images) != EXPECTED_IMAGES or total != EXPECTED_IMAGE_BYTES:
        raise SystemExit(
            "Extracted photo check failed: "
            f"listings={len(listings)} images={len(images)} bytes={total}. "
            f"Expected {EXPECTED_LISTINGS} listings, {EXPECTED_IMAGES} images, "
            f"{EXPECTED_IMAGE_BYTES} bytes."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify the full photo archive.")
    parser.add_argument("--archive", type=Path, help="Verify and extract a local zip instead of downloading.")
    parser.add_argument("--check", action="store_true", help="Verify the archive without extracting it.")
    args = parser.parse_args()

    if args.archive is None and not ZENODO_URL:
        print(
            "The full photo archive is not published. "
            "METHODS_AND_SOURCES.md records that these seller photographs "
            "are not licensed for public redistribution, so there is no Zenodo file yet. "
            "data/all already contains the three specimens used by run_test.sh.",
            file=sys.stderr,
        )
        return 2

    digest = expected_sha()
    if args.archive is not None:
        archive = args.archive
    else:
        archive = ROOT / "data" / ARCHIVE_NAME
        print(f"Downloading {ZENODO_URL}", flush=True)
        download(ZENODO_URL, archive)

    got = sha256_file(archive)
    if got != digest:
        raise SystemExit(f"SHA-256 mismatch for {archive.name}: {got} != {digest}")

    with zipfile.ZipFile(archive) as handle:
        verify_zip(handle)
    if args.check:
        print(
            f"Verified archive {archive}: {EXPECTED_IMAGES} images, "
            f"{EXPECTED_LISTINGS} listings, SHA-256 {got}"
        )
        return 0

    extract_zip(archive, DATA_ALL)
    verify_tree(DATA_ALL)
    print(f"Verified {EXPECTED_IMAGES} images in {EXPECTED_LISTINGS} listings at {DATA_ALL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
