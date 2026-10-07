#!/usr/bin/env python3
"""Package the Exemplar fabric investigations for an internal support handoff."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tarfile
from pathlib import Path


ROOT = Path('/cluster/OVA/Exemplar')
LOGS = Path('/cluster/OVA/exemplar/logs')
NCCL = Path('/home/nvidia-ssh/OVA/NCCL2312')
SITE = Path('/cluster/OVA/NVISP2P/installed/releases/2.5.1-nvis.2-edc003-su1-b300-x86_64/site/console/static/downloads')
NAME = 'exemplar-fabric-investigation-20260926-v2.tar.gz'


def add_tree(found: dict[str, Path], base: Path, prefix: str, files) -> None:
    for path in files:
        if path.is_file() and not path.is_symlink():
            found[f'{prefix}/{path.relative_to(base).as_posix()}'] = path


def gather() -> dict[str, Path]:
    found: dict[str, Path] = {}
    add_tree(found, ROOT, 'exemplar', ROOT.glob('*.md'))
    add_tree(found, ROOT, 'exemplar', ROOT.glob('*.json'))
    add_tree(found, ROOT, 'exemplar', ROOT.glob('*.csv'))
    add_tree(found, ROOT, 'exemplar', ROOT.glob('*.txt'))
    for path in ROOT.glob('*'):
        if path.suffix in ('.py', '.sh') and any(word in path.name for word in
                ('nccl', 'fabric', 'audit', 'check_32hca', 'compare_p2p', 'run_b300_suite',
                 'stage_held_job', 'fix_rendezvous')):
            add_tree(found, ROOT, 'exemplar', [path])
    add_tree(found, ROOT, 'exemplar', (ROOT / 'jobs').glob('job*.json'))
    for logdir in sorted(LOGS.glob('job*-logs')):
        add_tree(found, LOGS, 'logs', logdir.glob('*.out'))
    add_tree(found, LOGS, 'logs', LOGS.glob('nccl*.log'))
    add_tree(found, LOGS, 'logs', LOGS.glob('nccl*.md'))
    add_tree(found, LOGS, 'logs', LOGS.glob('last-full-hca-submit.log'))
    add_tree(found, LOGS, 'logs', (LOGS / 'suite').glob('*'))
    add_tree(found, NCCL, 'nccl2312', [NCCL / 'RESULTS.md', NCCL / 'canary.cc', NCCL / 'run_canary.py'])
    add_tree(found, NCCL, 'nccl2312', (NCCL / 'logs').glob('*'))
    add_tree(found, Path('/home/nvidia-ssh'), 'continuity',
             [Path('/home/nvidia-ssh/EXEMPLAR_RUNS.md'), Path('/home/nvidia-ssh/EXEMPLAR_RUNS.json')])
    add_tree(found, Path('/home/nvidia-ssh/OVA'), 'references', [
        Path('/home/nvidia-ssh/OVA/STN B300 SPX P2P v1.3.xlsx'),
        Path('/home/nvidia-ssh/OVA/stn_b300_spx_p2p_v1.7-draft.xlsx'),
        Path('/home/nvidia-ssh/OVA/GB300-Exemplar-Validation-Report.pdf'),
        Path('/home/nvidia-ssh/OVA/GB300-Exemplar-Engagement-Runbook.pdf'),
    ])
    recipe = ROOT / 'install/llmb_repo'
    add_tree(found, recipe, 'recipe', [recipe / 'exemplar.yaml'])
    for directory in ('nemotron-h', 'kimi-k2', 'deepseek_v3/pretrain/megatron_bridge',
                      'gpt-oss/pretrain/megatron_bridge', 'llama3.1/pretrain/megatron_bridge',
                      'nemotron3', 'qwen3/pretrain'):
        for name in ('README.md', 'launch.sh', 'metadata.yaml'):
            add_tree(found, recipe, 'recipe', [recipe / directory / name])
    return dict(sorted(found.items()))


def add_bytes(tar: tarfile.TarFile, arcname: str, content: bytes) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(content)
    info.mode = 0o644
    info.mtime = int(dt.datetime.now(dt.timezone.utc).timestamp())
    tar.addfile(info, io.BytesIO(content))


def main() -> None:
    files = gather()
    if len(files) < 80:
        raise SystemExit(f'Unexpectedly small evidence set: {len(files)} files')
    SITE.mkdir(mode=0o755, parents=True, exist_ok=True)
    target = SITE / NAME
    temp = SITE / (NAME + '.tmp')
    intro = f'''# Exemplar B300 fabric investigation handoff

Captured: {dt.datetime.now(dt.timezone.utc).isoformat()}
Scope: EDC003 SU1, 64 B300 hosts; 32-node/256-GPU cohort investigation.
Archive contents: {len(files)} original files plus this index and SHA-256 manifest.

Start with `exemplar/fabric-32-subset-feasibility-20260926.md`,
`logs/nccl-four-hca-mapping-20260926.md`,
`exemplar/fabric-p03-p04-and-spine-handoff-20260926.md`,
`exemplar/port32-eligibility-20260926.md`,
`exemplar/fabric-first-hop-handoff-20260925.md`, and
`exemplar/p2p-v17-fabric-impact.md`.

All 2,048 intended host ports passed the local 32-HCA eligibility check.
The all-32-HCA GPU3-to-GPU1 canary showed 32 devices per rank and eight
merged groups of four, but failed on P02/P04 same-plane cross-leaf transport.
P03 bound ping passed 16/16; P04 passed 6/16. The P02/P04 spine CSV records
v1.7 design expectations, not observed LLDP/BGP state.
The 256-GPU suite was not launched.
Reports, probe outputs, full archived job stdout, scripts, recipe metadata,
P2P workbooks, and the separate NCCL 2.31.2 experiment are included.
No container image, NCCL wheel, credentials, or switch config is bundled.

NVIDIA references:
https://github.com/NVIDIA/exemplar-performance/blob/main/Exemplar_validation.md
https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html
'''
    checksums = []
    with tarfile.open(temp, 'w:gz', compresslevel=6, format=tarfile.PAX_FORMAT) as tar:
        add_bytes(tar, 'exemplar-fabric-investigation/README.md', intro.encode())
        for arcname, path in files.items():
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            member = 'exemplar-fabric-investigation/' + arcname
            tar.add(path, arcname=member, recursive=False, filter=lambda info: clean_info(info))
            checksums.append(f'{digest.hexdigest()}  {arcname}')
        add_bytes(tar, 'exemplar-fabric-investigation/MANIFEST.sha256',
                  ('\n'.join(checksums) + '\n').encode())
    temp.replace(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(json.dumps({'archive': str(target), 'files': len(files),
                      'bytes': target.stat().st_size, 'sha256': digest}, indent=2))


def clean_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ''
    info.gname = ''
    info.mode = 0o644
    return info


if __name__ == '__main__':
    main()
