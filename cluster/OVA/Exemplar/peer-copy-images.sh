#!/usr/bin/env bash
set -euo pipefail

number=${1:?recipient number required}
[[ $number =~ ^[0-9]{3}$ ]] || exit 2
target="od1-edc003-b300-$number"
ip=${2:-"172.16.0.$((2 * (10#$number - 1)))"}
root=/stn-disk/exemplar/OVA/Exemplar
images=(nvidia+nemo+26.04.01.sqsh nvidia+nemo+26.06.01.sqsh)
ssh_opts=(-F /dev/null -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o Compression=no -c aes128-gcm@openssh.com)

echo "start=$(date -u +%FT%TZ) source=$(hostname -s) target=$target ip=$ip"
actual=$(ssh "${ssh_opts[@]}" "root@$ip" hostname)
[[ $actual == "$target" ]] || { echo "identity mismatch: $actual"; exit 1; }
ssh "${ssh_opts[@]}" "root@$ip" "mountpoint -q /stn-disk && mkdir -p '$root/images'"

for image in "${images[@]}"; do
  source="$root/images/$image"
  destination="$root/images/$image"
  expected=$(awk -v p="images/$image" '$2==p {print $1}' "$root/SHA256SUMS")
  [[ -n $expected ]] || { echo "missing checksum: $image"; exit 1; }
  total=$(stat -c %s "$source")
  existing=$(ssh "${ssh_opts[@]}" "root@$ip" "stat -c %s '$destination' 2>/dev/null || echo 0")
  [[ $existing =~ ^[0-9]+$ ]] && (( existing <= total )) || { echo "invalid size: $existing"; exit 1; }
  if (( existing > 0 && existing < total )); then
    echo "checking partial image=$image bytes=$existing"
    local_hash=$(head -c "$existing" "$source" | sha256sum | cut -d ' ' -f1)
    remote_hash=$(ssh "${ssh_opts[@]}" "root@$ip" "sha256sum '$destination' | cut -d ' ' -f1")
    [[ $local_hash == "$remote_hash" ]] || { echo "partial checksum mismatch: $image"; exit 1; }
  fi
  if (( existing < total )); then
    echo "copying image=$image offset=$existing total=$total"
    tail -c "+$((existing + 1))" "$source" |
      ssh "${ssh_opts[@]}" "root@$ip" "cat >> '$destination'"
  fi
  remote_hash=$(ssh "${ssh_opts[@]}" "root@$ip" "sha256sum '$destination' | cut -d ' ' -f1")
  [[ $remote_hash == "$expected" ]] || { echo "checksum mismatch: $image"; exit 1; }
  ssh "${ssh_opts[@]}" "root@$ip" "chown 1001:1001 '$destination' && chmod 644 '$destination' && sync -f '$destination'"
  echo "verified image=$image sha256=$expected"
done
cat "$root/SHA256SUMS" | ssh "${ssh_opts[@]}" "root@$ip" "cat > '$root/SHA256SUMS' && chown 1001:1001 '$root/SHA256SUMS' && chmod 644 '$root/SHA256SUMS'"
echo "finish=$(date -u +%FT%TZ) target=$target"
