# Architecture Decision Records (ADRs)

## ADR-1: Utilization of `ntfsls` for Dirty NTFS Partitions
* **Context:** Windows fast shutdown leaves NTFS volumes in a "dirty" state, causing kernel mount blocks (`mount -t ntfs3`) to fail or risk metadata corruption.
* **Decision:** Bypass kernel mounting entirely by executing `sudo ntfsls -f -R <partition>` to generate read-only text manifests, or accept pre-generated manifests.
* **Consequences:** Ensures 100% non-destructive interaction with damaged partitions; requires user `sudo` authentication only for raw device scanning.

## ADR-2: Dual-Path Deployment via Unified Bootstrap Script (`setup.sh`)
* **Context:** Advanced users prefer isolated Conda environments on existing Linux hosts, while non-technical users require a zero-friction Live USB session.
* **Decision:** Implement a single `setup.sh` script that detects the runtime environment and installs dependencies locally without altering global host packages.
* **Consequences:** Balances developer flexibility with accessible end-user recovery paths.

## ADR-3: Snapshot Caching and Read-Only Report Viewer Mode
* **Context:** Application enumeration and heuristic scanning are time-consuming operations that users should not have to repeat.
* **Decision:** Support exporting enumeration results to a structured snapshot file and implement a Read-Only Viewer mode when loading reports.
* **Consequences:** Saves user time, prevents accidental re-triggering of long-running scans, and simplifies UI state management.
