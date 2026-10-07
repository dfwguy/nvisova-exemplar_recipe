#!/usr/bin/env python3
"""Bounded live Slurm and recipe-log metrics for the current Exemplar run."""
import json
import re
import shlex
import subprocess
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MANIFEST = Path('/cluster/OVA/Exemplar/active-job.json')
HISTORY = Path('/cluster/OVA/Exemplar/jobs')
SUITE_STATUS = Path('/cluster/OVA/exemplar/logs/suite/runner-status.json')
HISTORY_CACHE = {}
ACTIVE_PROGRESS = {}
SCONTROL = '/opt/slurm/25.11.2/bin/scontrol'
NODE = re.compile(r'^od1-edc003-b300-0(?:[0-5][0-9]|6[0-4])$')
ITER = re.compile(r'iteration\s+(\d+)\s*/\s*(\d+)', re.I)
TIME = re.compile(r'elapsed time per iteration \(ms\):\s*([\d.]+)', re.I)
FLOPS = re.compile(r'([\d.]+)\s*(?:MODEL_TFLOP/s/GPU|TFLOP/s/GPU)|TFLOPS_per_GPU:\s*([\d.]+)', re.I)

def quote(value):
    return json.dumps(str(value), ensure_ascii=True)

def submitted_metric(jid, data):
    stamp = datetime.fromisoformat(data['submitted_utc'].replace('Z', '+00:00')).timestamp()
    return f'stn_exemplar_submitted_timestamp_seconds{{job_id={quote(jid)}}} {stamp:.3f}'

def run(args, timeout=8):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, p.stdout[:300000], p.stderr[:1000]

def parsed_log(jid, output):
    lines = []
    relevant = deque(maxlen=6)
    recent = deque(maxlen=6)
    iteration = step = flops = None
    for line in output.splitlines() if isinstance(output, str) else output:
        clean = line.strip()[:300]
        if clean:
            recent.append(clean)
        lower = line.lower()
        match = ITER.search(line) if 'iteration' in lower else None
        if match:
            iteration = int(match.group(1))
            timing = TIME.search(line)
            if timing:
                step = float(timing.group(1)) / 1000
        flop_match = FLOPS.search(line) if 'tflop' in lower else None
        if flop_match:
            flops = float(flop_match.group(1) or flop_match.group(2))
        if match or flop_match or any(marker in lower for marker in ('error:', 'traceback', 'nccl warn', 'job exited with code')):
            relevant.append(clean)
    if iteration is not None:
        lines.append(f'stn_exemplar_iteration{{job_id={quote(jid)}}} {iteration}')
    if step is not None:
        lines.append(f'stn_exemplar_step_time_seconds{{job_id={quote(jid)}}} {step}')
    if flops is not None:
        lines.append(f'stn_exemplar_raw_tflops_per_gpu{{job_id={quote(jid)}}} {flops}')
    if not relevant:
        seen = set()
        unique = []
        for line in reversed(recent):
            message = re.sub(r'^\[[WE]\d+\s+[^]]+\]\s*', '', line)
            if message and message not in seen:
                unique.append(message)
                seen.add(message)
            if len(unique) == 6:
                break
        relevant = list(reversed(unique))
    for index, line in enumerate(relevant):
        lines.append(f'stn_exemplar_recent_log_line{{job_id={quote(jid)},slot={quote(index)},line={quote(line)}}} 1')
    return lines

def historical_lines(active_jid):
    lines = []
    for path in sorted(HISTORY.glob('job*.json'))[-100:]:
        data = json.loads(path.read_text())
        jid = int(data['job_id'])
        if jid == active_jid:
            continue
        log = Path(data['log_path'])
        allowed = (f'/cluster/OVA/Exemplar/job{jid}-logs/',
                   f'/cluster/OVA/exemplar/logs/job{jid}-logs/')
        if not str(log).startswith(allowed) or not log.is_file():
            continue
        labels = f'{{job_id={quote(jid)},workload={quote(data["workload"])}}}'
        state = data.get('final_state', 'UNKNOWN')
        lines += [f'stn_exemplar_job_info{labels} 1',
                  submitted_metric(jid, data),
                  f'stn_exemplar_target_gpus{labels} {int(data["gpus"])}',
                  f'stn_exemplar_job_state{{job_id={quote(jid)},state={quote(state)}}} 1',
                  f'stn_exemplar_job_running{labels} 0',
                  f'stn_exemplar_log_read_success{labels} 1']
        if data.get('failure'):
            lines.append(f'stn_exemplar_failure_info{{job_id={quote(jid)},reason={quote(data["failure"])}}} 1')
        if data.get('diagnostic'):
            lines.append(f'stn_exemplar_run_configuration_info{{job_id={quote(jid)},description={quote(data["diagnostic"])}}} 1')
        score_path = Path(data.get('score_window_path', ''))
        if score_path == Path(f'/cluster/OVA/Exemplar/job{jid}-score-window.json') and score_path.is_file():
            score = json.loads(score_path.read_text())
            if score.get('job_id') == jid and score.get('window_steps') == '35-44':
                lines.append(f'stn_exemplar_window_mean_step_seconds{{job_id={quote(jid)}}} {float(score["mean_step_seconds"]):.6f}')
                lines.append(f'stn_exemplar_window_mean_raw_tflops_per_gpu{{job_id={quote(jid)}}} {float(score["mean_raw_tflops_per_gpu"]):.3f}')
        stat = log.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        if HISTORY_CACHE.get(str(log), (None, None))[0] != key:
            with log.open('rb') as source:
                # The final recipe steps can precede verbose NCCL teardown by
                # ~0.5 MiB. A bounded 2 MiB tail keeps refresh fast under the
                # service CPU cap while retaining those final printed values.
                start = max(0, stat.st_size - 2 * 1024 * 1024)
                source.seek(start)
                if start:
                    source.readline()
                parsed = parsed_log(jid, source.read().decode('utf-8', errors='replace'))
            HISTORY_CACHE[str(log)] = (key, parsed)
        lines += HISTORY_CACHE[str(log)][1]
    return lines


def suite_status_lines(now):
    """Expose a local runner halt and detect failure of the status watcher itself."""
    try:
        status = json.loads(SUITE_STATUS.read_text())
        checked = datetime.fromisoformat(status['checked_utc'].replace('Z', '+00:00')).timestamp()
        if now - checked > 90:
            code, reason = 'STATUS_HEARTBEAT_STALE', f'Suite status heartbeat is {now-checked:.0f}s old'
        elif status.get('alert'):
            code = str(status.get('alert_code') or 'RUNNER_ALERT')[:80]
            reason = str(status.get('alert_message') or code)[:300]
        else:
            code, reason = 'none', ''
        pending = max(0, int(status.get('pending_keys', 0)))
        running = 1 if status.get('runner_pid') else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checked, pending, running = 0, 0, 0
        code, reason = 'STATUS_UNAVAILABLE', f'Suite status unavailable: {type(exc).__name__}'
    alert = 0 if code == 'none' else 1
    lines = [f'stn_exemplar_suite_runner_alert{{code={quote(code)}}} {alert}',
             f'stn_exemplar_suite_runner_running {running}',
             f'stn_exemplar_suite_pending_jobs {pending}',
             f'stn_exemplar_suite_status_timestamp_seconds {checked:.3f}']
    if alert:
        lines.append(f'stn_exemplar_suite_runner_alert_info{{code={quote(code)},reason={quote(reason)}}} 1')
    return lines

def collect():
    now = time.time()
    lines = [f'stn_exemplar_collector_timestamp_seconds {now:.3f}', *suite_status_lines(now)]
    if not MANIFEST.exists():
        return '\n'.join(lines + ['stn_exemplar_configured 0'] + historical_lines(None)) + '\n'
    data = json.loads(MANIFEST.read_text())
    jid = int(data['job_id'])
    if jid < 1 or jid > 999999999:
        raise ValueError('invalid job id')
    host = data.get('batch_host', '')
    log = str(data['log_path'])
    if not NODE.fullmatch(host) or not log.startswith('/cluster/OVA/Exemplar/install/workloads/') or not log.endswith('.out'):
        raise ValueError('unapproved log source')
    labels = f'{{job_id={quote(jid)},workload={quote(data.get("workload", "unknown"))}}}'
    lines += [f'stn_exemplar_configured 1', f'stn_exemplar_job_info{labels} 1',
              submitted_metric(jid, data), f'stn_exemplar_target_gpus{labels} {int(data.get("gpus", 0))}']
    if data.get('diagnostic'):
        lines.append(f'stn_exemplar_run_configuration_info{{job_id={quote(jid)},description={quote(data["diagnostic"])}}} 1')
    rc, status, error = run([SCONTROL, 'show', 'job', '-o', str(jid)])
    state = re.search(r'\bJobState=([A-Z_]+)', status)
    if state:
        value = state.group(1)
        lines += [f'stn_exemplar_job_state{{job_id={quote(jid)},state={quote(value)}}} 1',
                  f'stn_exemplar_job_running{labels} {1 if value == "RUNNING" else 0}']
    else:
        lines.append(f'stn_exemplar_job_state_read_success{labels} 0')
    command = 'tail -c 131072 ' + shlex.quote(log)
    rc, output, error = run(['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config', '-o', 'BatchMode=yes',
                             '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=4', host, command], 7)
    if rc:
        lines.append(f'stn_exemplar_log_read_success{labels} 0')
    else:
        lines.append(f'stn_exemplar_log_read_success{labels} 1')
        parsed = parsed_log(jid, output)
        progress = ACTIVE_PROGRESS.setdefault(jid, {})
        prefixes = ('stn_exemplar_iteration{', 'stn_exemplar_step_time_seconds{',
                    'stn_exemplar_raw_tflops_per_gpu{')
        present = set()
        for line in parsed:
            for prefix in prefixes:
                if line.startswith(prefix):
                    progress[prefix] = line
                    present.add(prefix)
        lines += [progress[prefix] for prefix in prefixes if prefix in progress and prefix not in present]
        lines += parsed
    lines += historical_lines(jid)
    return '\n'.join(lines) + '\n'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/metrics':
            self.send_error(404)
            return
        with self.server.lock:
            body = self.server.body.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

def refresh(server):
    while True:
        try:
            body = collect()
        except Exception:
            traceback.print_exc()
            body = f'stn_exemplar_collector_timestamp_seconds {time.time():.3f}\nstn_exemplar_collector_success 0\n'
        else:
            body += 'stn_exemplar_collector_success 1\n'
        with server.lock:
            server.body = body
        time.sleep(5)

if __name__ == '__main__':
    server = ThreadingHTTPServer(('172.21.0.1', 19135), Handler)
    server.lock = threading.Lock()
    server.body = 'stn_exemplar_collector_success 0\n'
    threading.Thread(target=refresh, args=(server,), daemon=True).start()
    server.serve_forever()
