# Architecture Decision Records (ADRs)

## ADR-1: Read-Only NTFS Acquisition Using `ntfs-3g` and `ntfsls`

### Context

Windows fast shutdown and BSOD events can leave NTFS volumes in a dirty state. Kernel mounting or desktop auto-mounting can risk metadata corruption or accidental writes. Users may also click drives in the file manager out of habit, causing unsafe mounts.

The application must protect the user’s drives while still allowing registry hive parsing, filesystem enumeration, and portable-application discovery.

### Decision

The application shall support only two acquisition methods:

#### `ntfs3g_ro`

Read-only mounting using `ntfs-3g` with the safe option contract defined in the SRS.

#### `ntfsls_manifest`

Read-only enumeration using recursive `ntfsls`, producing a manifest file.

The primary Windows source shall be mounted using `ntfs3g_ro` because offline registry hive parsing requires direct access to hive files.

Secondary sources may be mounted using `ntfs3g_ro` or processed through an `ntfsls` manifest.

The application shall not support externally mounted paths, including paths mounted by the kernel `ntfs3` driver or desktop auto-mounters.

Safe mount options shall prohibit:

- write access;
- NTFS log recovery;
- hibernation-file removal;
- dirty-bit clearing;
- filesystem repair.

If a safe read-only mount cannot be obtained:

- primary source failure shall abort the scan;
- secondary source failure may be handled by manifest generation where applicable.

Mounts shall be released after successful scan completion, failure, cancellation, and application exit.

### Consequences

This preserves the non-destructive guarantee and avoids unsafe kernel mounts.

Manifest-only sources reduce available metadata, so heuristic confidence may be lower when file sizes, timestamps, or counts are unavailable.

---

## ADR-2: Unified Bootstrap Using `setup.sh` and `venv`

### Context

Users may be stressed and technically inexperienced. They need a simple setup path that does not pollute the host Python environment and does not require advanced tooling.

### Decision

The application shall use a single `setup.sh` bootstrap script.

The script shall create and use a local virtual environment named:

```text
Win10DRBPythonVenv
```

The application shall require a Python 3.12-series interpreter, with Python 3.12.3 as the validated reference version.

The application shall not reference or depend upon Conda.

The application shall not require `git`.

The documentation shall state that typical users should download the repository ZIP file and extract it.

The script shall not automatically install host-level system packages. If required packages are missing, the script shall print clear manual installation instructions and exit.

### Consequences

Setup remains simple and isolated. Users are protected from accidental host-package pollution. Non-technical users receive explicit guidance instead of silent failures.

---

## ADR-3: Report Caching and Triage Mode

### Context

Scanning can be time-consuming. Users should not be forced to repeat long scans merely to review results. Reviewing hundreds of potential user-data findings often requires multiple sessions over several days.

### Decision

The application shall support exporting scan results to a structured JSON report.

The application shall support loading a report in Triage Mode.

Report import shall hydrate the database and UI into Triage Mode.

During hydration, the database may be written as necessary to restore the report.

After hydration completes, the database shall be considered mutable only for:

- `USER_DATA_FINDING.user_confirmed`
- `USER_DATA_FINDING.user_notes`

No scanned source drives shall be written to.

The report shall include the full evidence package and the current triage state.

The report shall not include file contents.

Loading a report shall replace the current application session after safely releasing active source access.

### Consequences

Users can safely close the application and resume their manual review days later by loading the JSON report.

The UI clearly distinguishes active scanning from triage.

The application avoids unnecessary re-scans, reduces user stress, and maintains strict read-only safety for the actual source drives.

---

## ADR-4: Thread-Safe Queue Communication for Asynchronous UI Updates

### Context

Ingestion, manifest parsing, registry parsing, correlation, and heuristic classification are heavy operations. Running them on the Tkinter main thread would freeze the UI.

### Decision

Background work shall execute in worker threads.

Workers shall communicate with the UI exclusively through thread-safe queues.

The UI shall update only from its own thread in response to queued events.

Progress events shall be throttled or batched.

The UI shall not receive one event per evidence record under normal operation.

### Consequences

The UI remains responsive.

Background processing is decoupled from presentation logic.

Progress and error reporting become easier to test.

---

## ADR-5: Forced Read-Only Isolation and Explicit Unmount Confirmation

### Context

Users may have already mounted a damaged NTFS partition through the desktop file manager, often using the kernel `ntfs3` driver with write access. Continuing to use such a mount could endanger the user’s data.

### Decision

The application shall not operate on externally mounted paths.

If the user selects a block device that is already mounted, the application shall:

1. Explain why the current mount is unsupported.
2. Request explicit confirmation before unmounting.
3. Attempt a normal unmount first.
4. If the normal unmount fails because the volume is busy, explain the condition.
5. Use lazy unmount only as an explicit fallback after additional confirmation.
6. Abort source preparation if the user declines.

After confirmation and successful unmount, the application shall remount the partition using `ntfs-3g` in read-only mode under an isolated temporary mount point.

The application shall use distinct mount subdirectories for distinct sources.

The application shall clean up mounts on exit, failure, cancellation, and successful scan completion.

### Consequences

This protects damaged drives from accidental writes.

The explicit confirmation prevents surprising non-technical users.

The isolated mount point prevents confusion with host-mounted paths.

---

## ADR-6: Evidence-Centric Enumeration Before Application Correlation

### Context

The application must discover applications from many weak, partial, or conflicting evidence sources. Some evidence will belong to orphaned applications, portable applications, or incomplete installations.

If the parser only produces application records, valuable evidence may be discarded when correlation is ambiguous.

### Decision

The ingestion pipeline shall first collect raw evidence records.

Evidence records shall be persisted before correlation.

Application records shall be created by correlating persisted evidence.

Evidence shall remain stored even if it is not correlated to an application.

Evidence collection shall be bounded to protect memory, database size, report size, and user comprehension.

### Consequences

The application preserves forensic value.

It can display orphaned evidence, portable candidates, and partially registered applications.

Correlation can improve over time without losing raw observations.

---

## ADR-7: Portable Application Discovery by Read-Only Heuristics

### Context

Some applications are portable and leave little or no Windows registry fingerprint. Users may store portable applications on secondary drives and forget about them.

### Decision

The application shall identify portable application candidates using read-only heuristics based on:

- directory structure;
- file names;
- executable bundles identified by name/extension only;
- known portable layouts identified by path structure only;
- manifest evidence.

The application shall not execute scanned binaries.

The application shall not inspect file contents.

Portable candidates shall receive confidence levels and shall be distinguishable from registered applications.

### Consequences

Portable applications become visible to users.

False positives are possible, so the UI must show confidence and rationale.

---

## ADR-8: Advisory User-Data Classification Without Content Inspection

### Context

The most important goal of the application is to help users locate potentially irreplaceable self-authored files before wiping drives.

However, the application cannot safely or reliably determine whether a file is truly user-generated by opening or parsing file contents.

### Decision

The application shall classify potential user-generated-content locations using only:

- file names;
- directory names;
- paths;
- extensions;
- sizes, when available;
- timestamps, when available;
- file counts, when available;
- registry path hints;
- manifest entries.

The application shall not open or parse file contents.

The application shall not use AI or remote classification.

Findings shall be advisory only.

The user shall make the final judgment about whether discovered content is valuable.

### Consequences

The application remains safe, private, and maintainable.

Users receive useful guidance without false certainty.

The documentation and UI must clearly explain that findings are potential, not guaranteed.

---

## ADR-9: Multi-Source Sessions With Strict Acquisition Methods

### Context

A recovery session may involve a primary Windows drive and one or more secondary drives.

### Decision

A scan session shall support multiple sources.

Each source shall record:

- source type;
- source role;
- acquisition method;
- device path, where known;
- manifest path, where applicable;
- mount point, where applicable;
- filesystem type;
- label and UUID where known;
- read-only status;
- status and warnings.

Supported acquisition methods shall be limited to:

- `ntfs3g_ro`
- `ntfsls_manifest`

Externally mounted paths shall not be supported.

Manifest-only sources shall be secondary sources only.

Application records shall be source-scoped.

### Consequences

The application can scan primary and secondary drives while preserving provenance.

The data model supports evidence from multiple sources without relying on unsafe mount paths.

---

## ADR-10: Explicit Secondary Source Advisory

### Context

Users may assume that scanning the primary Windows drive is sufficient.

### Decision

The application shall display a clear advisory near the source-list panel reminding users to add secondary drives that may contain programs or personal files.

The advisory shall state that wiping or reinstalling can make data unrecoverable.

The advisory shall not require technical knowledge to understand.

### Consequences

Users are less likely to overlook secondary data sources.

The application remains simple because it does not need to automatically infer which secondary drives are important.

---

## ADR-11: Least-Privilege Elevation Model

### Context

The application requires elevated privileges for mounting, unmounting, and raw-device enumeration, but running an entire graphical application as root increases security and stability risk.

### Decision

The application shall run as the normal desktop user.

Privileged operations shall be performed through a small allowlist of external system commands.

The application shall:

- resolve command paths before use;
- invoke commands with argument vectors only;
- avoid shell interpretation;
- request elevation only when necessary;
- fail safely if elevation is unavailable.

The application shall not write to scanned sources under elevated privileges.

### Consequences

The application reduces security risk while preserving required acquisition capabilities.

The privilege model remains understandable and testable.

---

## ADR-12: Critical I/O Failure Stops Source Access

### Context

Although users are guided to verify drive health before using the application, a drive may still exhibit I/O errors.

Continuing to read a failing drive can worsen data loss.

### Decision

If a low-level I/O error occurs while accessing a source, the application shall stop all further access to that source and stop the active scan.

The application shall not automatically retry the failed operation.

The application shall present a critical, calm error message and advise the user that the drive may be failing.

If partial results are already persisted, the application may allow report export, because export does not require source access.

### Consequences

The application adheres to the do-no-harm principle even when pre-scan health checks were insufficient.

Users are protected from aggressive retry behavior.

---

## ADR-13: Bounded Evidence Admission

### Context

A naive evidence-first implementation could store millions of manifest entries or registry subkeys, overwhelming the database, report, UI, and user.

### Decision

Evidence collection shall be bounded by deterministic configuration limits.

When a bound is reached, the application shall record a warning and stop adding further evidence for that bounded category or source.

Evidence already collected shall be retained.

Bounds shall apply to:

- registry enumeration;
- filesystem enumeration;
- manifest-derived evidence;
- finding metric computation.

### Consequences

The evidence-first model remains practical in constrained Live Session environments.

The application remains usable for non-technical users.

---

## ADR-14: Terminal-Interactive `sudo` Elevation Mechanism

### Context

ADR-11 established a least-privilege elevation model but did not specify the exact mechanism for obtaining elevated privileges. In Ubuntu 24.04 Live sessions, users may not have configured passwordless sudo, and in-app password dialogs or pkexec can fail or confuse non-technical users.
The application requires elevation for mounting, unmounting, and raw-device enumeration, but running the entire GUI as root increases security risk.

### Decision

The application shall use terminal-interactive `sudo` exclusively for privilege elevation.
The application shall:
Resolve `/usr/bin/sudo` to an absolute path before any invocation.
Probe sudo availability with `sudo -n true` at startup.
If the probe succeeds (common in Live sessions with passwordless sudo), proceed silently.
If the probe fails, display a calm Tkinter dialog instructing the user to answer the sudo prompt in the terminal they launched the application from.
Cache credentials with `sudo -v` for batch operations.
Invoke privileged commands with argument vectors only, never through a shell interpreter.
Use an allowlist of privileged commands with absolute paths:
`sudo -n true` and `sudo -v` for credential management.
`sudo <abs_ntfs-3g> -o <safe_opts> <device> <mountpoint>` for mounting.
`sudo /bin/umount <mountpoint>` for normal unmount.
`sudo /bin/umount -l <mountpoint>` for lazy unmount (only after explicit confirmation).
`sudo <abs_ntfsls> <flags> <device>` for manifest generation.
The application shall not use `sudo -S`, pkexec, or in-app password dialogs.
The application shall not run the entire GUI as root.

### Consequences

Elevation remains simple and works reliably in Live sessions.
Users are not confused by unexpected password prompts in the GUI.
The allowlist prevents privilege escalation through shell injection.
Terminal-interactive sudo requires the user to have access to the launching terminal, which is acceptable for the target environment.

---

## ADR-15: Cooperative Cancellation Contract for Long-Running Operations

### Context

Scanning, ingestion, correlation, and classification are long-running operations that may take minutes on large drives. Users need the ability to cancel these operations, but abrupt termination can leave the database in an inconsistent state or leak resources.
SDD §4.7 requires a cooperative cancellation mechanism that preserves already-persisted work.

### Decision

Long-running ingestion, correlation, classification, and manifest-generation functions shall accept an optional `cancel_event: threading.Event | None = None` parameter.
When the cancel event is set:
The function shall stop producing new results within a bounded number of internal steps.
The function shall not initiate new reads against a source drive.
The function shall return normally without raising an exception.
The function shall leave already-yielded or already-persisted results intact.
The coordinator shall own the session cancel event and all state transitions resulting from cancellation.
Functions without a `cancel_event` parameter are bounded tightly enough not to require one.
The cancel event shall be checked between major processing steps (e.g., between evidence batches, between directory entries, between registry keys).

### Consequences

Users can cancel long operations without data loss or corruption.
The cancellation mechanism is cooperative, preventing resource leaks.
The coordinator maintains a single source of truth for session state.
Functions remain testable by passing a pre-set cancel event.

---

## ADR-16: Stateless Functions vs Stateful Classes Assignment Rule

### Context

Python supports both free functions and classes, but mixing them inconsistently leads to unclear ownership and lifecycle management. The application has modules that are purely functional (path normalization, configuration) and modules that manage state (database connections, mount points, UI).
A clear rule is needed to guide module design and prevent accidental state leakage.

### Decision

The application shall assign module structures as follows:
Stateless operations → free functions.
State, lifecycle, or owned resources → classes.
Examples of free-function modules:
`pathnorm.py` (pure path transformations).
`src/config/*` (configuration data).
All `ingest/*` modules (evidence parsing, no persistent state).
`correlator.py` (evidence correlation, no state).
`heuristics/*` (classification, no state).
`exclusions.py` (pattern matching, no state).
Examples of class-based modules:
`Database` in `db.py` (owns SQLite connection, serialized write access).
`MountManager` in `mount_manager.py` (owns mount points, tracks mounted sources).
`ReportService` in `state.py` (owns database reference, manages import/export).
`Coordinator` in `coordinator.py` (owns session state, worker threads, cancel event).
`App` in `ui.py` (owns Tkinter root, event queue, UI state).
This is not a performance decision—Python OOP overhead is negligible here. The rule enforces idiomatic state ownership and makes resource lifecycle explicit.

### Consequences

Module responsibilities are clear: functions transform data, classes manage resources.
Resource cleanup is explicit through class methods (`close`, `release_all`).
Testing is simplified: functions are pure, classes can be instantiated with test fixtures.
The rule prevents accidental global state in functional modules.

---

## ADR-17: Tiered Contract Governance with Mechanical Verification

### Context

The application uses a local quantized LLM to generate code against frozen contracts, but the LLM cannot review its own output. Drift between implemented code and contracts must be detected mechanically to prevent silent divergence.
A governance system is needed to manage contract lifecycle, enforce freeze rules, and verify compliance.

### Decision

The application shall use a tiered contract governance system:
Tier 0 (frozen): Core models (`models.py`, `pathnorm.py`, `src/config/*`, DDD schema). Changes require coordinator + reviewer approval and §9 rationale.
Tier 1 (rolling freeze): Per-module contract sheets in `docs/contracts/`. A sheet moves DRAFT → FROZEN exactly when the previous module enters review.
Tier 2 (never frozen): Private helpers, heuristic internals, rationale strings, SQL text.
Governance rules:
Only the coordinator promotes DRAFT → FROZEN after reviewer sign-off. The local LLM never edits sheets.
Post-freeze changes are amendments: minor version bump, §9 rationale, re-review of modules generated against the old revision. Purely additive code changes are still contract amendments.
Drift is mechanical: `tests/test_contracts.py` verifies implemented modules against their FROZEN sheets by parsing §1 API fences with `ast` and comparing symbols, parameters, and types.
Contract sheets mirror `src/` exactly (`docs/contracts/ingest/hive_locator.md` ⇄ `src/ingest/hive_locator.py`).
Sheets follow a standard anatomy: status header · §1 Public API · §2 postconditions · §3 error contract · §4 events/warnings · §5 I/O surface · §6 threading/cancellation · §7 non-contract internals · §8 fixtures · §9 amendment record.
Paper-trail rule: contract baseline and each amendment are separate commits with rationale.

### Consequences

The local LLM can generate code against frozen contracts without review, while drift is caught mechanically.
Contract evolution is tracked with clear rationale for future contributors.
The governance system scales as new modules are added.
The mechanical verification prevents silent contract violations.

---

## ADR-18: XDG-Compliant Filesystem Layout with Strict Permissions

### Context

The application creates session databases, manifests, mount points, and logs. These files contain sensitive metadata (file paths, registry data) that should not be accessible to other local users, especially in shared Live session environments.
A consistent filesystem layout is needed to prevent accidental writes to sources and to support report portability.

### Decision

The application shall use an XDG-compliant filesystem layout:
Base directory: `$WIN10DRB_HOME` if set, else `$XDG_STATE_HOME/win10drb` (default `~/.local/state/win10drb`).
Directory structure:
`<base>/sessions/<session_id>/win10drb.sqlite` — active session database.
`<base>/sessions/<session_id>/manifests/<source_id>.txt` — generated manifests.
`<base>/mounts/<source_id>/` — application-owned mount points.
`<base>/logs/win10drb.log` — application log.
Permissions:
Directories: 0700 (owner read/write/execute only).
Files: 0600 (owner read/write only).
Rules:
Never write to scanned sources or inside mount points.
`db.py` receives the database path via `Database.open(db_path)` and never resolves paths itself.
Export dialog suggests `<base>/sessions/<id>/report.json` as the default location.
Report import creates a fresh session directory and database (per filesystem-layout rule 5).
Startup orphan sweep cross-references `/proc/mounts` to detect stale application-owned mounts.
Live-session caveat: `$HOME` is RAM-backed in Ubuntu Live sessions. The status tooltip reminds users to export reports to persistent media (USB drive, external disk).

### Consequences

Sensitive metadata is protected from other local users.
The layout is predictable and supports manual inspection if needed.
Report portability is maintained through the fresh-session import rule.
The Live-session caveat prevents accidental data loss when users reboot.

---

## ADR-19: regipy Exception Taxonomy and Critical I/O Escalation

### Context

Offline registry hive parsing can fail for multiple reasons: hive structure damage (truncated, bad cells), missing optional hives, OS-level read errors (EIO from a failing drive), or programmer errors. A blanket `except Exception` would disguise a dying drive as a "corrupt hive" and continue hammering it, violating ADR-12.
A precise exception taxonomy is needed to distinguish recoverable parse failures from critical I/O failures.

### Decision

The application shall use the following exception taxonomy for registry parsing:
Hive structure/parse damage (truncated, bad cells, decode errors; including `struct.error`, `UnicodeDecodeError`, `EOFError`, and regipy-specific parse exceptions):
Emit `WarningEvent(category='registry')`.
Skip the damaged hive or key.
Continue processing other hives/sources.
Missing optional hive (file not found):
Emit `WarningEvent(category='registry')`.
Continue processing.
OS-level read error mid-read (`OSError` with `errno.EIO` or similar):
Emit `CriticalIoFailureEvent`.
Stop all source access immediately (per ADR-12).
Do not retry.
Programmer error (e.g., `TypeError`, `AttributeError` from incorrect API usage):
Not caught.
Surfaces as a test failure or unhandled exception.
The exact regipy exception names shall be verified against the pinned `regipy` version in `requirements.txt` at contract freeze time.
The `registry_parser.md` contract sheet §3 shall document this taxonomy explicitly.

### Consequences

Dying drives are detected early and do not cause further data loss.
Corrupt hives are handled gracefully without terminating the entire scan.
Programmer errors are caught in testing, not masked by broad exception handling.
The taxonomy aligns with SRS §3.9 and ADR-12.

---

## ADR-20: ntfsls Manifest Generation with Force Flag and Streaming

### Context

`ntfsls` is used to generate recursive filesystem manifests from raw block devices without mounting. Unbootable Windows drives often have the dirty bit set, causing `ntfsls` to refuse enumeration unless the force flag is used.
Large manifests can exceed available memory if loaded entirely, and manifest generation must respect cancellation and bounds.

### Decision

The application shall invoke `ntfsls` with the following contract:
Command: `sudo <abs_ntfsls> -R -a -f <device>`.
`-R` (recursive): enumerate directory trees.
`-a` (all): include hidden files (also the default, but passed explicitly for clarity).
`-f` (force): required because unbootable drives carry the dirty bit; safe because `ntfsls` only enumerates the MFT (read-only, no mount).
Output processing:
Stream stdout line-by-line using a generator; never load the entire manifest into memory.
Enforce `max_manifest_entries` bound (from `HeuristicBounds`); set `ManifestGenerationResult.truncated = True` if exceeded.
Check `cancel_event` between lines; stop generation if set.
Output format:
UTF-8 text file.
Comment header: `# Device: <device_path>`, `# Timestamp: <UTC_ISO8601>`, `# Tool: ntfsls <version>`, `# Command: <full_command>`.
State machine: lines ending `:` are directory transitions (e.g., `/Corel/Painter 2020:`); subsequent lines are entries until the next directory or end of output.
Skip `.` and `..` entries.
Normalize `/` → `\` (root `/` → `\`), yielding source-relative Windows paths.
Output location:
Write only to safe locations (`<base>/sessions/<session_id>/manifests/<source_id>.txt`).
Never write to the scanned source.
Error handling:
Mid-generation device failure (I/O error) escalates per SRS §3.9 (manifest generation is an explicit critical-I/O context).
Emit `CriticalIoFailureEvent` and stop.

### Consequences

Dirty volumes can be enumerated safely without mounting.
Large manifests are processed without memory exhaustion.
The manifest format is normalized and suitable for bounded streaming parsing.
Critical I/O failures are detected early, preventing further drive stress.

---

## ADR-21: Report Import Creates Fresh Session Directory

### Context

Loading a report should hydrate the UI into Triage Mode without modifying the original report file or the active session. If the import reused the current session directory, it could overwrite existing triage state or create uniqueness conflicts.
A clean separation is needed between the imported report and the active session.

### Decision

Report import shall create a fresh session directory and database:
The coordinator constructs a new `Database` instance pointing to `<base>/sessions/<new_session_id>/win10drb.sqlite`.
The `ReportService` is bound to this new database.
Import validates schema compatibility, preserves original IDs, and hydrates all tables into the new database.
The current session (if any) is safely released (mounts unmounted, database closed) before hydration.
The UI transitions to Triage Mode with the new session.
The original report file is not modified.
If a uniqueness conflict occurs during hydration (e.g., duplicate evidence hash), the import fails with an actionable error rather than silently overwriting local triage state.

### Consequences

Imported reports are isolated from the active session, preventing accidental data loss.
Original report files remain immutable and can be re-imported if needed.
Uniqueness conflicts are detected early, preventing silent state corruption.
The fresh-session rule aligns with the filesystem-layout contract (ADR-18).

---

## ADR-22: Database Persistence Contract with Serialized Access

### Context

SQLite supports concurrent reads but serializes writes. The application has multiple background workers (ingestion, correlation, classification) that may attempt concurrent writes, and the UI thread may write triage edits. Unserialized access can cause database locks, corruption, or lost updates.
A clear persistence contract is needed to ensure thread safety and data integrity.

### Decision

The `Database` class shall enforce the following persistence contract:
Deduplication is idempotent: duplicate `evidence_hash`, app identity, or finding unique keys return the existing ID, never raise.
`save_evidence_batch` accepts 1–500 rows per call; one transaction per batch.
`iter_persisted_evidence` yields results in bounded batches (default 1000 rows), deterministic `rowid` order.
`update_finding_triage` is the only post-hydration mutator (enforces ADR-3: only `user_confirmed` and `user_notes` may be modified after import).
SQLite configuration:
WAL mode enabled (`PRAGMA journal_mode=WAL`).
`busy_timeout` ≥ 5000ms (`PRAGMA busy_timeout=5000`).
`foreign_keys=ON` (`PRAGMA foreign_keys=ON`).
Access serialization:
Single SQLite connection owned by the `Database` instance.
All write operations serialized through one `threading.Lock`.
Read operations may proceed concurrently (SQLite handles this in WAL mode).
Database connections are not shared directly across threads or exposed to UI widgets.
Error handling:
Database errors (e.g., `sqlite3.Error`) are host-side and must never map to `CriticalIoFailureEvent`.
Database errors are logged and surfaced as warnings or exceptions to the caller.
No events are emitted by `db.py`; event emission is the coordinator's responsibility.
The module-level `init_db(db_path)` function is retained for SDD fidelity but delegates to `Database.open(db_path)`.

### Consequences

Thread safety is enforced through serialization, preventing race conditions.
WAL mode improves concurrent read performance.
Deduplication prevents duplicate evidence records without raising errors.
The contract aligns with DDD §10 and ADR-3.

---

## ADR-23: UI Confirmation Flow with Asynchronous Worker Coordination

### Context

ADR-5 requires explicit user confirmation before unmounting externally mounted partitions or using lazy unmount. These confirmations occur mid-worker (the mount preparation is running on a background thread), but the UI must remain responsive and the user must be able to approve or decline.
A mechanism is needed to coordinate asynchronous confirmations between the UI thread and worker threads without blocking the UI or losing cancellation support.

### Decision

The application shall use the following confirmation flow:
Models (added in `models.py` v1.1):
`ConfirmationKind` enum: `UNMOUNT_EXTERNAL`, `LAZY_UNMOUNT`.
`ConfirmationRequestEvent(kind, message, details, request_id)`: emitted by the coordinator to request user confirmation.
`SourceRequest(role, acquisition_method, device_path, manifest_path, label)`: UI selections cross into the session via this DTO, with `__post_init__` validation (e.g., `ntfs3g_ro` requires `device_path`; manifest-backed sources require `SECONDARY_DATA` role).
Coordinator:
Exposes `request_device_list()` (async, emits `DeviceListEvent`).
Exposes `answer_confirmation(request_id, approved)` (called from UI thread to release blocked worker).
Worker blocks on a `threading.Event` or `queue.Queue` waiting for the UI's answer; the wait is cancellation-aware (checks `cancel_event`).
UI:
Dispatches `ConfirmationRequestEvent` by showing a modal dialog with the message and details.
User clicks "Approve" or "Decline"; UI calls `coordinator.answer_confirmation(request_id, approved)`.
Dialog is calm, clear, and non-blaming (per UIDD §11).
The safest outcome ("Return to App" or "Decline") is the default button.
Threading:
UI → coordinator: direct method calls (`request_device_list`, `answer_confirmation`) are thread-safe.
Coordinator → UI: exclusively via `event_queue` (ADR-4).

### Consequences

Confirmations are handled asynchronously without blocking the UI.
Workers can be cancelled during confirmation waits.
The confirmation flow is testable by injecting `ConfirmationRequestEvent` and simulating UI responses.
The UI remains responsive during long-running operations.