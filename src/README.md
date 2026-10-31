### 1. Python Project Directory Structure

```text
win10-disaster-recovery/
├── setup.sh                   # Root bootstrap script (ADR-2)
├── requirements.txt           # Python dependencies
├── README.md                  # Project goals, setup, and execution guide
├── src/
│   ├── __init__.py
│   ├── models.py              # DTOs / Dataclasses (AppRecord, ScanSession, etc.)
│   ├── mount_manager.py       # Block device discovery & safe read-only mounting (ADR-5)
│   ├── db.py                  # SQLite persistence & connection pooling (DDD.md)
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── manifest_parser.py # ntfsls manifest reader (ADR-1)
│   │   └── registry_parser.py # Offline SOFTWARE/SYSTEM hive parser
│   ├── heuristics.py          # Local save directory detection & pattern matching
│   ├── state.py               # Snapshot export & JSON/SQLite report hydration (ADR-3)
│   ├── coordinator.py         # Background worker thread & queue coordinator (ADR-4)
│   ├── ui.py                  # Tkinter Presentation layer & dashboard (UIDD.md)
│   ├── main.py                # Application entry point
│   └── README.md              # YOU ARE HERE!
└── tests/
    ├── __init__.py
    ├── test_ingest.py         # Mocked tests for manifest & registry parsing
    ├── test_heuristics.py     # Mocked tests for save directory matching
    └── test_db.py             # SQLite persistence unit tests
```

---

### 2. Implementation Roadmap (Execution Order)

To ensure smooth integration and adhere to our dependency graph (where lower-level data layers feed higher-level presentation layers), we will implement the modules in the following ordered sequence:

1. **Phase 3.1: Project Scaffolding & Configuration**
   * **A.** Create `requirements.txt` and `setup.sh`. **(Completed)**
   * **B.** Create `src/models.py` (Core DTOs & Dataclasses).
2. **Phase 3.2: Persistence & Mount Layers (`src/db.py` & `src/mount_manager.py`)**
   * **A.** Implement SQLite connection management, schema initialization, and transactional queries per `DDD.md`.
   * **B.** Implement block device discovery (`lsblk`) and safe read-only mounting (`ntfs-3g` / `umount -l`) per `ADR-5`.
3. **Phase 3.3: Ingestion & Heuristic Engines (`src/ingest/` & `src/heuristics.py`)**
   * **A.** Build `manifest_parser.py` (handling `ntfsls` text output).
   * **B.** Build `registry_parser.py` (parsing offline Windows hives using `regipy`).
   * **C.** Build `heuristics.py` (scanning installation paths for save nomenclature like `saves`, `profiles`, etc.).
4. **Phase 3.4: State Manager & Coordinator (`src/state.py` & `src/coordinator.py`)**
   * **A.** Implement snapshot export/import serialization (`FR-5`, `ADR-3`).
   * **B.** Implement thread-safe `queue.Queue` communication layer (`NFR-1`, `ADR-4`).
5. **Phase 3.5: Presentation Layer & Main Entry Point (`src/ui.py` & `src/main.py`)**
   * Implement the Tkinter Dashboard (`UIDD.md`), master-detail treeview, status indicators, and Report Viewer mode.
6. **Phase 3.6: Automated Testing (`tests/`)**
   * Write `pytest` unit tests with mocked fixtures for independent module verification.

---

### 2.1. Technical Debt & Edge Cases to Monitor During Implementation

1. **Orphaned Mount Point Cleanup:** 
   * *Risk:* If the application crashes during an active scan after mounting a partition to `/tmp/win10_recovery`, the temporary mount point may remain active or locked.
   * *Mitigation:* Ensure `src/mount_manager.py` implements a robust `atexit` handler or `try...finally` block to unmount and clean up `/tmp/win10_recovery` gracefully upon exit.
2. **`lsblk` JSON Output Variations:**
   * *Risk:* Different versions of util-linux (`lsblk`) across Linux distributions may output slightly varying JSON structures.
   * *Mitigation:* Explicitly pass `--json` and `--output NAME,FSTYPE,SIZE,MOUNTPOINTS,LABEL` flags to `lsblk`, and write defensive parsing keys in `src/mount_manager.py`.
3. **Registry Hive Permission Locking:**
   * *Risk:* Offline `SOFTWARE` and `SYSTEM` hives might occasionally throw read errors if incomplete journal recovery files (`$LogFile`) are present on dirty NTFS partitions.
   * *Mitigation:* Ensure `src/ingest/registry_parser.py` gracefully catches `regipy` hive-loading exceptions and flags affected application records as `Unknown` rather than crashing the worker thread.

---

### 3. Quick Start & Installation

1. **Clone the Repository & Bootstrap Environment:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Run the Application:**
   ```bash
   conda activate win10-recovery  # (or activate your python virtual environment)
   python src/main.py
   ```

3. **Run Unit Tests:**
   ```bash
   pytest tests/
   ```
