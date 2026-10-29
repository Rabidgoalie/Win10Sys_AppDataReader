# Software Design Document (SDD): Windows 10 Disaster Recovery Application

## 1. Architecture Overview
The application follows a modular, layered architecture separating system bootstrapping, data ingestion, heuristic processing, and presentation layers.

```
[ setup.sh (Bootstrap Orchestrator) ]
               │
               ▼
┌───────────────────────────────┐
│     Core Python Package       │
│  ├── Ingestion Engine         │  (Registry Parser & ntfsls Manifest Reader)
│  ├── Heuristic Scanner        │  (Local Save Directory Detection)
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
* **`bootstrap/setup.sh`**: Detects execution environment (Conda vs. Live USB), verifies Python/Git/ntfs-3g prerequisites, and installs local dependencies.
* **`app/ingest.py`**: Handles user drive path inputs, executes `sudo ntfsls -f` when raw partitions are targeted, and reads offline registry hives (`SOFTWARE`, `SYSTEM`).
* **`app/heuristics.py`**: Implements directory traversal and pattern matching against application folders to flag hidden user save files.
* **`app/state.py`**: Manages data serialization, exporting enumeration results to a report file, and loading reports into memory.
* **`app/ui.py`**: Implements the Tkinter GUI, providing treeview tables, progress bars, and mode-switching between active scanning and read-only report viewing.

## 3. Data Flow & State Management
1. User provides paths via GUI dialogs.
2. Ingestion layer extracts registry and manifest data into intermediate data classes (`AppRecord`).
3. Heuristic engine decorates records with local save findings.
4. UI renders records; user can export snapshots or reload previous exports to lock the UI into report-viewer mode.
