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
