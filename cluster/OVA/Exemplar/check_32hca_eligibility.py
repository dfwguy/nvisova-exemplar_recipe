#!/usr/bin/env python3
"""Read-only, parallel host check for the 32 intended B300 RoCE ports.

This checks host-local link and GID prerequisites. It does not certify fabric
forwarding, NCCL P2P, or readiness to launch a training job.
"""

import argparse
import concurrent.futures
import datetime as dt
import ipaddress
import json
import pathlib
import re
import subprocess
import sys


HCA_IDS = (*range(0, 12), *range(14, 22), *range(26, 30), *range(32, 40))
HCAS = [f"mlx5_{i}" for i in HCA_IDS]
APPROVED = [f"od1-edc003-b300-{i:03d}" for i in range(1, 65)]
REMOTE = r'''
import json
import pathlib
import subprocess

root = pathlib.Path('/sys/class/infiniband')
out = {}
try:
    ip_data = json.loads(subprocess.check_output(
        ['/sbin/ip', '-j', '-4', 'addr', 'show'], text=True, timeout=5))
except (OSError, subprocess.CalledProcessError):
    ip_data = json.loads(subprocess.check_output(
        ['ip', '-j', '-4', 'addr', 'show'], text=True, timeout=5))
addresses = {item['ifname']: [addr['local'] for addr in item.get('addr_info', [])
                              if addr.get('family') == 'inet'] for item in ip_data}
for i in [*range(0, 12), *range(14, 22), *range(26, 30), *range(32, 40)]:
    hca = f'mlx5_{i}'
    base = root / hca / 'ports' / '1'
    def read(path):
        try:
            return (base / path).read_text().strip()
        except OSError:
            return None
    netdev = read('gid_attrs/ndevs/3')
    try:
        carrier = (pathlib.Path('/sys/class/net') / netdev / 'carrier').read_text().strip() if netdev else None
    except OSError:
        carrier = None
    out[hca] = {'state': read('state'), 'phys_state': read('phys_state'),
                'rate': read('rate'), 'gid3_type': read('gid_attrs/types/3'),
                'gid3': read('gids/3'), 'gid3_netdev': netdev,
                'netdev_carrier': carrier, 'netdev_ipv4': addresses.get(netdev, [])}
print(json.dumps(out))
'''


def load_nodes(args):
    if args.all64:
        return APPROVED
    lines = args.nodes_file.read_text().splitlines()
    nodes = [part.strip() for line in lines for part in line.split('#', 1)[0].split(',') if part.strip()]
    if not nodes or len(nodes) != len(set(nodes)):
        raise ValueError('nodes file must contain unique, nonempty node names')
    bad = sorted(set(nodes) - set(APPROVED))
    if bad:
        raise ValueError(f'unapproved node names: {bad}')
    return nodes


def assess(hca, record):
    problems = []
    if record.get('state') != '4: ACTIVE':
        problems.append(f"state={record.get('state')}")
    if record.get('phys_state') != '5: LinkUp':
        problems.append(f"phys_state={record.get('phys_state')}")
    if record.get('rate') != '200 Gb/sec (2X NDR)':
        problems.append(f"rate={record.get('rate')}")
    if record.get('gid3_type') != 'RoCE v2':
        problems.append(f"gid3_type={record.get('gid3_type')}")
    netdev = record.get('gid3_netdev')
    if not netdev or not re.fullmatch(r'[a-zA-Z0-9_.-]+', netdev):
        problems.append(f'gid3_netdev={netdev}')
    if record.get('netdev_carrier') != '1':
        problems.append(f"netdev_carrier={record.get('netdev_carrier')}")
    try:
        ip = ipaddress.IPv6Address(record['gid3']).ipv4_mapped
        if ip is None or ip.is_unspecified or ip.is_loopback or ip.is_link_local:
            problems.append(f"gid3_not_valid_ipv4_mapped={record.get('gid3')}")
        elif str(ip) not in record.get('netdev_ipv4', []):
            problems.append(f'gid3_ipv4_not_on_netdev={ip}')
    except (ValueError, KeyError, TypeError):
        problems.append(f"gid3_invalid={record.get('gid3')}")
    return problems


def check(node, timeout):
    cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
           '-o', 'StrictHostKeyChecking=accept-new', node, 'python3 -']
    try:
        proc = subprocess.run(cmd, input=REMOTE, capture_output=True, text=True, timeout=timeout)
        if proc.returncode:
            return {'node': node, 'eligible': False, 'error': f'ssh exit {proc.returncode}: {proc.stderr.strip()[:300]}'}
        data = json.loads(proc.stdout)
        failures = {hca: assess(hca, data.get(hca, {})) for hca in HCAS}
        failures = {hca: issues for hca, issues in failures.items() if issues}
        return {'node': node, 'eligible': not failures, 'passing_hcas': 32 - len(failures),
                'failures': failures, 'ports': data}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        return {'node': node, 'eligible': False, 'error': str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--all64', action='store_true')
    scope.add_argument('--nodes-file', type=pathlib.Path)
    parser.add_argument('--json-out', type=pathlib.Path)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--timeout', type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.workers <= 32 or not 6 <= args.timeout <= 60:
        parser.error('workers must be 1–32 and timeout 6–60 seconds')
    try:
        nodes = load_nodes(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda node: check(node, args.timeout), nodes))
    report = {'checked_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'required_hcas': HCAS, 'required_gid_index': 3,
              'eligibility_scope': 'host-local HCA/GID/netdev prerequisites only',
              'eligible_nodes': [r['node'] for r in results if r['eligible']],
              'ineligible_nodes': [r['node'] for r in results if not r['eligible']],
              'nodes': {r['node']: r for r in results}}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        temp = args.json_out.with_name(args.json_out.name + '.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(args.json_out)
    print(f"eligible {len(report['eligible_nodes'])}/{len(nodes)}; ineligible {len(report['ineligible_nodes'])}")
    for row in results:
        if row['eligible']:
            print(f"ELIGIBLE {row['node']} 32/32")
        else:
            print(f"INELIGIBLE {row['node']} {row.get('error') or row.get('failures')}")
    return 0 if not report['ineligible_nodes'] else 1


if __name__ == '__main__':
    sys.exit(main())
