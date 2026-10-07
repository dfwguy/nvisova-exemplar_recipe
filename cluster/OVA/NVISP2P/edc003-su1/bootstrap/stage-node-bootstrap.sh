#!/usr/bin/env bash
# Validate and stage the persistent Exemplar v4 release on one node.
set -euo pipefail

base=/stn-disk/exemplar/nvis-p2p
incoming="$base/.incoming"
archive="$incoming/nvis-p2p-exemplar-root-release-v4.tar.gz"
expected_archive_sha=b4680fff0da8c4729c533947054c54eb93b5446bbfd839d3d9fa800d0508a52e
expected_boot_sha=$(cat "$incoming/boot-activate.sha256")
releases=/stn-disk/exemplar/node-bootstrap/releases
release="$releases/2026-09-24-v4"

[[ $EUID -eq 0 ]]
mountpoint -q /stn-disk
printf '%s  %s\n' "$expected_archive_sha" "$archive" | sha256sum -c --status
printf '%s  %s\n' "$expected_boot_sha" "$incoming/boot-activate.sh" | sha256sum -c --status
install -d -m 0755 "$releases" "$base/bin"
if [[ ! -d $release ]]; then
  tmp=$(mktemp -d "$releases/.v4.XXXXXXXX")
  trap 'rm -rf -- "$tmp"' EXIT
  tar -xzf "$archive" -C "$tmp"
  (cd "$tmp/release-v4" && sha256sum -c SHA256SUMS >/dev/null)
  mv "$tmp/release-v4" "$release"
  rmdir "$tmp"
  trap - EXIT
fi
(cd "$release" && sha256sum -c SHA256SUMS >/dev/null)
install -m 0755 "$incoming/boot-activate.sh" "$base/bin/boot-activate.sh"
ln -sfn releases/2026-09-24-v4/restore-fleet.sh \
  /stn-disk/exemplar/node-bootstrap/restore.sh
"$release/restore-fleet.sh" --check
printf 'BOOT_RELEASE_STAGED host=%s release=%s\n' "$(hostname -s)" "$release"
