#!/usr/bin/env python3
"""Validate each Exemplar rank's NCCL RoCE inventory from INIT/NET output.

The gate is deliberately strict: an absent or damaged log line is not evidence
that a rank saw every requested port. It never changes a recipe or fabric state.
"""

import json
import re
import shlex
import subprocess
from pathlib import Path


PREFIX = re.compile(r'(od1-edc003-b300-\d{3}):(\d+):\d+ \[(\d+)\] NCCL INFO ')
USING = re.compile(r'\[(\d+)\](mlx5_\d+):(\d+)/RoCE')
VIRTUAL = re.compile(r'NET/IB : Made virtual device \[\d+\] name=([\w+]+) speed=\d+ ndevs=(\d+)')
TAIL = r'''
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); pos = int(sys.argv[2]); cap = 8 * 1024 * 1024
if not p.is_file():
    print(json.dumps({'exists': False, 'offset': pos, 'lines': []})); sys.exit(0)
with p.open('rb') as stream:
    size = stream.seek(0, 2)
    if pos > size: pos = 0
    stream.seek(pos)
    block = stream.read(min(cap, size - pos))
    end = block.rfind(b'\n')
    if end >= 0:
        block = block[:end + 1]
    else:
        block = b''
    pos += len(block)
lines = [line for line in block.decode('utf-8', 'replace').splitlines()
         if 'NCCL INFO NET/IB : Using ' in line or
            'NCCL INFO NET/IB : Made virtual device ' in line]
print(json.dumps({'exists': True, 'offset': pos, 'lines': lines}))
'''


class RuntimeGate:
    def __init__(self, nodes, hca_names):
        self.nodes = set(nodes)
        self.expected = set(hca_names)
        if len(self.expected) != 32:
            raise ValueError(f'runtime gate requires 32 distinct HCAs, got {len(self.expected)}')
        self.ranks = {}
        self.errors = []
        self.lines_seen = 0

    def feed(self, line):
        if 'NCCL INFO NET/IB : ' not in line:
            return
        match = PREFIX.search(line)
        if not match or match.group(1) not in self.nodes:
            return
        host, pid, gpu = match.group(1), match.group(2), int(match.group(3))
        if not 0 <= gpu < 8:
            self.errors.append(f'{host} pid={pid}: unexpected GPU index {gpu}')
            return
        identity = (host, gpu)
        record = self.ranks.setdefault(identity, {'pids': set(), 'using': False, 'groups': set()})
        record['pids'].add(pid)
        self.lines_seen += 1
        if 'NET/IB : Using ' in line:
            # An interleaved Slurm line might be damaged; require the completed
            # inventory marker before deciding it is a genuine NCCL inventory.
            body = line.split('NET/IB : Using ', 1)[1]
            if '; OOB ' not in body:
                return
            body = body.split('; OOB ', 1)[0]
            if PREFIX.search(body):
                return  # Slurm interleaved another process's line.
            entries = USING.findall(body)
            indices = [int(i) for i, _, _ in entries]
            names = [name for _, name, _ in entries]
            ports = [port for _, _, port in entries]
            if indices != list(range(32)) or set(names) != self.expected or len(set(names)) != 32 or any(p != '1' for p in ports):
                self.errors.append(f'{host} gpu={gpu} pid={pid}: NCCL Using has {len(entries)} devices; '
                                   f'missing={sorted(self.expected - set(names))}, extra={sorted(set(names) - self.expected)}')
            else:
                record['using'] = True
        elif 'NET/IB : Made virtual device ' in line:
            virtual = VIRTUAL.search(line)
            if not virtual:
                return
            members = tuple(virtual.group(1).split('+'))
            count = int(virtual.group(2))
            if count == 1:
                return  # NCCL first declares individual physical HCAs.
            if count != 4 or len(members) != 4 or len(set(members)) != 4 or not set(members) <= self.expected:
                self.errors.append(f'{host} gpu={gpu} pid={pid}: invalid merged NIC '
                                   f'{virtual.group(1)} ndevs={count}')
            else:
                record['groups'].add(frozenset(members))

    def feed_file(self, path):
        with Path(path).open(errors='replace') as stream:
            for line in stream:
                self.feed(line)

    def summary(self):
        expected_ranks = {(node, gpu) for node in self.nodes for gpu in range(8)}
        completed = set()
        for identity, record in self.ranks.items():
            groups = record['groups']
            union = set().union(*groups) if groups else set()
            if record['using'] and len(groups) == 8 and union == self.expected and sum(map(len, groups)) == 32:
                completed.add(identity)
        missing = sorted(expected_ranks - completed)
        return {'passed': not self.errors and not missing,
                'observed_ranks': len(self.ranks), 'validated_ranks': len(completed),
                'expected_ranks': len(expected_ranks), 'missing_ranks': [f'{h}/gpu{g}' for h, g in missing[:24]],
                'errors': self.errors[:24], 'lines_seen': self.lines_seen}


def read_remote_delta(host, path, offset, timeout=12):
    """Fetch only complete NCCL inventory lines from a node-local Slurm log."""
    path = str(path)
    if not path.startswith('/cluster/OVA/Exemplar/install/workloads/') or not path.endswith('.out'):
        raise ValueError(f'unexpected NCCL log path: {path}')
    remote = f'python3 -c {shlex.quote(TAIL)} {shlex.quote(path)} {offset}'
    result = subprocess.run(['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config',
                             '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=6', host, remote],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'NCCL log read on {host}: ssh exit {result.returncode}: {result.stderr[-250:]}')
    return json.loads(result.stdout)


def read_remote_rank_inventory(host, directory, timeout=12):
    """Read isolated per-process NCCL inventories from one job's mounted directory."""
    directory = str(directory)
    if not directory.startswith('/cluster/OVA/Exemplar/install/workloads/') or '..' in Path(directory).parts:
        raise ValueError(f'unexpected NCCL directory: {directory}')
    script = r'''
import json, pathlib, sys
files = sorted(pathlib.Path(sys.argv[1]).glob('nccl-*.out'))
if len(files) > 256: raise ValueError('too many NCCL process files')
lines = []
for path in files:
    with path.open('rb') as stream:
        block = stream.read(8 * 1024 * 1024)
    end = block.rfind(b'\n')
    if end < 0: continue
    for line in block[:end + 1].decode('utf-8', 'replace').splitlines():
        if 'NCCL INFO NET/IB : Using ' in line or 'NCCL INFO NET/IB : Made virtual device ' in line:
            lines.append(line)
print(json.dumps({'files': len(files), 'lines': lines}))
'''
    remote = f'python3 -c {shlex.quote(script)} {shlex.quote(directory)}'
    result = subprocess.run(['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config',
                             '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=6', host, remote],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'NCCL inventory read on {host}: {result.stderr[-250:]}')
    return json.loads(result.stdout)
