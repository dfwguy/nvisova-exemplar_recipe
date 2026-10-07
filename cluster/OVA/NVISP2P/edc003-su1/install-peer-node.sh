#!/usr/bin/env bash
# Run through strict, trusted root SSH only after the node passes preflight.
set -euo pipefail

base=/stn-disk/exemplar/nvis-p2p
incoming=$base/.incoming
package=$incoming/NVIS-P2P-2.5.1-nvis.2-EDC003-SU1-B300-x86_64-client.tar.gz
package_sha=271e915d721066b9251b03d644a56d8ed264b1cb261d411a151c7f42e509f06f
package_dir=$incoming/NVIS-P2P-2.5.1-nvis.2-EDC003-SU1-B300-x86_64-client

mountpoint -q /stn-disk
[[ $(uname -m) == x86_64 && $(getconf PAGESIZE) == 4096 ]]
[[ $(id -u nvidia-ssh) == 1001 && $(id -g nvidia-ssh) == 1001 ]]
[[ $(docker info --format '{{.DockerRootDir}}') == /stn-disk/docker ]]
[[ $(hostname -s) =~ ^od1-edc003-b300-[0-9]{3}$ ]]
node_ip=$(getent ahostsv4 "$(hostname -s)" | awk 'NR==1 {print $1}' || true)
if [[ -z $node_ip ]]; then
  node_ip=$(ip -o -4 addr show scope global | awk '$4 ~ /^10[.]6[.]33[.][0-9]+\// {sub(/\/.*/, "", $4); print $4; exit}')
fi
[[ $node_ip =~ ^10[.]6[.]33[.][0-9]+$ ]]
node_suffix=$(hostname -s)
node_suffix=${node_suffix##*-}
[[ ${node_ip##*.} == $((10#$node_suffix)) ]]
printf '%s  %s\n' "$package_sha" "$package" | sha256sum -c - >/dev/null

mkdir -p "$incoming"
tar -xzf "$package" -C "$incoming"
(cd "$package_dir" && sha256sum -c SHA256SUMS >/dev/null)

install -d -m 0755 "$base" "$base/bin" "$base/catalog" "$base/systemd"
for name in dfdaemon dfget dfstore dfstore-sync-catalog.sh; do
  install -m 0755 "$package_dir/bin/$name" "$base/bin/$name"
done
for name in images.json images.tsv; do
  install -m 0644 "$package_dir/catalog/$name" "$base/catalog/$name"
done
for name in nvis-p2p-peer.service nvis-p2p-catalog-sync.service nvis-p2p-catalog-sync.timer; do
  install -m 0644 "$package_dir/systemd/$name" "$base/systemd/$name"
  install -m 0644 "$package_dir/systemd/$name" "/etc/systemd/system/$name"
done
for name in cache storage run logs staging receipts quarantine plugins; do
  install -d -o nvidia-ssh -g nvidia-ssh -m 0750 "$base/$name"
done
install -d -o nvidia-ssh -g nvidia-ssh -m 0700 "$base/secrets"
install -o nvidia-ssh -g nvidia-ssh -m 0600 "$incoming/dfstore-readonly.env" "$base/secrets/dfstore-readonly.env"
sed -e "s/__RACK__/edc003-b300/g" -e "s/__HOSTNAME__/$(hostname -s)/g" -e "s/__NODE_IP__/$node_ip/g" "$incoming/peer.template.yaml" > "$base/peer.yaml"
chmod 0644 "$base/peer.yaml"
! grep -Eq '__[A-Z_]+__' "$base/peer.yaml"

image_dir=/stn-disk/exemplar/OVA/Exemplar/images
[[ -d $image_dir ]]
chown nvidia-ssh:nvidia-ssh "$image_dir"
chmod 0755 "$image_dir"

systemctl daemon-reload
systemctl enable --now nvis-p2p-peer.service
systemctl is-active --quiet nvis-p2p-peer.service
for attempt in $(seq 1 20); do
  [[ -S $base/run/dfdaemon.sock ]] && break
  sleep 1
done
[[ -S $base/run/dfdaemon.sock ]]
printf 'NVIS_P2P_PEER_READY host=%s ip=%s boot_id=%s\n' "$(hostname -s)" "$node_ip" "$(cat /proc/sys/kernel/random/boot_id)"
