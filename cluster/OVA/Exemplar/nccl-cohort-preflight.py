#!/usr/bin/env python3
"""Two-rank four-HCA edge probe for the first 32-node cohort."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

root = Path('/cluster/OVA/Exemplar')
logroot = Path('/cluster/OVA/exemplar/logs')
node_a, node_b = sys.argv[1:3] if len(sys.argv) >= 3 else ('001', '032')
no_merge = '--no-merge' in sys.argv[3:]
split_quad = '--split-quad' in sys.argv[3:]
all32 = '--all32' in sys.argv[3:]
gpu_a = int(next((x.split('=', 1)[1] for x in sys.argv[3:] if x.startswith('--gpu-a=')), '3'))
gpu_b = int(next((x.split('=', 1)[1] for x in sys.argv[3:] if x.startswith('--gpu-b=')), '1'))
assert 0 <= gpu_a < 8 and 0 <= gpu_b < 8
assert node_a.isdigit() and node_b.isdigit() and node_a != node_b
spec = importlib.util.spec_from_file_location('suite', root / 'run_b300_suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)
names = [f'mlx5_{i}' for i in sorted(set(suite.HCA_IDS) | {16, 17})] if all32 else ['mlx5_0', 'mlx5_1', 'mlx5_2', 'mlx5_3']
env = os.environ.copy()
env.update(suite.ENV)
env.update({
    'NCCL_IB_HCA': '=' + ','.join(x + ':1' for x in names),
    'UCX_NET_DEVICES': ','.join(x + ':1' for x in names),
    'NVSHMEM_HCA_LIST': ','.join(names),
    'NCCL_DEBUG_SUBSYS': 'INIT,NET,GRAPH',
    'CANARY_MASTER_ADDR': '10.6.33.' + str(int(node_a)),
    'CANARY_MASTER_PORT': '19065' if (node_a, node_b) == ('002', '033') else '19064',
    'CANARY_GPU_0': str(gpu_a),
    'CANARY_GPU_1': str(gpu_b),
})
if split_quad:
    env['CANARY_HCA_RANK0'] = 'mlx5_0,mlx5_1,mlx5_2,mlx5_3'
    env['CANARY_HCA_RANK1'] = 'mlx5_14,mlx5_15,mlx5_16,mlx5_17'
if no_merge:
    env['NCCL_IB_MERGE_NICS'] = '0'
else:
    env.pop('NCCL_IB_MERGE_NICS', None)
keys = sorted(set(suite.ENV) | {'CANARY_MASTER_ADDR', 'CANARY_MASTER_PORT', 'CANARY_GPU_0', 'CANARY_GPU_1'} | ({'CANARY_HCA_RANK0', 'CANARY_HCA_RANK1'} if split_quad else set()) | ({'NCCL_IB_MERGE_NICS'} if no_merge else set()))
cmd = ['/opt/slurm/25.11.2/bin/srun',
       '--job-name=nccl-cohort32-four-hca',
       '--partition=exemplar', '--account=exemplar',
       f'--nodelist=od1-edc003-b300-[{node_a},{node_b}]',
       '--nodes=2', '--ntasks=2', '--ntasks-per-node=1',
       '--time=00:04:00', '--wait=60', '--kill-on-bad-exit=1',
       '--container-image=' + str(root / 'install/images/nvidia+nemo+26.06.01.sqsh'),
       '--container-mounts=/tmp/nccl-kimi-edge-canary.py:/tmp/nccl-kimi-edge-canary.py',
       '--container-env=' + ','.join(keys),
       'python', '/tmp/nccl-kimi-edge-canary.py']
log = logroot / f'nccl-cohort32-four-hca-{node_a}-{node_b}-gpu{gpu_a}-gpu{gpu_b}{"-no-merge" if no_merge else ""}{"-split-quad" if split_quad else ""}{"-all32" if all32 else ""}.log'
log.parent.mkdir(parents=True, exist_ok=True)
with log.open('w') as output:
    print(' '.join(cmd), file=output, flush=True)
    result = subprocess.run(cmd, env=env, stdout=output, stderr=subprocess.STDOUT)
print(f'exit={result.returncode} log={log}', flush=True)
sys.exit(result.returncode)
