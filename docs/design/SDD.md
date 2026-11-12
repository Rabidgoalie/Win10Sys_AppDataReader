# Software Design Document (SDD): Windows 10 Disaster Recovery Application

## 1. Architecture Overview

The application follows a modular, layered architecture.

The major layers are:

1. Bootstrap and environment validation.
2. Source acquisition and mount safety.
3. Evidence ingestion.
4. Evidence correlation.
5. Heuristic classification.
6. Persistence.
7. Report export and import.
8. Background coordination.
9. Tkinter presentation.

The application is designed so that raw evidence is collected and persisted before application correlation occurs.

Evidence remains first-class and exportable.

---

## 2. Module Specifications

### 2.1 `setup.sh`

Bootstrap orchestrator.

Responsibilities:

- Detect Linux.
- Detect Ubuntu 24.04 or compatible environment.
- Require Python 3.12-series support.
- Verify `python3-venv`.
- Verify Tkinter.
- Verify required system commands.
- Verify `ntfs-3g` tooling.
- Create or reuse `Win10DRBPythonVenv`.
- Install runtime Python dependencies.
- Avoid automatic host-package installation.
- Print clear, empathetic manual instructions when prerequisites are missing.

The script shall not require or reference Conda.

The script shall not require `git`.

---

### 2.2 `src/main.py`

Application entry point.

Responsibilities:

- Initialize the database.
- Initialize the coordinator.
- Construct the UI.
- Register cleanup handlers.
- Start the Tkinter main loop.
- Ensure safe cleanup on window close.

---

### 2.3 `src/models.py`

Data transfer objects and dataclasses.

Responsibilities:

Define immutable or controlled data structures for:

- block devices;
- sources;
- user profiles;
- evidence;
- persisted evidence references;
- portable candidates;
- application records;
- user-data findings;
- warnings;
- progress events;
- error events.

DTOs shall not expose database rows directly to UI widgets.

---

### 2.4 `src/pathnorm.py`

Path normalization utility.

Responsibilities:

- Normalize Windows-style paths.
- Compare paths case-insensitively.
- Map offline mount paths to logical source-relative paths.
- Map manifest paths to source-relative paths.
- Determine whether one path is under another path.
- Support Documents-baseline comparison.

Normative rules:

- Paths shall be normalized to backslash separators.
- Drive prefixes shall be uppercase.
- Paths shall be lowercased only for comparison or hashing, not for display.
- Trailing backslashes shall be removed except for drive roots.
- NTFS alternate data stream suffixes shall be removed for comparison and hashing.
- UNC paths shall be preserved but treated as unresolved where source mapping is impossible.
- The primary Windows source shall be logically mapped as `C:`.
- Secondary sources shall be logically mapped as `S1:`, `S2:`, etc., based on source addition order.
- Raw Linux mount paths shall not be stored as the canonical path in evidence or findings.

---

### 2.5 `src/config/evidence_locations.py`

Evidence configuration.

Responsibilities:

- Define supported registry evidence roots.
- Define evidence types.
- Define hive types.
- Define confidence defaults.
- Define enumeration bounds for registry evidence.
- Version the evidence-location list.

---

### 2.6 `src/config/heuristic_patterns.py`

Heuristic configuration.

Responsibilities:

- Define potential user-data folder patterns.
- Define portable-application patterns.
- Define exclusion patterns.
- Define severity defaults.
- Define confidence defaults.
- Define developer-content patterns, including:
	- **Visual Studio:** `<UserProfile>\source`, `<UserProfile>\source\repos`
	- **IntelliJ / JetBrains Suite:** `<UserProfile>\IdeaProjects`
	- **Rider / ReSharper:** `<UserProfile>\RiderProjects`
	- **Eclipse:** `<UserProfile>\workspace` or `<UserProfile>\eclipse-workspace`
	- **NetBeans:** `<UserProfile>\NetBeansProjects`
	- **VS Code / Generic:** `<UserProfile>\projects`, `<UserProfile>\code`, `<UserProfile>\dev`
- Define OneDrive path patterns.
- Define category precedence rules.
- Define enumeration bounds for filesystem and manifest heuristics.

---

### 2.7 `src/mount_manager.py`

Source acquisition and mount safety.

Responsibilities:

- Enumerate block devices using `lsblk --json`.
- Identify candidate NTFS partitions.
- Detect current mount state.
- Refuse externally mounted paths.
- Request confirmation before unmounting already-mounted partitions.
- Mount sources using `ntfs-3g` in read-only mode using the safe option contract.
- Create isolated temporary mount points under an application-owned recovery directory.
- Track mounted sources.
- Release mounts on exit, cancellation, failure, and successful scan completion.

`lsblk` contract:

- Request JSON output.
- Explicitly request device path, name, type, filesystem type, size, label, UUID, mount points, transport, and partition label where available.
- Parse defensively.
- Support both singular and plural mount-point field variations where possible.
- Exclude non-NTFS and non-disk/partition candidates according to SRS rules.

Mount contract:

- Use safe read-only `ntfs-3g` options only.
- Prohibit log recovery, hibernation removal, and write access.
- Present mounted files only to the invoking user.
- Fail safely if safe mounting is unavailable.

Unmount contract:

- Attempt normal unmount first.
- Use lazy unmount only after explicit user confirmation as a fallback.
- Track and clean up application-owned mounts.

Core APIs:

```text
UnmountConfirmCallback = Callable[[str, tuple[str, ...]], bool]
# (explanation_message, existing_mount_points) -> user_approved

class MountManager:
    def __init__(self, base_mount_dir: Path): ...

    # --- Discovery (SRS FR-1.2, UIDD §3–4) ---
    def list_block_devices(self) -> list[BlockDevice]: ...
    # Runs `lsblk --json` with explicitly requested fields; parses defensively
    # (singular/plural mount-point variants, README §5.2); returns ONLY NTFS
    # candidates per the SDD §2.7 lsblk contract: partitions preferred; whole
    # disks only when directly NTFS with no partition children; loop, ram,
    # optical, swap, squashfs, ISO9660, LUKS, and LVM candidates excluded.
    # Does not require elevation. Never called on the Tk thread (see §2.19).

    # --- Preparation (SRS §3.8, FR-1.11, ADR-5) ---
    def prepare_source(
        self,
        source: SourceRecord,
        *,
        confirm_unmount: UnmountConfirmCallback | None = None,
    ) -> PreparedSource: ...
    # Dispatches on source_type:
    #   mounted_block_device -> safe read-only ntfs-3g mount under
    #     <base_mount_dir>/<source_id>/ (safe option contract, SRS §3.8).
    #   manifest_file -> validates the manifest exists and is readable;
    #     no mount, no elevation; returns PreparedSource with mount_point=None.
    # If the device is externally mounted: invokes confirm_unmount; declines
    # abort preparation (raise); normal unmount first; lazy unmount only after
    # a second confirm_unmount invocation.

    # --- Release (SRS §3.8, ADR-5) ---
    def release_source(self, source_id: str, *,
                       confirm_lazy: UnmountConfirmCallback | None = None) -> None: ...
    def release_all(self, *,
                    confirm_lazy: UnmountConfirmCallback | None = None) -> None: ...
    # Normal unmount first. Busy volume + callback present -> offer lazy
    # unmount via callback. Busy + no callback (e.g., during exit when the UI
    # is gone) -> leave mounted, record for startup sweep, never lazy silently.

    # --- Startup hygiene (README §5.1) ---
    def sweep_orphans(self) -> list[Path]: ...
    # Detects application-owned mount dirs under base_mount_dir still present
    # in /proc/mounts; returns them for guided release.
```

---

### 2.8 `src/ingest/manifest_generator.py`

Manifest generation module.

Responsibilities:

- Generate recursive `ntfsls` manifests from raw block devices.
- Write manifest output only to safe writable locations.
- Never write to the scanned source.
- Report progress and errors.
- Produce a normalized manifest format.
- Stop safely on critical I/O errors.

Core API:

```text
generate_manifest(
    device_path: str,
    output_path: Path,
    progress_callback: Callable | None = None,
    cancel_event: threading.Event | None = None,
) -> ManifestGenerationResult
```

Manifest output contract:

- UTF-8 text.
- One path per line.
- Source-relative Windows-style paths.
- No file contents.
- Comments and blank lines permitted.
- Malformed lines shall not be generated intentionally.

---

### 2.9 `src/ingest/hive_locator.py`

Hive discovery module.

Responsibilities:

- Locate machine hives:
  - `SOFTWARE`
  - `SYSTEM`
  - optionally `DEFAULT`
- Locate user hives:
  - `NTUSER.DAT`
  - `UsrClass.dat`
- Detect missing hives.
- Detect unreadable hives.
- Report hive warnings.
- Avoid treating Default or system profile hives as normal user hives unless marked.

Core APIs:

```text
locate_machine_hives(source: PreparedSource) -> MachineHiveSet

locate_user_hives(source: PreparedSource) -> list[UserHiveSet]
```

---

### 2.10 `src/ingest/registry_parser.py`

Offline registry evidence parser.

Responsibilities:

- Parse configured registry evidence locations.
- Parse machine and user hives.
- Resolve `SYSTEM` control sets.
- Handle WOW6432Node paths.
- Extract application metadata where available.
- Emit evidence records.
- Handle corrupt or unreadable hives gracefully.
- Respect evidence bounds.
- Treat UserAssist evidence as usage evidence only.
- Decode UserAssist ROT13 entries where appropriate.
- Treat AppCompatCache parsing as best-effort.

Core API:

```text
enumerate_registry_evidence(
    source: PreparedSource,
    hives: HiveSet,
    options: RegistryParseOptions,
    cancel_event: threading.Event | None = None,
) -> Iterator[RegistryEvidence]
```

Registry parse failures shall produce warnings and shall not terminate the entire scan unless a critical I/O failure occurs.

---

### 2.11 `src/ingest/user_profile_parser.py`

User profile parser.

Responsibilities:

- Enumerate user profile directories.
- Use `ProfileList` data where available.
- Identify usernames and SIDs where available.
- Mark Default and system profiles.
- Locate `NTUSER.DAT` and `UsrClass.dat`.
- Resolve Documents, Desktop, Downloads, Pictures, Music, Videos, Saved Games, and AppData paths.
- Expand environment variables in shell-folder values using offline profile knowledge.
- Detect common IDE source-code workspace directories, including Visual Studio (`source`, `source\repos`), IntelliJ (`IdeaProjects`), Rider (`RiderProjects`), Eclipse (`workspace`), and generic development directories (`projects`, `code`, `dev`).
- Handle redirected folders conservatively.
- Mark unresolved Documents baselines as unknown.

Core API:

```text
parse_user_profiles(
    source: PreparedSource,
    cancel_event: threading.Event | None = None
) -> Iterator[UserProfile]
```

---

### 2.12 `src/ingest/manifest_parser.py`

Manifest ingestion module.

Responsibilities:

- Parse manifests line by line.
- Avoid loading entire manifests into memory.
- Extract path evidence.
- Infer file and directory presence.
- Emit manifest evidence records.
- Support portable-application and user-data heuristics.
- Respect manifest evidence bounds.
- Count malformed lines.
- Continue after malformed lines where practical.

Core API:

```text
parse_manifest(
    manifest_path: Path,
    source: PreparedSource,
    cancel_event: threading.Event | None = None
) -> Iterator[ManifestEvidence]
```

---

### 2.13 `src/ingest/portable_scanner.py`

Portable application discovery module.

Responsibilities:

- Identify portable application candidates from mounted sources or manifests.
- Detect executable bundles by name and extension only.
- Detect known portable layouts by path structure only.
- Detect application-like directories on secondary drives.
- Avoid obvious false positives using exclusion configuration.
- Emit portable candidates with confidence.
- Respect traversal bounds.
- Not follow symlinks.
- Not inspect file contents.

Core API:

```text
discover_portable_candidates(
    source: PreparedSource,
    evidence_stream: Iterable[PersistedEvidence],
    cancel_event: threading.Event | None = None,
) -> Iterator[PortableCandidate]
```

Portable scanning shall operate after evidence persistence and may consume persisted evidence in bounded batches.

---

### 2.14 `src/correlator.py`

Evidence correlation module.

Responsibilities:

- Group persisted evidence into source-scoped application identities.
- Match evidence by normalized names, publishers, paths, product codes, and executable names.
- Assign fingerprint status.
- Assign confidence.
- Choose deterministic identity basis and identity key.
- Create application-to-evidence links.
- Avoid linking evidence from one source to an application owned by another source.

Core API:

```text
correlate_evidence(
    evidence_rows: Iterable[PersistedEvidence],
    portable_candidates: Iterable[PortableCandidate],
    cancel_event: threading.Event | None = None,
) -> Iterator[CorrelatedApplication]
```

Correlation shall operate on persisted evidence references that include evidence identifiers.

---

### 2.15 `src/heuristics/user_data_classifier.py`

Potential user-data classifier.

Responsibilities:

- Identify potential user-generated-content locations.
- Compare candidate paths against resolved Documents baselines.
- Detect IDE source-code directories (Visual Studio, IntelliJ, Rider, Eclipse, VS Code workspace paths).
- Detect OneDrive-like paths by path patterns only.
- Classify findings as inside Documents, outside Documents, or unknown.
- Assign severity and confidence.
- Produce human-readable rationale.
- Deduplicate findings by normalized path per source.
- Preserve multiple rationales when merging findings.

The classifier shall not open file contents.

Core API:

```text
classify_user_data(
    app: CorrelatedApplication | None,
    profiles: Iterable[UserProfile],
    source: PreparedSource,
    cancel_event: threading.Event | None = None,
) -> Iterator[UserDataFinding]
```

Severity and confidence defaults shall come from heuristic configuration.

---

### 2.16 `src/heuristics/exclusions.py`

Exclusion logic.

Responsibilities:

- Define default exclusion patterns.
- Reduce false positives from caches, system directories, package managers, and development artifacts.
- Allow exclusions to remain configurable.
- Prevent traversal of known noisy or irrelevant directories where safe.

Default exclusion categories shall include:

- recycle bins;
- volume metadata directories;
- temporary caches;
- package caches;
- version-control metadata;
- virtual environment directories;
- compiler caches;
- obvious system restore/recovery areas.

---

### 2.17 `src/db.py`

SQLite persistence layer.

Responsibilities:

- Initialize schema.
- Manage connections.
- Enforce foreign keys.
- Persist sources, profiles, evidence, applications, links, findings, and warnings.
- Support report hydration.
- Serialize write access.
- Support bounded batch inserts.
- Return assigned identifiers where needed.

Core APIs:

```text
class Database:
    @classmethod
    def open(cls, db_path: Path) -> "Database": ...
    def close(self) -> None: ...
    def __enter__(self) -> "Database": ...
    def __exit__(self, *exc) -> None: ...

    # ---- Writers ----
    def save_session(self, session: ScanSession) -> str: ...
    def update_session_status(self, session_id: str, status: SessionStatus) -> None: ...
    def save_source(self, source: SourceRecord) -> str: ...
    def update_source_status(self, source_id: str, status: SourceStatus,
                             warnings_json: str | None = None) -> None: ...
    def save_user_profile(self, profile: UserProfile) -> str: ...
    def save_evidence(self, evidence: Evidence) -> str: ...
    def save_evidence_batch(self, rows: Sequence[Evidence]) -> tuple[str, ...]: ...
    def save_application(self, app: CorrelatedApplication) -> str: ...
    def link_evidence_to_app(self, app_id: str, evidence_id: str,
                             relevance: Relevance) -> None: ...
    def save_user_data_finding(self, finding: UserDataFinding) -> str: ...
    def save_warning(self, warning: WarningRecord) -> str: ...
    def update_finding_triage(self, finding_id: str, *,
                              user_confirmed: bool | None,
                              user_notes: str | None) -> None: ...

    # ---- Readers ----
    def load_session_data(self, session_id: str) -> SessionBundle: ...
    def iter_persisted_evidence(self, session_id: str, *,
                                source_id: str | None = None,
                                batch_size: int = 1000,
                                ) -> Iterator[tuple[PersistedEvidence, ...]]: ...
    def get_summary(self, session_id: str) -> ScanSummary: ...

def init_db(db_path: Path) -> None: ...
```

The persistence layer shall be thread-safe.

Write access shall be serialized.

Database connections shall not be shared directly across threads without serialization.

---

### 2.18 `src/state.py`

Report export and import manager.

Responsibilities:

- Export session data to JSON.
- Include schema version.
- Include full evidence package.
- Include warnings.
- Load report files.
- Validate report compatibility.
- Hydrate TRIAGE-mode data.
- Replace current session state safely during import.
- Preserve original IDs.
- Run import/export work off the UI thread.

Core APIs:

```text
class ReportService:
    def __init__(self, db: Database): ...

    def export_report(self, session_id: str, output_path: Path) -> None: ...
    def import_report(self, report_path: Path) -> SessionBundle: ...
    # Import validates schema compatibility (DDD §9), hydrates into the
    # bound Database, and returns the full SessionBundle for UI hydration.
    # Per filesystem-layout contract rule 5, import targets a FRESH session
    # directory + database; the coordinator constructs ReportService bound to
    # that new Database (session replacement is coordinator-orchestrated).
```

Import shall not access source drives.

Export shall not access source drives.

---

### 2.19 `src/coordinator.py`

Background worker coordinator.

Responsibilities:

- Run scanning tasks off the UI thread.
- Coordinate source preparation, ingestion, correlation, and classification.
- Persist evidence before correlation.
- Emit typed progress events.
- Emit typed error events.
- Support cancellation where practical.
- Stop immediately on critical I/O failure.
- Ensure cleanup is requested on failure.
- Throttle progress events.
- Batch result notifications.
- The coordinator shall own one session `threading.Event` for cancellation, set it on user cancellation and on critical I/O failure, and pass it to every cancellation-aware stage.

Example event types:

```text
ProgressEvent
SourcePreparedEvent
EvidenceBatchPersistedEvent
UserProfileParsedEvent
PortableCandidateEvent
ApplicationCorrelatedEvent
UserDataFindingEvent
WarningEvent
ScanCompletedEvent
ScanFailedEvent
CriticalIoFailureEvent
```

Core APIs:

```text
class Coordinator:
    def __init__(self, event_queue: queue.Queue, db: Database,
                 mount_manager: MountManager): ...

    # --- Pre-scan services (run on worker threads, never the Tk thread) ---
    def request_device_list(self) -> None: ...
    # Async. Emits DeviceListEvent(devices=...) on success, or
    # DeviceListEvent(devices=(), error=...) on lsblk failure.

    def start_session(self, requests: Sequence[SourceRequest],
                      options: ScanOptions) -> str: ...
    # Validates: exactly one windows_os request; every manifest source is
    # secondary_data (SRS FR-1.3). Creates the ScanSession, constructs
    # SourceRecords, launches the scan worker. Returns session_id.

    def cancel_session(self) -> None: ...
    # Sets the session cancel_event; unblocks any pending confirmation wait.

    def answer_confirmation(self, request_id: str, approved: bool) -> None: ...
    # Called from the Tk thread in response to a ConfirmationRequestEvent;
    # releases the blocked worker.

    def run(self) -> None: ...
```

The coordinator shall not emit one UI event per individual evidence row under normal operation.

---

### 2.20 `src/ui.py`

Tkinter presentation layer.

Responsibilities:

- Present source list.
- Present secondary-drive advisory.
- Present scan controls.
- Present cancellation control during scanning.
- Present application and finding grid.
- Present details pane.
- Present single-line status bar with tooltips and compact progress indication.
- Support report loading and export.
- Support TRIAGE mode.
- Update only from queued UI events.
- Flush unsaved triage notes before export and application exit.

Core APIs:

```text
class App:
    def __init__(self, root: tk.Tk, event_queue: queue.Queue,
                 coordinator: Coordinator): ...
    def run(self) -> None: ...
    # UI -> coordinator: direct method calls (start_session, cancel_session,
    # request_device_list, answer_confirmation) — these are thread-safe.
    # Coordinator -> UI: exclusively via event_queue (ADR-4).
```

The UI shall not perform direct drive operations.

---

## 3. Data Flow

A full active scan proceeds as follows:

1. The user adds one or more sources.
2. The UI displays the secondary-source advisory.
3. The user starts the scan.
4. The coordinator prepares sources safely.
5. The hive locator finds machine and user hives on the primary Windows source.
6. The user profile parser resolves profiles and shell-folder baselines.
7. The registry parser emits raw registry evidence.
8. Registry evidence is persisted in bounded batches.
9. Manifest sources are parsed line by line.
10. Manifest evidence is persisted in bounded batches.
11. Mounted secondary sources are scanned for filesystem evidence.
12. Filesystem evidence is persisted in bounded batches.
13. The portable scanner identifies portable candidates from persisted evidence.
14. The correlator groups persisted evidence into source-scoped application records.
15. The user-data classifier produces potential user-data findings.
16. Findings are deduplicated and persisted.
17. Warnings are persisted.
18. Mounts are released.
19. The UI updates through queued events.
20. The user may export a report.

If a critical I/O failure occurs, the coordinator stops source access and enters the critical failure state.

---

## 4. Safety and Error Boundaries

### 4.1 Source Safety

The mount manager is the only component allowed to prepare mounted sources.

No module may write to a scanned source.

Manifest generation must write only to safe output paths.

Temporary mount directories shall be securely created and owned by the privileged acquisition process.

### 4.2 Registry Parse Failures

Registry parse failures shall produce warnings.

A corrupted hive shall not terminate the entire scan if other hives or sources remain processable.

### 4.3 Manifest Parse Failures

Malformed manifest lines shall be skipped and counted.

The parser shall continue unless the manifest is unreadable.

### 4.4 Filesystem Enumeration Failures

Unreadable directories shall produce warnings.

Enumeration shall respect bounds and exclusions.

Enumeration shall not follow symlinks.

### 4.5 Critical I/O Failures

Critical I/O failures shall stop source access and the active scan.

The application shall not retry automatically.

The UI shall present a critical, calm error.

The session may preserve already-persisted results.

### 4.6 UI Error Presentation

Errors shall be user-facing and actionable.

The UI shall avoid blaming the user.

The UI shall avoid implying that data loss has already occurred.

### 4.7 Cooperative Cancellation
Long-running ingestion, correlation, classification, and manifest-generation functions accept an optional `cancel_event: threading.Event | None`. Cancellation is cooperative. When the event is set, the function shall stop producing new results within a bounded number of internal steps, shall not initiate new reads against a source drive, shall return normally without raising, and shall leave already-yielded or already-persisted results intact. The coordinator owns all session-state transitions resulting from cancellation. Functions without a `cancel_event` parameter are bounded tightly enough not to require one.

---

## 5. Architectural Patterns

### Observer / Queue Pattern

Background workers emit events through a thread-safe queue.

The UI consumes events on the Tkinter thread.

Progress events are throttled or batched.

### DTO Boundaries

Ingestion, correlation, and heuristic layers exchange dataclasses.

Database rows are not passed directly to UI widgets.

### Evidence-First Model

Raw evidence is persisted before correlation.

This preserves orphaned and portable evidence.

### Bounded Processing

Evidence admission, traversal depth, directory entry counts, and UI updates are bounded to protect stability and usability.

### Testability

Modules shall be testable with fixture manifests, synthetic hive data, mocked subprocess calls, and temporary SQLite databases.

Unit tests shall not require root, live drives, or real Windows installations.
