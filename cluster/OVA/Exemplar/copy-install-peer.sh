#!/usr/bin/env bash
set -euo pipefail

number=${1:?recipient number required}
[[ $number =~ ^[0-9]{3}$ ]] || exit 2
target="od1-edc003-b300-$number"
ip="172.16.0.$((2 * (10#$number - 1)))"
root=/stn-disk/exemplar/OVA/Exemplar
ssh_opts=(-F /dev/null -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o Compression=no -c aes128-gcm@openssh.com)

echo "start=$(date -u +%FT%TZ) source=$(hostname -s) target=$target ip=$ip"
actual=$(ssh "${ssh_opts[@]}" "root@$ip" hostname)
[[ $actual == "$target" ]] || { echo "identity mismatch: $actual"; exit 1; }
ssh "${ssh_opts[@]}" "root@$ip" "mountpoint -q /stn-disk && mkdir -p '$root'"
tar -C "$root" -cf - install verify-node.sh |
  ssh "${ssh_opts[@]}" "root@$ip" "tar -C '$root' -xpf - && sync -f '$root'"
echo "copied=$(date -u +%FT%TZ) target=$target"
ssh "${ssh_opts[@]}" "root@$ip" "bash /cluster/OVA/Exemplar/verify-node.sh"
echo "finish=$(date -u +%FT%TZ) target=$target"
