#!/usr/bin/env bash
# Install the persistent boot hook on one EDC003 compute node. Run as root.
set -euo pipefail

base=/stn-disk/exemplar/nvis-p2p
incoming="$base/.incoming"
image=nvis-p2p-edc003-bootstrap:2.5.1-nvis.2
# ID of the exported OCI config loaded on compute nodes (the build host's
# local Docker storage ID differs from this portable archive config digest).
image_id=sha256:c4b38991ef626aeb01b34d0c07f8c5705f93d823f07886b855b8e532e19137f7
image_archive="$incoming/nvis-p2p-edc003-bootstrap-2.5.1-nvis.2.tar.gz"
image_sha=a6e604959eefbaafdceb9a8a98adda7192259572a4775393667f3df7558c7d74
release_archive="$incoming/nvis-p2p-exemplar-root-release-v4.tar.gz"
release_sha=$(cat "$incoming/nvis-p2p-exemplar-root-release-v4.sha256")
release=/stn-disk/exemplar/node-bootstrap/releases/2026-09-24-v4
container=nvis-p2p-exemplar-boot

[[ $EUID -eq 0 ]]
mountpoint -q /stn-disk
[[ $(docker info --format '{{.DockerRootDir}}') == /stn-disk/docker ]]
systemctl is-enabled --quiet docker.service
test -x "$base/bin/boot-activate.sh"
test -x "$base/bin/dfdaemon"
test -r "$base/peer.yaml"
test -r "$base/secrets/dfstore-readonly.env"
test -x "$release/restore-fleet.sh"
[[ $(readlink -f /stn-disk/exemplar/node-bootstrap/restore.sh) == "$release/restore-fleet.sh" ]]
"$release/restore-fleet.sh" --check
printf '%s  %s\n' "$image_sha" "$image_archive" | sha256sum -c --status
printf '%s  %s\n' "$release_sha" "$release_archive" | sha256sum -c --status

if ! docker image inspect "$image" >/dev/null 2>&1; then
  gzip -dc "$image_archive" | docker load >/dev/null
fi
[[ $(docker image inspect "$image" --format '{{.Id}}') == "$image_id" ]]

if docker container inspect "$container" >/dev/null 2>&1; then
  [[ $(docker container inspect "$container" --format '{{.Image}}') == "$image_id" ]]
  [[ $(docker container inspect "$container" --format '{{.HostConfig.RestartPolicy.Name}}') == always ]]
  [[ $(docker container inspect "$container" --format '{{.HostConfig.Privileged}}') == true ]]
  [[ $(docker container inspect "$container" --format '{{.HostConfig.PidMode}}') == host ]]
  [[ $(docker container inspect "$container" --format '{{.HostConfig.NetworkMode}}') == host ]]
  [[ $(docker container inspect "$container" --format '{{index .HostConfig.Binds 0}}') == /stn-disk:/stn-disk:rw ]]
  [[ $(docker container inspect "$container" --format '{{.State.Running}}') == true ]]
else
  docker run -d --name "$container" --restart=always --privileged \
    --pid=host --network=host --ipc=host --uts=host \
    -v /stn-disk:/stn-disk:rw "$image" >/dev/null
fi

# The entrypoint is a one-shot activation followed by sleep. Look for the
# success marker from this boot, rather than just a running container.
boot_id=$(cat /proc/sys/kernel/random/boot_id)
for attempt in {1..30}; do
  if docker logs "$container" 2>&1 | grep -Fq "NVIS_P2P_BOOT_READY host=$(hostname -s) boot_id=$boot_id"; then
    systemctl is-active --quiet nvis-p2p-peer.service
    systemctl is-enabled --quiet nvis-p2p-catalog-sync.timer
    systemctl is-active --quiet nvis-p2p-catalog-sync.timer
    [[ $(cat /stn-disk/exemplar/node-bootstrap/last-restored-boot-id) == "$boot_id" ]]
    printf 'BOOT_PERSISTENCE_READY host=%s boot_id=%s\n' "$(hostname -s)" "$boot_id"
    exit 0
  fi
  sleep 2
done
docker logs --tail 80 "$container" >&2
exit 1
