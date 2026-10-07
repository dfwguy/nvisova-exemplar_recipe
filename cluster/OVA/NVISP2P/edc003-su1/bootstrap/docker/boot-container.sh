#!/usr/bin/env bash
set -euo pipefail

while ! mountpoint -q /stn-disk; do sleep 2; done
nsenter --target 1 --mount --uts --ipc --net --pid --root -- \
  /stn-disk/exemplar/nvis-p2p/bin/boot-activate.sh
exec sleep infinity
