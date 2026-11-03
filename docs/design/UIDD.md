# UI Design Document (UIDD): Windows 10 Disaster Recovery Application

## SDLC Phase Summary: Design & Prototyping

Current Stage: Low-to-High Fidelity Prototyping & Layout Mapping.

Objective: Translate the Tkinter GUI requirements into a calm, simple, and non-intimidating interface that supports source selection, scanning, report loading, report export, and review of potential user-data findings.

The UI is designed for users who may be stressed, non-technical, and afraid of losing data.

## 1. Component Blueprint

The application uses a simplified vertical layout:

- Top toolbar: mode and report actions.
- Secondary-drive advisory banner.
- Source list panel.
- Scan action.
- Application and findings grid.
- Details pane.
- Single-line status bar with tooltips.

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Win10 Disaster Recovery Tool                      Mode: ACTIVE SCAN        │
│                                              [Load Report] [Export Report] │
├────────────────────────────────────────────────────────────────────────────┤
│ Important: If you used secondary drives for programs, games, projects,     │
│ photos, videos, or other personal files, add those drives now.             │
│ Wiping or reinstalling can make data unrecoverable.                        │
├────────────────────────────────────────────────────────────────────────────┤
│ Sources                                                     [Add] [Remove] │
│ ┌────────────────────────────────────────────────────────────────────────┐ │
│ │ /dev/nvme0n1p3   Windows drive   ntfs-3g read-only   Ready             │ │
│ │ /dev/sdb1        Secondary drive  ntfsls report      Ready             │ │
│ └────────────────────────────────────────────────────────────────────────┘ │
│ [Start Scan]                                                               │
├────────────────────────────────────────────────────────────────────────────┤
│ Applications and Potential User Data                     Filter: [All ▾]   │
│ ┌────────────────────────┬─────────┬─────────────┬──────────────┬────────┐ │
│ │ Application            │ Version │ Source      │ Status       │ Risk   │ │
│ ├────────────────────────┼─────────┼─────────────┼──────────────┼────────┤ │
│ │ Steam Client           │ 2.10.4  │ Windows     │ Registered   │ Low    │ │
│ │ Cyberpunk 2077         │ 1.63    │ Windows     │ Registered   │ High   │ │
│ │ Portable Notes         │ n/a     │ Secondary   │ Portable     │ Medium │ │
│ │ Custom Python Tool     │ 1.0.0   │ Windows     │ Orphaned     │ High   │ │
│ │ Mozilla Firefox        │ 115.0   │ Windows     │ Registered   │ Low    │ │
│ └────────────────────────┴─────────┴─────────────┴──────────────┴────────┘ │
├────────────────────────────────────────────────────────────────────────────┤
│ Details: Cyberpunk 2077                                                    │
│ Summary: Registered application found on the Windows drive.                │
│ Evidence: 9 registry items, 4 filesystem items.                            │
│ Potential User Data:                                                       │
│   HIGH: Users\Admin\Saved Games\CD Projekt Red\Cyberpunk 2077              │
│   Reason: Outside resolved Documents folder and matches saved-game path.   │
├────────────────────────────────────────────────────────────────────────────┤
│ Status: Ready. Hover for details.                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

## 2. Source List Panel

The source list panel is the primary way users understand what will be scanned.

Each source row shall show:

- Device name or manifest file name.
- Source role:
  - Windows drive.
  - Secondary drive.
- Acquisition method:
  - ntfs-3g read-only.
  - ntfsls report.
- Read-only indicator.
- Status:
  - Pending.
  - Ready.
  - Error.

The panel shall avoid exposing raw technical details unless the user opens source details.

The user shall not be required to type device paths manually unless necessary.

## 3. Secondary Drive Advisory

The advisory banner shall be visible near the source list.

It shall remain visible during active scan mode.

It shall use calm but clear wording.

Example:

> Important: If you used secondary drives for programs, games, projects, photos, videos, or other personal files, add those drives now. Wiping or reinstalling can make data unrecoverable.

The banner should not be dismissible by default, because the risk is significant and users may overlook it under stress.

## 4. Application and Findings Grid

The main grid shall remain simple.

Default columns:

- Application.
- Version.
- Source.
- Status.
- Risk.

`Status` may show:

- Registered.
- Partial.
- Portable.
- Orphaned.
- Unknown.

`Risk` may show:

- None.
- Low.
- Medium.
- High.

Color may be used, but color alone shall not convey meaning.

The grid shall support sorting by column.

The grid shall support a simple filter dropdown.

Recommended filters:

- All.
- Registered.
- Portable.
- Orphaned.
- High Risk.
- Outside Documents.
- Specific user profile.

## 5. Details Pane

The details pane shall explain the selected item without overwhelming the user.

For an application, the details pane shall show:

- Application name.
- Version.
- Publisher, if known.
- Install path, if known.
- Fingerprint status.
- Confidence.
- Evidence summary.
- Potential user-data findings.
- Rationale for findings.
- Warnings.

For a user-data finding, the details pane shall show:

- Path.
- Source.
- Associated user, if known.
- Associated application, if known.
- Location category.
- Inside Documents result.
- Severity.
- Confidence.
- Rationale.

The details pane shall not display file contents.

## 6. Status Bar

The status bar shall be one line.

It shall provide a brief summary of current state.

Examples:

```text
Status: Ready. 2 sources added.
Status: Scanning Windows registry...
Status: Completed. 42 applications, 9 potential user-data findings.
Status: Report loaded. Viewer mode.
```

The status bar shall support tooltips that provide expanded detail.

Tooltip detail may include:

- Number of sources.
- Number of applications.
- Number of evidence items.
- Number of portable candidates.
- Number of user-data findings.
- Number of warnings.

The status bar shall not become a multi-line log panel in the main UI.

## 7. Theme and Color Tokens

```python
COLOR_BG_PRIMARY = "#1e1e2e"
COLOR_BG_SURFACE = "#252538"
COLOR_TEXT_MAIN = "#cdd6f4"
COLOR_ACCENT_BLUE = "#89b4fa"
COLOR_SUCCESS = "#78f36c"
COLOR_WARNING = "#f9e2af"
COLOR_DANGER = "#ff5c65"
FONT_FAMILY_BASE = ("Segoe UI", 10)
```

Color usage:

- Green: ready, safe, registered.
- Amber: medium confidence or medium risk.
- Red: high risk, orphaned, or error.

Color shall always be paired with text labels.

## 8. Interaction State Logic

### Active Scan State

Enabled controls:

- Add Source.
- Remove Source.
- Load Report.
- Export Report.
- Start Scan.

Behavior:

- Selecting a source triggers safe acquisition checks.
- If a selected partition is already mounted, the application requests explicit confirmation before unmounting.
- Scanning runs in a background worker.
- Progress is shown through the status bar and progress indicator.
- UI updates occur through queue callbacks.

### Report Viewer State

Triggered by loading a report.

Behavior:

- Source acquisition controls are locked.
- Scan controls are locked.
- Mode badge shows `REPORT VIEWER`.
- The UI hydrates from the report.
- No drive operations are permitted.

## 9. Accessibility and QA Checklist

- [ ] Keyboard navigation flows logically from toolbar to source list to scan button to grid to details pane.
- [ ] All buttons have accessible labels.
- [ ] Tooltips are accessible by keyboard focus where practical.
- [ ] Amber and red warning colors meet contrast requirements against the surface background.
- [ ] The source list remains usable at minimum window size 800x600.
- [ ] The advisory banner remains readable when the window is resized.
- [ ] Viewer mode clearly disables active controls.
- [ ] The status bar remains one line.
- [ ] Expanded status details are available through tooltips.
- [ ] Long paths are truncated gracefully with tooltips or details-pane access.
- [ ] Error messages are actionable and non-blaming.