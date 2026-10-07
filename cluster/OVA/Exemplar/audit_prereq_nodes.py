#!/usr/bin/env python3
"""Read-only Exemplar RDMA and container prerequisite audit of approved B300 nodes."""
import concurrent.futures
import json
import shlex
import subprocess
from pathlib import Path

REMOTE = r'''
import json,re
from pathlib import Path
ports=[]
for dev in sorted(Path('/sys/class/infiniband').glob('mlx5_*')):
    port=dev/'ports/1'
    try:
        state=(port/'state').read_text().strip()
        phys_state=(port/'phys_state').read_text().strip()
        rate=(port/'rate').read_text().strip()
        gid=(port/'gids/3').read_text().strip()
        gid_type=(port/'gid_attrs/types/3').read_text().strip()
        ndev=(port/'gid_attrs/ndevs/3').read_text().strip()
        oper=(Path('/sys/class/net')/ndev/'operstate').read_text().strip()
        carrier=(Path('/sys/class/net')/ndev/'carrier').read_text().strip()
    except OSError:
        continue
    if ':ffff:' in gid:
        ports.append({'hca':dev.name,'state':state,'phys_state':phys_state,
                      'rate':rate,'gid3':gid,'gid3_type':gid_type,'netdev':ndev,'operstate':oper,
                      'carrier':carrier})
keys=('NCCL_IB_HCA','NCCL_IB_GID_INDEX','NCCL_IB_TC','NCCL_IB_SL','NCCL_IB_TIMEOUT',
      'NCCL_NET','NCCL_CROSS_NIC','UCX_NET_DEVICES','NVSHMEM_HCA_LIST',
      'MELLANOX_VISIBLE_DEVICES','NCCL_SOCKET_IFNAME','GLOO_SOCKET_IFNAME')
env={}
env_sources={}
for source in list(Path('/etc/enroot/environ.d').glob('*.env'))+[Path('/etc/environment')]:
    if not source.is_file():continue
    try:
        for line in source.read_text().splitlines():
            line=line.strip()
            if line.startswith('export '):line=line[7:]
            key=line.split('=',1)[0].strip()
            if key in keys and '=' in line:
                value=line.split('=',1)[1].strip().strip('"').strip("'")
                env[key]=value
                env_sources.setdefault(str(source),{})[key]=value
    except OSError:pass
conf={}
for source in (Path('/etc/enroot/enroot.conf'),Path('/etc/enroot.conf')):
    if not source.is_file():continue
    for line in source.read_text().splitlines():
        m=re.match(r'^\s*(ENROOT_(?:ROOTFS_WRITABLE|REMAP_ROOT))\s*(?:=|\s)\s*(\S+)',line)
        if m:conf[m.group(1)]=m.group(2)
print(json.dumps({'ports':ports,'env':env,'env_sources':env_sources,'enroot':conf}))
'''

def audit(number):
    node=f'od1-edc003-b300-{number:03d}'
    command=['/usr/bin/ssh','-F','/home/nvidia-ssh/.ssh/config','-o','BatchMode=yes',
             '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5',node,
             'python3 -c '+shlex.quote(REMOTE)]
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=12)
        if p.returncode: return node,{'error':p.stderr[-200:]}
        return node,json.loads(p.stdout)
    except Exception as error:
        return node,{'error':str(error)}

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    data=dict(pool.map(audit,range(1,65)))
for node,value in data.items():
    if 'error' in value:continue
    ports=value['ports']
    value['gid3_total']=len(ports)
    value['gid3_active']=sum(p['state'].startswith('4:') for p in ports)
    value['gid3_down']=[p['hca'] for p in ports if not p['state'].startswith('4:')]
path=Path('/cluster/OVA/Exemplar/prereq-node-audit-20260925.json')
path.write_text(json.dumps(data,indent=2)+'\n')
print('nodes',len(data),'errors',sum('error' in v for v in data.values()))
print('GID3 active counts',sorted(set(v.get('gid3_active') for v in data.values())))
print('short ports',[(n,v['gid3_active'],v['gid3_down']) for n,v in data.items()
                     if 'error' not in v and v['gid3_active']<32])
print(path)
