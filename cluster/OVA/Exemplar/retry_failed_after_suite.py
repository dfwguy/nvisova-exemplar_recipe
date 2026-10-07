#!/usr/bin/env python3
"""After the first-pass B300 queue, retry each failed recipe once."""
import datetime as dt
import fcntl
import json
import time
from pathlib import Path

import run_b300_suite as suite

STATE=suite.STATE
RETRIES=suite.SUITE/'retry-state.json'
LOCK=suite.SUITE/'runner.lock'


def save(path,data):
    suite.atomic_json(path,data)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ready():
    if not STATE.is_file(): return False
    state=json.loads(STATE.read_text())
    return len(state.get('completed_keys',[]))==12


def main():
    while not ready():
        time.sleep(30)
    with LOCK.open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        while suite.ACTIVE.exists():
            time.sleep(15)
        state=json.loads(STATE.read_text())
        retry=json.loads(RETRIES.read_text()) if RETRIES.exists() else {'started_utc':now(),'attempts':[]}
        attempted={x['key'] for x in retry['attempts']}
        for task in suite.official_queue():
            key=task['key']
            if key in attempted or state.get('results',{}).get(key,{}).get('final_state')=='COMPLETED':
                continue
            # A known two-port optical outage on node 043 caused one DeepSeek
            # failure. Wait for restored link and let the runner's exact-IDLE
            # preflight check all 64 Slurm nodes before every retry.
            while True:
                check=suite.command(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',
                                     'od1-edc003-b300-043',
                                     'cat /sys/class/net/enp3s0f2np2/carrier /sys/class/net/enp3s0f3np3/carrier'],timeout=12)
                if check.returncode==0 and check.stdout.strip().splitlines()==['1','1']:
                    break
                suite.event('retry_wait_fabric',key=key,node='od1-edc003-b300-043')
                time.sleep(60)
            suite.event('retry_start',key=key)
            try:
                result=suite.run_one(task)
                row={'key':key,'job_id':result['job_id'],'final_state':result['final_state'],
                     'completed_utc':now()}
                state['results'][key]={'job_id':result['job_id'],'final_state':result['final_state']}
                save(STATE,state)
            except Exception as exc:
                row={'key':key,'job_id':None,'final_state':'SETUP_ERROR',
                     'error':str(exc),'completed_utc':now()}
                suite.event('retry_setup_error',**row)
                # Leave any held job and evidence intact for investigation.
                retry['attempts'].append(row); save(RETRIES,retry)
                raise
            retry['attempts'].append(row); save(RETRIES,retry)
            suite.event('retry_done',**row)
        retry['finished_utc']=now(); save(RETRIES,retry)
        suite.event('retry_queue_done',attempts=len(retry['attempts']))


if __name__=='__main__':
    main()
