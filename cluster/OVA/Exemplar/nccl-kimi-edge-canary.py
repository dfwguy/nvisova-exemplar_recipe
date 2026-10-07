#!/usr/bin/env python3
"""Two-rank Kimi edge probe: node052 GPU3 <-> node056 GPU1."""
import datetime
import os
import socket

rank = int(os.environ['SLURM_PROCID'])
rank_hca = os.environ.get('CANARY_HCA_RANK' + str(rank))
if rank_hca:
    names = rank_hca.split(',')
    os.environ['NCCL_IB_HCA'] = '=' + ','.join(name + ':1' for name in names)
    os.environ['UCX_NET_DEVICES'] = ','.join(name + ':1' for name in names)
    os.environ['NVSHMEM_HCA_LIST'] = ','.join(names)

import torch
import torch.distributed as dist

device = int(os.environ.get('CANARY_GPU_0' if rank == 0 else 'CANARY_GPU_1', '3' if rank == 0 else '1'))
torch.cuda.set_device(device)
os.environ['RANK'] = str(rank)
os.environ['WORLD_SIZE'] = '2'
os.environ['MASTER_ADDR'] = os.environ.get('CANARY_MASTER_ADDR', '10.6.33.52')
os.environ['MASTER_PORT'] = os.environ.get('CANARY_MASTER_PORT', '19059')
print(f'CANARY_START rank={rank} host={socket.gethostname()} cuda={device} '
      f'nccl={torch.cuda.nccl.version()} merge={os.getenv("NCCL_IB_MERGE_NICS", "default")} '
      f'hca={os.getenv("NCCL_IB_HCA")}', flush=True)
dist.init_process_group('nccl', init_method='env://', timeout=datetime.timedelta(seconds=90))
tensor = torch.full((256 * 1024,), rank + 1, dtype=torch.float32, device=f'cuda:{device}')
dist.all_reduce(tensor)
assert torch.all(tensor == 3).item()
print(f'CANARY_ALLREDUCE_PASS rank={rank}', flush=True)
tensor.fill_(rank + 100)
if rank == 0:
    dist.send(tensor, dst=1)
    dist.recv(tensor, src=1)
    assert torch.all(tensor == 101).item()
else:
    dist.recv(tensor, src=0)
    assert torch.all(tensor == 100).item()
    tensor.fill_(101)
    dist.send(tensor, dst=0)
print(f'CANARY_P2P_PASS rank={rank}', flush=True)
dist.destroy_process_group()
