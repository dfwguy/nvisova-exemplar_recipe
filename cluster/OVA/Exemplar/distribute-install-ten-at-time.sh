#!/usr/bin/env bash
set -euo pipefail

root=/cluster/OVA/Exemplar
run_dir="$root/peer-install-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run_dir"
printf '%s\n' "$run_dir" > "$root/peer-install-latest.txt"
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3)
ssh-add /home/nvidia-ssh/.ssh/id_ed25519 </dev/null
sources=(001 002 003 004 005)
for source in "${sources[@]}"; do
  scp -q "${ssh_opts[@]}" "$root/copy-install-peer.sh" "root@od1-edc003-b300-$source:/tmp/copy-install-peer.sh"
done

for ((first=6, batch=1; first<=64; first+=10, batch++)); do
  last=$((first + 9))
  (( last <= 64 )) || last=64
  echo "batch=$batch start=$(date -u +%FT%TZ) recipients=$first-$last"
  pids=()
  recipients=()
  for ((n=first; n<=last; n++)); do
    target=$(printf '%03d' "$n")
    source=${sources[$(((n-first) % ${#sources[@]}))]}
    recipients+=("$target")
    (ssh -A "${ssh_opts[@]}" "root@od1-edc003-b300-$source" \
      "bash /tmp/copy-install-peer.sh '$target'" > "$run_dir/$target.log" 2>&1) &
    pids+=("$!")
  done
  failed=0
  for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
      echo "failed target=${recipients[$i]} log=$run_dir/${recipients[$i]}.log" >&2
      failed=1
    fi
  done
  (( failed == 0 )) || exit 1
  echo "batch=$batch finish=$(date -u +%FT%TZ) recipients=$first-$last verified=all"
done
echo "complete=$(date -u +%FT%TZ) run_dir=$run_dir"
