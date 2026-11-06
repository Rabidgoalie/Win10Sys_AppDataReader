# Software Requirements Specification (SRS): Windows 10 Disaster Recovery Application

## 1. Introduction and Objectives

The Windows 10 Disaster Recovery Application is a free, MIT-licensed Linux desktop utility designed to help users recover from catastrophic Windows 10 boot failures, such as “Inaccessible Boot Device” BSOD events.

The application’s primary purpose is to help users locate and preserve irreplaceable, self-authored files before they reinstall an operating system or wipe a drive.

The application’s secondary purpose is to reconstruct a useful inventory of installed applications so users can rebuild their former Windows environment as accurately as possible.

The application is intentionally non-destructive. It performs read-only discovery and analysis. It does not modify, repair, wipe, decrypt, or write to scanned drives.

The application is designed for users who may have limited technical experience and who are likely to be stressed, anxious, or fearful after a data-loss event. The interface and documentation shall therefore be calm, clear, explicit, and forgiving.

The primary supported environment is an Ubuntu 24.04 Live Session. Pop!_OS 24.04 and closely compatible Linux systems are also supported.

---

## 2. Target Environment and Distribution

### 2.1 Supported Operating Environments

The application shall support:

- Ubuntu 24.04 Live Session, as the primary recommended environment.
- Pop!_OS 24.04, as a secondary supported environment.
- Other Ubuntu 24.04-compatible Linux systems, on a best-effort basis.

The application shall not support Windows as a host operating environment.

### 2.2 Distribution Model

The project shall be distributed in a form that does not require users to understand source-control tooling.

Documentation shall state that typical users should:

1. Download the project ZIP file.
2. Extract the ZIP file.
3. Run `setup.sh` from the extracted project directory.

The application shall not require `git` to be installed.

### 2.3 Python Environment

The application shall require a Python 3.12-series interpreter.

The validated reference interpreter is Python 3.12.3, but any Python version satisfying:

- `>= 3.12.0`
- `< 3.13.0`

shall be accepted.

This avoids blocking users whose Ubuntu 24.04-compatible system has received a safe Python patch update.

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

---

## 3. Scope and Constraints

### 3.1 Non-Destructive Principle

The application shall perform strictly read-only operations against scanned drives and partitions.

The application shall never:

- Write to a scanned source drive.
- Modify NTFS metadata.
- Repair file systems.
- Clear dirty bits.
- Replay NTFS transaction logs in a way that modifies source media.
- Remove hibernation files.
- Execute Windows binaries.
- Delete files.
- Move files.
- Rename files.
- Change permissions on scanned source files.

### 3.2 Supported Source Acquisition Methods

The application shall support only the following source acquisition methods:

#### `ntfs3g_ro`

Read-only mounting through `ntfs-3g` using the safe option set defined in section 3.8.

#### `ntfsls_manifest`

Read-only filesystem enumeration using `ntfsls`, producing a manifest file.

The application shall not support externally mounted paths.

The application shall not operate against paths mounted by the kernel `ntfs3` driver, desktop auto-mounters, or file-manager mount points.

A manifest file itself may reside on a normal host filesystem. This does not constitute use of an externally mounted source path.

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

File-based evidence types shall be interpreted using path, name, extension, size, timestamp, and directory-layout information only.

Specifically:

- Shortcut evidence shall not parse `.lnk` targets.
- AppX manifest evidence shall not parse `AppxManifest.xml` contents.
- Executable evidence shall not parse PE headers.
- Portable-layout evidence shall not parse configuration files.

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

The application shall run as the normal logged-in desktop user.

The application shall not require the entire graphical application to be launched as root.

Elevated privileges shall be used only for the following operations:

- Performing unmount operations.
- Mounting read-only through `ntfs-3g`.
- Running `ntfsls` against raw block devices.
- Creating and removing application-owned temporary mount directories.

The application shall request elevation through an explicit, user-visible privilege mechanism appropriate to a terminal-launched Linux desktop application.

The application shall:

- Use an allowlist of privileged helper commands.
- Invoke privileged commands with argument vectors only.
- Never invoke privileged commands through a shell interpreter.
- Resolve helper binaries to absolute paths before execution.
- Fail with actionable guidance if elevation fails.

The application shall not use elevated privileges to write to scanned source drives.

### 3.8 Safe Read-Only Mount Contract

The only permitted mounted-source acquisition command family is `ntfs-3g` with read-only, non-repair options.

The normative safe mount option set shall include:

- read-only mounting;
- no NTFS log recovery;
- no hibernation-file removal;
- no metadata replay;
- restrictive presented permissions for the mounted filesystem.

The application shall present mounted files only to the invoking desktop user and shall not expose mounted source files to other local users.

If a volume is dirty or hibernated:

- The application shall not clear the dirty state.
- The application shall not remove hibernation data.
- The application shall not repair the volume.
- If safe read-only mounting is refused by the operating environment, the application shall fail that source safely.

For the primary Windows source, safe mount failure shall be treated as a fatal scan error because offline registry parsing requires direct hive access.

For secondary sources, safe mount failure may be handled by guiding the user to manifest generation, which is already a supported secondary acquisition method.

Mounts shall be released:

- after successful scan completion;
- on scan failure;
- on cancellation;
- on application exit;
- when a prepared source is safely discarded before scanning.

### 3.9 Critical I/O Failure Behavior

The application assumes users have performed the external drive-health checks before use.

If the application nevertheless encounters a low-level I/O error while reading a source, including errors during:

- mounting;
- registry hive reading;
- filesystem enumeration;
- manifest generation;
- manifest reading from a generated raw-device manifest;

the application shall treat this as a potential failing-drive condition.

The application shall:

1. Immediately stop all further source access.
2. Stop the active scan.
3. Disable further source acquisition controls.
4. Present a calm, critical, non-blaming error message.
5. Advise the user that the drive may be failing and that continued access may worsen data loss.
6. Recommend powering down the machine and seeking professional data-recovery assistance if the data is valuable.

The application shall not automatically retry failed reads.

The application shall not attempt to continue scanning the affected source.

If partial results have already been persisted, the application may allow the user to export those results, because export does not require further source access.

### 3.10 Bounded Enumeration and Evidence Admission

The application shall collect evidence first, but shall not store unbounded quantities of low-value filesystem or manifest entries.

Evidence enumeration shall be bounded by configured safety limits.

The purpose of bounding is to protect:

- Live Session memory;
- SQLite database size;
- report size;
- UI responsiveness;
- non-technical user comprehension.

When a configured bound is reached, the application shall:

- stop adding further evidence for the bounded category or source;
- record a warning;
- continue processing other evidence categories where safe.

Bounding shall not be interpreted as permission to inspect file contents.

---

## 4. Functional Requirements

## FR-1: Source Management and Acquisition

### FR-1.1 Source List Panel

The application shall provide a simple source-list panel.

The user shall be able to:

- Add a source.
- Remove a source before scanning begins.
- See the source type.
- See the source role.
- See the acquisition method.
- See whether the source is pending, ready, complete, or failed.

The application shall not require users to manually type raw device paths.

Sources shall be locked once scanning begins.

A source may be removed before scanning begins. Removing a source before scanning shall not require unmounting because source preparation occurs during scan start.

### FR-1.2 Block Device Discovery

The application shall enumerate block devices using JSON-formatted `lsblk` output.

The application shall explicitly request the fields it requires and shall parse the output defensively.

The application shall identify likely NTFS partitions and present them as candidate sources.

Candidate filtering shall:

- prefer partitions;
- allow whole disks only when they directly contain an NTFS filesystem and do not contain partition children;
- exclude loop devices, RAM disks, optical media, swap, squashfs, ISO9660, LUKS, LVM physical volumes, and other non-NTFS candidates;
- display size, label, and UUID where available;
- not require the user to understand raw device paths.

### FR-1.3 Source Roles

Each source shall have exactly one role:

- `windows_os`
- `secondary_data`

A scan session shall support exactly one primary Windows source.

A manifest-only source shall always be treated as `secondary_data`, because manifest-only sources cannot provide offline registry hive access.

When adding a block-device source, the application shall ask the user whether the drive is:

- the drive that contains Windows;
- a secondary drive containing programs, games, or personal files.

The application shall not silently infer source role without user confirmation.

If no primary Windows source is present, scanning shall not start.

If more than one source is designated as the Windows source, the application shall prevent the second designation.

### FR-1.4 Primary Windows Source

The primary Windows source shall be a block device or partition containing the offline Windows installation.

The primary Windows source shall be mounted using `ntfs-3g` in read-only mode using the safe mount contract.

The primary Windows source must be mounted because offline registry hive parsing requires direct read access to hive files.

The application shall mount the primary Windows source to an isolated temporary mount point under an application-owned temporary recovery directory.

The application shall use a distinct mount subdirectory per source to avoid collisions between multiple sources.

If the primary source cannot be safely mounted, the scan shall fail with an actionable error.

### FR-1.5 Secondary Sources

The application shall support zero or more secondary sources.

Secondary sources may be:

- Secondary internal drives.
- External USB drives.
- Additional NTFS partitions.
- Manifest files generated from those drives.

For secondary sources, the application shall support:

- Read-only mounting through `ntfs-3g`, or
- Manifest generation using recursive `ntfsls`.

Manifest generation is recommended when the user only needs filesystem enumeration and does not need offline registry parsing from that secondary source.

### FR-1.6 Manifest Generation

The application shall support generating recursive read-only manifests from raw block devices using `ntfsls`.

Manifest generation shall be read-only.

The application shall write generated manifest files only to a user-selected writable location or another safe writable location chosen by the application.

The application shall never write a manifest file to the source being scanned.

Manifest files shall be treated as read-only evidence sources after generation.

The application-generated manifest format shall be a normalized, line-oriented text format suitable for bounded streaming parsing.

The manifest shall not include file contents.

### FR-1.7 Manifest Format Contract

A manifest file shall be a UTF-8 text file.

The application shall accept CRLF and LF line endings.

Each non-empty line shall represent one filesystem path unless the line is a comment or malformed.

The application-generated manifest shall contain source-relative Windows-style paths.

The parser shall:

- skip blank lines;
- skip comment lines beginning with `#`;
- count malformed lines;
- continue after malformed lines unless the manifest is unreadable;
- normalize paths before evidence creation;
- not require file contents.

Manifest-derived metadata shall be considered lower confidence than mounted-source metadata when size, timestamp, or file-count data is unavailable.

### FR-1.8 Memory-Bounded Parsing

To protect Live Session memory constraints, parsing of manifests and large directory enumerations shall use streaming or bounded-memory techniques.

The application shall not load entire large manifests into memory when avoidable.

The application shall prefer line-by-line processing, incremental database insertion, and bounded batching.

### FR-1.9 Secondary Source Advisory

Before scanning begins, the application shall display a clear advisory message similar to:

> Important: If you used secondary drives for programs, games, projects, documents, photos, videos, or other personal files, add those drives now. If you reinstall an operating system or wipe a drive, data on that drive may become unrecoverable.

This advisory shall be visible near the source-list panel.

The advisory shall use calm, non-alarming language while still making the risk clear.

### FR-1.10 No Externally Mounted Paths

The application shall not allow the user to select an already-mounted filesystem path as a source.

If the user attempts to provide a mounted path, the application shall explain that this is unsupported and shall guide the user to select the underlying block device instead.

### FR-1.11 Already-Mounted Block Devices

If the user selects a block device that is already mounted, the application shall not use the existing mount.

Before scan start, the application shall:

1. Detect existing mount points.
2. Explain that the existing mount is unsupported.
3. Request explicit user confirmation before unmounting.
4. Attempt a normal unmount first.
5. If normal unmount fails because the volume is busy, explain that programs may still be using the drive.
6. Offer a deferred/lazy unmount only as an explicit fallback.
7. Abort source preparation if the user declines.

The application shall not silently unmount user-mounted filesystems.

---

## FR-2: Exhaustive Offline Application Evidence Enumeration

### FR-2.1 Evidence-First Discovery

The application shall collect raw discovery evidence before attempting to correlate that evidence into application records.

Evidence shall be treated as a first-class concept.

Evidence that cannot be correlated to an application shall still be retained so that it can be reviewed, exported, and potentially correlated later.

Evidence records shall be persisted before application correlation occurs.

### FR-2.2 Supported Evidence Sources

The application shall enumerate application evidence from supported offline Windows registry locations, filesystem locations, and manifest entries.

The list of supported evidence locations shall be maintained as versioned, data-driven configuration so that new evidence locations can be added without redesigning the parser.

The application shall parse all configured evidence locations unless:

- a location is unavailable;
- a location is unreadable;
- a configured evidence bound has been reached;
- a critical I/O failure occurs.

### FR-2.3 Bounded Evidence Enumeration

The application shall enforce configured bounds on evidence collection.

Default bounds shall include:

- maximum evidence records per source;
- maximum registry subkeys examined per registry key;
- maximum registry values examined per registry key;
- maximum filesystem entries examined per source;
- maximum manifest-derived evidence entries per source;
- maximum directory entries examined when computing finding file counts and sizes.

When a bound is reached, the application shall record a warning and continue where possible.

Bounds shall be deterministic and documented in configuration.

### FR-2.4 Registry Evidence Locations

The application shall enumerate supported registry evidence from at least the following hive types:

- Machine `SOFTWARE` hive.
- Machine `SYSTEM` hive.
- Per-user `NTUSER.DAT` hives.
- Per-user `UsrClass.dat` hives.
- `DEFAULT` user hive, where available.

The application shall explicitly handle both native and WOW6432Node registry views where applicable.

The application shall resolve the active `SYSTEM` control set from `SYSTEM\Select` instead of assuming `CurrentControlSet` is directly usable offline.

Appendix A lists the supported registry evidence locations.

### FR-2.5 Multi-User Enumeration

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
- Pictures path.
- Music path.
- Videos path.
- AppData Local path.
- AppData Roaming path.
- AppData LocalLow path.
- Saved Games path.
- Visual Studio source-code path, where present.

The application shall not assume that only one user profile exists.

The application shall identify Default and system profiles and shall mark them as such.

Default and system profiles shall not be treated as normal user data owners unless explicitly appropriate.

### FR-2.6 Evidence Retention

The application shall retain raw evidence records even when:

- The evidence is orphaned.
- The evidence is incomplete.
- The evidence cannot be correlated.
- The evidence conflicts with other evidence.
- The hive is partially unreadable.
- The manifest is incomplete.
- A configured evidence bound has been reached.

Parse failures shall produce warnings and shall not crash the scan unless no further progress is possible or a critical I/O failure occurs.

### FR-2.7 Application Correlation

The application shall correlate evidence into application records where possible.

Application records shall be source-scoped.

An application record shall belong to one source. Evidence linked to that application record shall come from the same source.

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

Each application record shall have a deterministic identity basis and identity key, as defined in the database design.

---

## FR-3: Portable and Unregistered Application Discovery

### FR-3.1 Portable Discovery Purpose

The application shall identify candidate portable or unregistered applications, especially on secondary drives and in manifest-derived evidence.

Portable applications may leave little or no registry fingerprint on the primary Windows installation.

### FR-3.2 Portable Discovery Methods

The application shall identify portable application candidates using read-only heuristics based on:

- Directory structure.
- File names.
- Executable presence by name/extension only.
- Known portable-application layout patterns.
- Manifest entries.
- Absence of correlated registry evidence on the same source.

The application shall not execute scanned executables.

The application shall not inspect executable contents.

### FR-3.3 Portable Confidence

Portable application findings shall include a confidence level.

The application shall distinguish between:

- Strong portable candidates.
- Possible portable candidates.
- Unregistered installed applications.
- Unknown executable bundles.

Confidence shall be lowered when only manifest evidence is available.

---

## FR-4: Potential User-Generated Content Classification

### FR-4.1 Purpose

The application shall identify potential locations where user-generated content may exist.

The application shall especially identify potential user-generated content that is not stored inside the user’s resolved Documents folder.

The application shall not claim to know whether a file is valuable, irreplaceable, or truly user-generated.

The application shall present findings as advisory guidance to help the user decide what to preserve.

### FR-4.2 No Content Inspection

The application shall not open file contents.

The application shall not parse document contents, image contents, database contents, archive contents, save-file contents, or any other file payload.

The application shall use only path, name, extension, metadata, and count-based signals where available.

### FR-4.3 Documents Baseline Resolution

For each discovered user profile, the application shall attempt to resolve the Documents folder path.

The preferred source for Documents resolution is:

```text
Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders
```

using the value:

```text
Personal
```

If registry resolution fails, the application shall fall back to conventional paths, including:

```text
<UserProfile>\Documents
```

If the Documents path cannot be resolved, the application shall mark related findings as having an unknown Documents baseline.

The application shall also attempt to resolve:

- Desktop
- Downloads
- Pictures
- Music
- Videos
- Saved Games

from User Shell Folders values where available.

Environment variables in shell-folder values shall be expanded using offline profile knowledge.

If a resolved shell-folder path points to a drive or source that has not been scanned, the application shall mark related comparisons as unknown where necessary.

### FR-4.4 Candidate User-Data Locations

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
- OneDrive user folders, where identifiable by path only.
- Visual Studio source-code folders.
- Other user-profile-specific folders that commonly contain user-authored data.

### FR-4.5 Visual Studio Source Detection

For every discovered user profile, the application shall check for Visual Studio source-code locations, including:

```text
<UserProfile>\source
<UserProfile>\source\repos
```

If these directories exist and contain child entries, the application shall flag them as potential user-generated developer content.

The application shall not assume that every `source` directory is valuable, but it shall surface the location so the user can make the judgment.

If both locations exist and contain child entries, the classifier may emit separate findings for each.

### FR-4.6 Classification Output

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
- User triage state.
- User notes.

The `inside_documents` result may be:

- True.
- False.
- Unknown.

### FR-4.7 Finding Deduplication

A finding shall be uniquely identified within a session and source by its normalized path.

If multiple heuristics identify the same normalized path, the application shall merge them into one finding.

The merged finding shall:

- preserve all human-readable rationales;
- use the highest severity among matched heuristics;
- use the highest confidence among matched heuristics;
- choose a single location category using a deterministic precedence rule;
- choose a single associated application using a deterministic relevance rule;
- remain associated with the appropriate user profile where known.

### FR-4.8 Severity Model

The application shall classify findings using:

- `Low`
- `Medium`
- `High`

Severity shall reflect the likelihood that the location contains user-generated content and the risk that the user might overlook it.

The application shall not use severity to imply certainty.

Severity defaults shall be deterministic and documented in heuristic configuration.

### FR-4.9 Confidence Model

Finding confidence shall reflect the strength of metadata and pattern evidence.

Confidence shall be lower when:

- only manifest evidence is available;
- file counts are unavailable;
- sizes are unavailable;
- timestamps are unavailable;
- only a weak name pattern matched;
- the path resides on an unresolved secondary source.

Confidence shall not imply content inspection.

---

## FR-5: Tkinter GUI Dashboard

### FR-5.1 General UI Requirements

The application shall provide a Tkinter graphical interface.

The interface shall be designed for users who may be stressed and non-technical.

The interface shall avoid unnecessary visual density.

The interface shall use clear labels, calm wording, and explicit warnings.

### FR-5.2 Source List Panel

The UI shall present sources in a simple list panel.

The user shall be able to add and remove sources before scanning.

The source list shall show:

- Device or manifest name.
- Source role.
- Acquisition method.
- Read-only status.
- Readiness state.

Source states shall be displayed using user-facing labels mapped from internal states.

### FR-5.3 Application and Findings Grid

The UI shall present discovered applications and potential user-data findings in a sortable treeview or equivalent grid.

The grid shall remain as simple as possible.

Columns:

- Confirmed, in TRIAGE mode.
- Application.
- Version.
- Source.
- Status.
- Risk.

The grid shall support a deterministic row model that distinguishes application rows from finding rows.

Additional detail shall be shown in a details pane rather than crowding the main grid.

### FR-5.4 Details Pane

The details pane shall show:

- Application summary.
- Fingerprint status.
- Evidence summary.
- Potential user-data findings.
- Rationale for findings.
- Warnings.

In TRIAGE mode, for user-data findings, the details pane shall include:

- A checkbox to confirm the finding.
- A multi-line text area for user notes.

The details pane shall not display file contents.

### FR-5.5 Status Bar

The status bar shall be a single-line summary.

The status bar may provide expanded information through tooltips.

The status bar shall not become a multi-line log console in the main layout.

The status bar shall include a compact progress indication during scanning.

### FR-5.6 Report Controls

The UI shall provide:

- Load Report.
- Export Report.

The UI shall use the word “Report” rather than “Snapshot” in user-facing controls.

### FR-5.7 Triage Mode

When a report is loaded, the application shall enter Triage Mode.

In Triage Mode:

- Source acquisition controls are locked.
- Scan controls are locked.
- The mode badge shows TRIAGE.
- The user may toggle `user_confirmed`.
- The user may edit `user_notes`.
- Changes are persisted to the internal database.
- No drive operations are permitted.

Loading a report shall replace the current session state after safely releasing any active source access.

---

## FR-6: Report Export and Triage Mode

### FR-6.1 Report Export

The application shall export scan results to a structured JSON report.

The report shall include:

- Session metadata.
- Schema version.
- Sources.
- User profiles.
- Application records.
- Evidence records.
- Application-to-evidence links.
- User-data findings, including `user_confirmed` and `user_notes`.
- Warnings.
- Scan status.

The report shall not include file contents.

The report shall preserve original record identifiers.

The report shall be UTF-8 encoded.

### FR-6.2 Report Import

When a report is loaded, the application shall hydrate the UI into Triage Mode, restoring all previous triage states and notes without rescanning sources.

The application shall preserve read-only behavior toward all source drives.

Report import shall:

- validate schema compatibility;
- preserve original IDs;
- replace the current in-application session;
- safely release any active source mounts before hydration;
- reject malformed or incompatible reports with an actionable message.

### FR-6.3 Report Compatibility

The report format shall include a schema version.

The application shall reject incompatible report files.

Compatibility policy:

- The major schema version must match.
- Unknown fields shall be ignored where safe.
- Missing optional fields shall be tolerated where safe.
- Missing required fields shall cause rejection.
- Malformed JSON shall cause rejection.

### FR-6.4 Partial and Failed Scans

If a scan fails or is stopped before completion, the application may export already-persisted results.

The exported report shall preserve the session status, including failed or cancelled states.

Report import shall support loading reports from failed or cancelled scans.

---

## FR-7: Transparency and Error Handling

### FR-7.1 Evidence Transparency

The application shall present evidence counts and warnings in a way that does not overwhelm the user.

The user shall be able to understand why an application was classified as registered, portable, orphaned, or unknown.

The user shall be able to understand why a potential user-data location was flagged.

Raw evidence shall be retained and exported even when it is not prominently displayed in the main grid.

### FR-7.2 Graceful Failure

The application shall handle corrupted hives, missing hives, unreadable manifest lines, missing binaries, and permission failures gracefully.

Where possible, the application shall continue scanning remaining evidence sources.

The application shall not crash silently.

The application shall present actionable, empathetic error messages.

Critical I/O failures are treated differently from ordinary parse failures, as defined in section 3.9.

### FR-7.3 Warning Storage

User-visible warnings shall be stored as first-class warning records.

Warnings shall include:

- category;
- severity;
- message;
- optional source association;
- timestamp.

Warnings shall be included in report export.

---

## 5. Non-Functional Requirements

### NFR-1: Responsiveness

Long-running operations shall run in background worker threads.

The Tkinter UI shall remain responsive during scanning.

UI updates from background threads shall be coordinated through thread-safe queues.

Progress updates shall be batched or throttled to avoid overwhelming the UI queue.

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

The application shall use bounded database batches and throttled UI updates.

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

Color shall not be the only indicator of state.

### NFR-9: Read-Only Safety

The application shall enforce read-only behavior toward scanned sources.

The application shall not accept externally mounted paths.

The application shall require explicit confirmation before unmounting a mounted partition.

The application shall use safe temporary mount directories.

### NFR-10: Maintainability and Testability

Core logic shall be independently testable.

Tests shall use mocked devices, manifests, and fixture data where practical.

Tests shall not require live drives, root privileges, or actual Windows installations.

Registry parsing tests may use synthetic fixture hives, mocked registry structures, or pregenerated fixture data.

---

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
- Drive-health diagnosis.

---

## Appendix A: Supported Registry Evidence Locations

The application shall maintain supported registry evidence locations as versioned configuration.

The following list defines the initial supported set.

All enumeration is subject to configured bounds and graceful failure rules.

---

## A.1 Machine `SOFTWARE` Hive

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
| `SOFTWARE\Classes\CLSID` | COM registration evidence, best-effort and bounded. |
| `SOFTWARE\Classes\AppID` | COM application identifier evidence, best-effort and bounded. |
| `SOFTWARE\Classes\TypeLib` | Type library evidence, best-effort and bounded. |
| `SOFTWARE\Classes` programmatic identifier subkeys | Programmatic identifier evidence, best-effort and bounded. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Browser Helper Objects` | Browser helper object evidence. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\AppModel`, where present | Modern application evidence, best-effort. |
| `SOFTWARE\Microsoft\Windows\CurrentVersion\Appx`, where present | AppX package evidence, best-effort. |

---

## A.2 Machine `SYSTEM` Hive

| Evidence Location | Purpose |
|---|---|
| `SYSTEM\Select` | Resolves the active control set. |
| `SYSTEM\<ResolvedControlSet>\Services` | Service and driver installation evidence, bounded. |
| `SYSTEM\<ResolvedControlSet>\Control\Session Manager\AppCompatCache` | Application compatibility cache evidence, best-effort. |

Control-set resolution order shall be:

1. Use `Default` from `SYSTEM\Select` if valid.
2. Else use `LastKnownGood` if valid.
3. Else use the first available `ControlSet00X` key in numeric order.
4. If no control set can be resolved, skip SYSTEM evidence and record a warning.

---

## A.3 Per-User `NTUSER.DAT` Hive

| Evidence Location | Purpose |
|---|---|
| `Software\Microsoft\Windows\CurrentVersion\Uninstall` | Per-user installed application evidence. |
| `Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall` | Per-user 32-bit installed application evidence. |
| `Software\Microsoft\Windows\CurrentVersion\App Paths` | Per-user executable registration evidence. |
| `Software\Microsoft\Windows\CurrentVersion\Run` | Per-user startup evidence. |
| `Software\Microsoft\Windows\CurrentVersion\RunOnce` | Per-user startup evidence. |
| `Software\Microsoft\Windows\CurrentVersion\UserAssist` | Executed application evidence, best-effort. |
| `Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache` | Application display-name and path evidence. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders` | User shell folder resolution. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders` | Legacy shell folder resolution. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs` | Recent document path hints, best-effort. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\TypedPaths` | Explorer typed-path hints, best-effort. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage` | Application usage hints, best-effort. |

UserAssist values shall be treated as usage evidence only, not installation proof.

ROT13 decoding shall be applied where appropriate, and decode failures shall produce warnings rather than crashes.

---

## A.4 Per-User `UsrClass.dat` Hive

| Evidence Location | Purpose |
|---|---|
| Per-user file association keys | File type handler evidence. |
| Per-user ProgID keys | Programmatic identifier evidence. |
| Per-user CLSID keys | COM registration evidence, bounded. |
| AppX/MSIX per-user class evidence | Modern app association evidence, best-effort. |
| `Applications\*\shell\open\command` style keys | Executable launch-command evidence, name/path only. |

---

## A.5 Filesystem Evidence Locations

The application shall consider the following filesystem evidence locations where available:

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

Filesystem enumeration shall:

- not follow symlinks;
- not traverse junction-like links where detectable;
- respect configured depth and entry bounds;
- use file and directory names only;
- not open file contents.

---

## A.6 Required Profile-Resolution Locations

The following registry locations are required to satisfy user-profile and shell-folder resolution:

| Location | Purpose |
|---|---|
| `SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList` | Maps profile SIDs to profile paths. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders` | Resolves user shell folders. |
| `Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders` | Legacy fallback shell folder resolution. |

The profile parser may use these locations even when they are not emitted as application evidence.
