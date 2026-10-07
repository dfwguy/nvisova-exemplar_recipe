"""Maintain the 256-GPU suite heartbeat and resume checkpoint every 15 seconds."""
import datetime as dt
import json
from pathlib import Path
import time
import update_exemplar_memory as memory
import run_b300_suite_256 as runner

ROOT = Path('/cluster/OVA/Exemplar')
SUITE = Path('/cluster/OVA/exemplar/logs/suite-256')
memory.SUITE = SUITE
memory.STATUS = SUITE / 'runner-status.json'
memory.QUEUE = [(t['full_name'], t['dtype']) for t in runner.official_queue()]
original_process_for = memory.process_for
def process_for(path):
    if path == ROOT / 'run_b300_suite.py':
        path = ROOT / 'run_b300_suite_256.py'
    return original_process_for(path)
memory.process_for = process_for
while True:
    state = memory.load_json(SUITE / 'state.json', {'completed_keys': [], 'results': {}})
    active = memory.load_json(ROOT / 'active-job.json', None)
    status = memory.runner_status(state, active)
    status['scale'] = 256
    status['suite_dir'] = str(SUITE)
    content = json.dumps(status, indent=2) + '\n'
    memory.atomic(memory.STATUS, content)
    # The existing dashboard exporter reads this canonical heartbeat path.
    memory.atomic(Path('/cluster/OVA/exemplar/logs/suite/runner-status.json'), content)
    checkpoint = memory.load_json(memory.MACHINE, {})
    archived = {entry['job_id']: entry for entry in checkpoint.get('runs', [])}
    for path in (ROOT / 'jobs').glob('job*.json'):
        record = memory.load_json(path, {})
        if record.get('run_tag') == 'b300-scale256':
            archived[record['job_id']] = {
                'job_id': record['job_id'], 'workload': record.get('workload'),
                'state': record.get('final_state'), 'gpus': 256,
                'completed_utc': record.get('completed_utc'),
                'log_path': record.get('log_path'), 'archive_dir': record.get('archive_dir'),
                'failure': record.get('failure'), 'runtime_gate': record.get('runtime_gate'),
                **memory.log_progress(Path(record.get('log_path', '/nonexistent')))}
    checkpoint.update(updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                      requested_scale=256, requested_nodes=32, current_job=active,
                      runner_script=str(ROOT / 'run_b300_suite_256.py'),
                      tmux_session='exemplar-suite-256', runner_log=str(SUITE / 'runner.log'),
                      runner_status=status, runner_status_file=str(memory.STATUS),
                      suite_state=str(SUITE / 'state.json'),
                      runs=[archived[key] for key in sorted(archived)],
                      completed_attempt_keys=state['completed_keys'],
                      pending_recipe_keys=[t['key'] for t in runner.official_queue()
                                           if t['key'] not in state['completed_keys']],
                      current_cohort_file=str(ROOT / 'cohort256-nodes.txt'),
                      current_preflight_file=str(ROOT / 'cohort256-preflight.json'))
    checkpoint['current_preflight_ready'] = memory.load_json(
        ROOT / 'cohort256-preflight.json', {}).get('ready', False)
    memory.atomic(memory.MACHINE, json.dumps(checkpoint, indent=2) + '\n')
    header = '\n## Current 256-GPU suite heartbeat\n'
    previous = memory.MEMORY.read_text().split(header, 1)[0]
    text = (header + '\nUpdated: ' + status['checked_utc'] + '\n\n'
            + 'Runner: `tmux attach -t exemplar-suite-256`; state: `' + str(SUITE / 'state.json') + '`.\n'
            + 'Phase: ' + status['phase'] + '; completed: ' + str(status['completed_keys'])
            + '/13; active job: ' + str(status['active_job_id']) + '.\n'
            + '32-node cohort: `/cluster/OVA/Exemplar/cohort256-nodes.txt`; gate: `/cluster/OVA/Exemplar/cohort256-preflight.json`.\n'
            + 'Queue begins with Nemotron-H 56B FP8; failed recipes retry immediately once, then halt.\n'
            + (('Alert: ' + str(status['alert_message']) + '\n') if status['alert'] else ''))
    memory.atomic(memory.MEMORY, previous + text)
    time.sleep(15)
