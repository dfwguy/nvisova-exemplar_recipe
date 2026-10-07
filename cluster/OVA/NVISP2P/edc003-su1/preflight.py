#!/usr/bin/env python3
"""Read-only NVIS-P2P EDC003 SU1 baseline; never discovers targets."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
ROSTER = Path('/cluster/OVA/Exemplar/fleet-64node-smoke-hosts.txt')
EXPECTED = {
    'arch': 'x86_64',
    'page': '4096',
    'stn': 'yes',
    'docker': 'active',
    'docker_root': '/stn-disk/docker',
    'service_uid': '1001',
    'image1_bytes': '36649082880',
    'image2_bytes': '29557919744',
}
REMOTE = '''printf '%s\\n' \
"arch=$(uname -m)" \
"page=$(getconf PAGESIZE)" \
"stn=$(mountpoint -q /stn-disk && echo yes || echo no)" \
"docker=$(systemctl is-active docker 2>/dev/null)" \
"docker_root=$(docker info --format {{.DockerRootDir}} 2>/dev/null)" \
"service_uid=$(id -u nvidia-ssh 2>/dev/null)" \
"image1_bytes=$(stat -c %s /stn-disk/exemplar/OVA/Exemplar/images/nvidia+nemo+26.04.01.sqsh 2>/dev/null)" \
"image2_bytes=$(stat -c %s /stn-disk/exemplar/OVA/Exemplar/images/nvidia+nemo+26.06.01.sqsh 2>/dev/null)"'''


def check(node: str) -> dict:
    try:
        result = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
             '-o', 'StrictHostKeyChecking=yes', f'root@{node}', REMOTE],
            capture_output=True, text=True, timeout=12, check=False,
        )
    except subprocess.TimeoutExpired:
        return {'node': node, 'status': 'deferred', 'reason': 'ssh_timeout'}
    if result.returncode:
        reason = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'ssh_failed'
        return {'node': node, 'status': 'deferred', 'reason': reason}
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    mismatch = {key: {'expected': value, 'actual': fields.get(key)}
                for key, value in EXPECTED.items() if fields.get(key) != value}
    return {'node': node, 'status': 'eligible' if not mismatch else 'deferred',
            'fields': fields, 'mismatch': mismatch}


def main() -> int:
    nodes = [line.strip() for line in ROSTER.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(nodes) != 64 or len(set(nodes)) != 64 or any(
        not re.fullmatch(r'od1-edc003-b300-\d{3}', node) for node in nodes
    ):
        raise SystemExit('invalid approved 64-node inventory')
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = sorted((future.result() for future in as_completed(
            [pool.submit(check, node) for node in nodes])), key=lambda row: row['node'])
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'inventory': str(ROSTER), 'expected': EXPECTED, 'nodes': rows,
              'eligible': sum(row['status'] == 'eligible' for row in rows),
              'deferred': sum(row['status'] == 'deferred' for row in rows)}
    state = ROOT / 'state'
    state.mkdir(exist_ok=True)
    path = state / 'baseline-preflight.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(f"eligible={report['eligible']} deferred={report['deferred']} report={path}")
    for row in rows:
        if row['status'] != 'eligible':
            print(f"deferred {row['node']}: {row.get('reason', row.get('mismatch'))}")
    return 0 if report['deferred'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
