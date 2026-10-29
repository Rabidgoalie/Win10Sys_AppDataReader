# Software Design Document (SDD): Windows 10 Disaster Recovery Application

## 1. Architecture Overview
The application follows a modular, layered architecture separating system bootstrapping, data ingestion, heuristic processing, persistent storage, and presentation layers.

```
[ setup.sh (Bootstrap Orchestrator) ]
               │
               ▼
┌───────────────────────────────┐
│     Core Python Package       │
│  ├── Ingestion Engine         │  (Registry Parser & ntfsls Manifest Reader)
│  ├── Heuristic Scanner        │  (Local Save Directory Detection)
│  ├── SQLite Persistence Layer │  (Structured Data & Caching - see DDD.md)
│  └── State & Export Manager   │  (JSON Report Caching & Snapshot Load)
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│      Tkinter Presentation     │
│  ├── Interactive Grid View    │
│  └── Read-Only Report Viewer  │
└───────────────────────────────┘
```

## 2. Module Specifications
* **`setup.sh`**: Detects execution environment (Conda vs. Live USB), verifies Python/Git/ntfs-3g prerequisites, and installs local dependencies.
* **`src/ingest`**: Handles user drive path inputs, executes `sudo ntfsls -f` when raw partitions are targeted, and reads offline registry hives (`SOFTWARE`, `SYSTEM`).
* **`src/heuristics.py`**: Implements directory traversal and pattern matching against application folders to flag hidden user save files.
* **`src/db.py`**: Manages SQLite connection pooling, schema initialization, and transactional persistence based on `docs/design/DDD.md`.
* **`src/state.py`**: Manages data serialization, exporting enumeration results to snapshot reports, and loading reports into memory.
* **`src/ui.py`**: Implements the Tkinter GUI, providing treeview tables, progress bars, and mode-switching between active scanning and read-only report viewing.

## 3. Data Flow & State Management
1. User provides paths via GUI dialogs.
2. Ingestion layer extracts registry and manifest data into intermediate data classes (`AppRecord`).
3. Heuristic engine decorates records with local save findings.
4. UI records render; user can export snapshots or reload previous exports to lock the UI into report-viewer mode.

## 4. Detailed Module Map & Core APIs
* **`setup.sh`**: `check_environment()`, `install_dependencies()`
* **`src/ingest`**: `parse_manifest(manifest_path: str) -> List[AppRecord]`, `read_registry_hives(hive_dir: str) -> RegistryData`
* **`src/heuristics.py`**: `scan_for_saves(install_path: str) -> List[HeuristicSaveResult]`
* **`src/db.py`**: `init_db(db_path: str)`, `save_session_data(session: ScanSession)`, `load_session_data(session_id: str)`
* **`src/state.py`**: `export_snapshot(session_id: str, output_path: str)`, `import_snapshot(snapshot_path: str) -> ScanSession`
* **`src/ui.py`**: `AppDashboard(tk.Tk)`, `update_treeview(records: List[AppRecord])`, `set_view_mode(mode: str)`

### 4.1 Dependency Graph & Coupling Analysis
```text
┌─────────────────────────┐
│        setup.sh         │ (Infrastructure - Independent)
└─────────────────────────┘

┌─────────────────────────┐     ┌──────────────────────────┐
│        src/ingest       │     │    src/heuristics.py     │
└────────────┬────────────┘     └────────────┬─────────────┘
             │                               │
             └───────────────┬───────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│                      src/db.py                           │ (Persistence Engine)
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                      src/state.py                        │ (Serialization & Snapshot)
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                      src/ui.py                           │ (Presentation Layer)
└──────────────────────────────────────────────────────────┘
```

## 5. Architectural Patterns & Decoupling Strategies
* **Observer / Callback Pattern (`NFR-1`):** Background worker threads communicate progress and parsed records back to `app/ui.py` using thread-safe queues (`queue.Queue`) and Tkinter event bindings, ensuring the UI remains non-blocking and responsive.
* **Data Transfer Objects (DTOs):** Ingestion and heuristic layers pass immutable Python `dataclasses` (`AppRecord`) rather than raw database cursors or UI widgets, enforcing strict boundary encapsulation.
* **Testability:** All modules are independently testable via `pytest` with mocked filesystem paths and dummy registry hive fixtures, requiring no live root privileges or physical drives during unit testing.
