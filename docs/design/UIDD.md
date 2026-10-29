### SDLC Phase Summary: Design & Prototyping (Phase 2)
* **Current Stage:** Low-to-High Fidelity Prototyping & Layout Mapping.
* **Objective:** Translate the Tkinter GUI requirements (`FR-4`, `NFR-2`) and SQLite/Snapshot state behaviors (`DDD.md`) into a structured layout. Since the project uses a Tkinter frontend (`app/ui.py`), we will use high-clarity ASCII/Unicode structural wireframes combined with Blazor-compatible CSS tokens (`FR-4`, `SDD.md` Section 2) to bridge the Penpot design tokens with our desktop Python UI architecture.

---

### 1. Component Blueprint (Terminal & Tkinter Layout Wireframe)

The application utilizes a split-pane layout: a top control toolbar for drive/manifest ingestion, a primary master-detail data grid (Treeview) for discovered applications and save risk indicators, and a bottom status/log console.

```text main_dashboard
┌───────────────────────────────────────────────────────────────────────────────────┐
│ [Win10 Disaster Recovery Tool]               Mode: ACTIVE SCAN  [📁 Load Snapshot]│
├───────────────────────────────────────────────────────────────────────────────────┤
│ Source Drive / Manifest: [/dev/sdd1                         ] [ Browse... ] [Scan]│
├───────────────────────────────────────────────────────────────────────────────────┤
│ Application Inventory & Heuristic Saves                           Filter: [All   ]│
├───────────────────────────────────────────┬─────────────┬──────────┬──────────────┤
│ Application Name                          │ Version     │ Registry │ Local Saves  │
├───────────────────────────────────────────┼─────────────┼──────────┼──────────────┤
│ 🟢 Steam Client                           │ 2.10.4      │ Verified │ None         │
│ 🟡 Cyberpunk 2077                         │ 1.63        │ Verified │ ⚠️ /saves (H)│
│ 🔴 Custom Python Tool                     │ 1.0.0       │ Orphaned │ ⚠️ /profiles │
│ 🟢 Mozilla Firefox                        │ 115.0       │ Verified │ None         │
│ 🟡 Visual Studio Code                     │ 1.85.1      │ Verified │ ⚠️ /userdata │
├───────────────────────────────────────────┴─────────────┴──────────┴──────────────┤
│ Details: Cyberpunk 2077                                                           │
│   Install Path: C:/Program Files/CD Projekt Red/Cyberpunk 2077                    │
│   Discovered Saves: C:/Users/Admin/Saved Games/CD Projekt Red/Cyberpunk 2077      │
│   Severity Level: HIGH (User data present in unmanaged partition path)            │
├───────────────────────────────────────────────────────────────────────────────────┤
│ Status: Idle. 42 applications parsed. 3 heuristic save directories flagged.       │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

### 2. Penpot-Aligned CSS Tokens & Tkinter / Blazor Styling

To maintain design parity between Penpot UI mockups and implementation, the following color and spacing tokens map directly to `NFR-2` (Empathy & Warning Colors):

```css
:root {
  --color-bg-primary: #1e1e2e;
  --color-bg-surface: #252538;
  --color-text-main: #cdd6f4;
  --color-accent-blue: #89b4fa;
  --color-success: #78f36c;    /* Green: Verified / Safe */
  --color-warning: #f9e2af;    /* Amber: Medium Risk Saves */
  --color-danger: #ff5c65;     /* Red: Orphaned / High Risk Saves */
  --font-family-base: "Segoe UI", system-ui, sans-serif;
}
```

---

### 3. Interaction State Logic

* **Active Scan State (`active`):**
  * `@onclick` / Button Trigger: Dispatches background worker thread (`NFR-1`) executing `app/ingest.py` and `app/heuristics.py`.
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