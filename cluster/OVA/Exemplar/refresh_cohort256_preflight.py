#!/usr/bin/env python3
"""Refresh approval only after a new full-cohort all-rail diagnostic passes."""
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys

from nccl_runtime_gate import RuntimeGate
import run_b300_suite_256 as suite


def main():
    path = Path(sys.argv[1])
    nodes_file = Path(sys.argv[2])
    data = json.loads(path.read_text())
    nodes = suite.load_nodes(nodes_file)
    if sorted(data['nodes']) != nodes or not data.get('ready'):
        raise RuntimeError('approval revoked or cohort changed; manual diagnosis required')
    suite.NODES = nodes
    suite.NODES_FILE = nodes_file
    suite.configure_hcas(data)
    suite.verify_master_ip()
    ok, note = suite.all_nodes_idle()
    if not ok:
        raise RuntimeError(note)
    suite.check_hca_eligibility()
    suite.check_psu_health()
    logs = suite.LOGROOT / ('nccl-cohort256-refresh-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    data.update(ready=False, blocked_reasons=['Full-cohort preflight refresh in progress'])
    suite.atomic_json(path, data)
    result = subprocess.run([sys.executable, suite.ROOT / 'launch-cohort256-preflight-20261007.py', logs], timeout=900)
    gate = RuntimeGate(nodes, data['hca_names'])
    files = list(logs.glob('*/*.log'))
    markers = {kind: set() for kind in ('START', 'ALLREDUCE_PASS', 'P2P_PASS')}
    for file in files:
        content = file.read_text(errors='replace')
        for line in content.splitlines():
            gate.feed(line)
        for kind, ranks in markers.items():
            ranks.update(int(x) for x in re.findall(r'COHORT_' + kind + r' rank=(\d+)', content))
    launcher = json.loads((logs / 'exit.json').read_text())
    runtime = gate.summary()
    passed = result.returncode == 0 and launcher['exit_code'] == 0 and len(files) == 256 \
        and set(launcher['fetch_status']) == set(nodes) and all(v == 0 for v in launcher['fetch_status'].values()) \
        and runtime['passed'] and all(ranks == set(range(256)) for ranks in markers.values())
    report = {'checked_utc': suite.utc(), 'status': 'PASS' if passed else 'FAIL',
              'files': len(files), 'markers': {k: len(v) for k, v in markers.items()},
              'runtime_gate': runtime, 'launcher': launcher}
    suite.atomic_json(logs / 'validation.json', report)
    if not passed:
        raise RuntimeError(f'Full-cohort all-rail preflight failed: {logs}')
    data.update(ready=True, checked_utc=report['checked_utc'], blocked_reasons=[],
                all_rail_canary_pass=True, rendezvous_verified=True,
                qualification_status='Fresh passing 256-GPU diagnostic; training qualification separate')
    data['all_rail_validation'] = {'status': 'PASS', 'node_count': 32, 'gpu_count': 256,
                                  'hca_count': 32, 'evidence_path': str(logs / 'validation.json'),
                                  'runtime_gate': runtime, 'scope': '1MiB/16MiB all-reduce; 1MiB P2P offsets1/9/65/129'}
    suite.atomic_json(path, data)
    suite.load_fabric_preflight(path, nodes)
    print(f'Fresh all-rail approval: {logs}', flush=True)


if __name__ == '__main__':
    main()
