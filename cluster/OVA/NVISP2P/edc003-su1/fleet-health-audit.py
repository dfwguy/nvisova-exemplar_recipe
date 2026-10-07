#!/usr/bin/env python3
"""Read-only EDC003 NVIS P2P health audit over the approved 64-node roster."""
import concurrent.futures
import datetime
import json
import pathlib
import subprocess
import sys

BASE = pathlib.Path('/cluster/OVA/NVISP2P/edc003-su1')
ROSTER = pathlib.Path('/cluster/OVA/Exemplar/fleet-64node-smoke-hosts.txt')
STATE = BASE / 'state'
EXPECTED = {
    'nvidia+nemo+26.04.01.sqsh': (36649082880, '270342a31e1727511f1b5bd923f4bee6fdb886fc0f42d371583aed012d83f604'),
    'nvidia+nemo+26.06.01.sqsh': (29557919744, 'e34c7a5bf2c64d80e161d026bebe083512a93491f33d9e1bf06836e99629ac1f'),
}
REMOTE = r'''set -u
base=/stn-disk/exemplar/nvis-p2p
printf 'host\t%s\n' "$(hostname -s)"
printf 'boot_id\t%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
printf 'disk\t%s\n' "$(mountpoint -q /stn-disk && echo mounted || echo missing)"
printf 'peer\t%s\n' "$(systemctl is-active nvis-p2p-peer.service 2>/dev/null || true)"
printf 'sync_timer\t%s\n' "$(systemctl is-active nvis-p2p-catalog-sync.timer 2>/dev/null || true)"
printf 'boot_container\t%s\n' "$(docker inspect nvis-p2p-exemplar-boot --format '{{.State.Running}}:{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null || true)"
printf 'restore_boot_id\t%s\n' "$(cat /stn-disk/exemplar/node-bootstrap/last-restored-boot-id 2>/dev/null || true)"
printf 'munge\t%s\n' "$(systemctl is-active munge.service 2>/dev/null || true)"
printf 'slurmd\t%s\n' "$(systemctl is-active slurmd.service 2>/dev/null || true)"
printf 'enroot\t%s\n' "$(enroot version 2>/dev/null || true)"
printf 'pyxis\t%s\n' "$(test -f /etc/slurm/plugstack.conf.d/pyxis.conf && echo present || echo missing)"
printf 'exemplar_link\t%s\n' "$(readlink -f /cluster/OVA/Exemplar 2>/dev/null || true)"
for name in nvidia+nemo+26.04.01.sqsh nvidia+nemo+26.06.01.sqsh; do
  image=/stn-disk/exemplar/OVA/Exemplar/images/$name
  receipt=$base/receipts/$name.sha256
  printf 'size:%s\t%s\n' "$name" "$(stat -c %s "$image" 2>/dev/null || true)"
  printf 'receipt:%s\t%s\n' "$name" "$(head -n 1 "$receipt" 2>/dev/null || true)"
done
'''


def audit(host):
    proc = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
         '-o', 'ConnectTimeout=6', f'root@{host}', 'bash', '-s'],
        input=REMOTE, text=True, capture_output=True, timeout=25,
    )
    if proc.returncode:
        return {'host': host, 'healthy': False, 'error': proc.stderr[-500:] or f'ssh rc={proc.returncode}'}
    fields = {}
    for line in proc.stdout.splitlines():
        key, sep, value = line.partition('\t')
        if sep:
            fields[key] = value
    issues = []
    if fields.get('host') != host:
        issues.append('hostname')
    if not fields.get('boot_id') or fields.get('boot_id') != fields.get('restore_boot_id'):
        issues.append('root_restore')
    for key, good in [('disk', 'mounted'), ('peer', 'active'),
                      ('sync_timer', 'active'), ('boot_container', 'true:always'),
                      ('munge', 'active'), ('slurmd', 'active'),
                      ('enroot', '4.2.1'), ('pyxis', 'present'),
                      ('exemplar_link', '/stn-disk/exemplar/OVA/Exemplar')]:
        if fields.get(key) != good:
            issues.append(key)
    for name, (size, digest) in EXPECTED.items():
        path = f'/stn-disk/exemplar/OVA/Exemplar/images/{name}'
        if fields.get(f'size:{name}') != str(size):
            issues.append(f'image_size:{name}')
        if fields.get(f'receipt:{name}') != f'{digest}  {path}':
            issues.append(f'receipt:{name}')
    return {'host': host, 'healthy': not issues, 'issues': issues,
            'boot_id': fields.get('boot_id'), 'peer': fields.get('peer'),
            'sync_timer': fields.get('sync_timer'),
            'boot_container': fields.get('boot_container')}


def main():
    hosts = ROSTER.read_text().splitlines()
    if len(hosts) != 64 or len(set(hosts)) != 64 or any(
        not h.startswith('od1-edc003-b300-') for h in hosts
    ):
        raise SystemExit('invalid approved 64-node roster')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records = sorted(pool.map(audit, hosts), key=lambda r: r['host'])
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report = {'timestamp_utc': timestamp, 'hosts': len(records),
              'healthy': sum(bool(r['healthy']) for r in records),
              'records': records}
    STATE.mkdir(exist_ok=True)
    path = STATE / 'fleet-health-latest.json'
    tmp = STATE / 'fleet-health-latest.json.tmp'
    tmp.write_text(json.dumps(report, indent=2) + '\n')
    tmp.replace(path)
    print(f"NVIS_P2P_HEALTH hosts={report['hosts']} healthy={report['healthy']} report={path}")
    return 0 if report['healthy'] == 64 else 1


if __name__ == '__main__':
    sys.exit(main())
