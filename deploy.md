# Agent deployment entry point

Give this file and its source directory to Codex, Claude, or another deployment agent.

Read [repository rules](AGENTS.md), [overview](README.md), [agent phases](agent_exemplar_skills.md), [execution runbook](run_exemplar.md), [air-gap procedure](docs/airgap.md), and [acceptance gates](docs/acceptance.md).

## Discover and prepare

Use the authorized controller and approved node scope. Discover the Slurm inventory, then verify DGX/HGX identity, GPU model/count, CPU architecture, drivers, GPU/RDMA topology, Pyxis/Enroot, storage and active allocations. Treat missing or failed probes as unknown. Do not infer a hardware family from a hostname. Keep the discovered roster and evidence outside Git.

Copy [the input template](config/cluster.example.json) into a private workspace. Resolve every placeholder and pin the official upstream commit. Provision NGC and Hugging Face access through credential files. Validate configuration with `python3 tools/prepare.py validate-config /absolute/private/cluster.json`. Select recipes supported by the actual hardware, precision, scheduler and GPU scale.

## Install and run

Follow the linked execution runbook through prerequisites, source installation, payload delivery, one-node canary and full-cohort communication acceptance. Resolve the exact container set from the pinned recipe; a universal two-container assumption is not supported. Record registry digests and verify delivery on every allocated node. Use P2P delivery only after its integrity checks pass.

Preview the installed CLI's plan and confirm partition, account, node list, ranks, mounts and model configuration. When running validations is authorized, submit the accepted workload matrix, monitor all ranks and retain stdout, stderr, scripts, configurations, timings and failure evidence. Register artifacts with the collection framework before submission. There is no web UI supplied by this deployment kit.

## Acceptance and recovery

Use the linked acceptance checklist. Distinguish structural checks, live readiness and measured recipe outcomes. Report exact commits, image digests, cohort, commands, timestamps, results, failures and remaining gaps. Keep a resumable checkpoint and follow documented recovery without deleting evidence. Offline repository tests do not qualify a GPU cluster.
