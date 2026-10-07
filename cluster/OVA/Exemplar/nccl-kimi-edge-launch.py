#!/usr/bin/env python3
"""Run one 2-rank Kimi transport canary; argument: baseline, no-merge, one-hca."""
import importlib.util
import os
import pathlib
import subprocess
import sys

variant = sys.argv[1]
assert variant in ('baseline', 'no-merge', 'one-hca', 'p02-four')
root = pathlib.Path('/cluster/OVA/Exemplar')
spec = importlib.util.spec_from_file_location('suite', root / 'run_b300_suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)
env = os.environ.copy()
env.update(suite.ENV)
env['NCCL_DEBUG_SUBSYS'] = 'INIT,NET,GRAPH'
env['CANARY_MASTER_ADDR'] = '10.6.33.52'
env['CANARY_MASTER_PORT'] = {'baseline':'19059', 'no-merge':'19060', 'one-hca':'19061', 'p02-four':'19062'}[variant]
if variant == 'no-merge':
    env['NCCL_IB_MERGE_NICS'] = '0'
elif variant in ('one-hca', 'p02-four'):
    names = ['mlx5_0'] if variant == 'one-hca' else ['mlx5_5', 'mlx5_15', 'mlx5_9', 'mlx5_1']
    env['NCCL_IB_HCA'] = '=' + ','.join(name + ':1' for name in names)
    env['UCX_NET_DEVICES'] = ','.join(name + ':1' for name in names)
    env['NVSHMEM_HCA_LIST'] = ','.join(names)
    env.pop('NCCL_IB_MERGE_NICS', None)
else:
    env.pop('NCCL_IB_MERGE_NICS', None)
keys = sorted(set(suite.ENV) | {'NCCL_IB_MERGE_NICS','CANARY_MASTER_ADDR','CANARY_MASTER_PORT'})
keys = [key for key in keys if key in env]
cmd = ['/opt/slurm/25.11.2/bin/srun',
       '--job-name=nccl-kimi-edge-' + variant,
       '--partition=exemplar', '--account=exemplar',
       '--nodelist=od1-edc003-b300-[052,056]',
       '--nodes=2', '--ntasks=2', '--ntasks-per-node=1',
       '--time=00:04:00', '--wait=60', '--kill-on-bad-exit=1',
       '--container-image=' + str(root / 'install/images/nvidia+nemo+26.06.01.sqsh'),
       '--container-mounts=/tmp/nccl-kimi-edge-canary.py:/tmp/nccl-kimi-edge-canary.py',
       '--container-env=' + ','.join(keys),
       'python', '/tmp/nccl-kimi-edge-canary.py']
log = root / ('nccl-kimi-edge-' + variant + '.log')
with log.open('w') as output:
    print(' '.join(cmd), file=output, flush=True)
    result = subprocess.run(cmd, env=env, stdout=output, stderr=subprocess.STDOUT)
print(f'{variant}: exit={result.returncode} log={log}', flush=True)
sys.exit(result.returncode)
