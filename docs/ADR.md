# Architecture Decision Records (ADRs)

## ADR-1: Utilization of `ntfsls` for Dirty NTFS Partitions
* **Context:** Windows fast shutdown leaves NTFS volumes in a "dirty" state, causing kernel mount blocks (`mount -t ntfs3`) to fail or risk metadata corruption.
* **Decision:** Bypass kernel mounting entirely by executing `sudo ntfsls -f -R <partition>` to generate read-only text manifests, or accept pre-generated manifests.
* **Consequences:** Ensures 100% non-destructive interaction with damaged partitions; requires user `sudo` authentication only for raw device scanning.

## ADR-2: Unified Virtual Environment Deployment via `setup.sh`
* **Context:** Users facing catastrophic "Inaccessible Boot Device" failures are often in a high state of anxiety and stress, making them vulnerable to blindly approving automated system modifications that could risk their dual-boot host integrity (if applicable).
* **Decision:** Implement a single `setup.sh` script that provisions an isolated local `.venv` virtual environment. For host-level system utilities (such as `python3-venv` or `ntfs-3g` for `ntfsls`), the script must *never* automatically install packages or prompt for blind confirmation. Instead, it must print a clear, empathetic explanation of why the tool is pausing, provide exact manual instructions, and safely exit to prevent compounding the user's stressful situation.
* **Consequences:** Prioritizes user safety and system caution over convenience, protecting vulnerable users from making destructive host-system decisions under duress.

## ADR-3: Snapshot Caching and Read-Only Report Viewer Mode
* **Context:** Application enumeration and heuristic scanning are time-consuming operations that users should not have to repeat.
* **Decision:** Support exporting enumeration results to a structured snapshot file and implement a Read-Only Viewer mode when loading reports.
* **Consequences:** Saves user time, prevents accidental re-triggering of long-running scans, and simplifies UI state management.

## ADR-4: Thread-Safe Queue Communication for Asynchronous UI Updates
* **Context:** Ingestion and heuristic scanning are heavy operations that would freeze the Tkinter GUI if executed on the main thread (`NFR-1`).
* **Decision:** Execute background tasks in daemon threads communicating back to `src/ui.py` exclusively via `queue.Queue` and thread-safe callbacks.
* **Consequences:** Ensures 60 FPS UI responsiveness and decouples background workers from presentation logic.
