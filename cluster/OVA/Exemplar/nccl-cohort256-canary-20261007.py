import os,socket,datetime
import torch
import torch.distributed as dist
rank=int(os.environ['SLURM_PROCID']);local=int(os.environ['SLURM_LOCALID']);world=int(os.environ['SLURM_NTASKS'])
assert world==256
torch.cuda.set_device(local)
os.environ.update(RANK=str(rank),LOCAL_RANK=str(local),WORLD_SIZE=str(world))
dist.init_process_group('nccl',timeout=datetime.timedelta(seconds=180))
print(f'COHORT_START rank={rank} host={socket.gethostname()} gpu={local}',flush=True)
for count in [262144,4194304]:
 t=torch.full((count,),rank+1,dtype=torch.float32,device=f'cuda:{local}')
 dist.all_reduce(t)
 assert torch.all(t==world*(world+1)//2).item()
print(f'COHORT_ALLREDUCE_PASS rank={rank}',flush=True)
for offset in [1,9,65,129]:
 target=(rank+offset)%world;source=(rank-offset)%world
 tx=torch.full((262144,),rank,dtype=torch.float32,device=f'cuda:{local}');rx=torch.empty_like(tx)
 ops=[dist.P2POp(dist.isend,tx,target),dist.P2POp(dist.irecv,rx,source)]
 for req in dist.batch_isend_irecv(ops):req.wait()
 assert torch.all(rx==source).item()
 dist.barrier()
print(f'COHORT_P2P_PASS rank={rank}',flush=True)
dist.destroy_process_group()
