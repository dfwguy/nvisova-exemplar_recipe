#!/usr/bin/env python3
"""Copy the tested Exemplar system bundle to EDC003 B300 nodes and restore it."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path('/cluster/OVA/Exemplar')
BUNDLE = ROOT / 'fleet-bundle-20260923-v3.tar'
RELEASE = '2026-09-23-v3'
LOG_DIR = ROOT / 'deploy-logs-20260923'
RESULTS = ROOT / 'fleet-deploy-results-20260923.json'
HOSTS = [f'od1-edc003-b300-{n:03d}' for n in range(1, 65) if n != 45]
LOCK = threading.Lock()


def run(args: list[str], *, input_text: str | None = None, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=timeout)


def ssh(host: str, command: str, *, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=8', host, 'bash', '-s'], input_text=command, timeout=timeout)


def deploy(host: str, digest: str) -> dict[str, object]:
    start = time.monotonic()
    log_path = LOG_DIR / f'{host}.log'
    chunks: list[str] = []
    try:
        preflight = ssh(host, '''set -euo pipefail
test "$(hostname -s)" = "''' + host + '''"
mountpoint -q /stn-disk
test "$(findmnt -n -o FSTYPE /stn-disk)" = ext4
test "$(nvidia-smi -L | grep -c '^GPU ')" = 8
install -d -m 0700 /stn-disk/exemplar/node-bootstrap/releases
''', timeout=30)
        chunks.append('PREFLIGHT\n' + preflight.stdout + preflight.stderr)
        if preflight.returncode:
            raise RuntimeError(f'preflight exit {preflight.returncode}')

        remote_tmp = '/stn-disk/exemplar/node-bootstrap/fleet-bundle-v3.tar.tmp'
        copy = run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    str(BUNDLE), f'{host}:{remote_tmp}'], timeout=180)
        chunks.append('COPY\n' + copy.stdout + copy.stderr)
        if copy.returncode:
            raise RuntimeError(f'copy exit {copy.returncode}')

        stage = ssh(host, f'''set -euo pipefail
base=/stn-disk/exemplar/node-bootstrap
release=$base/releases/{RELEASE}
test "$(sha256sum "$base/fleet-bundle-v3.tar.tmp" | cut -d' ' -f1)" = {digest}
if [[ ! -d "$release" ]]; then
  install -d -m 0700 "$release.tmp"
  tar -C "$release.tmp" -xf "$base/fleet-bundle-v3.tar.tmp"
  mv "$release.tmp" "$release"
fi
ln -sfn releases/{RELEASE}/restore-fleet.sh "$base/restore.sh"
rm -f "$base/fleet-bundle-v3.tar.tmp"
''', timeout=60)
        chunks.append('STAGE\n' + stage.stdout + stage.stderr)
        if stage.returncode:
            raise RuntimeError(f'stage exit {stage.returncode}')

        restore = ssh(host, '/stn-disk/exemplar/node-bootstrap/restore.sh --force\n', timeout=240)
        chunks.append('RESTORE\n' + restore.stdout + restore.stderr)
        if restore.returncode:
            raise RuntimeError(f'restore exit {restore.returncode}')

        verify = ssh(host, '''set -euo pipefail
systemctl is-active --quiet slurmd
systemctl is-active --quiet munge
test "$(id -u nvidia-ssh)" = 1001
test "$(id -u slurm)" = 64030
test "$(enroot version)" = 4.2.1
test -x /usr/local/bin/python3.12
test -f /etc/slurm/plugstack.conf.d/pyxis.conf
test "$(readlink -f /cluster/OVA/Exemplar)" = /stn-disk/exemplar/OVA/Exemplar
test "$(grep -c '^NodeName=' /etc/slurm/slurm.conf)" = 64
test -f /stn-disk/exemplar/node-bootstrap/last-restored-boot-id
echo verified
''', timeout=30)
        chunks.append('VERIFY\n' + verify.stdout + verify.stderr)
        if verify.returncode:
            raise RuntimeError(f'verify exit {verify.returncode}')
        return {'host': host, 'status': 'ok', 'seconds': round(time.monotonic() - start, 1)}
    except Exception as exc:
        chunks.append(f'ERROR\n{exc}\n')
        return {'host': host, 'status': 'error', 'error': str(exc),
                'seconds': round(time.monotonic() - start, 1)}
    finally:
        log_path.write_text('\n'.join(chunks))
        log_path.chmod(0o600)


def main() -> int:
    LOG_DIR.mkdir(mode=0o700, exist_ok=True)
    expected = (ROOT / 'fleet-bundle-20260923-v3.tar.sha256').read_text().split()[0]
    actual = hashlib.file_digest(BUNDLE.open('rb'), 'sha256').hexdigest()
    if expected != actual:
        raise SystemExit('local bundle SHA-256 mismatch')

    selected = set(sys.argv[1:]) if len(sys.argv) > 1 else set(HOSTS)
    hosts = [h for h in HOSTS if h in selected]
    if not hosts:
        raise SystemExit('no matching hosts')
    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(deploy, host, expected): host for host in hosts}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            with LOCK:
                results.append(result)
                RESULTS.write_text(json.dumps(sorted(results, key=lambda r: str(r['host'])), indent=2) + '\n')
                RESULTS.chmod(0o600)
                print(f"{result['host']} {result['status']} {result['seconds']}s",
                      result.get('error', ''), flush=True)
    return 0 if all(r['status'] == 'ok' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
