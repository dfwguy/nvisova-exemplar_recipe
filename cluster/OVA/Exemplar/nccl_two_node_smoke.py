#!/usr/bin/env python3
"""Two-node NCCL all-reduce transport check; no Exemplar recipe changes."""
import datetime
import os
import socket
import torch
import torch.distributed as dist

rank = int(os.environ['SLURM_PROCID'])
world = int(os.environ['SLURM_NTASKS'])
local = int(os.environ['SLURM_LOCALID'])
torch.cuda.set_device(local)
os.environ['RANK'] = str(rank)
os.environ['WORLD_SIZE'] = str(world)
os.environ['MASTER_ADDR'] = '172.16.192.76'
os.environ['MASTER_PORT'] = '19045'
dist.init_process_group('nccl', init_method='env://', timeout=datetime.timedelta(seconds=90))
value = torch.tensor([rank + 1.0], device=f'cuda:{local}')
dist.all_reduce(value)
expected = world * (world + 1) / 2
if value.item() != expected:
    raise SystemExit(f'rank {rank}: wrong sum {value.item()} != {expected}')
if rank == 0:
    print(f'NCCL all-reduce PASS: {world} ranks, sum={value.item()}, host={socket.gethostname()}', flush=True)
dist.destroy_process_group()
