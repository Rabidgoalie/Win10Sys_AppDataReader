# Software Requirements Specification (SRS): Windows 10 Disaster Recovery Application

## 1. Introduction and Objectives

The Windows 10 Disaster Recovery Application is a free, MIT-licensed Linux desktop utility designed to help users recover from catastrophic Windows 10 boot failures, such as “Inaccessible Boot Device” BSOD events.

The application’s primary purpose is to help users locate and preserve irreplaceable, self-authored files before they reinstall an operating system or wipe a drive.

The application’s secondary purpose is to reconstruct a useful inventory of installed applications so that users can rebuild their former Windows environment as accurately as possible.

The application is intentionally non-destructive. It performs read-only discovery and analysis. It does not modify, repair, wipe, decrypt, or write to scanned drives.

The application is designed for users who may have limited technical experience and who are likely to be stressed, anxious, or fearful after a data-loss event. The interface and documentation should therefore be calm, clear, explicit, and forgiving.

The primary supported environment is an Ubuntu 24.04 Live Session. Pop!_OS 24.04 and closely compatible Linux systems are also supported for users who already have a Linux installation on the same machine.

## 2. Target Environment and Distribution

### 2.1 Supported Operating Environments

The application shall support:

- Ubuntu 24.04 Live Session, as the primary recommended environment.
- Pop!_OS 24.04, as a secondary supported environment.
- Other Ubuntu 24.04-compatible Linux systems, on a best-effort basis.

The application shall not support Windows as a host operating environment.

### 2.2 Distribution Model

The project shall be distributed in a form that does not require users to understand source-control tooling.

The documentation shall state that typical users should:

1. Download the project ZIP file.
2. Extract the ZIP file.
3. Run `setup.sh` from the extracted project directory.

The application shall not require `git` to be installed.

### 2.3 Python Environment

The application shall require Python 3.12.3 exactly.

This version is selected because it is the default Python version provided by Ubuntu 24.04.

The application shall use a local Python virtual environment named:

```text
Win10DRBPythonVenv
```

The application shall not reference, require, recommend, or depend upon Conda in any way.

The virtual environment shall isolate Python package dependencies from the host operating system.

Host-level system packages, such as `ntfs-3g`, are required by the application and must be installed on the host system. The application shall not attempt to install host packages automatically.

### 2.4 Network Requirement

A working internet connection is required during initial setup so that `setup.sh` can install Python dependencies into the virtual environment.

The application itself shall not require network access during scanning, analysis, report export, or report viewing.

## 3. Scope and Constraints

### 3.1 Non-Destructive Principle

The application shall perform strictly read-only operations against scanned drives and partitions.

The application shall never:

- Write to a scanned source drive.
- Modify NTFS metadata.
- Repair file systems.
- Clear dirty bits.
- Execute Windows binaries.
- Delete files.
- Move files.
- Rename files.
- Change permissions on scanned source files.

### 3.2 Supported Source Acquisition Methods

The application shall support only the following source acquisition methods:

1. `ntfs3g_ro`
   - Read-only mounting through `ntfs-3g` using safe read-only options.
2. `ntfsls_manifest`
   - Read-only filesystem enumeration using `ntfsls`, producing a manifest file.

The application shall not support externally mounted paths.

The application shall not operate against paths mounted by the kernel `ntfs3` driver, desktop auto-mounters, or file-manager mount points.

If a selected block device is already mounted, the application shall require explicit user confirmation before performing a lazy unmount and remounting the device through `ntfs-3g` in read-only mode.

### 3.3 No File-Content Inspection

The application shall not open, read, parse, display, or analyze file contents.

The application may use only:

- File names.
- Directory names.
- Full paths.
- File extensions.
- File sizes, when available.
- Timestamps, when available.
- File counts, when available.
- Registry key names.
- Registry value names.
- Registry value data.
- Manifest entries.

The application shall not attempt to determine with certainty whether a file is user-generated.

All user-generated-content findings shall be advisory only.

The user shall make the final judgment about whether a discovered location contains valuable data.

### 3.4 No AI or Automated Content Classification

The application shall not use AI, machine learning, remote classification services, or heuristic content interpretation that requires opening file contents.

The application shall not overstate confidence.

The application shall present findings as possible locations of user-generated content, not as confirmed backups or confirmed valuable files.

### 3.5 Secondary Drive Advisory

Because many users store programs, games, projects, and personal files on secondary drives, the application shall clearly warn users that they should add any secondary drives that may contain software or user data before reinstalling an operating system or wiping any drive.

The application shall not be expected to automatically determine whether an unadded secondary drive contains important data.

The responsibility for adding secondary sources remains with the user, but the application shall prominently remind the user of this responsibility.

### 3.6 Privacy

The application shall operate locally.

The application shall not transmit scanned data, file names, paths, registry data, report files, or telemetry to any external service.

The application shall not display file contents.

Reports may contain file paths, directory names, registry evidence, and related metadata. Users should understand that report files may reveal sensitive information about their files and installed applications.

### 3.7 Privilege Handling

The application shall use elevated privileges only when required for:

- Querying block devices with `lsblk`, where necessary.
- Performing lazy unmounts with `umount -l`.
- Mounting read-only through `ntfs-3g`.
- Running `ntfsls` against raw block devices.
- Generating `ntfsls` manifests from raw block devices.

The application shall not use elevated privileges to write to scanned source drives.

## 4. Functional Requirements

### FR-1: Source Management and Acquisition

#### FR-1.1 Source List Panel

The application shall provide a simple source-list panel.

The user shall be able to:

- Add a source.
- Remove a source.
- See the source type.
- See the source role.
- See the acquisition method.
- See whether the source is ready, pending, or failed.

The application shall not require users to manually type raw device paths unless no practical alternative exists.

#### FR-1.2 Block Device Discovery

The application shall enumerate block devices using JSON-formatted `lsblk` output.

The application shall explicitly request the fields it requires and shall parse the output defensively.

The application shall identify likely NTFS partitions and present them as candidate sources.

#### FR-1.3 Primary Windows Source

The application shall support one primary Windows source per scan session.

The primary Windows source shall be a block device or partition containing the offline Windows installation.

The primary Windows source shall be mounted using `ntfs-3g` in read-only mode.

The primary Windows source must be mounted because offline registry hive parsing requires direct read access to hive files.

The application shall mount the primary Windows source to an isolated temporary mount point under `/tmp/win10_recovery`.

The application shall use a distinct mount subdirectory per source to avoid collisions between multiple sources.

#### FR-1.4 Secondary Sources

The application shall support zero or more secondary sources.

Secondary sources may be:

- Secondary internal drives.
- External USB drives.
- Additional NTFS partitions.
- Manifest files generated from those drives.

For secondary sources, the application shall support:

1. Read-only mounting through `ntfs-3g`, or
2. Manifest generation using recursive `ntfsls`.

Manifest generation is recommended when the user only needs filesystem enumeration and does not need offline registry parsing from that secondary source.

#### FR-1.5 Manifest Generation

The application shall support generating recursive read-only manifests from raw block devices using `ntfsls`.

The logical equivalent of the manifest-generation command is:

```bash
sudo ntfsls -f -R /dev/DEVICEID > DEVICEID_manifest.txt
```

The application shall write generated manifest files only to a user-selected writable location or another safe writable location chosen by the application.

The application shall never write a manifest file to the source being scanned.

Manifest files shall be treated as read-only evidence sources after generation.

#### FR-1.6 Memory-Bounded Parsing

To protect Live Session memory constraints, parsing of manifests and large directory enumerations shall use streaming or bounded-memory techniques.

The application shall not load entire large manifests into memory when avoidable.

The application shall prefer line-by-line processing, incremental database insertion, or similarly memory-safe strategies.

#### FR-1.7 Secondary Source Advisory

Before scanning begins, the application shall display a clear advisory message similar to:

> Important: If you used secondary drives for programs, games, projects, documents, photos, videos, or other personal files, add those drives now. If you reinstall an operating system or wipe a drive, data on that drive may become unrecoverable.

This advisory shall be visible near the source-list panel.

The advisory shall use calm, non-alarming language while still making the risk clear.

#### FR-1.8 No Externally Mounted Paths

The application shall not allow the user to select an already-mounted filesystem path as a source.

If the user attempts to provide a mounted path, the application shall explain that this is unsupported and shall guide the user to select the underlying block device instead.

### FR-2: Exhaustive Offline Application Evidence Enumeration

#### FR-2.1 Evidence-First Discovery

The application shall collect raw discovery evidence before attempting to correlate that evidence into application records.

Evidence shall be treated as a first-class concept.

Evidence that cannot be correlated to an application shall still be retained so that it can be reviewed, exported, and potentially correlated later.

#### FR-2.2 Supported Evidence Sources

The application shall enumerate application evidence from supported offline Windows registry locations, filesystem locations, and manifest entries.

The list of supported evidence locations shall be maintained as versioned, data-driven configuration so that new evidence locations can be added without redesigning the parser.

The application shall parse all configured evidence locations unless a location is unavailable or unreadable.

#### FR-2.3 Registry Evidence Locations

The application shall enumerate supported registry evidence from at least the following hive types:

- Machine `SOFTWARE` hive.
- Machine `SYSTEM` hive.
- Per-user `NTUSER.DAT` hives.
- Per-user `UsrClass.dat` hives.
- `DEFAULT` user hive, where available.

The application shall explicitly handle both native and WOW6432Node registry views where applicable.

The application shall resolve the active `SYSTEM` control set from `SYSTEM\Select` instead of assuming `CurrentControlSet` is directly usable offline.

Appendix A lists the supported registry evidence locations.

#### FR-2.4 Multi-User Enumeration

The application shall enumerate multiple user profiles from the selected Windows source.

For each discovered user profile, the application shall attempt to identify:

- Username.
- Profile directory.
- Security identifier, where available.
- `NTUSER.DAT` path.
- `UsrClass.dat` path.
- Documents path.
- Desktop path.
- Downloads path.
- AppData Local path.
- AppData Roaming path.
- AppData LocalLow path.
- Saved Games path.
- Visual Studio source-code path, where present.

The application shall not assume that only one user profile exists.

#### FR-2.5 Evidence Retention

The application shall retain raw evidence records even when:

- The evidence is orphaned.
- The evidence is incomplete.
- The evidence cannot be correlated.
- The evidence conflicts with other evidence.
- The hive is partially unreadable.
- The manifest is incomplete.

Parse failures shall produce warnings and shall not crash the scan unless no further progress is possible.

#### FR-2.6 Application Correlation

The application shall correlate evidence into application records where possible.

Correlation may use:

- Display name.
- Publisher.
- Version.
- Install path.
- Normalized path.
- Product code.
- Executable name.
- Registry evidence type.
- Filesystem evidence type.
- Manifest evidence type.

Each application record shall receive a fingerprint status:

- `Registered`
- `PartiallyRegistered`
- `Portable`
- `Orphaned`
- `Unknown`

Each application record shall receive a confidence level:

- `Low`
- `Medium`
- `High`

### FR-3: Portable and Unregistered Application Discovery

#### FR-3.1 Portable Discovery Purpose

The application shall identify candidate portable or unregistered applications, especially on secondary drives and in manifest-derived evidence.

Portable applications may leave little or no registry fingerprint on the primary Windows installation.

#### FR-3.2 Portable Discovery Methods

The application shall identify portable application candidates using read-only heuristics based on:

- Directory structure.
- File names.
- Executable presence.
- Known portable-application layouts.
- Manifest entries.
- Absence of correlated registry evidence.

The application shall not execute scanned executables.

#### FR-3.3 Portable Confidence

Portable application findings shall include a confidence level.

The application shall distinguish between:

- Strong portable candidates.
- Possible portable candidates.
- Unregistered installed applications.
- Unknown executable bundles.

### FR-4: Potential User-Generated Content Classification

#### FR-4.1 Purpose

The application shall identify potential locations where user-generated content may exist.

The application shall especially identify potential user-generated content that is not stored inside the user’s resolved Documents folder.

The application shall not claim to know whether a file is valuable, irreplaceable, or truly user-generated.

The application shall present findings as advisory guidance to help the user decide what to preserve.

#### FR-4.2 No Content Inspection

The application shall not open file contents.

The application shall not parse document contents, image contents, database contents, archive contents, save-file contents, or any other file payload.

The application shall use only path, name, extension, metadata, and count-based signals where available.

#### FR-4.3 Documents Baseline Resolution

For each discovered user profile, the application shall attempt to resolve the Documents folder path.

The preferred source for Documents resolution is:

```text
Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders
```

with the value:

```text
Personal
```

If registry resolution fails, the application shall fall back to conventional paths, including:

```text
<UserProfile>\Documents
```

If the Documents path cannot be resolved, the application shall mark related findings as having an unknown Documents baseline.

#### FR-4.4 Candidate User-Data Locations

The application shall evaluate potential user-generated-content locations in at least the following categories:

- Application installation directories.
- Portable application data directories.
- Secondary-drive application directories.
- `AppData\Local`.
- `AppData\Roaming`.
- `AppData\LocalLow`.
- `Saved Games`.
- `VirtualStore`.
- `ProgramData`.
- User Desktop.
- User Downloads.
- User Pictures.
- User Music.
- User Videos.
- User Documents.
- OneDrive user folders, where identifiable.
- Visual Studio source-code folders.
- Other user-profile-specific folders that commonly contain user-authored data.

#### FR-4.5 Visual Studio Source Detection

For every discovered user profile, the application shall check for Visual Studio source-code locations, including:

```text
<UserProfile>\source
<UserProfile>\source\repos
```

If these directories exist and contain child entries, the application shall flag them as potential user-generated developer content.

The application shall not assume that every `source` directory is valuable, but it shall surface the location so the user can make the judgment.

#### FR-4.6 Classification Output

Each potential user-generated-content finding shall include:

- Source.
- Path.
- Normalized path.
- Location category.
- Associated application, if known.
- Associated user profile, if known.
- Whether the path is inside the resolved Documents folder.
- Matched heuristic pattern.
- File count, if available.
- Total size, if available.
- Severity.
- Confidence.
- Human-readable rationale.

The `inside_documents` result may be:

- True.
- False.
- Unknown.

#### FR-4.7 Severity Model

The application shall classify findings using at least the following severity levels:

- `Low`
- `Medium`
- `High`

Severity shall reflect the likelihood that the location contains user-generated content and the risk that the user might overlook it.

The application shall not use severity to imply certainty.

### FR-5: Tkinter GUI Dashboard

#### FR-5.1 General UI Requirements

The application shall provide a Tkinter graphical interface.

The interface shall be designed for users who may be stressed and non-technical.

The interface shall avoid unnecessary visual density.

The interface shall use clear labels, calm wording, and explicit warnings.

#### FR-5.2 Source List Panel

The UI shall present sources in a simple list panel.

The user shall be able to add and remove sources before scanning.

The source list shall show:

- Device or manifest name.
- Source role.
- Acquisition method.
- Read-only status.
- Readiness state.

#### FR-5.3 Application and Findings Grid

The UI shall present discovered applications and potential user-data findings in a sortable treeview or equivalent grid.

The grid shall remain as simple as possible.

Recommended columns:

- Confirmed (Checkbox), when in TRIAGE mode.
- Application.
- Version.
- Source.
- Status.
- User Data Risk.

Additional detail shall be shown in a details pane rather than crowding the main grid.

#### FR-5.4 Details Pane

The details pane shall show:

- Application summary.
- Fingerprint status.
- Evidence summary.
- Potential user-data findings.
- Rationale for findings.
- Warnings.
- TRIAGE mode
   - A checkbox to confirm the finding.
   - A multi-line text area for user notes.

The details pane shall not display file contents.

#### FR-5.5 Status Bar

The status bar shall be a single-line summary.

The status bar may provide expanded information through tooltips.

The status bar shall not become a multi-line log console in the main layout.

#### FR-5.6 Report Controls

The UI shall provide:

- Load Report.
- Export Report.

The UI shall use the word “Report” rather than “Snapshot” in user-facing controls.

#### FR-5.7 Triage Mode
When a report is loaded, the application shall enter "Triage Mode". In this mode, source acquisition and scanning controls are locked. The user shall be able to toggle the `user_confirmed` state and edit `user_notes` for potential user-data findings. These changes shall be persisted to the internal database.

### FR-6: Report Export and Triage Mode

#### FR-6.1 Report Export

The application shall export scan results to a structured JSON report.

The report shall include:

- Session metadata.
- Schema version.
- Sources.
- User profiles.
- Application records.
- Evidence records.
- Application-to-evidence links.
- User-data findings (including `user_confirmed` and `user_notes` states).
- Warnings.
- Scan status.

The report shall not include file contents.

#### FR-6.2 Report Import
When a report is loaded, the application shall hydrate the UI into Triage Mode, restoring all previous triage states and notes without rescanning sources. The application shall preserve read-only behavior toward all source drives.

#### FR-6.3 Report Compatibility

The report format shall include a schema version.

The application shall reject or clearly explain incompatible report files.

### FR-7: Transparency and Error Handling

#### FR-7.1 Evidence Transparency

The application shall present evidence counts and warnings in a way that does not overwhelm the user.

The user shall be able to understand why an application was classified as registered, portable, orphaned, or unknown.

The user shall be able to understand why a potential user-data location was flagged.

#### FR-7.2 Graceful Failure

The application shall handle corrupted hives, missing hives, unreadable manifest lines, missing binaries, and permission failures gracefully.

Where possible, the application shall continue scanning remaining evidence sources.

The application shall not crash silently.

The application shall present actionable, empathetic error messages.

## 5. Non-Functional Requirements

### NFR-1: Responsiveness

Long-running operations shall run in background worker threads.

The Tkinter UI shall remain responsive during scanning.

UI updates from background threads shall be coordinated through thread-safe queues.

### NFR-2: Empathy and Simplicity

The application shall use calm, supportive language.

The application shall avoid unnecessary technical jargon where simpler wording is possible.

Warnings shall be clear without being frightening.

The UI shall minimize visual overload.

### NFR-3: Portability and Isolation

The application shall be bootstrapped by a single `setup.sh` script.

The script shall create and use the `Win10DRBPythonVenv` virtual environment.

The script shall not automatically install host system packages.

The script shall provide exact manual installation instructions when host packages are missing.

### NFR-4: Evidence Extensibility

Supported evidence locations and heuristic patterns shall be maintainable as structured configuration where practical.

New evidence types shall be addable without redesigning the evidence model.

### NFR-5: Memory Safety

The application shall use bounded-memory processing for manifests and large enumerations.

The application shall avoid allocating entire large files in memory.

### NFR-6: False-Positive Transparency

Heuristic findings shall include rationale.

The application shall not present heuristic findings as certainty.

The application shall expose confidence levels.

### NFR-7: Privacy

The application shall run locally.

The application shall not transmit scanned data externally.

The application shall not display file contents.

The application shall not include telemetry.

### NFR-8: Accessibility

The application shall support keyboard navigation.

The application shall maintain sufficient color contrast.

The application shall provide understandable labels for buttons, lists, and status indicators.

### NFR-9: Read-Only Safety

The application shall enforce read-only behavior toward scanned sources.

The application shall not accept externally mounted paths.

The application shall require explicit confirmation before unmounting a mounted partition.

### NFR-10: Maintainability and Testability

Core logic shall be independently testable.

Tests shall use mocked devices, manifests, and fixture data where practical.

Tests shall not require live drives, root privileges, or actual Windows installations.

## 6. Out of Scope

The following are explicitly out of scope:

- File-content viewing.
- File-content parsing.
- AI-based classification.
- Deleted-file recovery.
- BitLocker decryption.
- Windows repair.
- Registry repair.
- Drive wiping.
- Backup creation.
- Automatic discovery of all secondary drives.
- Support for externally mounted paths.
- Support for Conda.
- Requirement of `git`.
- Windows host support.
- Network-based scanning or telemetry.

## Appendix A: Supported Registry Evidence Locations

The application shall maintain supported registry evidence locations as versioned configuration. The following list defines the initial supported set.

### A.1 Machine `SOFTWARE` Hive

| Evidence Location | Purpose |
|---|---|
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` | Primary installed application evidence. |
| `SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall` | 32-bit installed application evidence on 64-bit Windows. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths` | Registered executable launch paths. |
| `SOFTWARE\Classes\Installer\Products` | Windows Installer product evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\UserData\<SID>\Products` | Per-user Windows Installer product evidence. |
| `SOFTWARE\Classes\Installer\UpgradeCodes` | Windows Installer upgrade evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\Folders` | Installer-managed folder evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\SharedDLLs` | Installer-registered shared DLL evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Run` | Startup registration evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce` | Startup registration evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnceEx` | Startup registration evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run` | Policy-based startup evidence. |
| `SOFTWARE\Classes\CLSID` | COM registration evidence, best-effort. |
| `SOFTWARE\Classes\AppID` | COM application identifier evidence, best-effort. |
| `SOFTWARE\Classes\TypeLib` | Type library evidence, best-effort. |
| `SOFTWARE\Classes\ProgID` | Programmatic identifier evidence, best-effort. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Browser Helper Objects` | Browser helper object evidence. |
| AppX/AppModel-related keys where present | Modern application evidence, best-effort. |

### A.2 Machine `SYSTEM` Hive

| Evidence Location | Purpose |
|---|---|
| `SYSTEM\Select` | Resolves the active control set. |
| `SYSTEM\<CurrentControlSet>\Services` | Service and driver installation evidence. |
| `SYSTEM\<CurrentControlSet>\Control\Session Manager\AppCompatCache` | Application compatibility cache evidence, best-effort. |

### A.3 Per-User `NTUSER.DAT` Hive

| Evidence Location | Purpose |
|---|---|
| `Software\Microsoft\Windows\CurrentVersion\Uninstall` | Per-user installed application evidence. |
| `Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall` | Per-user 32-bit installed application evidence. |
| `Software\Microsoft\Windows\CurrentVersion\App Paths` | Per-user executable registration evidence. |
| `Software\Microsoft\Windows\CurrentVersion\Run` | Per-user startup evidence. |
| `Software\Microsoft\Windows\CurrentVersion\RunOnce` | Per-user startup evidence. |
| `Software\Microsoft\Windows\CurrentVersion\UserAssist` | Executed application evidence, best-effort. |
| `Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache` | Application display-name and path evidence. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders` | User shell folder resolution, including Documents. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders` | Legacy shell folder resolution. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs` | Recent document path hints, best-effort. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\TypedPaths` | Explorer typed-path hints, best-effort. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage` | Application usage hints, best-effort. |

### A.4 Per-User `UsrClass.dat` Hive

| Evidence Location | Purpose |
|---|---|
| Per-user file association keys | File type handler evidence. |
| Per-user ProgID keys | Programmatic identifier evidence. |
| Per-user CLSID keys | COM registration evidence. |
| AppX/MSIX per-user class evidence | Modern app association evidence, best-effort. |
| `Applications\*\shell\open\command` style keys | Executable launch-command evidence. |

### A.5 Filesystem Evidence Locations

The application shall also consider the following filesystem evidence locations where available:

- `Program Files`
- `Program Files (x86)`
- `ProgramData`
- `WindowsApps`
- `Users\*\AppData\Local\Programs`
- `Users\*\AppData\Local\Microsoft\WindowsApps`
- Start Menu program shortcut directories.
- Desktop shortcut directories.
- Secondary-drive application-like directories.
- Portable application directories.