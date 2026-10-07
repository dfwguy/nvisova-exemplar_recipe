#!/usr/bin/env bash
set -euo pipefail
export NCCL_IB_HCA='=mlx5_0:1,mlx5_1:1,mlx5_2:1,mlx5_3:1'
export NCCL_IB_GID_INDEX=3
export NCCL_CROSS_NIC=0
export NCCL_SOCKET_IFNAME=enp57s0f0np0
export GLOO_SOCKET_IFNAME=enp57s0f0np0
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,NET
exec /opt/slurm/25.11.2/bin/srun \
  --job-name=nccl-multirail-4hca \
  --partition=exemplar --account=exemplar \
  --nodes=2 --nodelist=od1-edc003-b300-[039-040] \
  --ntasks=16 --ntasks-per-node=8 \
  --time=00:06:00 --wait=60 --kill-on-bad-exit=1 \
  --container-image=/cluster/OVA/Exemplar/install/images/nvidia+nemo+26.04.01.sqsh \
  --container-mounts=/tmp/nccl-multirail-smoke.py:/tmp/nccl-multirail-smoke.py \
  --container-env=NCCL_IB_HCA,NCCL_IB_GID_INDEX,NCCL_CROSS_NIC,NCCL_SOCKET_IFNAME,GLOO_SOCKET_IFNAME,NCCL_DEBUG,NCCL_DEBUG_SUBSYS \
  python /tmp/nccl-multirail-smoke.py
