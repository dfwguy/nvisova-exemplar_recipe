# Run Exemplar: STN EDC003 SU1 B300 operating and reproduction guide

**Prepared 2026-10-07 UTC from deployed scripts, configuration and evidence.** Read `agent_exemplar_skills.md` with this document. This guide describes the existing STN installation and what another operator must supply to reproduce it. Commands that submit jobs, install components or restore nodes are explicitly identified. Reading this guide does not itself authorize changes to another cluster.

Download the companion operator kit and checksum files from the authorized [NVFTP Exemplar_OVA folder](https://nvftp.nvidia.com/file-explorer/8250a39b-4b0d-47dd-ae22-27b0db9a4618/nvidia-space/shared/STN/Exemplar_OVA). Access requires the owner's approved account. Save `run_exemplar.md`, `agent_exemplar_skills.md`, `exemplar-operator-scripts.tar.gz`, the external `operator-scripts-manifest.json` and `SHA256SUMS.txt` together; run `sha256sum -c SHA256SUMS.txt` before using them. The archive also carries its per-source-file manifest. A successful checksum verifies downloaded content against this handoff, not authority to run its infrastructure commands.


## 1. Scope, present state and what a result means

The installed NVIDIA Exemplar Performance recipe release is **v26.08.01**, originally staged from commit `82e952b173b2c9d94732064657de92dd5473d66e`. The official B300 Exemplar matrix is 13 cases, **512 GPUs**, one repeat and profiling disabled. This project's current user request is a separate **32-node / 256-GPU supported-scale diagnostic** using those same 13 workload/dtype cases and the supported 256-GPU recipe configurations. Completion at 256 GPUs does not qualify the 512-GPU suite or establish NVIDIA certification. NVIDIA reviews required-scale results against the applicable baseline; the checked local validation document describes a **greater than 95%** baseline requirement for all cases.

At the 2026-10-07 **14:07 UTC** handoff check, DeepSeek-V3 BF16 retry **job86 COMPLETED 50/50 with exit 0** and its output was archived. Its NCCL inventory gate validated **256/256 ranks**. There are now **two successful recipes of 13**: Nemotron-H FP8 job83 and DeepSeek-V3 BF16 job86. Nemotron job83's final step was 4.7806 seconds and 1,724.1 raw TFLOPS/GPU. DeepSeek job84 had failed after iteration 39 with Hybrid-EP timeout evidence; job86 was its diagnosed retry. The runner automatically refreshed full-cohort approval when it was 1,811 seconds old: diagnostic **job87 passed**, then DeepSeek-V3 FP8 **job88 entered RUNNING**. There are ten unattempted cases plus the current FP8 case. These facts will age: inspect current Slurm/state before acting, and distinguish a diagnostic allocation from training. `completed_keys` counts finished recipe keys, including failures until retried; derive successful count from latest per-key final states.

The old 512-GPU suite is separate and halted after Kimi retry job59 failed. Do not resume it as a substitute for the current 256-GPU request. Old September statements that no NVIS P2P was deployed, only one node was registered, or the fabric gate was blocked describe earlier checkpoints and are superseded by later evidence. Read timestamps rather than trusting an isolated sentence.

## 2. Architecture and exact paths

| Component | STN deployment | Purpose |
|---|---|---|
| Jump box / Slurm controller | `od1-nvidia-cvt`, management web IP `10.6.20.37` | Installer, CLI, scheduler control, runners, archive, NVIS services |
| Compute fleet | `od1-edc003-b300-001` through `-064`, eight B300 GPUs each | 64 candidate hosts; selected cohort is 32 |
| Exemplar project | `/cluster/OVA/Exemplar` | Site scripts, images, installation, jobs and gate files |
| CLI environment | `/home/nvidia-ssh/OVA/llmb_venv` | Jump-only CLI; `install/llmb-run` points here |
| Installed workloads | `/cluster/OVA/Exemplar/install/workloads/` | Megatron-Bridge and generated NeMo experiments |
| Runtime Python | `install/venvs/venv_f4496d246607/` | Workload venv; copied static payload |
| Compute persistence | `/stn-disk/exemplar/OVA/Exemplar` | Local persistent payload; `/cluster/OVA/Exemplar` is a symlink to it |
| Slurm tools | `/opt/slurm/25.11.2/bin/` on controller | `sinfo`, `squeue`, `scontrol`, `srun`, `sbatch` |
| Selected cohort | `/cluster/OVA/Exemplar/cohort256-nodes.txt` | Exactly 32 unique approved hostnames, one per line |
| Launch approval | `/cluster/OVA/Exemplar/cohort256-preflight.json` | Recent matching all-rail approval; never manufacture a pass |
| Current manifest | `/cluster/OVA/Exemplar/active-job.json` | Live workload, host, log path, node list and environment |
| 256 suite evidence | `/cluster/OVA/exemplar/logs/suite-256/` | State, events, runner logs, per-job archives and staging receipts |
| 512 evidence | `/cluster/OVA/exemplar/logs/suite/` | Historical suite; keep separate |
| Per-job metadata | `/cluster/OVA/Exemplar/jobs/job<ID>.json` | Final state, archive, SHA256, runtime gate and qualification label |
| NVIS P2P | `/cluster/OVA/NVISP2P/installed/current` | Versioned EDC003 x86_64 site release |
| NVIS site overlay | `/cluster/OVA/NVISP2P/edc003-su1/` | Inventory, peer installer, bootstrap, audits and evidence |

Identical pathname does **not** mean shared filesystem here. Every compute node has its own local `/cluster/OVA/Exemplar` tree. New experiment files must be copied to each allocated node **before releasing a held job**. Logs must then be fetched from compute nodes. NVIS static image distribution does not remove this requirement.

## 3. What someone receiving only these two Markdown files must obtain

For the existing STN cluster, get approved login/network access to the jump box and trust the installed scripts only after reviewing their source. For a new cluster, provision the following before running anything:

1. A functioning Slurm control plane, approved compute inventory and operator account; eight healthy B300 GPUs per node for this configuration; suitable NVIDIA driver, CUDA/RDMA stack and correctly wired full-bandwidth RoCE fabric. Do not transplant STN hostnames or VLAN/IP settings into another environment.
2. The official [NVIDIA Exemplar Performance repository](https://github.com/NVIDIA/exemplar-performance) and the selected fixed recipe release. For reproducing these runs use v26.08.01 and record the commit. For a new certification campaign, follow the version policy in that campaign's official guide; do not silently upgrade an in-progress campaign.
3. Licensed/approved NGC access for the selected NeMo images and authorized Hugging Face access for gated configs/tokenizers, particularly Llama. The standard pretraining cases do not need pretrained weight tensors or production datasets; the installer needs model metadata. Request gated access ahead of installation.
4. The **site scripts** listed in section 12, available in the companion `exemplar-operator-scripts.tar.gz` in the same NVFTP folder, the cluster configuration and static payload manifests. They are custom operating code, not supplied by installing a coding agent or by copying these guides. The kit preserves paths relative to filesystem root and includes `operator-scripts-manifest.json` with SHA256 plus `reference/job86/` generated sbatch, recipe script and llmb-config examples. Extract into an empty review directory with `tar -xzf exemplar-operator-scripts.tar.gz -C <review-dir>`, verify the manifest and review/adapt hostnames, paths, identities, cohort, ports and telemetry bindings before deploying anything. **Never extract blindly into `/` or submit the reference job86 script unchanged.** Bootstrap archives include protected infrastructure material and must not be placed in a public documentation bundle.
5. For reproducing NVIS delivery, the NVIS-P2P-2.5.1-nvis.2 release and its EDC003 x86_64 overlay or an adapted site overlay, checksum manifests, client binaries, service definitions and approved credentials. Obtain that release through its owner; upstream Dragonfly alone does not include STN's restore/catalog automation.
6. Monitoring providing current GPU/DCGM, PSU/Redfish and NIC/LLDP data, or a reviewed adaptation of gates to equally strong evidence. The installed runner expects the local Prometheus-compatible API at `127.0.0.1:18428` and `redfish_psu_health` labelled by Slurm `node`. Missing coverage must fail closed.
7. Persistent storage and an approved restoration mechanism if the OS root is disposable. Budget at least the upstream guide's 300 GB per installation and extra space for experiments, extracted containers, caches and logs. Measure actual capacity; the runner's jump-box 50 GiB guard is not a full per-node sizing rule.

These files give an agent the operating procedure and decision rules. They do not carry licensed images, account access, private keys, secrets, executable site helpers or a provisioned cluster. A new operator must adapt and validate the code, not invent missing prerequisites or weaken gates to make a command launch.

## 4. Controller and compute prerequisites

The checked recipe README requires Bash  >= 4.2, Python 3.12, Git LFS and NGC access on the installer host. Its generic minima include CUDA >=12.3, NVIDIA driver >=535.129.03, OFED >=5.9 and NCCL >=2.19.4. Those generic floors are not a tested B300 compatibility prescription: use the driver/RDMA/CUDA combination approved for B300 and the pinned container recipes. The STN bring-up recorded driver 580.173.02. Containers provide their user-space training software; a host driver and working RDMA device access remain necessary.

Slurm must have `task/affinity`, PMIx support (`srun --mpi=list`), eight GPU GRES per host, consistent user/group IDs and working Munge. STN uses Slurm **25.11.2**, **Enroot 4.2.1**, **Pyxis 0.24.0**, PMIx and Python **3.12.14** for the host bootstrap. The copied workload environment has its own Python **3.12.12** runtime. The `exemplar` partition and `exemplar` account are set in `install/cluster_config.yaml`; GPU GRES is 8. The Slurm account/partition must be valid for the launching user. Confirm actual GPU visibility in a container, rather than assuming the configured GRES count proves hardware health.

Required Enroot integration includes `/etc/enroot/hooks.d/50-slurm-pytorch.sh`, distributed PMI hooks and `/etc/slurm/plugstack.conf.d/pyxis.conf`. Upstream setup specifies `ENROOT_ROOTFS_WRITABLE yes` and `ENROOT_REMAP_ROOT yes`. Jobs use `--no-container-mount-home` to keep host Python settings from overriding container settings. Audit `/etc/enroot/environ.d/*.env` and `/etc/environment` for legacy network defaults: inherited `NCCL_SOCKET_IFNAME=bond0` previously failed because that interface does not exist here.

STN's bootstrap creates benchmark UID/GID **1001** and Slurm UID/GID **64030**, restores approved Slurm/Munge/Enroot/Pyxis configuration and starts `munge` and `slurmd`. Munge keys must match by secure provisioning; never print their bytes or place them in documentation. Check permissions and interoperability using service and smoke tests.

### Official system prescreen and configuration review

The installed prescreen is `install/llmb_repo/microbenchmarks/system_info/README.md` and its launcher. Upstream command selects one host's GPU count, for example:

```bash
# Plan only; inspect pinned CLI behavior and intended node allocation first.
cd /cluster/OVA/Exemplar/install
./llmb-run submit -w microbenchmark_system_info --scale 8 --dry-run
```

An actual prescreen submission is a job, needs authorized idle capacity, and must preserve node-local generated-file staging before release. Inspect its own launcher/output layout; do not assume the training-only32-node staging validator supports an8-GPU prescreen. Run through a reviewed held-job staging path or approved shared storage. The prescreen runs `lscpu`, CPU governors/C-states, PCIe/NUMA layout, kernel command line/virtualization/page size, full GPU health/topology/NVLink, NUMA balancing, verbs device/port attributes, IBGDA readiness, Slurm topology and PMIx, Enroot configuration and a container GPU/hook test. Its checks are **nonfatal and continue after warnings**: exit 0 alone is not acceptance. Inspect each warning and attach results to launch evidence.

Pay attention to CPU/NUMA affinity and governor/clock consistency, full GPU-to-NIC topology, NVLink status, kernel/RDMA module compatibility and IBGDA prerequisites. The prescreen recognizes an approved peer-mapping path or GDRCopy kernel driver as alternative IBGDA readiness evidence. Do not enable kernel module parameters, change CPU power settings, disable NUMA balancing or install a driver blindly; compare approved platform configuration and diagnose measurable deviations with the owner. B300 local interconnect checks differ from GB300 NVL72/IMEX requirements; do not enforce72 up links on B300.

**Secret-handling detail:** the prescreen dumps Enroot `environ.d` contents. Review whether those files contain only non-secret runtime settings before running or sharing the output. Do not allow token/credential environment entries to enter a transcript/archive; use a reviewed redacted collection if such entries exist. Transport policy values in this guide are non-secret; secret files are not.

### Persistent root restoration

The compute OS root is a disposable overlay. `/stn-disk` is persistent ext4. Earlier release v3 had an incomplete clean-boot package closure and needed missing PMIx dependencies; it is historical. Current release **2026-09-24-v4** is under `/stn-disk/exemplar/node-bootstrap/releases/`; `/stn-disk/exemplar/node-bootstrap/restore.sh` selects it. It verifies the release manifest and restores live-root packages/configs once per boot ID. `--check` verifies release contents without restoring; `--force` is a mutation and should only be used for a diagnosed approved restoration.

NVIS installs a persistent Docker container `nvis-p2p-exemplar-boot`, with Docker data under `/stn-disk/docker`, restart policy `always`, privileged host namespace access and the reviewed bootstrap image. `bootstrap/boot-container.sh` enters the host namespace; `bootstrap/boot-activate.sh` runs the persistent Exemplar restore hook, installs the peer/catalog systemd units and enables them. Success prints `NVIS_P2P_BOOT_READY`. `bootstrap/install-node-bootstrap.sh`, `stage-node-bootstrap.sh` and `rollout-boot.py` are the deployment helpers. They mutate nodes and are not routine health-check commands.

**Standing STN instruction: never reboot any node.** Recovery was activated successfully on the current boot; no intentional reboot test was performed. Do not claim a reboot-tested result or reboot to validate persistence. If a node is externally reprovisioned, verify its hostname/IP and fingerprint through an approved identity source before changing known_hosts. Do not disable SSH verification or blindly accept a replacement key.

## 5. How the recipe installation and static payload were staged

Source checkout: `/home/nvidia-ssh/OVA/exemplar-performance`. Installation playbook: `/cluster/OVA/Exemplar/install-playbook.yaml`. Installed cluster config: `/cluster/OVA/Exemplar/install/cluster_config.yaml`; source copy used by the installation: `install/llmb_repo/`. The official installer is `./install.sh`, optionally `-i /cluster/OVA/Exemplar/images` to reuse the approved image folder. A fresh environment should read the pinned release's installer and CLI documentation and select GPU type B300, Slurm and Exemplar Cloud workload set; do not blindly replay the old STN playbook on other hardware.

The seven installed families are `pretrain_deepseek-v3`, `pretrain_gpt_oss`, `pretrain_kimi-k2`, `pretrain_llama3.1`, `pretrain_nemotron-h`, `pretrain_nemotron_3` and `pretrain_qwen3`. `microbenchmark_system_info` was also installed for official prescreen. The images are:

| Local filename | Used by | Exact bytes | SHA256 |
|---|---|---:|---|
| `nvidia+nemo+26.04.01.sqsh` | Nemotron-H | 36,649,082,880 | `270342a31e1727511f1b5bd923f4bee6fdb886fc0f42d371583aed012d83f604` |
| `nvidia+nemo+26.06.01.sqsh` | Other six families | 29,557,919,744 | `e34c7a5bf2c64d80e161d026bebe083512a93491f33d9e1bf06836e99629ac1f` |

Images live in `images/`; `install/images/` links to them. Static `install/` includes workload code, venv/runtime, uv, tools and `install/.cache/huggingface`. The earlier separate `hf-cache/` is unnecessary when the embedded cache is present. No Git/LFS is required on compute nodes after this payload is installed. The `install/llmb-run` symlink is jump-only; run CLI submissions on the controller.

Historically the large images were seeded directly to a limited number of nodes and fanned out by peer copies. Scripts `seed-five-direct.sh`, `resume-five-seeds.sh`, `distribute-images-ten-at-time.sh`, `copy-install-peer.sh` and `distribute-install-ten-at-time.sh` record that bring-up. They target historical rosters and should not be rerun on a prepared fleet. NVIS later **adopted the already-staged images** in place rather than sending 4.2 TB again.

`verify-node.sh` checks both images, all seven workload Megatron-Bridge directories, config, HF cache, Python/uv and SHA256 manifest. On compute it also checks Enroot/hooks/Pyxis. On controller use `--payload-only`. Full image hashing is useful once after first delivery or when corruption is suspected; prefer fresh receipt/size health audits for routine checks rather than repeatedly hashing every image on 64 nodes during training.

```bash
# Read-only static validation; full SHA256 scan can be expensive.
bash /cluster/OVA/Exemplar/verify-node.sh --payload-only
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes od1-edc003-b300-002 \
  'bash /cluster/OVA/Exemplar/verify-node.sh'
```

## 6. NVIS P2P deployment, adoption and operational checks

Read `/home/nvidia-ssh/RESUME_NVIS_P2P.md`, `/cluster/OVA/NVISP2P/RESUME.md`, and `edc003-su1/README.md` first. The active EDC003 site release is `installed/current`; original signed/provenance release stays separate. Both jump and compute are x86_64 with 4 KiB pages; the matching Dragonfly client is v1.4.9. Do not use bundled legacy fleet scripts aimed at different architecture, UID/GID or roster.

The jump-host control plane consists of PostgreSQL, Redis, TLS MinIO, Manager, scheduler, read-only origin, two seed peers, console and site status API, with boot restart rules. Manager REST is loopback-only. The object API is `https://10.6.32.246:19000`. Console is `http://10.6.20.37:4300`; `/nvis-p2p-health` and Manager-proxy `/healthy` are health endpoints. Fleet status requires an authorized Manager root session. Site console mutation routes are disabled (`503`) because the original operations implementation was not safe for this fleet; leave them disabled.

Exactly two native **dfstore imports** were performed sequentially, requesting two persistent replicas with a seven-day Dragonfly task TTL. MinIO object byte counts matched the table above. A 1 MiB native import/export probe was validated through both seeds and compute node005, then removed. `edc003-su1/render-site-config.py`, `setup-object-store.sh`, `build-x86-client.py`, `preflight.py` and `install-peer-node.sh` implement site preparation; review arguments/source before using because these are provisioning scripts, not generic safe rerun commands.

Every compute peer runs from `/stn-disk/exemplar/nvis-p2p`; its catalog sync checks the two existing local images and exact receipts. `rollout-existing-images.py` and `finalize-fleet-adoption.py` produced 128 exact receipts across 64 nodes. The expected adoption marker was:

```text
NVIS_P2P_SYNC_COMPLETE total=2 ready=2 installed=0 failed=0
```

`installed=0` is intentional: existing correct files were adopted. Do not interpret it as a failed image install. The two native catalog objects and local receipts are distinct evidence: server objects existing alone do not prove all compute recipients are ready.

The read-only `nvis-p2p-edc003-health-audit.timer` runs every ten minutes using `edc003-su1/fleet-health-audit.py`. Latest evidence is `edc003-su1/state/fleet-health-latest.json`. It checks strict SSH, peer/timer, boot container, current-boot restore marker, Munge/slurmd, Enroot/Pyxis, image sizes and receipts. The read-only handoff observed 64/64 healthy at 13:55 UTC. That validates delivery/runtime prerequisites, not GPU/PSU or fabric health.

```bash
curl --fail --silent http://127.0.0.1:4300/nvis-p2p-health
systemctl status nvis-p2p-edc003-health-audit.timer --no-pager
python3 -m json.tool /cluster/OVA/NVISP2P/edc003-su1/state/fleet-health-latest.json
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes od1-edc003-b300-002 \
  'systemctl is-active nvis-p2p-peer.service nvis-p2p-catalog-sync.timer munge slurmd'
```

Secrets are in restricted NVIS directories and per-node `secrets/dfstore-readonly.env`. Inspect filenames, permissions and service status only; never `cat` secret files into the coding agent transcript. Use approved read-only identities. Rotate the previously exposed switch service identity through its owner; do not reproduce it. Owner confirmation of observed switch TLS pins remains separate from service authentication.

## 7. Health validation and selecting 32 nodes

Begin with read-only discovery; avoid trying to repair infrastructure by restarting a training runner. Read `/home/nvidia-ssh/AGENTS.md`, both Exemplar checkpoint files, the current cohort/gate and incident records. Date-stamped source reports explain why checks exist; live evidence determines readiness.

```bash
export PATH=/opt/slurm/25.11.2/bin:/home/nvidia-ssh/OVA/llmb_venv/bin:$PATH
export LLMB_INSTALL=/cluster/OVA/Exemplar/install
squeue -o '%.18i %.40j %.12T %.10M %.6D %R'
sinfo -N -o '%N %t %G'
scontrol show node -o
tmux list-sessions
python3 -m json.tool /cluster/OVA/exemplar/logs/suite-256/runner-status.json
python3 -m json.tool /cluster/OVA/exemplar/logs/suite-256/state.json
# Inspect only if the manifest exists. Its absence does not replace checking Slurm.
python3 -m json.tool /cluster/OVA/Exemplar/active-job.json
```

For each selected host verify management reachability, trusted identity, eight GPUs, Munge/slurmd, container startup, PMIx, persistent mounts, exact images/config/cache and adequate free disk. `audit_suite_prereq.py` checks resource paths, scratch mount, GPU count, Enroot and slurmd; `audit_prereq_nodes.py` reads HCA/GID plus known network environment settings. **Both old audit scripts write fixed September filenames and use all 64**, so inspect/adapt output names to preserve original evidence before rerunning. They are supporting audits, not a launch approval.

Check GPU/DCGM current temperature/power/clock behavior, volatile and aggregate uncorrected ECC, remapped row failures/pending remap, reset-required status, Xid and NVLink errors. Aggregate ECC is historical and must be reported separately from current volatile errors. Do not automatically reset a GPU, mask warnings or change Slurm state. Current candidate exclusions are PSU-critical nodes001/017/026/058/060/063 plus user-excluded nodes007/010; selected cohort also avoids nodes013/030/048 with prior ECC history. Node007 had mlx5_4–7 down in the October scan. These reasons are dated; a changed cohort requires explicit revalidation and a new isolated manifest, not silent replacement.

Useful read-only per-host checks (field availability depends on driver; if a field is unsupported, use `nvidia-smi -q` and record the corresponding value):

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes od1-edc003-b300-002 \
  'nvidia-smi -L; nvidia-smi -q -d ECC,ROW_REMAPPER,TEMPERATURE,POWER; df -h /stn-disk /scratch; systemctl is-active munge slurmd'
```

Power must have current Redfish coverage for every selected node and no PSU-critical metric. The runner queries `redfish_psu_health` and blocks on missing node coverage or any zero value. Independently inspect sample age/exporter success and all expected PSU bays; the installed presence/value check alone does not prove freshness or complete bay coverage. GPU/PSU telemetry is not replaced by static NVIS readiness.

### Exact host port eligibility

Every selected host must have all **32 intended HCA port1 devices**:

```text
mlx5_0..11, mlx5_14..21, mlx5_26..29, mlx5_32..39
```

`check_32hca_eligibility.py` requires, per device, `4: ACTIVE`, `5: LinkUp`, `200 Gb/sec (2X NDR)`, GID index3 type `RoCE v2`, carrier1 and a valid IPv4-mapped GID actually assigned to its associated netdev. A missing port makes that **node ineligible**; never intersect the available lists and reduce everybody to 30 or one HCA.

```bash
# Read-only hosts; writes a NEW audit report on controller.
python3 /cluster/OVA/Exemplar/check_32hca_eligibility.py \
  --nodes-file /cluster/OVA/Exemplar/cohort256-nodes.txt \
  --json-out /cluster/OVA/exemplar/logs/cohort256-hca-current.json
```

This script currently uses SSH `StrictHostKeyChecking=accept-new`, so ensure all selected hosts already have independently verified trusted keys. A novel key must be verified before use; an audit must not become unreviewed identity enrollment.

Current cohort is nodes002/003/004/005/006/008/009/011/012/015/016/018/019/020/021/022/023/024/025/027/028/029/031/032/033/034/035/036/037/038/039/040. Read the canonical file rather than hand-maintaining this list. The sorted first host is node002; numeric rendezvous is **10.6.33.2** on `enp57s0f0np0`. Verify that IP still belongs to that host, and that all selected nodes can route/connect to it at the chosen rendezvous port. Earlier hostname-resolution failure on node039 prevented eight ranks joining TCPStore. Numeric rendezvous prevents that particular DNS dependency; it does not cure a missing TCPStore server or firewall failure.

## 8. Fabric evidence, topology and NCCL preflight

There are three separate meanings of “P2P”: NVIS/Dragonfly peer distribution of image artifacts; the physical point-to-point wiring spreadsheet; and NCCL GPU send/receive tests. A passing image transfer or host link test does not validate NCCL data paths.

Wiring design is `/home/nvidia-ssh/OVA/stn_b300_spx_p2p_v1.7-draft.xlsx`. Do not treat its leaf-spine lines as observed wiring. Live topology at `http://localhost:4300/topology/` uses host LLDP/NIC/DCGM/Redfish plus Slurm/rank/NCCL attempted paths. Authenticated `/nvis/api/topology/snapshot?job_id=<ID>` requires an NVIS root session. Switch collection is currently selective, not complete fabric flow attribution. Read `/home/nvidia-ssh/TOPOLOGY_WORK.md`, `/home/nvidia-ssh/OVA/Observability/live_topology/README.md` and `SWITCH_TELEMETRY_BLOCKER.md`. Three leaf timers observe P02-01/P02-04/P04-04, expire samples after 300 seconds and distinguish planned from observed neighbor. Other leaves/spines and per-job switch-flow attribution remain absent. Dated September wrong-neighbor/down-port evidence explained failures; verify current repairs through fresh switch samples and end-to-end transport tests.

Local 32-port link health previously coexisted with same-plane cross-leaf RDMA failure. Matched GPU four-HCA tests passed while GPU3-to-GPU1/all-rail tests exposed pairing failures. A single-HCA pass, same-leaf control or two-node subset cannot approve the full cohort. Preserve rail/GPU pairing and failed-path evidence. Inspect `fabric-p03-p04-and-spine-handoff-20260926.md`, `fabric-32-subset-feasibility-20260926.md`, `job59-rdma-failure-analysis.md`, `job59-fabric-design-map.md`, and `logs/suite/node043-fabric-incident.md` before changing related state or interpreting old failures.

### The installed transport policy

The 256 runner overrides inherited settings and passes them through generated sbatch exports **and** `srun --container-env`:

| Variable | Value / meaning |
|---|---|
| `NCCL_SOCKET_IFNAME`, `GLOO_SOCKET_IFNAME` | `enp57s0f0np0`: actual bootstrap interface |
| `NCCL_IB_HCA` | `=` followed by all 32 `mlx5_N:1` names; exact allowlist |
| `NCCL_IB_GID_INDEX` | `3` |
| `NCCL_CROSS_NIC` | `0` |
| `NCCL_NET` | `IB` (NCCL verbs/RoCE transport; not a claim of InfiniBand physical fabric) |
| `NCCL_IB_QPS_PER_CONNECTION` | `4` |
| `NCCL_IB_TC`, `NCCL_IB_SL`, `NCCL_IB_TIMEOUT` | `104`, `1`, `20` |
| `NCCL_NET_GDR_C2C` | `1` |
| `UCX_NET_DEVICES` | Same 32 `mlx5_N:1` names without leading `=` |
| `NVSHMEM_HCA_LIST` | Same 32 HCA names without `:1` |
| `NCCL_DEBUG`, `NCCL_DEBUG_SUBSYS` | `INFO`, `INIT,NET` |
| `NCCL_DEBUG_FILE` | `/nemo_run/nccl-%h-%p.out`, per-process isolated output |
| `MASTER_ADDR` | Verified numeric first-cohort-host IPv4 |

These traffic/QoS/GID settings are site-specific. On another network derive them from approved configuration, then validate; do not merely copy them.

### Full-cohort test implementation and acceptance

`launch-cohort256-preflight-20261007.py` stages `nccl-cohort256-canary-20261007.py` to `/tmp` on all selected nodes and launches `srun` on `exemplar`, 32 nodes, 256 tasks, eight tasks/GPUs per node, 10-minute allocation, kill-on-bad-exit and NeMo26.06.01 image. It sets numeric MASTER_ADDR and port 19180. It writes `command.json`, `launcher.log`, `exit.json` and fetches each rank's `/tmp/<prefix>-<rank>.log` into per-node archive directories.

The canary sets CUDA device from SLURM_LOCALID and initializes NCCL with 180-second timeout. It verifies all-reduce correctness for float32 tensors of **1 MiB and 16 MiB** and P2P correctness for **1 MiB** at rank offsets **1,9,65,129**, barrier after each offset. Acceptance needs all 256 `COHORT_START`, `COHORT_ALLREDUCE_PASS` and `COHORT_P2P_PASS` rank markers, zero launcher exit, successful fetch from all 32 nodes, 256 rank files and the strict runtime inventory gate. Passing proves these tested sizes/pairings, not all possible traffic or sustained-training performance.

`nccl_runtime_gate.py` parses `NET/IB : Using` inventory and `Made virtual device` lines by host/local GPU. Each of the **256 ranks** must show exactly **32 distinct expected port1 devices**, indexed0..31, and **eight disjoint merged groups each `ndevs=4`** whose union is exactly all 32. Individual `ndevs=1` declarations are ignored. Missing/damaged log lines are not evidence of success. Separate process files avoid Slurm line interleaving; job82 stopped because merged stdout lost inventory evidence, not because 206 validated ranks alone proved a transport failure. Gate pass is mandatory evidence but not proof that later collectives will complete.

### Refreshing stale approval

The gate must be <=30 minutes old for a new recipe launch. `refresh_cohort256_preflight.py` performs a **new actual full-cohort test**, not a timestamp edit:

```bash
# SUBMITS a diagnostic srun job and writes approval/evidence.
# Run only when authorized, no training allocation is active, and all 32 nodes are idle.
python3 /cluster/OVA/Exemplar/refresh_cohort256_preflight.py \
  /cluster/OVA/Exemplar/cohort256-preflight.json \
  /cluster/OVA/Exemplar/cohort256-nodes.txt
```

It requires an existing `ready:true` approval with unchanged cohort, verifies master IP/idle nodes/current HCA/PSU, then sets `ready:false` while the test runs. Failed validation keeps readiness false. Successful validation writes `validation.json` and a new timestamp/evidence path. It preserves prior canary context. If readiness has been revoked or cohort changed, it refuses; diagnose and rebuild reviewed approval from passing evidence rather than flipping the boolean manually.

**Implementation limitation:** the launcher reads the canonical `/cluster/OVA/Exemplar/cohort256-nodes.txt` and `cohort256-preflight.json` internally. Although refresh accepts positional file arguments, do not point them to alternate cohorts and expect isolation; adapt and review launcher paths first. The runner's between-job helper automatically calls this refresh when an otherwise-ready approval exceeds 30 minutes, with a960-second timeout. Initial runner startup itself still rejects stale approval, so refresh before restarting.

Approval requires exact 32 nodes, exact 32 names, `four_hca_canary_pass:true`, `all_rail_canary_pass:true`, all-rail statusPASS with node_count 32/hca_count 32 and a nonempty absolute evidence file, `rendezvous_verified:true`, first selected master hostname and private numeric master IPv4, and recent checked_utc. Independent telemetry refresh remains necessary; historic true flags must not carry a changed policy through a new launch.

## 9. Plan and run the 13 cases

The 256 runner reads B300 entries from `install/llmb_repo/exemplar.yaml`, expands dtype lists and deliberately moves Nemotron-H first. It does not edit official scale 512 matrix. Current order:

| # | Workload | Size | Dtype |
|---:|---|---|---|
| 1 | `pretrain_nemotron-h` | `56b` | `fp8` |
| 2 | `pretrain_deepseek-v3` | `671b` | `bf16` |
| 3 | `pretrain_deepseek-v3` | `671b` | `fp8` |
| 4 | `pretrain_deepseek-v3` | `671b` | `nvfp4` |
| 5 | `pretrain_gpt_oss` | `120b` | `bf16` |
| 6 | `pretrain_kimi-k2` | `1t` | `fp8` |
| 7 | `pretrain_llama3.1` | `405b` | `fp8` |
| 8 | `pretrain_llama3.1` | `405b` | `nvfp4` |
| 9 | `pretrain_llama3.1` | `70b` | `fp8` |
| 10 | `pretrain_llama3.1` | `70b` | `nvfp4` |
| 11 | `pretrain_nemotron_3` | `120b` | `bf16` |
| 12 | `pretrain_qwen3` | `235b` | `bf16` |
| 13 | `pretrain_qwen3` | `235b` | `fp8` |

```bash
# Plan only: no Slurm submission.
python3 /cluster/OVA/Exemplar/run_b300_suite_256.py \
  --nodes-file /cluster/OVA/Exemplar/cohort256-nodes.txt --plan
```

**Do not run `llmb-run exemplar` for the256 campaign**: its official matrix requests512. Do not run the old `run_b300_suite.py` or `launch_verified_nemotron.py`; the latter is historical30-HCA code. Preserve selected recipe topology, 50-step workload and dtype. Do not lower bandwidth or disable NIC merging to hide fabric faults.

Before launch reconcile **all** of tmux, runner process/lock, Slurm, active manifest, runner-status and state. If job86 or any newer job is active, monitor it; do not restart runner, refresh while it occupies cohort or duplicate submission. The runner has an exclusive `runner.lock` and refuses existing active-job.json, but Slurm is the independent source of truth for orphaned jobs.

When no active job/runner exists, user authorization permits continuation, fresh checks pass and retry policy allows it, run in a persistent session:

```bash
# SUBMITS training jobs. Example normal continuation, not for use while an active runner exists.
tmux new-session -d -s exemplar-suite-256 \
  'export PATH=/opt/slurm/25.11.2/bin:/home/nvidia-ssh/OVA/llmb_venv/bin:$PATH; export LLMB_INSTALL=/cluster/OVA/Exemplar/install; python3 -u /cluster/OVA/Exemplar/run_b300_suite_256.py --nodes-file /cluster/OVA/Exemplar/cohort256-nodes.txt --fabric-preflight-file /cluster/OVA/Exemplar/cohort256-preflight.json >> /cluster/OVA/exemplar/logs/suite-256/runner.log 2>&1'
```

A recorded failed key is retried before unattempted keys. `--priority-failed-key pretrain_deepseek-v3_671b_bf16` can prioritize a diagnosed failed key; it does not bypass a second-failure halt. If a held job remains, `--resume-held-job <ID>` verifies its state and matching first incomplete recipe before staging/release. Inspect code and state carefully: failed-key priorities and held-job resume must refer to the same intended task. Never manually delete manifests or reset completed_keys to defeat safeguards. A changed cohort or HCA list is rejected against existing `run-manifest.json`; use a reviewed separate campaign directory and adapt paths, preserving existing state.

### What the runner invokes for each recipe

1. Rechecks cohort file, current gate (refreshing it if stale), numeric master IP, all 32 **IDLE** and eight GPU GRES, controller free disk  >= 50 GiB and available RAM  >= 4 GiB, 32-HCA eligibility and PSU health.
2. Raises submission `RLIMIT_NOFILE` soft to 65535; refuses hard limit below 65535. This is inherited by the generated launch; do not reduce it to accommodate a misconfigured host.
3. Invokes from `install/`:

```text
/cluster/OVA/Exemplar/install/llmb-run submit
  -w <workload> --model-size <size> --dtype <dtype> --scale 256
  --nodelist <exact comma-separated32 hosts> --slurm-arg hold
  --env <each transport key=value from section 8>
```

4. Parses `jobid=`, verifies Slurm `PENDING/JobHeldUser`, finds generated `Command` path and `_CONFIG`, checks every required export and container env forwarding.
5. Builds `suite-256/job<ID>-stage.tar.gz`; invokes `stage_held_job_256.py <ID> <experiment> --nodes-file ... --archive ... --summary suite-256/job<ID>-staging.json`. It streams the tar via strict SSH to exactly 32 hosts, verifies its SHA256, extracts at identical paths and requires32/32 without failures. Failed staging leaves job held.
6. Writes active-job.json, then invokes `scontrol release <ID>`. It polls every 5 seconds and validates isolated NCCL evidence before continuing.
7. Cancels and halts for a malformed inventory, inaccessible NCCL evidence after 3 reads or incomplete gate after 300 seconds. A RUNNING job without valid BatchHost after 30 seconds is also cancelled. This is a strict evidence failure, not permission to silently rerun a recipe or weaken validation.
8. Archives stdout and each node's `nccl-*.out`, computes log SHA256, writes jobs/job<ID>.json and suite state, clears only its own active manifest, and updates durable checkpoint/observer state through the installed monitoring workflow.

### Generated sbatch and container chain

NeMo-Run generates `*_sbatch.sh` under `install/workloads/<workload>/experiments/<shape>/<shape>_<timestamp>/`. Job86 example shape:

```text
pretrain_deepseek_v3_bf16_gpus256_tp1_pp8_cp1_vp2_ep8_etp1_mbs1_gbs4096
```

The generated job86 script requests account/partition exemplar, exclusive allocation, hold, nodes32, ntasks-per-node8, mem0 and time 45min. It sets TorchX retries 0, offline HF/Transformers flags, transport env and recipe-specific Hybrid-EP settings. A preliminary `srun` queries head-node IP, but explicit MASTER_ADDR remains the verified numeric override. Its main `srun` invokes Pyxis with NeMo26.06.01, mounts HF cache and Megatron performance scripts plus experiment child directory at `/nemo_run`, passes required env, uses `--mpi=pmix`, `--no-container-mount-home`, `--container-writable`, `--wait=60` and `--kill-on-bad-exit=1`, then runs:

```text
bash /nemo_run/scripts/<shape>.sh
```

That child script/config calls the installed workload's performance entry point. The sbatch epilogue prints `job exited with code N`; nonzero exits propagate. Exact scripts/configs are retained in each experiment along with `_CONFIG`, `__main__.py`, `llmb-config_<ID>.yaml`, generated config YAML and run script. Inspect them rather than hand-writing an alternate training command. Bare `sbatch` of a historical generated script reuses old environment/path/allocation and bypasses runner staging/gates; do not use it for continuation.

### Retry and halt policy

A normal failed recipe gets one **immediate retry before the next LLM** after required checks. A second failure stops for diagnosis. Setup/preflight/staging/archive errors also halt. **Runtime inventory evidence failures halt immediately** and need diagnosis; the implementation does not automatically retry them. Job82 was diagnosed before the succeeding job83. A halted retry may be resumed only after targeted diagnosis, repaired prerequisites and new passing evidence under the user's authorization; starting the runner again without diagnosis is not a valid recovery procedure.

## 10. Logs, status, monitoring and reading numbers

| Evidence | How to use |
|---|---|
| `suite-256/runner.log` | Human-readable runner stdout; events/errors and automatic refresh |
| `suite-256/events.jsonl` | Timestamped submitted_held/staged/released/runtime_gate/job_done/immediate_retry/halt events |
| `suite-256/state.json` | Latest final state per recipe key; completed_keys includes attempts that failed |
| `suite-256/runner-status.json` | 15-second observer heartbeat, active Slurm state and alert codes |
| `suite-256/run-manifest.json` | Cohort/HCA/campaign identity |
| `suite-256/job<ID>-staging.json` | SHA256 archive and32/32 recipient result |
| `suite-256/job<ID>-logs/` | Retrieved main/batch logs and per-host isolated NCCL files |
| `jobs/job<ID>.json` | Result record, main log path/hash and final runtime gate summary |
| `active-job.json` | Current experiment/log/batch host; node-local live output |
| `logs/nccl-cohort256-refresh-<UTC>/` | Fresh canary commands, per-rank logs and validation |
| `suite-256/host-profile.jsonl` | Controller resource profile every 30 seconds, not GPU training performance |

The live main log is on the **BatchHost** at manifest.log_path. A same-named controller path may be empty or stale until archived. Use strict SSH to that host and path. After completion read the recorded archive path. Isolated rank NCCL files are on every compute node under the experiment child mounted at `/nemo_run`; the runner fetches them under per-host directories.

```bash
# Discover live host/path without assuming node001 or a historic path.
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/cluster/OVA/Exemplar/active-job.json')
if p.exists():
    x=json.loads(p.read_text())
    print('job:',x['job_id'],'host:',x['batch_host'])
    print('log:',x['log_path'])
else:
    print('No active manifest: check Slurm and suite state before acting.')
PY
# Replace HOST and ABSOLUTE_LOG_PATH with the discovered values.
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes HOST 'tail -n 80 ABSOLUTE_LOG_PATH'
tail -n 30 /cluster/OVA/exemplar/logs/suite-256/events.jsonl
```

Dashboard: `http://localhost:3300/d/stn-b300-exemplar?orgId=1&refresh=5s`. Observer scripts are `watch_suite_256.py`, `refresh_exemplar_dashboard.py`, and `exemplar_exporter.py`; verify deployed service/process status rather than starting duplicate observers. The watcher does **not** send chat notifications. An active agent must report a blocker when observed.

Compute log wall-clock strings have sometimes used UTC-7 while the jump-box/JSON evidence uses UTC. Preserve the original timestamp/timezone and normalize to UTC when correlating events; do not infer a seven-hour delay from two differently zoned clocks. Use JSON `*_utc` timestamps and Slurm durations where possible. On this site `sacct` reports accounting storage disabled. Use `scontrol` while jobs remain resident and durable jobs/job<ID>.json plus batch/runner archives after removal; absence from scontrol does not alone establish completion.

A typical training line contains `iteration 50/50`, elapsed time per iteration in milliseconds and `TFLOPs`. Convert milliseconds to seconds (`4780.6 ms = 4.7806 s`). Distinguish initialization/compilation/optimizer setup from completed training steps: log growth or RUNNING state alone is not progress through iterations. Report latest completed step and UTC age; if none, say none. A warning count alone does not establish failure. Fatal evidence includes NCCL ibv_modify_qp/async transport timeout, TCPStore connection timeout, Hybrid-EP ALLGATHER TIMEOUT, OOM, rank exception, node failure and nonzero batch exit. Main stdout can omit first-fault rank context; inspect per-host logs and scheduler/node data before assigning cause.

Recipe names encode **GPUs**, **TP** tensor parallel, **PP** pipeline parallel, **CP** context parallel, **VP** virtual pipeline, **EP** expert parallel, **ETP** expert tensor parallel, **MBS** micro-batch size and **GBS** global batch size. Example DeepSeek256 is TP1 PP8 CP1 VP2 EP8 ETP1 MBS1 GBS4096. Nemotron256 is TP2 PP1 CP1 EP1 MBS1 GBS768. GBS changes with supported scale; compare only matching configured recipes. Do not assume that doubling GPUs halves step time with unchanged GBS.

A DeepSeek line can read `GPU utilization: 864.6MODEL_TFLOP/s/GPU`. Despite that label,864.6 is throughput, **not a percent**. DCGM GPU utilization percent is a separate telemetry measure.

TFLOPS/GPU in the logs is the recipe's modeled floating-point work divided by elapsed time and GPU count; it is not a direct hardware-counter utilization percentage. Record precision/recipe/scale and score window. Do not mix a single final step with a steady-state mean or compare raw values across models/precision as if they describe identical work. Use the official recipe's scoring/parser conventions and approved baseline for the same configuration. Prior analyses used steps 35–44 to avoid startup and profiling boundary effects; do not declare this universally prescribed for every recipe without checking its scoring documentation.

For a simple independent log inspection:

```bash
rg 'iteration|elapsed time per iteration|TFLOPs|TIMEOUT|NCCL WARN|Traceback|out of memory|job exited with code' \
  /cluster/OVA/exemplar/logs/suite-256/job83-logs/*.out
```

For archived job52 at 512 GPUs, the measured mean35–44 was 5.71647 s and 1,441.84 TFLOPS/GPU against supplied 1,641.52 baseline, **87.84%**. That was below the >95% threshold. Job83's256-GPU final 1,724.1 value must not be divided by that 512 baseline and presented as certification. A job can exit 0 and complete50 steps yet remain below performance threshold; a runtime gate can pass yet training later fail. Report execution success, fabric evidence and performance qualification separately.

## 11. Troubleshooting and recovery without duplicate work

| Symptom | Evidence / next action |
|---|---|
| Existing active manifest or Slurm RUNNING | Monitor existing job; inspect tmux/runner. Do not resubmit. |
| PENDING `JobHeldUser` | Inspect matching experiment and staging summary; use reviewed held-job resume only. Do not release blindly. |
| Stale gate | Refresh with new full-cohort diagnostic when idle; do not edit checked_utc. |
| `ready:false` | Diagnose recorded blockers; no training launch or old 512 substitution. |
| Down/ineligible HCA | Exclude/repair node under approved policy; preserve all 32 requirement and regenerate matching campaign evidence. |
| TCPStore DNS or connection timeout | Verify numeric master ownership, route/port/listener and rank coverage; hostname fix alone does not validate RDMA. |
| RDMA QP timeout | Correlate local/remote GIDs, HCA/GPU mapping and live switch path; reproduce failed bound verbs/P2P pairs plus controls. |
| Hybrid-EP allgather timeout | Preserve first rank/timeout details; correlate expert-group mapping, network/rank participation and GPU health. A generic all-reduce preflight pass does not establish expert-collective health. |
| Inventory incomplete | Read isolated per-process files; distinguish logging damage, missing process init and actual device mismatch. Never count interleaved fragments as a pass. |
| Archive failure | Halt; collect surviving node-local files and preserve metadata before proceeding. |
| Slurm DOWN/NOT_RESPONDING or changed host keys | Verify management and live-root restore; do not reboot or mark nodes IDLE without diagnosis. |
| Runner heartbeat stale, job still running | Treat as observer/runner incident; reconcile without another submit. |

`reconcile_suite_job.py`, `reconcile_then_resume_suite.sh`, `retry_failed_after_suite.py` and `stage_held_job.py` are mostly historical 512 tools. Review hardcoded paths/counts before considering adaptation. The old retry-after-suite strategy does not implement the current immediate-retry policy. Do not invoke it to silently advance past a failure.

Read `logs/suite/node043-fabric-incident.md` before changing node043 state or rerunning jobs54/55 conditions. Its carrier recovery did not explain prior optical loss. Read `logs/suite/job59-fabric-incident.md` before historical 512 continuation. New repair work must preserve evidence and current Slurm allocations. User authorization for this guide does not authorize infrastructure repair or a new job.

## 12. Operator script inventory and handoff evidence

| Script / file | Contract |
|---|---|
| `run_b300_suite_256.py` | Canonical256 sequential runner and all launch gates |
| `stage_held_job_256.py` | SHA256 staging exactly 32 selected recipients; no job release itself |
| `nccl_runtime_gate.py` | Strict32 devices/eight ndevs4 groups per host/GPU |
| `refresh_cohort256_preflight.py` | Idle-only new full-cohort diagnostic and atomic gate refresh |
| `launch-cohort256-preflight-20261007.py` | Canonical cohort staging/srun/log retrieval |
| `nccl-cohort256-canary-20261007.py` | Correctness all-reduce and offset P2P workload |
| `check_32hca_eligibility.py` | Host-local link/GID/netdev checks, JSON report |
| `audit_suite_prereq.py`, `audit_prereq_nodes.py` | Historical supporting audits; fixed output names/all 64 caveat |
| `verify-node.sh`, `SHA256SUMS` | Static payload/runtime verification |
| `watch_suite_256.py` | Status heartbeat/alerts, no chat notifications |
| `exemplar_exporter.py`, `refresh_exemplar_dashboard.py` | Dashboard metric/export support |
| `sync_logs.py` | Links local logs into central tree; does not fetch all live compute files |
| `run_b300_suite.py`, `stage_held_job.py` | Historical512 suite; not current256 launch |
| `deploy-fleet-staging.py` | Historical v3 mutating component rollout; prefer current v4 path |
| NVIS `fleet-health-audit.py` | Read-only delivery/bootstrap audit |
| NVIS `install-peer-node.sh`, `rollout-existing-images.py` | Mutating peer/adoption deployment; do not retransmit prepared images |
| NVIS `bootstrap/rollout-boot.py`, `boot-activate.sh` | Persistent restore/peer activation deployment |

Retain current `cohort256-nodes.txt`, gate with referenced canary evidence, `run-manifest.json`, installer playbook, installed config, source commit, image manifests, Slurm configuration without secrets, transport policy, generated experiment/config/script trees, staging summaries, all rank/stdout/batch logs and per-job SHA256 records. For packaging official results inspect `llmb-run archive --help` from the installed release; it creates an experiment/config archive, but custom external site evidence may need a separate attachment. On this local-disk setup make sure all remote outputs are retrieved first. Do not assume the CLI archive includes files never copied from compute nodes.

Submission/publication requires the owner's approved destination and authorized upload; do not send NVIDIA messages automatically. Remove credentials, private keys, tokens, Munge keys and sensitive environment dumps from shareable archives. These two guides contain operational paths/hostnames and non-secret hashes; obtain the owner's approval for distributing cluster-specific information outside its intended audience.

## 13. Suggested instruction for the next coding agent

> Read `run_exemplar.md` and `agent_exemplar_skills.md`, then local AGENTS.md and current Exemplar/NVIS checkpoints. Discover and reconcile the current job, runner, gate and cohort before changing anything. If a job is running, monitor it and report actual iteration progress. If authorized to continue and no job is active, validate all compute/GPU/PSU/HCA/runtime prerequisites, refresh full-cohort all-rail evidence when needed, and use the canonical256 runner with immediate retry/second failure halt. Preserve official recipes and all 32 HCAs. Never reboot nodes, expose secrets, manufacture a gate pass or restart the old 512 queue as a substitute. If a required artifact/access is absent, identify precisely what the owner must provide and complete independent read-only checks.
