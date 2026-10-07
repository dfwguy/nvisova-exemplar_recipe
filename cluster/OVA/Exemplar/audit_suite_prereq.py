#!/usr/bin/env python3
"""Read-only 64-node Exemplar suite resource and staging audit."""
import concurrent.futures
import json
import shlex
import subprocess
from pathlib import Path

REMOTE = r'''
import json,os,shutil,subprocess
from pathlib import Path
paths={
 'nemo_260401':'/cluster/OVA/Exemplar/images/nvidia+nemo+26.04.01.sqsh',
 'nemo_260601':'/cluster/OVA/Exemplar/images/nvidia+nemo+26.06.01.sqsh',
 'install':'/cluster/OVA/Exemplar/install',
 'workloads':'/cluster/OVA/Exemplar/install/workloads',
 'scratch':'/scratch',
}
out={'paths':{k:{'exists':Path(v).exists(),'size':Path(v).stat().st_size if Path(v).is_file() else None} for k,v in paths.items()}}
for k in ('workloads','scratch'):
 try:
  usage=shutil.disk_usage(paths[k]);out[k+'_free_gib']=round(usage.free/1024**3,1)
 except OSError as e:out[k+'_error']=str(e)
out['scratch_mount']=any(line.split()[1]=='/scratch' for line in Path('/proc/mounts').read_text().splitlines())
for k,args in {'slurmd':['systemctl','is-active','slurmd'],
               'gpu':['nvidia-smi','--query-gpu=index','--format=csv,noheader'],
               'enroot':['enroot','version']}.items():
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=6)
  out[k+'_rc']=p.returncode
  out[k+'_out']=p.stdout.strip() if k!='gpu' else len(p.stdout.strip().splitlines())
  if p.returncode:out[k+'_err']=p.stderr.strip()[-150:]
 except Exception as e:out[k+'_error']=str(e)
print(json.dumps(out))
'''

def audit(n):
    host=f'od1-edc003-b300-{n:03d}'
    cmd=['/usr/bin/ssh','-F','/home/nvidia-ssh/.ssh/config','-o','BatchMode=yes',
         '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',host,
         'python3 -c '+shlex.quote(REMOTE)]
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
        return host,json.loads(proc.stdout) if proc.returncode==0 else {'error':proc.stderr[-250:]}
    except Exception as e:
        return host,{'error':str(e)}

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    data=dict(pool.map(audit,range(1,65)))
output=Path('/cluster/OVA/Exemplar/suite-prereq-audit-20260925.json')
output.write_text(json.dumps(data,indent=2)+'\n')
print('responses',sum('error' not in v for v in data.values()),'of 64')
for host,value in data.items():
    if 'error' in value or any(not x['exists'] for x in value['paths'].values()) or value.get('gpu_out')!=8 or value.get('slurmd_out')!='active' or not value.get('scratch_mount'):
        print(host,value)
print(output)
