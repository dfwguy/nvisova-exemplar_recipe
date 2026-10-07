#!/usr/bin/env bash
set -euo pipefail

release=/stn-disk/exemplar/node-bootstrap/releases/2026-09-23-v3
state=/stn-disk/exemplar/node-bootstrap/last-restored-boot-id
payload=/stn-disk/exemplar/OVA/Exemplar
boot_id=$(cat /proc/sys/kernel/random/boot_id)

if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root' >&2
  exit 1
fi
mountpoint -q /stn-disk
test -f "$release/SHA256SUMS"
if [[ ${1:-} != --force && ${1:-} != --check && -f "$state" && $(cat "$state") == "$boot_id" ]]; then
  echo "Exemplar already restored for boot $boot_id on $(hostname -s)"
  exit 0
fi
(cd "$release" && sha256sum -c SHA256SUMS >/dev/null)
if [[ ${1:-} == --check ]]; then
  echo "Fleet bundle verified on $(hostname -s)"
  exit 0
fi

if getent group 64030 >/dev/null; then
  [[ $(getent group 64030 | cut -d: -f1) == slurm ]]
else
  groupadd --system --gid 64030 slurm
fi
if id -u slurm >/dev/null 2>&1; then
  [[ $(id -u slurm) == 64030 ]]
else
  useradd --system --uid 64030 --gid 64030 --no-create-home --shell /usr/sbin/nologin slurm
fi
if getent group 1001 >/dev/null; then
  [[ $(getent group 1001 | cut -d: -f1) == nvidia-ssh ]]
else
  groupadd --gid 1001 nvidia-ssh
fi
if id -u nvidia-ssh >/dev/null 2>&1; then
  [[ $(id -u nvidia-ssh) == 1001 ]]
else
  useradd --uid 1001 --gid 1001 --no-create-home --home-dir /home/nvidia-ssh --shell /bin/bash nvidia-ssh
fi

# Package post-install scripts start Munge and slurmd. Put their configuration
# in place first so neither service waits for a missing config during install.
tar --acls --xattrs --numeric-owner -C / -xpf "$release/exemplar-rootfs.tar"
install -m 0644 "$release/slurm.conf" /etc/slurm/slurm.conf
systemctl daemon-reload

shopt -s nullglob
debs=()
for name in bsdutils bsdextrautils ncal bsdmainutils libb64-0d libjwt2 libhttp-parser2.9 \
  liblua5.1-0 libmunge2 munge libslurm44t64 slurm-wlm-basic-plugins slurmd slurm-client \
  enroot 'enroot+caps'; do
  matches=("$release/packages/${name}"_*.deb "$release/bootstrap-source/${name}"_*.deb)
  if (( ${#matches[@]} != 1 )); then
    echo "Expected one $name package, found ${#matches[@]}" >&2
    exit 1
  fi
  debs+=("${matches[0]}")
done
DEBIAN_FRONTEND=noninteractive dpkg --force-confold --install "${debs[@]}"

tar --acls --xattrs --numeric-owner -C / -xpf "$release/exemplar-rootfs.tar"
install -m 0644 "$release/slurm.conf" /etc/slurm/slurm.conf
chown munge:munge /etc/munge /etc/munge/munge.key
chmod 0700 /etc/munge
chmod 0400 /etc/munge/munge.key

install -d -o nvidia-ssh -g nvidia-ssh -m 0750 /stn-disk/exemplar/home/nvidia-ssh
if [[ ! -e /home/nvidia-ssh && ! -L /home/nvidia-ssh ]]; then
  ln -s /stn-disk/exemplar/home/nvidia-ssh /home/nvidia-ssh
fi
install -d -o nvidia-ssh -g nvidia-ssh -m 0775 "$payload"
install -d -m 0755 /cluster/OVA
if [[ -L /cluster/OVA/Exemplar ]]; then
  ln -sfn "$payload" /cluster/OVA/Exemplar
elif [[ ! -e /cluster/OVA/Exemplar ]]; then
  ln -s "$payload" /cluster/OVA/Exemplar
else
  echo '/cluster/OVA/Exemplar exists and is not a symlink' >&2
  exit 1
fi

systemctl daemon-reload
systemctl enable munge slurmd
systemctl restart munge slurmd
systemctl is-active --quiet munge
systemctl is-active --quiet slurmd
test "$(enroot version)" = 4.2.1
test -x /etc/enroot/hooks.d/50-slurm-pytorch.sh
test -f /etc/slurm/plugstack.conf.d/pyxis.conf
test -x /usr/local/bin/python3.12
test "$(grep -c '^NodeName=' /etc/slurm/slurm.conf)" = 64

printf '%s\n' "$boot_id" > "$state"
chmod 0600 "$state"
echo "Exemplar restored on $(hostname -s) for boot $boot_id"
