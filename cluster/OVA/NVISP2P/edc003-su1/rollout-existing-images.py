#!/usr/bin/env python3
"""Install NVIS peers and adopt already-staged images without copying image data."""
import concurrent.futures
import fcntl
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path('/cluster/OVA/NVISP2P')
SITE = ROOT / 'edc003-su1'
ROSTER = pathlib.Path('/cluster/OVA/Exemplar/fleet-64node-smoke-hosts.txt')
PKG = ROOT / 'NVIS-P2P-2.5.1-nvis.2-EDC003-SU1-B300-x86_64-client.tar.gz'
RENDER = SITE / 'rendered-v2'
SCRIPT = SITE / 'install-peer-node.sh'
STATE = SITE / 'state'
TARGET = '/stn-disk/exemplar/OVA/Exemplar/images'
BASE = '/stn-disk/exemplar/nvis-p2p'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8']
SCP = ['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8']


def run(args, timeout=180):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'rc={p.returncode} {p.stderr.strip()[-500:]} {p.stdout.strip()[-500:]}')
    return p.stdout.strip()


def ssh(host, command, timeout=180):
    return run(SSH + [f'root@{host}', command], timeout)


def install(host):
    if host.endswith('-005'):
        return 'existing canary'
    remote = f'root@{host}:{BASE}/.incoming/'
    ssh(host, f'mountpoint -q /stn-disk && mkdir -p {BASE}/.incoming && chmod 0700 {BASE}/.incoming')
    for src in (PKG, RENDER / 'configs/peer.template.yaml', RENDER / 'secrets/dfstore-readonly.env', SCRIPT):
        run(SCP + [str(src), remote], 240)
    return ssh(host, f'bash {BASE}/.incoming/install-peer-node.sh', 180)


def adopt(host, filename, size, digest):
    path = f'{TARGET}/{filename}'
    receipt = f'{BASE}/receipts/{filename}.sha256'
    # Hash the existing file first. Never invoke dfstore export for adoption.
    command = (f'test "$(stat -c %s {path})" = {size} && '
               f'if grep -Fxq "{digest}  {path}" {receipt} 2>/dev/null; then '
               f'printf "ADOPTED %s receipt\\n" {filename}; exit 0; fi; '
               f'actual=$(sha256sum {path} | cut -d" " -f1) && '
               f'test "$actual" = {digest} && '
               f'printf "%s  %s\\n" "$actual" {path} > {receipt}.tmp && '
               f'chown nvidia-ssh:nvidia-ssh {receipt}.tmp && '
               f'mv {receipt}.tmp {receipt} && '
               f'printf "ADOPTED %s %s\\n" {filename} "$actual"')
    return ssh(host, command, 3600)


def fanout(hosts, action, label, records, workers=6):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(action, host): host for host in hosts}
        for future in concurrent.futures.as_completed(futures):
            host = futures[future]
            try:
                result = future.result()
                records[host][label] = {'status': 'ok', 'detail': result}
                print(f'{label} {host} OK {result}', flush=True)
            except Exception as exc:
                records[host][label] = {'status': 'failed', 'detail': str(exc)}
                print(f'{label} {host} FAILED {exc}', flush=True)
    write(records)


def write(records):
    dest = STATE / 'fleet-adoption-20260924.json'
    temp = dest.with_suffix('.json.tmp')
    temp.write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
    temp.replace(dest)


def main():
    STATE.mkdir(exist_ok=True)
    hosts = [line.strip() for line in ROSTER.read_text().splitlines() if line.strip()]
    assert len(hosts) == len(set(hosts)) == 64
    assert all(re.fullmatch(r'od1-edc003-b300-\d{3}', h) for h in hosts)
    images = []
    for line in (SITE / 'catalog/images.tsv').read_text().splitlines()[1:]:
        order, name, filename, size, digest = line.split('\t')
        assert re.fullmatch(r'[a-f0-9]{64}', digest)
        images.append((filename, size, digest))
    assert len(images) == 2
    records = {h: {} for h in hosts}
    lock = open(STATE / 'fleet-mutation.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fanout(hosts, install, 'peer', records)
    eligible = [h for h in hosts if records[h]['peer']['status'] == 'ok']
    for filename, size, digest in images:
        fanout(eligible, lambda h: adopt(h, filename, size, digest), filename, records)
    print('REPORT', STATE / 'fleet-adoption-20260924.json', flush=True)


if __name__ == '__main__':
    main()
