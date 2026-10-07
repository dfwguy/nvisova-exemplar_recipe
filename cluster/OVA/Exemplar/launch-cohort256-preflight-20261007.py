import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/cluster/OVA/Exemplar')
nodes = (ROOT / 'cohort256-nodes.txt').read_text().splitlines()
assert len(nodes) == len(set(nodes)) == 32
script = ROOT / 'nccl-cohort256-canary-20261007.py'
remote = '/tmp/nccl-cohort256-canary-20261007.py'
logs = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/cluster/OVA/exemplar/logs/nccl-cohort256-20261007')
prefix = logs.name
logs.mkdir(exist_ok=True)
def stage(node):
    subprocess.run(['scp', '-q', str(script), node + ':' + remote], check=True, timeout=20)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(stage, nodes))
spec = importlib.util.spec_from_file_location('suite256', ROOT / 'run_b300_suite_256.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)
gate = json.loads((ROOT / 'cohort256-preflight.json').read_text())
suite.configure_hcas(gate)
env = os.environ.copy()
env.update(suite.ENV)
env.update(MASTER_ADDR=gate['master_addr_ipv4'], MASTER_PORT='19180')
cmd = ['/opt/slurm/25.11.2/bin/srun', '--job-name=nccl-256-preflight',
       '--partition=exemplar', '--account=exemplar', '--nodelist=' + ','.join(nodes),
       '--nodes=32', '--ntasks=256', '--ntasks-per-node=8', '--gres=gpu:8',
       '--time=00:10:00', '--wait=30', '--kill-on-bad-exit=1',
       '--output=/tmp/' + prefix + '-%t.log',
       '--container-image=' + str(ROOT / 'install/images/nvidia+nemo+26.06.01.sqsh'),
       '--container-mounts=' + remote + ':' + remote,
       '--container-env=' + ','.join(sorted(set(suite.ENV) | {'MASTER_ADDR', 'MASTER_PORT'})),
       'python', remote]
(logs / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
with (logs / 'launcher.log').open('w') as output:
    result = subprocess.run(cmd, env=env, stdout=output, stderr=subprocess.STDOUT)
def fetch(node):
    out = logs / node
    out.mkdir(exist_ok=True)
    return subprocess.run(['scp', '-q', node + ':/tmp/' + prefix + '-*.log', str(out)],
                          capture_output=True, text=True, timeout=30).returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    fetched = dict(zip(nodes, pool.map(fetch, nodes)))
(logs / 'exit.json').write_text(json.dumps({'exit_code': result.returncode, 'fetch_status': fetched}, indent=2) + '\n')
print('exit=' + str(result.returncode) + ' logs=' + str(logs), flush=True)
sys.exit(result.returncode)
