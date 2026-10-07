#!/usr/bin/env bash
set -euo pipefail

root=/cluster/OVA/Exemplar
dest=/stn-disk/exemplar/OVA/Exemplar
run_dir="$root/direct-seed-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run_dir"
printf '%s\n' "$run_dir" > "$root/direct-seed-latest.txt"

nodes=(
  od1-edc003-b300-001
  od1-edc003-b300-002
  od1-edc003-b300-003
  od1-edc003-b300-004
  od1-edc003-b300-005
)

copy_one() {
  local node=$1 start end seconds bytes
  start=$(date +%s)
  printf 'start=%s node=%s\n' "$(date -u +%FT%TZ)" "$node"
  tar -C "$root" -cf - images install SHA256SUMS verify-node.sh |
    ssh -o BatchMode=yes -o Compression=no -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 -c aes128-gcm@openssh.com "root@$node" \
      "mkdir -p '$dest' && tar -C '$dest' -xpf - && sync -f '$dest'"
  end=$(date +%s)
  seconds=$((end - start))
  bytes=$(du -sb "$root/images" "$root/install" "$root/SHA256SUMS" "$root/verify-node.sh" | awk '{s+=$1} END {print s}')
  printf 'finish=%s node=%s elapsed_seconds=%s source_bytes=%s average_MiB_per_second=%s\n' \
    "$(date -u +%FT%TZ)" "$node" "$seconds" "$bytes" \
    "$(awk -v b="$bytes" -v s="$seconds" 'BEGIN {printf "%.1f", b/1048576/s}')"
}

pids=()
for node in "${nodes[@]}"; do
  (copy_one "$node" > "$run_dir/$node.log" 2>&1) &
  pids+=("$!")
done

failed=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then
    printf 'copy failed: %s (see %s)\n' "${nodes[$i]}" "$run_dir/${nodes[$i]}.log" >&2
    failed=1
  fi
done
printf 'run_dir=%s failed=%s\n' "$run_dir" "$failed"
exit "$failed"
