#!/usr/bin/env python3
"""Link local Exemplar .log/.out/.err evidence into the requested central log tree."""
import json
import os
from pathlib import Path

SOURCE = Path('/cluster/OVA/Exemplar')
DEST = Path('/cluster/OVA/exemplar/logs')
SUFFIXES = {'.log', '.out', '.err'}
DEST.mkdir(parents=True, exist_ok=True)
count = 0
bytes_total = 0
for src in SOURCE.rglob('*'):
    if not src.is_file() or src.suffix not in SUFFIXES:
        continue
    rel = src.relative_to(SOURCE)
    dst = DEST / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if not os.path.samefile(src, dst):
            raise RuntimeError(f'central log differs from source: {dst}')
    else:
        os.link(src, dst)
    count += 1
    bytes_total += src.stat().st_size

for meta_path in (SOURCE / 'jobs').glob('job*.json'):
    meta = json.loads(meta_path.read_text())
    old = Path(meta['log_path'])
    if old.is_relative_to(SOURCE) and old.suffix in SUFFIXES:
        new = DEST / old.relative_to(SOURCE)
        if not new.is_file() or not os.path.samefile(old, new):
            raise RuntimeError(f'archived job log missing: {new}')
        meta['log_path'] = str(new)
        meta_path.write_text(json.dumps(meta, indent=2) + '\n')

print(json.dumps({'central_log_root':str(DEST),'files':count,'logical_bytes':bytes_total},indent=2))
