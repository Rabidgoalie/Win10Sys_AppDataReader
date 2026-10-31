### SDLC Phase Summary: Design & Prototyping (Phase 2)
* **Current Stage:** Low-to-High Fidelity Prototyping & Layout Mapping.
* **Objective:** Translate the Tkinter GUI requirements (`FR-4`, `NFR-2`) and SQLite/Snapshot state behaviors (`DDD.md`) into a structured layout utilizing Tkinter grid and treeview components (`src/ui.py`).

---

### 1. Component Blueprint (Terminal & Tkinter Layout Wireframe)

The application utilizes a split-pane layout: a top control toolbar for block device ingestion (`lsblk` drive selection via `src/mount_manager.py`) or snapshot loading, a primary master-detail data grid (Treeview) for discovered applications and save risk indicators, and a bottom status/log console.

```text main_dashboard
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ [Win10 Disaster Recovery Tool]               Mode: ACTIVE SCAN  [📁 Load Snapshot]    │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Source Partition: [/dev/sdd1 (Windows - NTFS Unmounted)     ] [ Select Drive ] [Scan] │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Application Inventory & Heuristic Saves                               Filter: [All   ]│
├───────────────────────────────────────────────┬─────────────┬──────────┬──────────────┤
│ Application Name                              │ Version     │ Registry │ Local Saves  │
├───────────────────────────────────────────────┼─────────────┼──────────┼──────────────┤
│ 🟢 Steam Client                               │ 2.10.4      │ Verified │ None         │
│ 🟡 Cyberpunk 2077                             │ 1.63        │ Verified │ ⚠️ /saves (H)│
│ 🔴 Custom Python Tool                         │ 1.0.0       │ Orphaned │ ⚠️ /profiles │
│ 🟢 Mozilla Firefox                            │ 115.0       │ Verified │ None         │
│ 🟡 Visual Studio Code                         │ 1.85.1      │ Verified │ ⚠️ /userdata │
├───────────────────────────────────────────────┴─────────────┴──────────┴──────────────┤
│ Details: Cyberpunk 2077                                                               │
│   Install Path: /tmp/win10_recovery/Program Files/CD Projekt Red/Cyberpunk 2077       │
│   Discovered Saves: /tmp/win10_recovery/Users/Admin/Saved Games/CD Projekt Red/...    │
│   Severity Level: HIGH (User data present in unmanaged partition path)                │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Status: Idle. 42 applications parsed. 3 heuristic save directories flagged.           │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 2. Tkinter Theme & Color Tokens

To maintain design parity between UI mockups and implementation, the following color and spacing tokens map directly to `NFR-2` (Empathy & Warning Colors):

```python
# Tkinter Theme Tokens (src/ui.py)
COLOR_BG_PRIMARY = "#1e1e2e"
COLOR_BG_SURFACE = "#252538"
COLOR_TEXT_MAIN = "#cdd6f4"
COLOR_ACCENT_BLUE = "#89b4fa"
COLOR_SUCCESS = "#78f36c"    # Green: Verified / Safe
COLOR_WARNING = "#f9e2af"    # Amber: Medium Risk Saves
COLOR_DIGER = "#ff5c65"      # Red: Orphaned / High Risk Saves
FONT_FAMILY_BASE = ("Segoe UI", 10)
```

---

### 3. Interaction State Logic

* **Active Scan State (`active`):**
  * `@onclick` / Button Trigger: Dispatches background worker thread (`NFR-1`) executing `src/mount_manager.py`, `src/ingest/`, and `src/heuristics.py` via `src/coordinator.py`.
  * UI state updates via asynchronous queue callbacks, updating the progress bar and populating the Tkinter `ttk.Treeview`.
* **Report Viewer State (`viewer`):**
  * Triggered via `[📁 Load Snapshot]` (`FR-5`).
  * Locks ingestion controls, sets session mode to `viewer` in SQLite (`DDD.md`), and hydrates the grid directly from the cached JSON/SQLite snapshot without running filesystem scans.

---

### 4. QA Checklist (UI/UX & Accessibility)

* [X] **Color Contrast:** Verify Amber (`#f9e2af`) and Red (`#ff5c65`) warning indicators meet WCAG AA contrast ratios against `--color-bg-surface` (`#252538`).
* [ ] **Keyboard Navigation:** Ensure Tab-indexing flows logically from Source Drive input -> Browse Button -> Scan Action -> Treeview Grid -> Details Pane (`NFR-2`).
* [ ] **Responsiveness:** Test treeview column resizing behaviour when the main window is scaled down to minimum dimensions (800x600).
* [ ] **State Lockout:** Confirm that interacting with Snapshot Viewer mode correctly disables write-dependent buttons and clearly displays read-only indicator badges.