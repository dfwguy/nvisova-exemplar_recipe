#!/usr/bin/env bash
set -euo pipefail
export NCCL_IB_HCA='=mlx5_0:1,mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1,mlx5_8:1,mlx5_9:1,mlx5_10:1,mlx5_11:1,mlx5_14:1,mlx5_15:1,mlx5_18:1,mlx5_19:1,mlx5_20:1,mlx5_21:1,mlx5_26:1,mlx5_27:1,mlx5_28:1,mlx5_29:1,mlx5_32:1,mlx5_33:1,mlx5_34:1,mlx5_35:1,mlx5_36:1,mlx5_37:1,mlx5_38:1,mlx5_39:1'
export NCCL_IB_GID_INDEX=3
export NCCL_IB_QPS_PER_CONNECTION=4
export NCCL_CROSS_NIC=0
export NCCL_SOCKET_IFNAME=enp57s0f0np0
export GLOO_SOCKET_IFNAME=enp57s0f0np0
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=NET
exec /opt/slurm/25.11.2/bin/srun \
  --job-name=nccl-multirail-30hca-512 \
  --partition=exemplar --account=exemplar \
  --nodes=64 --ntasks=512 --ntasks-per-node=8 --exclusive \
  --time=00:08:00 --wait=60 --kill-on-bad-exit=1 \
  --container-image=/cluster/OVA/Exemplar/install/images/nvidia+nemo+26.04.01.sqsh \
  --container-mounts=/tmp/nccl-multirail-512-smoke.py:/tmp/nccl-multirail-512-smoke.py \
  --container-env=NCCL_IB_HCA,NCCL_IB_GID_INDEX,NCCL_IB_QPS_PER_CONNECTION,NCCL_CROSS_NIC,NCCL_SOCKET_IFNAME,GLOO_SOCKET_IFNAME,NCCL_DEBUG,NCCL_DEBUG_SUBSYS \
  python /tmp/nccl-multirail-512-smoke.py
