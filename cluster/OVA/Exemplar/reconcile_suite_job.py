#!/usr/bin/env python3
"""Archive one orphaned Exemplar suite job and commit its suite state.

This does not submit, release, cancel, or requeue Slurm jobs. The default is a
read-only status check; --apply commits after the selected job is terminal.
"""
import argparse
import fcntl
import json
from pathlib import Path
import time

import run_b300_suite as suite

TERMINAL = {'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL',
            'PREEMPTED', 'COMPLETED'}


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def check_manifest(job):
    manifest = load(suite.ACTIVE)
    if not manifest or manifest.get('job_id') != job:
        raise RuntimeError(f'active manifest must identify job {job}')
    key = manifest.get('suite_key')
    if key not in {task['key'] for task in suite.official_queue()}:
        raise RuntimeError(f'job {job}: invalid suite key {key!r}')
    experiment = Path(manifest['experiment']).resolve()
    expected = (suite.INSTALL / 'workloads').resolve()
    if expected not in experiment.parents or not (experiment / '_CONFIG').is_file():
        raise RuntimeError(f'job {job}: invalid or missing experiment {experiment}')
    if manifest.get('batch_host') not in suite.NODES:
        raise RuntimeError(f'job {job}: invalid batch host')
    state = load(suite.STATE) or {'completed_keys': [], 'results': {}}
    previous = state.get('results', {}).get(key)
    if previous and previous.get('job_id') != job:
        raise RuntimeError(f'job {job}: suite key {key} already belongs to {previous}')
    return manifest, state, experiment


def terminal_status(job, wait):
    while True:
        status = suite.scontrol_job(job)
        state = suite.field(status, 'JobState') if status else None
        if state in TERMINAL:
            return state, suite.field(status, 'BatchHost'), status
        if not status:
            return None, None, ''  # accounting may be disabled; infer from archived batch log
        if not wait:
            return state, suite.field(status, 'BatchHost'), status
        print(f'job {job}: {state}; waiting for terminal state', flush=True)
        time.sleep(15)


def reconcile(job, apply, wait):
    suite.SUITE.mkdir(parents=True, exist_ok=True)
    with (suite.SUITE / 'runner.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('suite runner owns the lock; stop it before reconciliation')
        manifest, state, experiment = check_manifest(job)
        final, host, slurm_status = terminal_status(job, wait)
        host = host if host in suite.NODES else manifest['batch_host']
        key = manifest['suite_key']
        existing = load(suite.JOBS / f'job{job}.json')
        if existing and (existing.get('job_id') != job or existing.get('suite_key') != key):
            raise RuntimeError(f'job {job}: existing archive record conflicts with active manifest')
        if not apply:
            print(json.dumps({'job_id': job, 'suite_key': key, 'slurm_state': final or 'NOT_IN_CONTROLLER',
                              'batch_host': host, 'archive_record_exists': bool(existing),
                              'would_commit': bool(final in TERMINAL or existing)}, indent=2))
            return
        if final and final not in TERMINAL:
            raise RuntimeError(f'job {job} is {final}; archive only after terminal state')
        if existing:
            record = existing
            path = Path(record.get('log_path', ''))
            if not path.is_file() or suite.file_sha256(path) != record.get('log_sha256'):
                raise RuntimeError(f'job {job}: existing archive record has missing/mismatched rank log')
        else:
            archived_log, files = suite.archive_outputs(job, experiment, host)
            batch_log = next((p for p in files if p.name.startswith('sbatch_')), None)
            exit_code = suite.get_exit_code(batch_log)
            if not final:
                if exit_code is None:
                    raise RuntimeError(f'job {job}: no controller state or archived batch exit code')
                final = 'COMPLETED' if exit_code == 0 else 'FAILED'
            if final == 'COMPLETED' and exit_code not in (None, 0):
                final = 'FAILED'
            record = {**manifest, 'batch_host': host, 'log_path': str(archived_log),
                      'archive_dir': str(suite.LOGROOT / f'job{job}-logs'),
                      'final_state': final, 'exit_code': exit_code,
                      'completed_utc': suite.utc(),
                      'qualification_status': 'recipe run on 30 fleetwide healthy RoCE ports; 2 node040 ports excluded',
                      'log_sha256': suite.file_sha256(archived_log)}
            if final != 'COMPLETED':
                record['failure'] = f'Slurm final state {final}; batch exit code {exit_code}'
            suite.atomic_json(suite.JOBS / f'job{job}.json', record)
        if key not in state['completed_keys']:
            state['completed_keys'].append(key)
        state.setdefault('results', {})[key] = {'job_id': job, 'final_state': record['final_state']}
        suite.atomic_json(suite.STATE, state)
        if load(suite.ACTIVE).get('job_id') != job:
            raise RuntimeError('active manifest changed during reconciliation; suite state committed')
        suite.ACTIVE.unlink()
        suite.event('job_reconciled', job_id=job, key=key, state=record['final_state'],
                    exit_code=record.get('exit_code'))
        print(json.dumps({'job_id': job, 'suite_key': key, 'final_state': record['final_state'],
                          'exit_code': record.get('exit_code'), 'log_path': record['log_path']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true', help='archive and commit (default: read-only)')
    parser.add_argument('--wait', action='store_true', help='wait for terminal Slurm state')
    args = parser.parse_args()
    reconcile(args.job_id, args.apply, args.wait)


if __name__ == '__main__':
    main()
