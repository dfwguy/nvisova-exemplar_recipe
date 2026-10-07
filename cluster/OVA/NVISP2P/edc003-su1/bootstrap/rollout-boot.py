#!/usr/bin/env python3
"""Stage and activate the persistent NVIS/Exemplar boot hook.

The fleet phase is intentionally separate from the canary. It must run only
after peer rollout ends, and it never reboots a node.
"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROSTER = pathlib.Path('/cluster/OVA/Exemplar/fleet-64node-smoke-hosts.txt')
STATE = HERE.parent / 'state'
CANARY = 'od1-edc003-b300-005'
REMOTE = '/stn-disk/exemplar/nvis-p2p/.incoming'
ARCHIVES = [
    'nvis-p2p-edc003-bootstrap-2.5.1-nvis.2.tar.gz',
    'nvis-p2p-exemplar-root-release-v4.tar.gz',
]
SCRIPTS = ['boot-activate.sh', 'stage-node-bootstrap.sh', 'install-node-bootstrap.sh']
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=6']
SCP = ['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=6']


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def call(args, *, timeout):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'command failed rc={result.returncode}: {args[0]}: '
                           f'{result.stderr[-1200:]} {result.stdout[-1200:]}')
    return result.stdout.strip()


def deploy(host):
    target = f'root@{host}'
    call(SSH + [target, 'mountpoint -q /stn-disk && mkdir -p '
          '/stn-disk/exemplar/nvis-p2p/.incoming'], timeout=20)
    # Reuse already staged archives if their exact hashes match. This also
    # avoids retransmitting the canary's 70 MB of boot artifacts.
    remote_hashes = call(SSH + [target, 'for x in '
        f'{" ".join(ARCHIVES)}; do '
        f'sha256sum {REMOTE}/$x 2>/dev/null || true; done'], timeout=20)
    present = {}
    for line in remote_hashes.splitlines():
        fields = line.split()
        if len(fields) == 2:
            present[pathlib.Path(fields[1]).name] = fields[0]
    for filename in ARCHIVES + SCRIPTS:
        path = HERE / filename
        if present.get(filename) == HASHES[filename]:
            continue
        call(SCP + [str(path), f'{target}:{REMOTE}/{filename}'], timeout=240)
    call(SSH + [target, f"printf '%s\\n' {HASHES[ARCHIVES[1]]} > "
          f'{REMOTE}/nvis-p2p-exemplar-root-release-v4.sha256; '
          f"printf '%s\\n' {HASHES['boot-activate.sh']} > "
          f'{REMOTE}/boot-activate.sha256; '
          f'bash {REMOTE}/stage-node-bootstrap.sh && '
          f'bash {REMOTE}/install-node-bootstrap.sh'], timeout=180)
    check = call(SSH + [target, 'docker inspect nvis-p2p-exemplar-boot '
          "--format '{{.State.Running}} {{.HostConfig.RestartPolicy.Name}}'; "
          'systemctl is-active nvis-p2p-peer.service '
          'nvis-p2p-catalog-sync.timer'], timeout=25)
    return {'host': host, 'status': 'ready', 'check': check}


def main():
    parser = argparse.ArgumentParser()
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument('--canary', action='store_true')
    phase.add_argument('--fleet', action='store_true')
    args = parser.parse_args()
    hosts = ROSTER.read_text().splitlines()
    if len(hosts) != 64 or len(set(hosts)) != 64 or CANARY not in hosts:
        raise SystemExit('approved 64-host roster is invalid')
    if any(not h.startswith('od1-edc003-b300-') for h in hosts):
        raise SystemExit('unexpected hostname in approved roster')
    selected = [CANARY] if args.canary else [h for h in hosts if h != CANARY]
    STATE.mkdir(exist_ok=True)
    if args.fleet:
        canary_report = STATE / 'boot-canary.jsonl'
        if not canary_report.is_file():
            raise SystemExit('boot canary report is missing')
        canary_records = [json.loads(line) for line in canary_report.read_text().splitlines()]
        if len(canary_records) != 1 or canary_records[0].get('host') != CANARY or canary_records[0].get('status') != 'ready':
            raise SystemExit('boot canary has not passed')
    mutation_lock = (STATE / 'fleet-mutation.lock').open('w')
    try:
        fcntl.flock(mutation_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('another NVIS fleet mutation is active')
    report = STATE / ('boot-canary.jsonl' if args.canary else 'boot-fleet.jsonl')
    failures = 0
    with report.open('w') as output:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1 if args.canary else 4) as pool:
            futures = {pool.submit(deploy, host): host for host in selected}
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    record = future.result()
                except Exception as exc:
                    failures += 1
                    record = {'host': host, 'status': 'failed', 'error': str(exc)}
                line = json.dumps(record, sort_keys=True)
                print(line, flush=True)
                output.write(line + '\n')
                output.flush()
    print(f'BOOT_ROLLOUT phase={"canary" if args.canary else "fleet"} '
          f'total={len(selected)} failed={failures} report={report}', flush=True)
    return 1 if failures else 0


HASHES = {name: sha256(HERE / name) for name in ARCHIVES + SCRIPTS}
if __name__ == '__main__':
    sys.exit(main())
