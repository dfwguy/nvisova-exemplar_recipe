#!/usr/bin/env python3
"""Package the verified NVIS P2P AMD64 client for EDC003 SU1."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import pathlib
import tarfile

SITE = pathlib.Path(__file__).resolve().parent
ROOT = SITE.parent
SOURCE = ROOT / "NVIS-P2P-2.5.1-nvis.2"
NAME = "NVIS-P2P-2.5.1-nvis.2-EDC003-SU1-B300-x86_64-client"
OUTPUT = ROOT / f"{NAME}.tar.gz"

FILES = {
    "bin/dfdaemon": SOURCE / "dist/client-amd64-v1.4.9/dfdaemon",
    "bin/dfget": SOURCE / "dist/client-amd64-v1.4.9/dfget",
    "bin/dfstore": SOURCE / "dist/client-amd64-v1.4.9/dfstore",
    "bin/dfstore-sync-catalog.sh": SOURCE / "scripts/dfstore-sync-catalog.sh",
    "catalog/images.json": SITE / "catalog/images.json",
    "catalog/images.tsv": SITE / "catalog/images.tsv",
    "systemd/nvis-p2p-peer.service": SITE / "systemd/nvis-p2p-peer.service",
    "systemd/nvis-p2p-catalog-sync.service": SITE / "systemd/nvis-p2p-catalog-sync.service",
    "systemd/nvis-p2p-catalog-sync.timer": SITE / "systemd/nvis-p2p-catalog-sync.timer",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    catalog = json.loads((SITE / "catalog/images.json").read_text())
    assert catalog["catalog_name"].startswith("NVIS-P2P")
    assert len(catalog["images"]) == 2
    expected = (SITE / "catalog/images.tsv").read_text().splitlines()
    assert len(expected) == 3
    for row, image in zip(expected[1:], catalog["images"], strict=True):
        fields = row.split("\t")
        assert fields == [str(image[key]) for key in ("order", "name", "filename", "bytes", "sha256")]

    data = {name: path.read_bytes() for name, path in FILES.items()}
    manifest = "".join(f"{digest(content)}  {name}\n" for name, content in sorted(data.items()))
    data["SHA256SUMS"] = manifest.encode()
    data["BUILD.json"] = json.dumps({
        "brand": "NVIS-P2P",
        "release": "2.5.1-nvis.2",
        "site": "EDC003 SU1 B300",
        "architecture": "x86_64",
        "page_size": 4096,
        "dragonfly_client": "1.4.9",
        "catalog_images": 2,
        "scope": "client package; control plane and credentials are separate",
    }, indent=2, sort_keys=True).encode() + b"\n"

    with OUTPUT.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w|") as archive:
            for name, content in sorted(data.items()):
                info = tarfile.TarInfo(f"{NAME}/{name}")
                info.size = len(content)
                info.mode = 0o755 if name.startswith("bin/") else 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
    print(f"{OUTPUT} sha256={digest(OUTPUT.read_bytes())}")


if __name__ == "__main__":
    main()
