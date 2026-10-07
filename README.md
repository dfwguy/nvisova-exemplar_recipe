# Exemplar recipe and operator kit

STN EDC003 SU1 B300 operating and reproduction handoff, imported from the NVFTP Exemplar_OVA folder on 2026-10-07.

Start with [run_exemplar.md](run_exemplar.md), then read [agent_exemplar_skills.md](agent_exemplar_skills.md).

The five original handoff files are preserved unchanged at the repository root. The operator archive is also extracted under `cluster/` and `reference/` for source review. All 59 source files were verified against `operator-scripts-manifest.json` at import.

Verify the original handoff with:

```bash
sha256sum -c SHA256SUMS.txt
```

These scripts contain site-specific paths and settings. Review and adapt them before execution. The kit excludes official workload repositories, licensed images, credentials, and live operational state. The 256-GPU diagnostic described here is separate from the official 512-GPU qualification matrix.

Source: https://nvftp.nvidia.com/file-explorer/8250a39b-4b0d-47dd-ae22-27b0db9a4618/nvidia-space/shared/STN/Exemplar_OVA
