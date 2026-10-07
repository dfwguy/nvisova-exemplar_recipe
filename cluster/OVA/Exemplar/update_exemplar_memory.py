#!/usr/bin/env python3
"""Continuously maintain the durable 'exemplar runs' resume checkpoint."""
import datetime as dt
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path('/cluster/OVA/Exemplar')
SUITE = Path('/cluster/OVA/exemplar/logs/suite')
MEMORY = Path('/home/nvidia-ssh/EXEMPLAR_RUNS.md')
MACHINE = Path('/home/nvidia-ssh/EXEMPLAR_RUNS.json')
STATUS = SUITE/'runner-status.json'
QUEUE = [
    ('pretrain_deepseek-v3_671b','bf16'), ('pretrain_deepseek-v3_671b','fp8'),
    ('pretrain_deepseek-v3_671b','nvfp4'), ('pretrain_gpt_oss_120b','bf16'),
    ('pretrain_kimi-k2_1t','fp8'), ('pretrain_llama3.1_405b','fp8'),
    ('pretrain_llama3.1_405b','nvfp4'), ('pretrain_llama3.1_70b','fp8'),
    ('pretrain_llama3.1_70b','nvfp4'), ('pretrain_nemotron_3_120b','bf16'),
    ('pretrain_qwen3_235b','bf16'), ('pretrain_qwen3_235b','fp8'),
]


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def atomic(path, content):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(content)
    os.replace(tmp, path)


def process_for(script):
    """Find the actual Python worker, excluding tmux/shell command strings."""
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = path.read_bytes().split(b'\0')
        except (OSError, PermissionError):
            continue
        if args and b'python' in Path(args[0].decode(errors='replace')).name.encode() \
                and str(script).encode() in args:
            return int(path.parent.name)
    return None


def latest_event():
    path = SUITE/'events.jsonl'
    if not path.is_file():
        return None
    with path.open('rb') as source:
        source.seek(max(0, path.stat().st_size-65536))
        tail = source.read().decode(errors='replace')
    for line in reversed(tail.splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def held_jobs():
    try:
        result = subprocess.run(['/opt/slurm/25.11.2/bin/squeue','-h','-u','nvidia-ssh',
                                 '-o','%i|%T|%r|%j'],capture_output=True,text=True,timeout=8)
    except (OSError,subprocess.TimeoutExpired):
        return []
    if result.returncode:
        return []
    rows=[]
    for line in result.stdout.splitlines():
        parts=line.split('|',3)
        if len(parts)==4 and parts[1]=='PENDING' and 'JobHeldUser' in parts[2] and 'exemplar' in parts[3]:
            rows.append({'job_id':int(parts[0]),'reason':parts[2],'job_name':parts[3]})
    return rows


def active_slurm_state(active):
    if not active or not active.get('job_id'):
        return None
    try:
        result=subprocess.run(['/opt/slurm/25.11.2/bin/squeue','-h','-j',str(int(active['job_id'])),
                               '-o','%T'],capture_output=True,text=True,timeout=8)
    except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):
        return None
    return result.stdout.strip().splitlines()[0] if result.returncode==0 and result.stdout.strip() else None


def runner_status(state, active):
    now=time.time()
    runner=process_for(ROOT/'run_b300_suite.py')
    retry=process_for(ROOT/'retry_failed_after_suite.py')
    profile=SUITE/'host-profile.jsonl'
    heartbeat_age=round(now-profile.stat().st_mtime,1) if profile.is_file() else None
    completed=len(state.get('completed_keys',[]))
    pending=max(0,len(QUEUE)-completed)
    failed_keys=[key for key,result in state.get('results',{}).items()
                 if result.get('final_state') != 'COMPLETED']
    held=held_jobs()
    active_state=active_slurm_state(active)
    recent=latest_event()
    code=None; message=None
    if pending and not runner and active_state=='RUNNING':
        code='RECOVERY_IN_PROGRESS'
        message=f"Job {active['job_id']} is running; archival and retry handoff are pending while the suite runner is stopped."
    elif (pending or failed_keys) and not runner:
        if recent and recent.get('kind')=='retry_failed_halt':
            code='RETRY_FAILED_HALT'
            message=f"Job {recent.get('job_id')} failed its retry for {recent.get('key')}; suite halted before the next model."
        elif held:
            code='RUNNER_STOPPED_HELD_JOB'
            message=f"Suite runner stopped with held Slurm job(s) {', '.join(str(x['job_id']) for x in held)}; staging/release needs operator review."
        else:
            code='RUNNER_STOPPED'
            message=f'Suite runner stopped with {pending} official B300 configurations remaining.'
        if recent and recent.get('kind') in ('runner_halted','held_setup_failure'):
            message += ' Last error: '+str(recent.get('error',''))[:300]
    elif runner and heartbeat_age is not None and heartbeat_age>90:
        code='RUNNER_HEARTBEAT_STALE'
        message=f'Runner process exists but host-profile heartbeat is {heartbeat_age:.0f}s old.'
    elif completed==len(QUEUE) and not retry:
        retry_state=load_json(SUITE/'retry-state.json',{})
        failures=[r for r in state.get('results',{}).values() if r.get('final_state')!='COMPLETED']
        if failures and not retry_state.get('finished_utc'):
            code='RETRY_RUNNER_STOPPED'
            message='First-pass suite finished with failed runs, but retry runner is stopped.'
    if code=='RECOVERY_IN_PROGRESS':
        phase='RECOVERY_IN_PROGRESS'
    elif not code:
        phase='RUNNING' if runner else 'RETRY_RUNNING' if retry else 'COMPLETE' if not pending else 'NOT_STARTED'
    else:
        phase='ALERT'
    return {'checked_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'phase':phase,'alert':bool(code),'alert_code':code,'alert_message':message,
            'runner_pid':runner,'retry_runner_pid':retry,'profile_age_seconds':heartbeat_age,
            'completed_keys':completed,'pending_keys':pending,
            'active_job_id':active.get('job_id') if active else None,
            'failed_keys':failed_keys,
            'active_slurm_state':active_state,
            'held_jobs':held,'last_event':recent}


def log_progress(path):
    if not path.is_file():
        return {}
    with path.open('rb') as source:
        source.seek(max(0, path.stat().st_size - 262144))
        tail = source.read().decode(errors='replace')
    iterations = re.findall(r'iteration\s+(\d+)\s*/\s*(\d+)', tail, re.I)
    times = re.findall(r'elapsed time per iteration \(ms\):\s*([\d.]+)', tail, re.I)
    flops = re.findall(r'([\d.]+)\s*MODEL_TFLOP/s/GPU', tail, re.I)
    return {'last_iteration': '/'.join(iterations[-1]) if iterations else None,
            'last_step_seconds': round(float(times[-1])/1000,5) if times else None,
            'last_raw_tflops_per_gpu': float(flops[-1]) if flops else None}


def build(status=None):
    state = load_json(SUITE/'state.json', {'completed_keys':[], 'results':{}})
    active = load_json(ROOT/'active-job.json', None)
    runs = []
    for path in sorted((ROOT/'jobs').glob('job*.json'), key=lambda p:int(p.stem[3:])):
        data = load_json(path, {})
        if not data.get('job_id'):
            continue
        log = Path(data.get('log_path',''))
        score_path = Path(data.get('score_window_path','')) if data.get('score_window_path') else None
        score = load_json(score_path, {}) if score_path else {}
        runs.append({'job_id':data['job_id'], 'workload':data.get('workload'),
                     'state':data.get('final_state','UNKNOWN'), 'exit_code':data.get('exit_code'),
                     'completed_utc':data.get('completed_utc'), 'log_path':str(log),
                     'log_sha256':data.get('log_sha256'), 'failure':data.get('failure'),
                     'score_window_path':str(score_path) if score_path else None,
                     'mean_step_seconds':score.get('mean_step_seconds'),
                     'mean_raw_tflops_per_gpu':score.get('mean_raw_tflops_per_gpu'),
                     **log_progress(log)})
    active_progress = None
    if active:
        active_progress = {'job_id':active['job_id'],'workload':active.get('workload'),
                           'dtype':active.get('dtype'),'log_path':active.get('log_path'),
                           'submitted_utc':active.get('submitted_utc')}
    tried = set(state.get('completed_keys',[]))
    pending = [f'{workload}_{dtype}' for workload,dtype in QUEUE if f'{workload}_{dtype}' not in tried]
    failed = [r for r in runs if r['job_id']>=53 and r['state']!='COMPLETED']
    status=status or runner_status(state,active)
    snapshot = {'memory_name':'exemplar runs','updated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                'recipe_release':'v26.08.01','suite_total':13,'nemotron_job_id':52,
                'current_job':active_progress,'completed_attempt_keys':state.get('completed_keys',[]),
                'pending_recipe_keys':pending,'failed_attempts':[r['job_id'] for r in failed],
                'runs':runs,
                'runner_script':str(ROOT/'run_b300_suite.py'),
                'tmux_session':'exemplar-suite',
                'runner_log':str(SUITE/'runner.log'),
                'runner_status':status,
                'runner_status_file':str(STATUS),
                'suite_state':str(SUITE/'state.json'),
                'dashboard':'http://localhost:3300/d/stn-b300-exemplar?orgId=1&refresh=5s',
                'network_note':'30 common healthy RoCEv2 HCAs; node040 mlx5_16 and mlx5_17 down',
                'storage_note':'/cluster/OVA/Exemplar is node-local; each held job is staged and SHA256 verified on all 64 nodes before release'}
    lines = ['# exemplar runs', '',
             f"Updated: {snapshot['updated_utc']}", '',
             'Resume instruction: read this file and `/cluster/OVA/exemplar/logs/suite/state.json`, inspect the tmux session and current Slurm job, then continue the official B300 recipe queue from the recorded state. Never resubmit a running job.', '',
             'Runner: `tmux attach -t exemplar-suite`',
             f"Runner log: `{snapshot['runner_log']}`",
             f"Runner status heartbeat: `{STATUS}`",
             f"Dashboard: {snapshot['dashboard']}",
             'Logs: `/cluster/OVA/exemplar/logs/job<id>-logs/`',
             'Host profile: `/cluster/OVA/exemplar/logs/suite/host-profile.jsonl`', '',
             'Recipe release: v26.08.01. B300 suite: 13 configurations at 512 GPUs, one repeat, profiling disabled. Nemotron-H FP8 job 52 completed; the tmux runner handles the other 12 sequentially.',
             'Fabric: 30 common healthy RoCEv2 HCAs; node 040 `mlx5_16` and `mlx5_17` remain down. The generated experiments are node-local and staged on all 64 nodes before release.', '']
    if status['alert']:
        lines += [f"**ALERT — {status['alert_code']}: {status['alert_message']}**", '']
    else:
        lines += [f"Runner status: **{status['phase']}**; heartbeat age {status['profile_age_seconds']} s.", '']
    if active_progress:
        lines += [f"Current job: **{active_progress['job_id']}** `{active_progress['workload']}` (submitted {active_progress['submitted_utc']}); live log `{active_progress['log_path']}`.", '']
    else:
        lines += ['Current job: none recorded in `active-job.json`.', '']
    lines += [f"Queued recipe keys remaining: **{len(pending)}**", '']
    lines += [f'- `{key}`' for key in pending]
    lines += ['', '## Completed attempts', '', '| Job ID | Workload | State | Step / TFLOPS/GPU | Log |', '| --- | --- | --- | --- | --- |']
    for r in runs:
        score = (f"35–44: {r['mean_step_seconds']} s / {r['mean_raw_tflops_per_gpu']}" if r['mean_step_seconds'] is not None
                 else f"last {r['last_iteration'] or '—'}: {r['last_step_seconds'] or '—'} s / {r['last_raw_tflops_per_gpu'] or '—'}")
        lines.append(f"| {r['job_id']} | `{r['workload']}` | {r['state']} | {score} | `{r['log_path']}` |")
    if failed:
        lines += ['', 'Failed attempts requiring review:', '']
        lines += [f"- Job {r['job_id']}: {r['failure'] or r['state']} — `{r['log_path']}`" for r in failed]
    lines += ['', 'Job 52 measured 5.71647 s/step and 1,441.84 raw TFLOPS/GPU over steps 35–44, 87.84% of the supplied 1,641.52 TFLOPS/GPU baseline. This is below NVIDIA’s >95% threshold and not an Exemplar certification.', '']
    return snapshot, '\n'.join(lines)


def signature(status):
    paths = [ROOT/'active-job.json', SUITE/'state.json', *(ROOT/'jobs').glob('job*.json')]
    files=tuple(sorted((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in paths if p.is_file()))
    health=(status['phase'],status['alert_code'],status['alert_message'],status['runner_pid'],
            status['retry_runner_pid'],tuple(x['job_id'] for x in status['held_jobs']))
    return files,health


def main():
    last = None
    while True:
        state=load_json(SUITE/'state.json', {'completed_keys':[], 'results':{}})
        active=load_json(ROOT/'active-job.json', None)
        status=runner_status(state,active)
        atomic(STATUS,json.dumps(status,indent=2)+'\n')
        marker = signature(status)
        if marker != last:
            snapshot, markdown = build(status)
            atomic(MACHINE, json.dumps(snapshot,indent=2)+'\n')
            atomic(MEMORY, markdown)
            print(f"{snapshot['updated_utc']} checkpoint updated: {len(snapshot['runs'])} archived runs; active={snapshot['current_job']['job_id'] if snapshot['current_job'] else None}",flush=True)
            last = marker
        time.sleep(15)


if __name__ == '__main__':
    main()
