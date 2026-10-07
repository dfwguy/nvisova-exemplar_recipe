#!/usr/bin/env python3
"""Sequential official B300 Exemplar runs on node-local experiment disks.

Use --plan to inspect the queue without submitting jobs. A normal invocation
submits each job held, stages its generated experiment to all 64 nodes, then
releases it. One instance at a time is enforced by flock.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml
from nccl_runtime_gate import RuntimeGate, read_remote_delta

ROOT = Path('/cluster/OVA/Exemplar')
INSTALL = ROOT / 'install'
LOGROOT = Path('/cluster/OVA/exemplar/logs')
SUITE = LOGROOT / 'suite'
JOBS = ROOT / 'jobs'
ACTIVE = ROOT / 'active-job.json'
STATE = SUITE / 'state.json'
EVENTS = SUITE / 'events.jsonl'
PROFILE = SUITE / 'host-profile.jsonl'
SLURM = Path('/opt/slurm/25.11.2/bin')
NODES = [f'od1-edc003-b300-{i:03d}' for i in range(1, 65)]
HCA_IDS = [*range(0, 12), *range(14, 22), *range(26, 30), *range(32, 40)]
HCA_NAMES = [f'mlx5_{i}' for i in HCA_IDS]
HCA = '=' + ','.join(f'{name}:1' for name in HCA_NAMES)
ENV = {
    'NCCL_SOCKET_IFNAME': 'enp57s0f0np0',
    'GLOO_SOCKET_IFNAME': 'enp57s0f0np0',
    'NCCL_IB_HCA': HCA,
    'NCCL_IB_GID_INDEX': '3',
    'NCCL_CROSS_NIC': '0',
    'NCCL_NET': 'IB',
    'NCCL_IB_QPS_PER_CONNECTION': '4',
    'NCCL_IB_TC': '104',
    'NCCL_IB_SL': '1',
    'NCCL_IB_TIMEOUT': '20',
    'NCCL_NET_GDR_C2C': '1',
    'UCX_NET_DEVICES': ','.join(f'{name}:1' for name in HCA_NAMES),
    'NVSHMEM_HCA_LIST': ','.join(HCA_NAMES),
    'NCCL_DEBUG': 'INFO',
    'NCCL_DEBUG_SUBSYS': 'INIT,NET',
}


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def event(kind, **fields):
    SUITE.mkdir(parents=True, exist_ok=True)
    row = {'time_utc': utc(), 'kind': kind, **fields}
    with EVENTS.open('a') as out:
        out.write(json.dumps(row) + '\n')
    print(json.dumps(row), flush=True)


def command(args, *, cwd=None, timeout=30, check=False):
    env = os.environ.copy()
    env['PATH'] = str(SLURM) + ':' + env.get('PATH', '/usr/bin:/bin')
    return subprocess.run([str(a) for a in args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=timeout, check=check)


def host_stats():
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            mem['mem_available_bytes'] = int(line.split()[1]) * 1024
            break
    status = Path('/proc/self/status').read_text()
    rss = re.search(r'^VmRSS:\s*(\d+) kB', status, re.M)
    disk = shutil.disk_usage('/cluster')
    return {'loadavg_1m': os.getloadavg()[0], **mem,
            'cluster_free_bytes': disk.free,
            'runner_rss_bytes': int(rss.group(1)) * 1024 if rss else None}


def profile_loop(stop):
    while not stop.is_set():
        try:
            row = {'time_utc': utc(), **host_stats()}
            with PROFILE.open('a') as out:
                out.write(json.dumps(row) + '\n')
        except Exception as exc:
            event('profile_error', error=str(exc))
        stop.wait(30)


def official_queue():
    source = yaml.safe_load((INSTALL / 'llmb_repo/exemplar.yaml').read_text())
    queue = []
    for entry in source['workloads']['b300']:
        for full_name, config in entry.items():
            workload, size = full_name.rsplit('_', 1)
            for dtype in config['dtypes']:
                if full_name == 'pretrain_nemotron-h_56b' and dtype == 'fp8':
                    continue  # completed as job 52
                queue.append({'key': f'{full_name}_{dtype}', 'workload': workload,
                              'full_name': full_name, 'size': size, 'dtype': dtype,
                              'gpus': 512})
    if len(queue) != 12:
        raise RuntimeError(f'Expected 12 remaining B300 configurations; found {len(queue)}')
    return queue


def all_nodes_idle():
    result = command([SLURM / 'scontrol', 'show', 'node', '-o'], timeout=20)
    if result.returncode:
        return False, f'scontrol exit {result.returncode}: {result.stderr[-200:]}'
    found = {}
    for line in result.stdout.splitlines():
        name = re.search(r'\bNodeName=(\S+)', line)
        state = re.search(r'\bState=(\S+)', line)
        gres = re.search(r'\bGres=(\S+)', line)
        if name and name.group(1) in NODES:
            found[name.group(1)] = (state.group(1) if state else '',
                                    gres.group(1) if gres else '')
    bad = [(n, found.get(n)) for n in NODES
           if n not in found or found[n][0] != 'IDLE'
           or ':8' not in found[n][1]]
    return not bad, f'{len(found)}/64 nodes; unavailable={bad[:8]}'


def wait_for_fleet():
    last = None
    while True:
        stats = host_stats()
        ok, note = all_nodes_idle()
        guard = stats['cluster_free_bytes'] >= 50 * 1024**3 and stats['mem_available_bytes'] >= 4 * 1024**3
        if ok and guard:
            event('preflight_pass', nodes=note, **stats)
            check_hca_eligibility()
            return
        reason = {'nodes': note, 'resources': stats}
        if reason != last:
            event('preflight_wait', **reason)
            last = reason
        time.sleep(60)


def check_hca_eligibility():
    evidence = SUITE / f'hca-eligibility-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.json'
    result = command([sys.executable, ROOT / 'check_32hca_eligibility.py',
                      '--all64', '--json-out', evidence], timeout=90)
    if result.returncode:
        raise RuntimeError(f'32-HCA fleet eligibility failed; {evidence}: {result.stdout[-1200:]} {result.stderr[-300:]}')
    report = json.loads(evidence.read_text())
    if set(report['required_hcas']) != set(HCA_NAMES) or len(report['eligible_nodes']) != 64:
        raise RuntimeError(f'32-HCA eligibility does not match suite policy: {evidence}')
    event('hca_eligibility_pass', nodes=64, hcas=32, evidence=str(evidence))


def scontrol_job(job):
    result = command([SLURM / 'scontrol', 'show', 'job', '-o', job], timeout=15)
    return result.stdout.strip() if result.returncode == 0 else ''


def field(line, key):
    match = re.search(r'(?:^|\s)' + re.escape(key) + r'=(\S+)', line)
    return match.group(1) if match else None


def submit(task):
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if hard < 65535:
        raise RuntimeError(f'nofile hard limit {hard} is below 65535')
    resource.setrlimit(resource.RLIMIT_NOFILE, (65535, hard))
    args = [INSTALL / 'llmb-run', 'submit', '-w', task['workload'],
            '--model-size', task['size'], '--dtype', task['dtype'], '--scale', '512',
            '--slurm-arg', 'hold']
    for key, value in ENV.items():
        args += ['--env', f'{key}={value}']
    result = command(args, cwd=INSTALL, timeout=180)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    (SUITE / f'submit-{task["key"]}-{stamp}.log').write_text(result.stdout + '\n' + result.stderr)
    match = re.search(r'jobid=(\d+)', result.stdout)
    if result.returncode or not match:
        raise RuntimeError(f'llmb-run submit failed ({result.returncode}); see submit log {stamp}')
    job = int(match.group(1))
    status = scontrol_job(job)
    if field(status, 'JobState') != 'PENDING' or field(status, 'Reason') != 'JobHeldUser':
        raise RuntimeError(f'job {job} not held: {status[:500]}')
    event('submitted_held', key=task['key'], job_id=job)
    return job, status


def generated_paths(status, task, job):
    script_path = field(status, 'Command')
    if not script_path:
        raise RuntimeError(f'job {job}: missing Command path')
    script = Path(script_path).resolve()
    expected = (INSTALL / 'workloads' / task['workload'] / 'experiments').resolve()
    if expected not in script.parents or not script.is_file():
        raise RuntimeError(f'job {job}: unexpected generated script {script}')
    content = script.read_text()
    for key in ENV:
        if not re.search(r'^export ' + re.escape(key) + r'=', content, re.M):
            raise RuntimeError(f'job {job}: {key} absent from sbatch exports')
    srun = next((line for line in content.splitlines() if line.startswith('srun --output ')), None)
    if not srun:
        raise RuntimeError(f'job {job}: no srun output in generated script')
    container_env = re.search(r'--container-env\s+(\S+)', srun)
    if not container_env or not set(ENV).issubset(set(container_env.group(1).split(','))):
        raise RuntimeError(f'job {job}: required environment not passed to container')
    log_template = re.search(r'^srun --output\s+(\S+)', srun).group(1)
    if not log_template.startswith(str(expected) + '/') or not log_template.endswith('.out'):
        raise RuntimeError(f'job {job}: unexpected output template {log_template}')
    log = log_template.replace('%j', str(job)).replace('${SLURM_RESTART_COUNT:-0}', '0')
    if '$' in log or '%' in log:
        raise RuntimeError(f'job {job}: unexpanded log template {log}')
    experiment = script.parent
    if not (experiment / '_CONFIG').is_file():
        raise RuntimeError(f'job {job}: generated experiment lacks _CONFIG')
    return experiment, log


def stage(job, experiment):
    archive = ROOT / f'job{job}-stage.tar.gz'
    result = command(['tar', '-czf', archive, '-C', experiment.parent, experiment.name], timeout=120)
    if result.returncode:
        raise RuntimeError(f'job {job}: tar failed: {result.stderr[-500:]}')
    result = command([sys.executable, ROOT / 'stage_held_job.py', job, experiment], timeout=300)
    if result.returncode:
        raise RuntimeError(f'job {job}: staging failed; held job preserved: {result.stdout[-1000:]} {result.stderr[-500:]}')
    summary = json.loads((ROOT / f'job{job}-staging.json').read_text())
    if summary.get('staged') != 64 or summary.get('failures'):
        raise RuntimeError(f'job {job}: stage summary is not 64/64')
    event('staged', job_id=job, nodes=64, sha256=summary['archive_sha256'])


def archive_outputs(job, experiment, batch_host):
    if batch_host not in NODES:
        raise RuntimeError(f'job {job}: invalid batch host {batch_host}')
    dest = LOGROOT / f'job{job}-logs'
    dest.mkdir(parents=True, exist_ok=True)
    # The generated experiment is node-local. List paths on the batch host and
    # copy every stdout file; no deletion of remote logs or staged evidence.
    listing = command(['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config',
                       '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                       '-o', 'ConnectTimeout=6', batch_host,
                       f'find {experiment} -type f -name "*.out" -print'], timeout=30)
    if listing.returncode:
        raise RuntimeError(f'job {job}: remote log list failed: {listing.stderr[-500:]}')
    files = [Path(p) for p in listing.stdout.splitlines() if p.startswith(str(experiment) + '/')]
    if not files:
        raise RuntimeError(f'job {job}: no .out files on {batch_host}')
    copied = []
    for source in files:
        target = dest / source.name
        result = command(['/usr/bin/scp', '-q', '-F', '/home/nvidia-ssh/.ssh/config',
                          '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                          '-o', 'ConnectTimeout=6', f'{batch_host}:{source}', target], timeout=120)
        if result.returncode:
            raise RuntimeError(f'job {job}: copy {source} failed: {result.stderr[-500:]}')
        copied.append(target)
    # Also expose the same files under the exporter's strict historical path.
    history = ROOT / f'job{job}-logs'
    history.mkdir(parents=True, exist_ok=True)
    for source in copied:
        target = history / source.name
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
    main = [p for p in copied if p.name.startswith('log-') and f'_{job}_' in p.name]
    if not main:
        main = [p for p in copied if p.name.startswith('log-')]
    if not main:
        raise RuntimeError(f'job {job}: no rank stdout among {len(copied)} .out files')
    selected = max(main, key=lambda p: p.stat().st_size)
    return selected, copied


def get_exit_code(batch_log):
    if not batch_log or not batch_log.is_file():
        return None
    text = batch_log.read_text(errors='replace')[-65536:]
    matches = re.findall(r'job exited with code\s+(\d+)', text)
    return int(matches[-1]) if matches else None


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def poll_job(job, log_path):
    last_state = None
    batch_host = None
    missing = 0
    gate = RuntimeGate(NODES, HCA_NAMES)
    offset = 0
    read_failures = 0
    running_since = None
    last_progress = 0
    gate_pass_announced = False
    gate_failure = None
    while True:
        status = scontrol_job(job)
        state = field(status, 'JobState') if status else None
        host = field(status, 'BatchHost') if status else None
        if host in NODES:
            batch_host = host
        if state and state != last_state:
            event('job_state', job_id=job, state=state, batch_host=batch_host)
            last_state = state
        if state == 'RUNNING' and batch_host and gate_failure is None:
            running_since = running_since or time.monotonic()
            try:
                delta = read_remote_delta(batch_host, log_path, offset)
                offset = delta['offset']
                for line in delta['lines']:
                    gate.feed(line)
                read_failures = 0
            except Exception as exc:
                read_failures += 1
                if read_failures >= 3:
                    gate_failure = f'NCCL log inaccessible after 3 reads: {exc}'
            summary = gate.summary()
            if summary['passed'] and not gate_pass_announced:
                event('runtime_gate_passed', job_id=job, **summary)
                gate_pass_announced = True
            if gate.errors:
                gate_failure = f'NCCL runtime inventory mismatch: {gate.errors[0]}'
            elif time.monotonic() - running_since > 300 and not summary['passed']:
                gate_failure = (f'NCCL runtime inventory incomplete after 300s: '
                                f'{summary["validated_ranks"]}/{summary["expected_ranks"]} ranks')
            if time.monotonic() - last_progress > 60:
                event('runtime_gate_progress', job_id=job, **summary)
                last_progress = time.monotonic()
            if gate_failure:
                event('runtime_gate_failed', job_id=job, reason=gate_failure, **summary)
                cancelled = command([SLURM / 'scancel', job], timeout=15)
                if cancelled.returncode:
                    event('runtime_gate_cancel_error', job_id=job, stderr=cancelled.stderr[-300:])
        elif state == 'RUNNING' and not batch_host and running_since is None:
            running_since = time.monotonic()
        elif state == 'RUNNING' and not batch_host and time.monotonic() - running_since > 30 and gate_failure is None:
            gate_failure = 'Slurm RUNNING without a valid batch host after 30s'
            event('runtime_gate_failed', job_id=job, reason=gate_failure)
            command([SLURM / 'scancel', job], timeout=15)
        if state in ('FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED', 'COMPLETED'):
            return state, batch_host, gate_failure
        if not status:
            missing += 1
            if missing >= 3:
                return 'REMOVED_FROM_CONTROLLER', batch_host, gate_failure
        else:
            missing = 0
        time.sleep(5)


def run_one(task, held_job=None):
    wait_for_fleet()
    if held_job is None:
        job, status = submit(task)
    else:
        job = held_job
        status = scontrol_job(job)
        if field(status, 'JobState') != 'PENDING' or field(status, 'Reason') != 'JobHeldUser':
            raise RuntimeError(f'job {job} is not held: {status[:500]}')
        name = (field(status, 'JobName') or '').replace('-', '_')
        if task['workload'].replace('-', '_') not in name or task['dtype'] not in name:
            raise RuntimeError(f'job {job} does not match {task["key"]}')
        event('resuming_held', job_id=job, key=task['key'])
    try:
        experiment, log = generated_paths(status, task, job)
        stage(job, experiment)
    except Exception as exc:
        event('held_setup_failure', job_id=job, key=task['key'], error=str(exc))
        raise
    manifest = {'job_id': job, 'workload': f'{task["full_name"]}_{task["dtype"]}',
                'gpus': 512, 'batch_host': NODES[0], 'log_path': log,
                'experiment': str(experiment), 'submitted_utc': utc(),
                'diagnostic': '32 RoCEv2 HCAs per node; host eligibility and per-rank NCCL runtime gates required',
                'transport_interface': 'enp57s0f0np0', 'hca': HCA,
                'submit_nofile_soft': 65535, 'nccl_env': ENV, 'suite_key': task['key']}
    atomic_json(ACTIVE, manifest)
    released = command([SLURM / 'scontrol', 'release', job], timeout=15)
    if released.returncode:
        raise RuntimeError(f'job {job}: release failed: {released.stderr[-500:]}')
    event('released', job_id=job, key=task['key'], experiment=str(experiment))
    final, batch_host, gate_failure = poll_job(job, log)
    batch_host = batch_host or NODES[0]
    archive_error = None
    try:
        archive_log, outputs = archive_outputs(job, experiment, batch_host)
    except Exception as exc:
        archive_error = str(exc)
        archive_log, outputs = None, []
    batch_log = next((p for p in outputs if p.name.startswith('sbatch_')), None)
    exit_code = get_exit_code(batch_log)
    if final == 'REMOVED_FROM_CONTROLLER':
        final = 'COMPLETED' if exit_code == 0 else 'FAILED' if exit_code is not None else 'UNKNOWN'
    if exit_code not in (None, 0) and final == 'COMPLETED':
        final = 'FAILED'
    runtime_gate = None
    if archive_log:
        checker = RuntimeGate(NODES, HCA_NAMES)
        checker.feed_file(archive_log)
        runtime_gate = checker.summary()
        if final == 'COMPLETED' and not runtime_gate['passed'] and not gate_failure:
            gate_failure = (f'archived NCCL inventory incomplete: '
                            f'{runtime_gate["validated_ranks"]}/{runtime_gate["expected_ranks"]} ranks; '
                            f'errors={runtime_gate["errors"][:1]}')
    if gate_failure:
        final = 'RUNTIME_GATE_FAILED'
    record = {**manifest, 'batch_host': batch_host,
              'log_path': str(archive_log) if archive_log else log,
              'archive_dir': str(LOGROOT / f'job{job}-logs'),
              'final_state': final, 'exit_code': exit_code,
              'runtime_gate': runtime_gate, 'runtime_gate_failure': gate_failure,
              'completed_utc': utc(),
              'qualification_status': '512-GPU recipe with 32-HCA host and NCCL runtime gates; fabric quality reported separately'}
    if archive_log:
        record['log_sha256'] = file_sha256(archive_log)
    if archive_error:
        record['failure'] = f'archive failed: {archive_error}'
        record['archive_error'] = archive_error
    elif final != 'COMPLETED':
        record['failure'] = gate_failure or f'Slurm final state {final}; batch exit code {exit_code}'
    atomic_json(JOBS / f'job{job}.json', record)
    if ACTIVE.exists() and json.loads(ACTIVE.read_text()).get('job_id') == job:
        ACTIVE.unlink()
    event('job_done', job_id=job, key=task['key'], state=final,
          exit_code=exit_code, archive_error=archive_error)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='print the official queue; no submissions')
    parser.add_argument('--resume-held-job', type=int, help='resume the first incomplete recipe from this held Slurm job')
    parser.add_argument('--priority-failed-key', help='retry this failed recipe before other backlog attempts')
    args = parser.parse_args()
    queue = official_queue()
    if args.plan:
        print(json.dumps(queue, indent=2))
        return
    SUITE.mkdir(parents=True, exist_ok=True)
    lock = (SUITE / 'runner.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('suite runner already active')
    if ACTIVE.exists():
        raise SystemExit(f'{ACTIVE} exists; reconcile the active job before starting suite')
    state = json.loads(STATE.read_text()) if STATE.exists() else {'completed_keys': [], 'results': {}}
    if args.priority_failed_key and state['results'].get(args.priority_failed_key, {}).get('final_state') == 'COMPLETED':
        raise SystemExit(f'{args.priority_failed_key} is already completed')
    if args.resume_held_job is not None:
        pending = next((task for task in queue if task['key'] not in state['completed_keys']), None)
        if pending is None:
            raise SystemExit('no incomplete recipe to resume')
        status = scontrol_job(args.resume_held_job)
        if field(status, 'JobState') != 'PENDING' or field(status, 'Reason') != 'JobHeldUser':
            raise SystemExit(f'job {args.resume_held_job} is not held')
        event('resume_held_requested', job_id=args.resume_held_job, key=pending['key'])
    stop = threading.Event()
    profiler = threading.Thread(target=profile_loop, args=(stop,), daemon=True)
    profiler.start()
    try:
        failed = [task for task in queue if task['key'] in state['results']
                  and state['results'][task['key']].get('final_state') != 'COMPLETED']
        if args.priority_failed_key:
            priority = next((task for task in failed if task['key'] == args.priority_failed_key), None)
            if priority is None:
                raise SystemExit(f'{args.priority_failed_key} is not a recorded failed recipe')
            failed.remove(priority)
            failed.insert(0, priority)
        pending = [task for task in queue if task['key'] not in state['completed_keys']]
        for task in failed + pending:
            existing_failure = task['key'] in state['results'] and state['results'][task['key']].get('final_state') != 'COMPLETED'
            try:
                result = run_one(task, args.resume_held_job)
                args.resume_held_job = None
            except Exception as exc:
                event('runner_halted', key=task['key'], error=str(exc))
                raise
            if task['key'] not in state['completed_keys']:
                state['completed_keys'].append(task['key'])
            state['results'][task['key']] = {'job_id': result['job_id'],
                                             'final_state': result['final_state']}
            atomic_json(STATE, state)
            if result.get('archive_error'):
                raise RuntimeError(f'job {result["job_id"]}: archive failed; suite stopped')
            if result.get('runtime_gate_failure'):
                raise RuntimeError(f'job {result["job_id"]}: {result["runtime_gate_failure"]}; suite stopped')
            if result['final_state'] != 'COMPLETED':
                if existing_failure:
                    event('retry_failed_halt', job_id=result['job_id'], key=task['key'])
                    raise RuntimeError(f'{task["key"]} failed again in job {result["job_id"]}; investigate before next model')
                event('immediate_retry', job_id=result['job_id'], key=task['key'])
                retry = run_one(task)
                state['results'][task['key']] = {'job_id': retry['job_id'],
                                                 'final_state': retry['final_state']}
                atomic_json(STATE, state)
                if retry.get('archive_error') or retry['final_state'] != 'COMPLETED':
                    event('retry_failed_halt', job_id=retry['job_id'], key=task['key'])
                    raise RuntimeError(f'{task["key"]} retry failed in job {retry["job_id"]}; investigate before next model')
        event('suite_done', jobs=len(state['completed_keys']))
    finally:
        stop.set()
        profiler.join(timeout=2)


if __name__ == '__main__':
    main()
