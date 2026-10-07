#!/usr/bin/env python3
"""SHA-verified staging of one held Exemplar experiment to a selected 32-node cohort."""

import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id', type=int)
    parser.add_argument('experiment', type=pathlib.Path)
    parser.add_argument('--nodes-file', type=pathlib.Path, required=True)
    parser.add_argument('--archive', type=pathlib.Path, required=True)
    parser.add_argument('--summary', type=pathlib.Path, required=True)
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    if not str(experiment).startswith('/cluster/OVA/Exemplar/install/workloads/') \
            or not (experiment / '_CONFIG').is_file():
        raise SystemExit('invalid generated experiment path')
    if not args.archive.is_file():
        raise SystemExit('stage archive missing')
    nodes = [line.split('#', 1)[0].strip() for line in args.nodes_file.read_text().splitlines()]
    nodes = [node for node in nodes if node]
    approved = {f'od1-edc003-b300-{i:03d}' for i in range(1, 65)}
    if len(nodes) != 32 or len(set(nodes)) != 32 or not set(nodes).issubset(approved):
        raise SystemExit('nodes file must contain 32 unique approved hosts, one per line')
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    remote_archive = f'/tmp/exemplar-256-job{args.job_id}-stage.tar.gz'
    parent = experiment.parent
    remote = ('mkdir -p ' + shlex.quote(str(parent)) + ' && cat > ' + remote_archive +
              ' && echo ' + shlex.quote(digest + '  ' + remote_archive) + ' | sha256sum -c -' +
              ' && tar -xzf ' + remote_archive + ' -C ' + shlex.quote(str(parent)) +
              ' && test -f ' + shlex.quote(str(experiment / '_CONFIG')) +
              ' && rm -f ' + remote_archive)

    def stage(node):
        with args.archive.open('rb') as source:
            result = subprocess.run(
                ['/usr/bin/ssh', '-F', '/home/nvidia-ssh/.ssh/config',
                 '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                 '-o', 'ConnectTimeout=8', node, remote],
                stdin=source, capture_output=True, text=True, timeout=60)
        return node, result.returncode, result.stdout[-200:], result.stderr[-500:]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = sorted(pool.map(stage, nodes))
    failures = [row for row in results if row[1]]
    summary = {'job_id': args.job_id, 'archive_sha256': digest,
               'staged': len(results) - len(failures), 'total': len(results),
               'nodes': sorted(nodes), 'failures': failures}
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
