# Agent operating instructions: Exemplar B300 end-to-end

**Version: 2026-10-07. Companion: `run_exemplar.md`.** This is a portable instruction document for a coding agent, not a claim that a cluster is installed by reading it. The user can ask their installed agent to read both files and operate an approved environment. It is not automatically registered as a Codex skill by its filename; use it as explicit task guidance or adapt it into that environment's approved skill format.

Download the companion operator kit and checksum files from the authorized [NVFTP Exemplar_OVA folder](https://nvftp.nvidia.com/file-explorer/8250a39b-4b0d-47dd-ae22-27b0db9a4618/nvidia-space/shared/STN/Exemplar_OVA). Access requires the owner's approved account. Save `run_exemplar.md`, `agent_exemplar_skills.md`, `exemplar-operator-scripts.tar.gz`, the external `operator-scripts-manifest.json` and `SHA256SUMS.txt` together; run `sha256sum -c SHA256SUMS.txt` before using them. The archive also carries its per-source-file manifest. A successful checksum verifies downloaded content against this handoff, not authority to run its infrastructure commands.


## Purpose and scope

Operate the fixed-release NVIDIA Exemplar Performance recipes on an approved Slurm cluster: discover current state; verify/install authorized prerequisites; validate compute/GPU/PSU/32-HCA/fabric health; stage identical recipe payloads; submit held jobs with exact transport settings; validate generated scripts and stage every recipient; release, monitor, archive and report actual training/performance evidence. Continue the selected queue without duplicate jobs, preserve the immediate-retry/second-failure-halt policy and retain evidence.

The existing STN target is **32 B300 nodes /256 GPUs**, with13 recipe cases from installed v26.08.01. Official Exemplar B300 qualification remains a separate512-GPU matrix. Do not reinterpret a256 supported-scale diagnostic as512 certification. Preserve official recipe/source configuration, dtype and scale-specific topology. Do not start the halted historical 512 suite as a substitute.

## Required inputs and agent bootstrap contract

Read `run_exemplar.md` fully before any action. Obtain the companion `exemplar-operator-scripts.tar.gz` from the same approved NVFTP folder. It contains reviewed-source starting points, a SHA256 manifest, and historical generated job86 examples; it does not contain licensed NeMo images, full official workload repositories, package closure/rootfs bootstrap bundles, credentials or operational state.

Extract the kit to an empty **review directory**, not root:

```bash
mkdir -p ./exemplar-script-review
tar -xzf exemplar-operator-scripts.tar.gz -C ./exemplar-script-review
```

Review `operator-scripts-manifest.json`, validate file digests and inspect source before selecting destination paths. Site paths are preserved under `cluster/OVA/Exemplar/` and `cluster/OVA/NVISP2P/`. `reference/job86/` illustrates actual generated execution, not a reusable submission. Provision authorized official v26.08.01 Exemplar source, pinned recipe install, image access, Slurm/container runtime and NVIS release independently. Adapt hardcoded bindings and rebuild hashes for the adapted release. Missing helpers must be obtained or implemented under review; do not invent an executable path because a guide names it.

For an existing cluster require owner-approved login/network access, trusted SSH identities, scheduler/account permissions and readable non-secret evidence. For a new cluster obtain roster, GPUs per host, persistence path, driver/RDMA/container compatibility, scheduler account/partition/GRES, allowed traffic/QoS/GID policy, telemetry endpoints, image/catalog endpoints and approved credential provisioning. The guides do not supply these inputs. If a dependency/access is absent, state exactly which input is missing, continue independent discovery and avoid dependent submission.

## Hard operating rules

- **Never reboot any STN node.** Do not reset GPUs, format/mount over data, replace boot hooks, change Slurm node state or mutate routes/switches simply to get a launch to succeed. Work within the user's authorized scope; routine reversible checks and authorized continuation do not need repeated confirmation. Infrastructure repair requiring additional scope must be explained with concrete evidence and proposed change.
- Never print/copy private keys, HF/NGC tokens, passwords, Munge keys, secret environment files or credential-valued config into tools, logs, guides or uploads. Search bounded non-secret code/docs, not the entire filesystem for credentials. Inspect secret **presence/permissions**, use approved credential paths and read-only identities, and keep secret values out of shell command arguments. Do not use `set -x` around secrets. The previously exposed switch identity needs owner rotation; never reproduce its value.
- Preserve host-key verification. Existing known_hosts must be verified against the intended host/IP. For unknown or changed keys, establish identity using an approved independent source before enrollment. Do not turn off strict checking or blindly accept changed keys. The installed HCA audit accepts new keys, so preverify selected hosts first.
- Every participating host must retain all 32 intended HCA port1 devices. Missing one makes the node ineligible. A one-HCA or 30-HCA pass is diagnostic only and cannot waive the full-bandwidth policy.
- Never change gate `ready:false` to true or alter timestamps to force a launch. Only actual matching passing evidence can approve. Never waive missing rank inventory, failed telemetry coverage or stale fabric evidence.
- There may be only one active Exemplar job/campaign runner using the shared active manifest. Never resubmit a running/pending job or erase state/manifest to bypass locking.
- Failed recipes retry immediately before another model, once. Another failure halts for diagnosis. Setup/staging/archive or runtime-inventory evidence errors halt immediately. Do not silently advance, invoke historical retry-after-suite scripts or loop indefinite retries.
- Preserve dated logs/configs and original512 state. Changing cohort/HCAs requires a reviewed separate run manifest/directory and new validation. Do not overwrite old evidence to make the current run look successful.

## State discovery: first action on any resume

For STN read `/home/nvidia-ssh/AGENTS.md`, `/home/nvidia-ssh/EXEMPLAR_RUNS.md`, `/home/nvidia-ssh/EXEMPLAR_RUNS.json`, `/home/nvidia-ssh/RESUME_NVIS_P2P.md` and `/home/nvidia-ssh/TOPOLOGY_WORK.md`. Then inspect:

```text
/cluster/OVA/exemplar/logs/suite-256/state.json
/cluster/OVA/exemplar/logs/suite-256/runner-status.json
/cluster/OVA/exemplar/logs/suite-256/events.jsonl
/cluster/OVA/exemplar/logs/suite-256/run-manifest.json
/cluster/OVA/Exemplar/active-job.json
/cluster/OVA/Exemplar/cohort256-nodes.txt
/cluster/OVA/Exemplar/cohort256-preflight.json
```

Inspect tmux `exemplar-suite-256`, runner/observer processes and Slurm independently (`squeue`, `scontrol show job -o`, `sinfo -N`, node state/GRES). Reconcile manifests with actual allocation before changing anything. A runner lock or tmux name is not proof no orphaned Slurm job exists. Site accounting storage is disabled; do not depend on `sacct`. Controller-removed jobs need archived batch exit and durable jobs/job<ID>.json evidence, not a guess from empty squeue.

As of **14:07 UTC October 7**, Nemotron job83 and DeepSeek retry job86 are successful: **two of 13 recipes completed successfully**. Job86 completed 50/50 and was archived with exit 0 and 256/256 runtime gate. Automatic refresh diagnostic job87 passed, then DeepSeek FP8 job88 entered RUNNING. Ten cases remained unattempted plus the active FP8 case. **This is a historical snapshot, not an instruction to submit another job.** Read actual current allocation and state.

## Prerequisite workflow

1. Validate controller Slurm/Munge/account/partition, no conflicting allocation, CLI/python/uv/install tree and free resources. Use source/config help from pinned release. Confirm controller `/cluster`  >= 50 GiB free and  >= 4 GiB available RAM, but also measure per-node persistent/extraction/log headroom.
2. Validate each selected host's identity, eight GPUs, persistent `/stn-disk`, Exemplar symlink, static image/cache/workload presence, Munge/slurmd, Enroot4.2.1/Pyxis 0.24.0/hooks, PMIx and container GPU/RDMA visibility. STN's root is disposable; use approved v4 restoration design. Current boot marker and service health must match the current boot. No reboot validation.
3. Check NVIS status from `edc003-su1/state/fleet-health-latest.json`; inspect age and exceptions. Current approved status needs peer/catalog timer/boot-container/runtime/image receipts. Never redistribute already-verified large images merely because an old checkpoint says not installed. `ready=2 installed=0 failed=0` is successful adoption.
4. Refresh GPU/DCGM and PSU/Redfish evidence. Check current volatile ECC, remap failures/pending/reset requirements, Xid/NVLink, temperatures/power and exporter freshness. Separate historical aggregate ECC. Require full selected-node PSU coverage, expected bay coverage and no critical bay. Existing runner checks node coverage/value but independently verify age and completeness.
5. Validate exactly 32 cohort names and all 32 HCA devices per host using `check_32hca_eligibility.py`. Require ACTIVE/LinkUp/200Gb/RoCEv2 GID3/carrier1 and IPv4-mapped GID matching netdev address. Save a new timestamped report. Never reduce list to intersection.
6. Validate first sorted selected host owns numeric `MASTER_ADDR` on `enp57s0f0np0` and all selected nodes can reach rendezvous. STN current master node002/10.6.33.2, but re-read gate/IP. DNS repair does not establish TCPStore or RDMA correctness.
7. Compare requested cohort with run-manifest identity and gate. Read incidents for related nodes/rails before repair proposals. Fresh switch LLDP/BGP is partial and cannot substitute for full-cohort NCCL. Design spreadsheet is a plan, not live observation.

Read the official system prescreen section in the run guide; its checks are nonfatal, and its environment dumps require secret review/redaction before collection or sharing. Inspect CPU/NUMA/GPU-NIC topology, PMIx/container bootstrap and IBGDA readiness without automatically changing platform settings.

Default supporting script locations are in `run_exemplar.md` section 12. Historical all 64 audit scripts write September output names: review/adapt destinations to avoid destroying old evidence. In another environment replace hardcoded approved fleet, SSH config/user, paths, account/partition, interface names, HCA identifiers, GID/QoS, master IP and telemetry labels consistently across all dependent scripts. Validate adaptation through plan and staged canaries before production scale.

## NCCL preflight and gate contract

Transport values must be explicit and forwarded through the generated container command. STN uses exact 32 HCA allowlist, GID3, CROSS_NIC0, NET=IB, QPS4, TC104, SL1, TIMEOUT20, GDR_C2C1, socket/Gloo interface `enp57s0f0np0`, matching UCX/NVSHMEM lists and INIT/NET isolated logs `/nemo_run/nccl-%h-%p.out`.

A launch approval must have exact cohort,32 unique HCA names, matching first master host/private numeric IP, recent UTC <= 1800 seconds, `four_hca_canary_pass:true`, `all_rail_canary_pass:true`, `rendezvous_verified:true` and all-rail validationPASS/node_count 32/hca_count 32 with actual nonempty evidence file. Recheck Slurm and dynamic health before launch; neither two-node nor host-only checks approve full scale.

Full-cohort canary requires **256 rank files**, successful retrieval from all 32, zero launcher exit, all 256 START/ALLREDUCE_PASS/P2P_PASS markers and strict rank inventory. Test verifies1/16MiB float32 all-reduce and1MiB P2P offsets 1/9/65/129. RuntimeGate requires each host/GPU exactly 32 port1 `NET/IB : Using` entries and eight disjoint four-device merged groups covering all 32. Missing/interleaved fragments are not pass evidence. Inventory validation is mandatory but cannot guarantee later Hybrid-EP training collectives.

With authorized diagnostic scope and idle cohort, refresh existing ready-but-stale approval via:

```bash
python3 /cluster/OVA/Exemplar/refresh_cohort256_preflight.py \
  /cluster/OVA/Exemplar/cohort256-preflight.json \
  /cluster/OVA/Exemplar/cohort256-nodes.txt
```

The helper runs actual new srun, marks readyfalse in progress, preserves false on fail and updates true only on full validation. It refuses revoked approval/changed cohort. Its launcher hardcodes canonical file paths; alternate positional files are not isolation. Review/adapt before another campaign. Runner automatically refreshes an otherwise-ready approval between recipes after 1800 seconds; startup still needs a current approval. Never run the refresh alongside active training.

## Authorized launch and resume workflow

1. If any matching job is running, monitor it. If an existing healthy runner is handling the queue, leave it running. Do not start another session because the user asked for progress.
2. If halted, identify exact event/failed key, retry history and whether a held job exists. Preserve outputs first. Diagnose second failures before any continuation. Reconcile an orphaned job without erasing active manifest to fake idleness.
3. Inspect no-submit plan:

```bash
python3 /cluster/OVA/Exemplar/run_b300_suite_256.py \
  --nodes-file /cluster/OVA/Exemplar/cohort256-nodes.txt --plan
```

4. Once all conditions and user authorization cover continuation, use the canonical `run_b300_suite_256.py` in `exemplar-suite-256` tmux with `python3 -u`, cohort file and preflight file; preserve append-only runner logs. Use section 9 of the run guide for the complete command.
5. Runner calls `llmb-run submit ... --scale 256 --slurm-arg hold`, verifies generated sbatch, stages 32/32 via SHA256 tar, writes active manifest and releases. Do not bypass with raw sbatch or release an unstaged held job.
6. Inspect resource/allocation32 nodes/eight ranks each, correct image/offline mounts/env, nofile65535 and isolated NCCL evidence. Runtime gate is required within 300 seconds; unreadable three times or invalid/incomplete inventory cancels/halts. Missing valid batch host 30 seconds also fails.
7. Monitor actual steps, scheduler and health. On terminal state archive all main/batch/per-process logs and metadata/hash, then apply immediate retry/halt. An archive failure halts; preserve remote files rather than moving on.

Use `--priority-failed-key` only for the recorded failed key under diagnosed continuation. `--resume-held-job` only for an existing verified held job matching intended first incomplete task; inspect interplay with failed priorities. Do not edit completed_keys manually: failed attempts belong there and results map carries success/failure. Starting the runner automatically prioritizes recorded failed tasks before new tasks. Do not call `llmb-run exemplar` for 256; it selects512. Do not invoke historical30-HCA or512 launchers.

## Monitoring and interpreting results

Read runner-status heartbeat every active check, latest events and Slurm state. Watcher updates every 15 seconds but sends no chat messages. Report any observed blocker promptly. During sustained active work give concise updates; do not invent progress from log growth. Use active manifest batch_host/log_path for SSH reads because experiments are node-local. After completion use archived record.log_path. Keep all per-host `nccl-*.out`, not just combined stdout.

Report workload/dtype/scale/job ID, Slurm state, elapsed time, latest completed step/total and its UTC observation time, latest step seconds/model TFLOPS per GPU, runtime gate rank count and any first-fault evidence. If no iteration exists, say so. Startup compilation/optimizer initialization and PyTorch warnings are not completed steps; a warning alone is not fatal.

DeepSeek text `GPU utilization: 864.6MODEL_TFLOP/s/GPU` reports modeled throughput, **not 864.6% utilization**. Distinguish DCGM utilization%. Convert iteration milliseconds to seconds. Preserve TP/PP/CP/VP/EP/ETP/MBS/GBS settings from generated configuration. Compare score-window mean using official parser and approved **same release/model/precision/scale/GPU** baseline; do not compare a256 final step to512 baseline or conclude qualification from exit 0. Document >95% criterion only with corresponding approved baseline and complete suite results.

Normalize timestamps: compute log strings may be UTC-7, while checkpoint/event JSON uses UTC. Record timezone or use explicit UTC source to correlate incidents. Preserve original timestamps in archives.

## Completion, artifacts and handoff

Keep suite-state and official 512 state separate. Verify all 13 latest result states are COMPLETED before saying256 suite complete; count failed attempts independently. Preserve qualification label “256-GPU supported-scale diagnostic; not 512-GPU Exemplar qualification.” Include gate/runtime evidence, source version/hash, image hashes, selected cohort, transport/env, generated scripts/configs, staging reports, main/batch/rank logs, first-fault diagnosis and performance window/baseline provenance.

Inspect pinned `llmb-run archive --help` for official archive behavior, retrieve all node-local outputs first, and package custom health/fabric evidence separately if not included. Upload only to an authorized destination and verify readback SHA256. Do not automatically message others. Documentation/kit publication is not authorization to submit a training job or rotate/alter infrastructure.

If blocked, report concrete blocker, evidence path/time, completed independent checks and exact next required owner input/repair. Do not say “install the agent and it will run everything” when access, payload or fabric is absent. Update durable approved checkpoint files through the existing workflow so the next agent resumes without repeating probes or jobs.
