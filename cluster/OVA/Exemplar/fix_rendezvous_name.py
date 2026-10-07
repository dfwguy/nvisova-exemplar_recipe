#!/usr/bin/env python3
"""Add the verified job-41 rendezvous hostname to allocated node hosts files."""
import concurrent.futures
import json
import shlex
import subprocess
from pathlib import Path

code = '''from pathlib import Path
import re
p=Path('/etc/hosts')
content=p.read_text()
host='od1-edc003-b300-001'
ip='10.6.33.1'
for line in content.splitlines():
    fields=line.split('#',1)[0].split()
    if host in fields[1:]:
        if fields[0] != ip:
            raise SystemExit('conflicting host mapping: '+line)
        print('already-correct')
        break
else:
    with p.open('a') as out:
        out.write('\\n' if content and not content.endswith('\\n') else '')
        out.write(ip+' '+host+' # Exemplar Slurm rendezvous\\n')
    print('added')
'''
remote = 'sudo -n /usr/bin/python3 -c ' + shlex.quote(code) + ' && getent ahostsv4 od1-edc003-b300-001'

def fix(node):
    p = subprocess.run(['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config',
                        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                        '-o', 'ConnectTimeout=5', node, remote], capture_output=True,
                       text=True, timeout=20)
    return {'node': node, 'ok': p.returncode == 0 and '10.6.33.1' in p.stdout,
            'stdout': p.stdout[-200:], 'stderr': p.stderr[-300:]}

nodes = [f'od1-edc003-b300-{i:03d}' for i in range(2, 65)]
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    results = sorted(pool.map(fix, nodes), key=lambda x: x['node'])
summary = {'job_id': 41, 'checked': len(results), 'passed': sum(x['ok'] for x in results),
           'failed': [x for x in results if not x['ok']]}
Path('/cluster/OVA/Exemplar/job41-rendezvous-dns.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
if summary['failed']:
    raise SystemExit(1)
