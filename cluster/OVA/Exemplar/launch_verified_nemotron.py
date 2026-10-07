#!/usr/bin/env python3
"""Submit the official held recipe with audited RDMA ports, stage, then release."""
import datetime
import json
import os
import re
import resource
import subprocess
import sys
from pathlib import Path

ROOT=Path('/cluster/OVA/Exemplar')
INSTALL=ROOT/'install'
SCONTROL='/opt/slurm/25.11.2/bin/scontrol'
audit=json.loads((ROOT/'prereq-node-audit-20260925.json').read_text())
healthy=[]
for node,record in audit.items():
    if 'error' in record:
        raise SystemExit(f'audit failed for {node}: {record["error"]}')
    healthy.append({p['hca'] for p in record['ports'] if p['state'].startswith('4:')
                    and p['gid3'].startswith('0000:0000:0000:0000:0000:ffff:')})
ports=sorted(set.intersection(*healthy),key=lambda name:int(name.split('_')[1]))
if len(ports)!=30 or ports[:4]!=['mlx5_0','mlx5_1','mlx5_2','mlx5_3']:
    raise SystemExit(f'unexpected audited HCA set: {ports}')
hca='='+','.join(f'{name}:1' for name in ports)
ucx=','.join(f'{name}:1' for name in ports)
nvshmem=','.join(ports)
env={
    'NCCL_SOCKET_IFNAME':'enp57s0f0np0',
    'GLOO_SOCKET_IFNAME':'enp57s0f0np0',
    'NCCL_IB_HCA':hca,
    'NCCL_IB_GID_INDEX':'3',
    'NCCL_CROSS_NIC':'0',
    'NCCL_NET':'IB',
    'NCCL_IB_QPS_PER_CONNECTION':'4',
    'NCCL_IB_TC':'104',
    'NCCL_IB_SL':'1',
    'NCCL_IB_TIMEOUT':'20',
    'NCCL_NET_GDR_C2C':'1',
    'UCX_NET_DEVICES':ucx,
    'NVSHMEM_HCA_LIST':nvshmem,
    'NCCL_DEBUG':'INFO',
    'NCCL_DEBUG_SUBSYS':'INIT',
}
args=[str(INSTALL/'llmb-run'),'submit','-w','pretrain_nemotron-h',
      '--dtype','fp8','--scale','512','--slurm-arg','hold']
for key,value in env.items():
    args+=['--env',f'{key}={value}']
soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE,(min(65535,hard),hard))
before={p.stem for p in (ROOT/'jobs').glob('job*.json')}
process_env=os.environ.copy()
process_env['PATH']='/opt/slurm/25.11.2/bin:'+process_env.get('PATH','/usr/bin:/bin')
result=subprocess.run(args,cwd=INSTALL,env=process_env,capture_output=True,text=True,check=False)
(ROOT/'last-full-hca-submit.log').write_text(result.stdout+'\n'+result.stderr)
if result.returncode:
    raise SystemExit(f'llmb-run submit failed: {result.returncode}; see last-full-hca-submit.log')
match=re.search(r'jobid=(\d+)',result.stdout)
if not match:
    raise SystemExit('No Slurm job ID in launch output; inspect last-full-hca-submit.log')
job=int(match.group(1))
if f'job{job}' in before:
    raise SystemExit('job ID was already archived')
status=subprocess.run([SCONTROL,'show','job','-o',str(job)],capture_output=True,text=True,check=True).stdout
if 'JobState=PENDING' not in status or 'Reason=JobHeldUser' not in status:
    raise SystemExit(f'job {job} is not held; inspect Slurm before staging')
match=re.search(r'\bCommand=(\S+)',status)
if not match:
    raise SystemExit('Slurm command path unavailable')
experiment=Path(match.group(1)).parent
if not str(experiment).startswith(str(INSTALL/'workloads/pretrain_nemotron-h/experiments/')) or not (experiment/'_CONFIG').is_file():
    raise SystemExit('unrecognized generated experiment path')
sbatch=Path(match.group(1)).read_text()
for key in env:
    if f'export {key}=' not in sbatch or key not in sbatch.split('--container-env ')[1].split(' ')[0]:
        raise SystemExit(f'{key} not exported into generated container command')
archive=ROOT/f'job{job}-stage.tar.gz'
subprocess.run(['tar','-czf',str(archive),'-C',str(experiment.parent),experiment.name],check=True)
subprocess.run([sys.executable,str(ROOT/'stage_held_job.py'),str(job),str(experiment)],check=True)
child=next(p for p in experiment.iterdir() if p.is_dir() and p.name.startswith('pretrain_nemotronh_56b_fp8_cs_'))
log=child/f'log-exemplar-exemplar.pretrain_nemotronh_56b_fp8_cs_gpus512_tp2_pp1_cp1_vpNone_ep1_etpNone_mbs1_gbs1536_{job}_0.out'
manifest={'job_id':job,'workload':'pretrain_nemotron-h_56b_fp8','gpus':512,
          'batch_host':'od1-edc003-b300-001','log_path':str(log),'experiment':str(experiment),
          'submitted_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'diagnostic':'30 fleetwide healthy RoCEv2 HCAs (2 node-040 ports excluded); full-bandwidth qualification still needs fabric review',
          'transport_interface':'enp57s0f0np0','hca':hca,'submit_nofile_soft':65535,
          'nccl_env':env}
(ROOT/'active-job.json').write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run([SCONTROL,'release',str(job)],check=True)
print('RELEASED JOB',job,'EXPERIMENT',experiment,flush=True)
