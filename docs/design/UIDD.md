# UI Design Document (UIDD): Windows 10 Disaster Recovery Application

## 1. Objective

Translate the Tkinter GUI requirements into a calm, simple, and non-intimidating interface that supports source selection, scanning, report loading, report export, and review of potential user-data findings.

The UI is designed for users who may be stressed, non-technical, and afraid of losing data.

---

## 2. Component Blueprint

The application uses a simplified vertical layout:

- Top toolbar: mode and report actions.
- Secondary-drive advisory banner.
- Source list panel.
- Scan action area.
- Application and findings grid.
- Details pane.
- Single-line status bar with tooltips and compact progress indication.

The scan action area shall show:

- `Start Scan` when no scan is running.
- `Cancel Scan` while a scan is running.

The status bar shall include a compact progress indicator during scanning.

### 2.1 UI Wireframes
The wireframes in this section are implementation guidance. The normative UI behavior is defined by the interaction-state logic, grid row contract, details-pane rules, and safety requirements in this document. If a wireframe conflicts with those rules, the textual rules prevail and the wireframe must be corrected.

#### 2.1.1 ACTIVE-Mode Pre-Scan
This is the main pre-scan review screen in active mode.

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ Win10 Disaster Recovery Tool                                            Mode: ACTIVE  │
│                                                         [Load Report] [Export Report] │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Important: If you used secondary drives for programs, games, projects, photos,        │
│ videos, or other personal files, add those drives now. Wiping or reinstalling can     │
│ make data unrecoverable.                                                              │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Sources                                                                [Add] [Remove] │
│ ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Windows drive (512 GB)    Windows drive    ntfs-3g read-only    Pending           │ │
│ └───────────────────────────────────────────────────────────────────────────────────┘ │
│ [Start Scan]                                                                          │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Applications and Potential User Data                                Filter: [All ▾]   │
│ ┌─────────────────────────┬─────────┬─────────────┬──────────────┬──────────────────┐ │
│ │ Application             │ Version │ Source      │ Status       │ Risk             │ │
│ ├─────────────────────────┼─────────┼─────────────┼──────────────┼──────────────────┤ │
│ │                         │         │             │              │                  │ │
│ │                         │         │             │              │                  │ │
│ │                         │         │             │              │                  │ │
│ │                         │         │             │              │                  │ │
│ │                         │         │             │              │                  │ │
│ └─────────────────────────┴─────────┴─────────────┴──────────────┴──────────────────┘ │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Details:                                                                              │
│ Summary:                                                                              │
│ Evidence:                                                                             │
│ Potential User Data:                                                                  │
│                                                                                       │
│                                                                                       │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Status: Ready to scan. 1 source added.                                                │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
**ACTIVE-Mode Pre-Scan Notes**

- The mode is `ACTIVE`, not `TRIAGE`.
- `Start Scan` is available.
- `Load Report` is available.
- `Export Report` is available.
- The grid remains empty.
- The details pane remains empty.
- The source is `Pending` because it has been added but not yet prepared. Preparation and mounting occur when the user clicks Start Scan.
- The status bar shows a user-facing readiness summary rather than exposing internal session-state terminology.
- The main Windows drive has been added; the secondary data drive has not yet been added.

#### 2.1.2 ACTIVE-Mode Scanning State Snippet

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ Win10 Disaster Recovery Tool                                            Mode: ACTIVE  │
│                                                         [Load Locked] [Export Locked] │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Important: If you used secondary drives for programs, games, projects, photos,        │
│ videos, or other personal files, add those drives now. Wiping or reinstalling can     │
│ make data unrecoverable.                                                              │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Sources                                                                   [Locked]    │
│ ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Windows drive (512 GB)    Windows drive    ntfs-3g read-only    Ready             │ │
│ │ Data drive (1 TB)         Secondary drive  ntfsls report        Ready             │ │
│ └───────────────────────────────────────────────────────────────────────────────────┘ │
│ [Start Scan: unavailable] [Cancel Scan]                                               │
├───────────────────────────────────────────────────────────────────────────────────────┤
|                                                                                       |
~                                                                                       ~

...UI Elements omitted for brevity...

~                                                                                       ~
|                                                                                       |
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Status: Scanning Windows registry...  [############----------------]                  │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

##### ACTIVE-Mode Scanning State Snippet Notes
- `Start Scan` is unavailable while scanning.
- `Cancel Scan` is visible while scanning.
- Progress is shown compactly in the status bar.
- Source controls remain locked.
- `Load Report` is locked.
- `Export Report` is locked.

#### 2.1.3 ACTIVE-Mode Post-Scan
This is the main post-scan review screen in active mode.

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ Win10 Disaster Recovery Tool                                            Mode: ACTIVE  │
│                                                         [Load Report] [Export Report] │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Important: If you used secondary drives for programs, games, projects, photos,        │
│ videos, or other personal files, add those drives now. Wiping or reinstalling can     │
│ make data unrecoverable.                                                              │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Sources                                                                   [Locked]    │
│ ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Windows drive (512 GB)    Windows drive    ntfs-3g read-only    Complete          │ │
│ │ Data drive (1 TB)         Secondary drive  ntfsls report        Complete          │ │
│ └───────────────────────────────────────────────────────────────────────────────────┘ │
│ [Start Scan: unavailable]                                                             │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Applications and Potential User Data                                Filter: [All ▾]   │
│ ┌─────────────────────────┬─────────┬─────────────┬──────────────┬──────────────────┐ │
│ │ Application             │ Version │ Source      │ Status       │ Risk             │ │
│ ├─────────────────────────┼─────────┼─────────────┼──────────────┼──────────────────┤ │
│ │ Steam Client            │ 2.10.4  │ Windows     │ Registered   │ Low              │ │
│ │ Cyberpunk 2077          │ 1.63    │ Windows     │ Registered   │ High             │ │
│ │ Potential user data     │ n/a     │ Secondary   │ Saved Games  │ High             │ │
│ │ Portable Notes          │ n/a     │ Secondary   │ Portable     │ Medium           │ │
│ │ Mozilla Firefox         │ 115.0   │ Windows     │ Registered   │ Low              │ │
│ └─────────────────────────┴─────────┴─────────────┴──────────────┴──────────────────┘ │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Details: Cyberpunk 2077                                                               │
│ Summary: Registered application found on the Windows drive.                           │
│ Evidence: 9 registry items, 4 filesystem items.                                       │
│ Potential User Data:                                                                  │
│   HIGH: Users\Admin\Saved Games\CD Projekt Red\Cyberpunk 2077                         │
│   Reason: Outside resolved Documents folder and matches saved-game path.              │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Status: Completed. 42 applications, 9 potential user-data findings. Hover for detail. │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
**ACTIVE-Mode Wireframe Notes**

- The mode is `ACTIVE`, not `TRIAGE`.
- Source controls are locked because scanning has already occurred.
- `Start Scan` is unavailable.
- `Export Report` is available.
- The grid does **not** show the Confirmed checkbox because Confirmed is a Triage Mode column.
- The grid includes both application rows and finding rows.
- The finding row uses a human-readable location category in the Status column.
- The status bar is one line.

#### 2.1.4 TRIAGE-Mode
This is the screen shown after loading a report.

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ Win10 Disaster Recovery Tool                                            Mode: TRIAGE  │
│                                                         [Load Report] [Export Report] │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Important: If you used secondary drives for programs, games, projects, photos,        │
│ videos, or other personal files, add those drives now. Wiping or reinstalling can     │
│ make data unrecoverable.                                                              │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Sources                                                                   [Locked]    │
│ ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Windows drive (512 GB)    Windows drive    ntfs-3g read-only    Complete          │ │
│ │ Data drive (1 TB)         Secondary drive  ntfsls report        Complete          │ │
│ └───────────────────────────────────────────────────────────────────────────────────┘ │
│ Scan controls are unavailable in Triage Mode.                                         │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Applications and Potential User Data                                Filter: [All ▾]   │
│ ┌──────────┬────────────────────────┬─────────┬─────────────┬──────────────┬────────┐ │
│ │Confirmed │ Application            │ Version │ Source      │ Status       │ Risk   │ │
│ ├──────────┼────────────────────────┼─────────┼─────────────┼──────────────┼────────┤ │
│ │   [ ]    │ Steam Client           │ 2.10.4  │ Windows     │ Registered   │ Low    │ │
│ │   [✓]    │ Cyberpunk 2077         │ 1.63    │ Windows     │ Registered   │ High   │ │
│ │   [ ]    │ Potential user data    │ n/a     │ Secondary   │ Saved Games  │ High   │ │
│ │   [ ]    │ Portable Notes         │ n/a     │ Secondary   │ Portable     │ Medium │ │
│ │   [ ]    │ Mozilla Firefox        │ 115.0   │ Windows     │ Registered   │ Low    │ │
│ └──────────┴────────────────────────┴─────────┴─────────────┴──────────────┴────────┘ │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Details: Cyberpunk 2077                                                               │
│ Summary: Registered application found on the Windows drive.                           │
│ Evidence: 9 registry items, 4 filesystem items.                                       │
│ Potential User Data:                                                                  │
│   HIGH: Users\Admin\Saved Games\CD Projekt Red\Cyberpunk 2077                         │
│   Reason: Outside resolved Documents folder and matches saved-game path.              │
│ ───────────────────────────────────────────────────────────────────────────────────── │
│ User Triage:                                                                          │
│ [✓] Confirm this contains my important user data.                                     │
│ Notes: [ Mom's save files for Cyberpunk. DO NOT DELETE.                         ]     │
│ Auto-saves when you click away.                                                       │
├───────────────────────────────────────────────────────────────────────────────────────┤
│ Status: Triage Mode. 1 of 5 findings confirmed. Hover for details.                    │
└───────────────────────────────────────────────────────────────────────────────────────┘
```
**TRIAGE-Mode Wireframe Notes**
- The mode badge is `TRIAGE`.
- Source acquisition controls are locked.
- Scan controls are unavailable.
- The Confirmed checkbox column appears.
- The details pane includes the User Triage section.
- Notes auto-save on blur.
- The status bar reflects triage confirmation count.

---

## 3. Source List Panel

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
- Status.

Internal source statuses shall be mapped to user-facing labels:

| Internal Status | User-Facing Label |
|---|---|
| pending | Pending |
| ready | Ready |
| complete | Complete |
| error | Error |

The panel shall avoid exposing raw technical details unnecessarily.

The user shall not be required to type device paths manually.

Sources may be added or removed before scanning begins.

Sources shall be locked once scanning begins.

---

## 4. Add Source Flow

When the user chooses to add a block-device source:

1. The application presents likely NTFS candidate devices.
2. The user selects a device.
3. The application asks:
   - “Is this the drive that contains Windows?”
   - “Is this a secondary drive with programs, games, or personal files?”
4. The application records the selected role.
5. The source appears in the source list as Pending.

Manifest sources shall always be added as secondary sources.

The application shall prevent more than one Windows drive role per session.

---

## 5. Secondary Drive Advisory

The advisory banner shall be visible near the source list.

It shall remain visible during active scan mode.

It shall use calm but clear wording.

Example:

> Important: If you used secondary drives for programs, games, projects, photos, videos, or other personal files, add those drives now. Wiping or reinstalling can make data unrecoverable.

The banner shall not be dismissible by default.

---

## 6. Application and Findings Grid

The main grid shall remain simple.

Default columns:

- Confirmed, in TRIAGE mode.
- Application.
- Version.
- Source.
- Status.
- Risk.

The grid shall support a deterministic mixed row model.

### 6.1 Row Types

The grid shall support two row types:

1. Application rows.
2. User-data finding rows.

The row type shall not be exposed as a technical column, but it shall drive rendering and filtering.

### 6.2 Application Row Rules

For application rows:

- Confirmed column is blank and inactive.
- Application shows display name.
- Version shows application version where known.
- Source shows the source role or friendly source label.
- Status shows fingerprint status.
- Risk shows the highest severity of associated user-data findings, or None.

Status display mapping:

| Internal Fingerprint Status | Display Label |
|---|---|
| Registered | Registered |
| PartiallyRegistered | Partial |
| Portable | Portable |
| Orphaned | Orphaned |
| Unknown | Unknown |

### 6.3 Finding Row Rules

For finding rows:

- Confirmed column shows a checkbox in TRIAGE mode.
- Application shows the associated application name, or “Potential user data” if no application is associated.
- Version is blank.
- Source shows the source role or friendly source label.
- Status shows a human-readable location category.
- Risk shows the finding severity.

Severity display mapping:

| Internal Severity | Display Label |
|---|---|
| Low | Low |
| Medium | Medium |
| High | High |

Color may be used, but color alone shall not convey meaning.

### 6.4 Sorting and Filtering

The grid shall support sorting by column.

The grid shall support a simple filter dropdown.

Filters:

- All.
- Registered.
- Portable.
- Orphaned.
- Low Risk.
- Medium Risk.
- High Risk.
- Outside Documents.
- Specific user profile.
- Confirmed, in TRIAGE mode.

Filter semantics:

- Application-status filters show application rows only.
- Risk-level filters (`Low Risk`, `Medium Risk`, `High Risk`) show application rows matching the derived risk level and finding rows matching the corresponding severity level.
- Outside Documents shows finding rows where `inside_documents` is false.
- Specific user profile shows finding rows associated with that profile and application rows directly associated with those findings.
- Confirmed shows confirmed finding rows.

---

## 7. Details Pane

The details pane shall explain the selected item without overwhelming the user.

### 7.1 Application Details

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

### 7.2 Finding Details

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

### 7.3 User Triage Section

For a user-data finding, while the application is in TRIAGE mode, the details pane shall include a User Triage section containing:

- A checkbox to confirm the finding.
- A multi-line text area for user notes.

The application shall automatically save the triage state when the checkbox is toggled.

The application shall automatically save notes text when the text area loses focus.

The application shall also flush unsaved notes before:

- report export;
- application exit;
- loading another report.

No manual save button is required.

---

## 8. Status Bar

The status bar shall be one line.

It shall provide a brief summary of current state.

Examples:

- `Status: Ready. 2 sources added.`
- `Status: Scanning Windows registry...`
- `Status: Completed. 42 applications, 9 potential user-data findings.`
- `Status: Report loaded. Triage mode.`
- `Status: Scan stopped because the drive reported an I/O error.`

The status bar shall support tooltips that provide expanded detail.

Tooltip detail may include:

- Number of sources.
- Number of applications.
- Number of evidence items.
- Number of portable candidates.
- Number of user-data findings.
- Number of warnings.

The status bar shall include a compact progress indication during scanning.

The status bar shall not become a multi-line log panel in the main UI.

---

## 9. Theme and Color Tokens

```text
COLOR_BG_PRIMARY = "#1e1e2e"
COLOR_BG_SURFACE = "#252538"
COLOR_TEXT_MAIN = "#cdd6f4"
COLOR_ACCENT_BLUE = "#89b4fa"
COLOR_SUCCESS = "#78f36c"
COLOR_WARNING = "#f9e2af"
COLOR_DANGER = "#ff5c65"
```

Font family shall include Linux fallbacks:

```text
FONT_FAMILY_BASE = ("Segoe UI", "Ubuntu", "DejaVu Sans", 10)
```

Color usage:

- Green: ready, safe, registered.
- Amber: medium confidence or medium risk.
- Red: high risk, orphaned, or error.

Color shall always be paired with text labels.

---

## 10. Interaction State Logic

### 10.1 Active Idle State

Enabled controls:

- Add Source.
- Remove Source.
- Load Report.
- Export Report, if prior results exist.
- Start Scan, if a valid source configuration exists.

Behavior:

- Source acquisition has not yet started.
- Selecting a source does not mount it.
- Source preparation occurs after the user starts scanning.

### 10.2 Scanning State

Enabled controls:

- Cancel Scan.
- Export Report only if partial results are already available and export does not access source drives.

Disabled controls:

- Add Source.
- Remove Source.
- Load Report.
- Start Scan.

Behavior:

- Scanning runs in a background worker.
- Progress is shown through the status bar and compact progress indicator.
- UI updates occur through queued events.
- Closing the window requests cancellation and cleanup.

### 10.3 Critical I/O Failure State

Enabled controls:

- Export Report, if partial results exist.
- Close application.

Disabled controls:

- Add Source.
- Remove Source.
- Start Scan.
- Load Report.
- Cancel Scan, because the scan has already stopped.

Behavior:

- The status bar clearly indicates that scanning stopped because of a drive I/O error.
- A calm, critical dialog explains the possible failing-drive condition.
- The application does not retry source access.

### 10.4 Scan Completed State

Enabled controls:

- Export Report.
- Load Report.
- Close application.

Disabled controls:

- Add Source.
- Remove Source.
- Start Scan.

Behavior:

- Results are available for review.
- Mounts have been released.
- To scan again, the user restarts the application.

### 10.5 Triage Mode State

Triggered by loading a report.

Behavior:

- Source acquisition controls are locked.
- Scan controls are locked.
- Mode badge shows TRIAGE.
- The UI hydrates from the report, including previous `user_confirmed` and `user_notes` states.
- The user may toggle checkboxes and edit notes for user-data findings.
- No drive operations are permitted.
- Loading another report replaces the current report session after confirmation and safe cleanup.

---

## 11. Confirmation Dialogs

The application shall use explicit confirmation for:

- unmounting an already-mounted partition;
- using lazy unmount as a fallback;
- closing during an active scan;
- overwriting an existing report file;
- overwriting an existing manifest file;
- replacing the current triage session by loading another report.

Confirmation wording shall be calm and non-blaming.

---

## 12. Accessibility and QA Checklist

- [ ] Keyboard navigation flows logically from toolbar to source list to scan button to grid to details pane.
- [ ] All buttons have accessible labels.
- [ ] Tooltips are accessible by keyboard focus where practical.
- [ ] Amber and red warning colors meet contrast requirements against the surface background.
- [ ] The source list remains usable at minimum window size 800x600.
- [ ] The advisory banner remains readable when the window is resized.
- [ ] TRIAGE mode clearly disables active controls.
- [ ] The status bar remains one line.
- [ ] Expanded status details are available through tooltips.
- [ ] Long paths are truncated gracefully with tooltips or details-pane access.
- [ ] Error messages are actionable and non-blaming.
- [ ] Grid checkboxes are keyboard accessible in TRIAGE mode.
- [ ] Progress indication is perceivable without color alone.
