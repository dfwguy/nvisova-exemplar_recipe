#!/usr/bin/env bash
set -euo pipefail

root=/cluster/OVA/Exemplar
dest=/stn-disk/exemplar/OVA/Exemplar
run_dir="$root/resume-seeds-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run_dir"
printf '%s\n' "$run_dir" > "$root/resume-seeds-latest.txt"
nodes=(001 002 003 004 005)
images=(nvidia+nemo+26.04.01.sqsh nvidia+nemo+26.06.01.sqsh)
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o Compression=no)

copy_one() {
  local node="od1-edc003-b300-$1" image source target size total local_hash remote_hash expected
  echo "start=$(date -u +%FT%TZ) node=$node"
  for image in "${images[@]}"; do
    source="$root/images/$image"
    target="$dest/images/$image"
    total=$(stat -c %s "$source")
    size=$(ssh "${ssh_opts[@]}" "root@$node" "mkdir -p '$dest/images' && stat -c %s '$target' 2>/dev/null || echo 0")
    [[ $size =~ ^[0-9]+$ ]] && (( size <= total )) || { echo "invalid existing size: $size"; return 1; }
    if (( size > 0 && size < total )); then
      echo "checking existing prefix image=$image bytes=$size"
      local_hash=$(head -c "$size" "$source" | sha256sum | cut -d ' ' -f1)
      remote_hash=$(ssh "${ssh_opts[@]}" "root@$node" "sha256sum '$target' | cut -d ' ' -f1")
      [[ $local_hash == "$remote_hash" ]] || { echo "prefix mismatch image=$image"; return 1; }
    fi
    if (( size < total )); then
      echo "resuming image=$image offset=$size total=$total"
      tail -c "+$((size + 1))" "$source" | ssh "${ssh_opts[@]}" "root@$node" "cat >> '$target'"
    fi
    expected=$(awk -v p="images/$image" '$2==p {print $1}' "$root/SHA256SUMS")
    remote_hash=$(ssh "${ssh_opts[@]}" "root@$node" "sha256sum '$target' | cut -d ' ' -f1")
    [[ -n $expected && $expected == "$remote_hash" ]] || { echo "image checksum mismatch: $image"; return 1; }
    ssh "${ssh_opts[@]}" "root@$node" "chown 1001:1001 '$target' && chmod 644 '$target'"
    echo "verified image=$image"
  done
  echo "copying install tree and verifier"
  tar -C "$root" -cf - install SHA256SUMS verify-node.sh |
    ssh "${ssh_opts[@]}" "root@$node" "tar -C '$dest' -xpf - && sync -f '$dest'"
  ssh "${ssh_opts[@]}" "root@$node" "bash /cluster/OVA/Exemplar/verify-node.sh"
  echo "finish=$(date -u +%FT%TZ) node=$node"
}

pids=()
for node in "${nodes[@]}"; do
  (copy_one "$node" > "$run_dir/$node.log" 2>&1) &
  pids+=("$!")
done
failed=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then
    echo "failed node=${nodes[$i]} log=$run_dir/${nodes[$i]}.log" >&2
    failed=1
  fi
done
echo "finish=$(date -u +%FT%TZ) failed=$failed run_dir=$run_dir"
exit "$failed"
