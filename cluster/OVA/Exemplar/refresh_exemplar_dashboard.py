#!/usr/bin/env python3
"""Keep the file-provisioned Exemplar dashboard default on the current Job ID."""
import json
import subprocess
import time
from pathlib import Path

root=Path('/cluster/OVA/Exemplar')
builder=Path('/home/nvidia-ssh/OVA/Observability/STN-B300/runtime/tools/build_exemplar.py')
last=None
while True:
    active=root/'active-job.json'
    state=root/'jobs'
    try:
        job=(int(json.loads(active.read_text())['job_id']) if active.exists()
             else max(int(p.stem.removeprefix('job')) for p in state.glob('job*.json')))
        if job!=last:
            subprocess.run(['/usr/bin/python3',str(builder)],check=True,capture_output=True,text=True)
            print(f'dashboard default Job ID {job}',flush=True)
            last=job
    except Exception as exc:
        print(f'dashboard refresh error: {exc}',flush=True)
    suite=root.parent/'exemplar/logs/suite/state.json'
    if suite.is_file():
        try:
            if len(json.loads(suite.read_text()).get('completed_keys',[]))>=12:
                break
        except Exception:
            pass
    time.sleep(15)
