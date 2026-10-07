#!/usr/bin/env python3
"""Stage one held Exemplar experiment to the 64 separate node-local disks."""
import concurrent.futures
import hashlib
import json
import pathlib
import shlex
import subprocess
import sys

job = int(sys.argv[1])
archive = pathlib.Path(f'/cluster/OVA/Exemplar/job{job}-stage.tar.gz')
experiment = pathlib.Path(sys.argv[2]).resolve()
parent = experiment.parent
if not archive.is_file() or not str(parent).startswith('/cluster/OVA/Exemplar/install/workloads/'):
    raise SystemExit('Invalid archive or experiment path')
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
nodes = [f'od1-edc003-b300-{i:03d}' for i in range(1, 65)]
remote_archive = f'/tmp/exemplar-job{job}-stage.tar.gz'
command = ('mkdir -p ' + shlex.quote(str(parent)) + ' && cat > ' + remote_archive +
           ' && echo ' + shlex.quote(digest + '  ' + remote_archive) + ' | sha256sum -c -' +
           ' && tar -xzf ' + remote_archive + ' -C ' + shlex.quote(str(parent)) +
           ' && test -f ' + shlex.quote(str(experiment / '_CONFIG')) +
           ' && getent ahostsv4 od1-edc003-b300-001 >/dev/null' +
           ' && rm -f ' + remote_archive)

def stage(node):
    with archive.open('rb') as source:
        p = subprocess.run(['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config',
                            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                            '-o', 'ConnectTimeout=8', node, command], stdin=source,
                           capture_output=True, text=True, timeout=60)
    return node, p.returncode, p.stdout[-200:], p.stderr[-500:]

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results = sorted(pool.map(stage, nodes))
failed = [result for result in results if result[1]]
summary = {'job_id': job, 'archive_sha256': digest, 'staged': len(results)-len(failed),
           'total': len(results), 'failures': failed}
path = pathlib.Path(f'/cluster/OVA/Exemplar/job{job}-staging.json')
path.write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
if failed:
    raise SystemExit(1)
