#!/usr/bin/env bash
# Executed in the host namespace by the persistent Docker boot bootstrap.
set -euo pipefail

base=/stn-disk/exemplar/nvis-p2p
restore=/stn-disk/exemplar/node-bootstrap/restore.sh
mountpoint -q /stn-disk
test -x "$restore"
test -x "$base/bin/dfdaemon"
test -x "$base/bin/dfstore-sync-catalog.sh"
test -r "$base/peer.yaml"
test -r "$base/secrets/dfstore-readonly.env"
install -d -m 0755 "$base/run" "$base/logs"
exec 9>"$base/run/boot-activate.lock"
flock -n 9 || exit 0

# The release is local and checksummed. It restores the disposable live root
# only when its recorded boot ID differs from the current one.
"$restore"
for name in nvis-p2p-peer.service nvis-p2p-catalog-sync.service nvis-p2p-catalog-sync.timer; do
  install -m 0644 "$base/systemd/$name" "/etc/systemd/system/$name"
done
systemctl daemon-reload
systemctl enable --now nvis-p2p-peer.service
systemctl enable --now nvis-p2p-catalog-sync.timer
systemctl is-active --quiet nvis-p2p-peer.service
printf 'NVIS_P2P_BOOT_READY host=%s boot_id=%s\n' "$(hostname -s)" "$(cat /proc/sys/kernel/random/boot_id)"
