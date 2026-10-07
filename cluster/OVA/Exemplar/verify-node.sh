#!/usr/bin/env bash
set -euo pipefail

root=/cluster/OVA/Exemplar
cd "$root"

for image in nvidia+nemo+26.04.01.sqsh nvidia+nemo+26.06.01.sqsh; do
  test -s "images/$image"
  test -s "install/images/$image"
done

for workload in pretrain_deepseek-v3 pretrain_gpt_oss pretrain_kimi-k2 \
  pretrain_llama3.1 pretrain_nemotron-h pretrain_nemotron_3 pretrain_qwen3; do
  test -d "install/workloads/$workload/Megatron-Bridge"
done

test -f install/cluster_config.yaml
test -d install/.cache/huggingface/hub
test -x install/venvs/venv_f4496d246607/bin/python
test -x install/bin/x86_64/uv
if [[ ${1:-} != --payload-only ]]; then
  test -x /etc/enroot/hooks.d/50-slurm-pytorch.sh
  test -f /etc/slurm/plugstack.conf.d/pyxis.conf
  command -v enroot >/dev/null
  test "$(enroot version)" = 4.2.1
fi

sha256sum -c SHA256SUMS
printf 'Exemplar B300 static payload verified on %s\n' "$(hostname)"
