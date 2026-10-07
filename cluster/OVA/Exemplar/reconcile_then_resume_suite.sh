#!/usr/bin/env bash
# Reconcile the running Kimi job, then continue the sequential suite.
set -euo pipefail

root=/cluster/OVA/Exemplar
log=/cluster/OVA/exemplar/logs/suite/reconcile-resume-job57.log
mkdir -p "$(dirname "$log")"
exec > >(tee -a "$log") 2>&1

date -u '+%Y-%m-%dT%H:%M:%SZ reconcile/resume wrapper started'
python3 -u "$root/reconcile_suite_job.py" --job-id 57 --apply --wait

state=$(python3 -c 'import json; print(json.load(open("/cluster/OVA/Exemplar/jobs/job57.json"))["final_state"])')
date -u "+%Y-%m-%dT%H:%M:%SZ reconciled job57 state=$state"
case "$state" in
  FAILED)
    python3 -u "$root/run_b300_suite.py" --priority-failed-key pretrain_kimi-k2_1t_fp8
    ;;
  COMPLETED)
    python3 -u "$root/run_b300_suite.py"
    ;;
  *)
    echo "job57 ended in $state; suite continuation requires review" >&2
    exit 1
    ;;
esac
