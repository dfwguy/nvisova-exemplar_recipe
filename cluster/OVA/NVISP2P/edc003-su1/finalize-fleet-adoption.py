#!/usr/bin/env python3
"""Close the NVIS adoption wave after the sequential two-image hash pass."""
import concurrent.futures
import fcntl
import importlib.util
import json
import pathlib
import subprocess

SITE = pathlib.Path('/cluster/OVA/NVISP2P/edc003-su1')
REPORT = SITE / 'state/fleet-adoption-20260924.json'
spec = importlib.util.spec_from_file_location('nvis_rollout', SITE / 'rollout-existing-images.py')
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


def final_check(host):
    command = (
        'systemctl is-active --quiet nvis-p2p-peer.service && '
        'systemctl is-enabled --quiet nvis-p2p-peer.service && '
        'test -S /stn-disk/exemplar/nvis-p2p/run/dfdaemon.sock && '
        'systemctl start nvis-p2p-catalog-sync.service && '
        'test "$(tail -n 1 /stn-disk/exemplar/nvis-p2p/logs/catalog-sync.log)" = '
        '"NVIS_P2P_SYNC_COMPLETE total=2 ready=2 installed=0 failed=0" && '
        'systemctl enable --now nvis-p2p-catalog-sync.timer >/dev/null && '
        'systemctl is-active --quiet nvis-p2p-catalog-sync.timer && '
        'systemctl is-enabled --quiet nvis-p2p-catalog-sync.timer && '
        'tail -n 1 /stn-disk/exemplar/nvis-p2p/logs/catalog-sync.log'
    )
    return rollout.ssh(host, command, 120)


def main():
    lock = open(SITE / 'state/fleet-mutation.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    records = json.loads(REPORT.read_text())
    host = 'od1-edc003-b300-025'
    records[host]['hostname_resolution'] = {
        'status': 'drift',
        'detail': 'After prior reboot, local getent ahostsv4 hostname returned no address; trusted SSH and configured 10.6.33.25 interface were intact. Installer validates interface address against hostname suffix.'
    }
    rollout.write(records)
    if records[host]['peer']['status'] != 'ok':
        records[host]['peer'] = {'status': 'ok', 'detail': rollout.install(host)}
        rollout.write(records)
    for filename, size, digest in [line.split('\t')[2:] for line in
                                   (SITE / 'catalog/images.tsv').read_text().splitlines()[1:]]:
        if records[host].get(filename, {}).get('status') != 'ok':
            records[host][filename] = {'status': 'ok', 'detail': rollout.adopt(host, filename, size, digest)}
            rollout.write(records)
    ready = [h for h, data in records.items()
             if data.get('peer', {}).get('status') == 'ok' and all(
                 data.get(name, {}).get('status') == 'ok' for name in
                 ('nvidia+nemo+26.04.01.sqsh', 'nvidia+nemo+26.06.01.sqsh'))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(final_check, h): h for h in ready}
        for future in concurrent.futures.as_completed(futures):
            h = futures[future]
            try:
                result = future.result()
                records[h]['sync'] = {'status': 'ok', 'detail': result}
                records[h]['timer'] = {'status': 'ok', 'detail': 'enabled active'}
                print(f'FINAL {h} OK {result}', flush=True)
            except Exception as exc:
                records[h]['sync'] = {'status': 'failed', 'detail': str(exc)}
                print(f'FINAL {h} FAILED {exc}', flush=True)
            rollout.write(records)
    print('REPORT', REPORT, flush=True)


if __name__ == '__main__':
    main()
