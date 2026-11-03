# Architecture Decision Records (ADRs)

## ADR-1: Read-Only NTFS Acquisition Using `ntfs-3g` and `ntfsls`

### Context

Windows fast shutdown and BSOD events can leave NTFS volumes in a dirty state. Kernel mounting or desktop auto-mounting can risk metadata corruption or accidental writes. Users may also click drives in the file manager out of habit, causing unsafe mounts.

The application must protect the user’s drives while still allowing registry hive parsing, filesystem enumeration, and portable-application discovery.

### Decision

The application shall support only two acquisition methods:

1. `ntfs3g_ro`
   - Read-only mounting using `ntfs-3g` with safe read-only options.
2. `ntfsls_manifest`
   - Read-only enumeration using recursive `ntfsls`, producing a manifest file.

The primary Windows source shall be mounted using `ntfs3g_ro` because offline registry hive parsing requires direct access to hive files.

Secondary sources may be mounted using `ntfs3g_ro` or processed through an `ntfsls` manifest.

The application shall not support externally mounted paths, including paths mounted by the kernel `ntfs3` driver or desktop auto-mounters.

### Consequences

This preserves the non-destructive guarantee and avoids unsafe kernel mounts. Manifest-only sources reduce available metadata, so heuristic confidence may be lower when file sizes, timestamps, or counts are unavailable.

## ADR-2: Unified Bootstrap Using `setup.sh` and `venv`

### Context

Users may be stressed and technically inexperienced. They need a simple setup path that does not pollute the host Python environment and does not require advanced tooling.

The project was previously described as supporting Conda, but `venv` provides the necessary Python-package isolation for this application. Conda would add unnecessary complexity.

### Decision

The application shall use a single `setup.sh` bootstrap script.

The script shall create and use a local virtual environment named:

```text
Win10DRBPythonVenv
```

The application shall require Python 3.12.3 exactly.

The application shall not reference or depend upon Conda.

The application shall not require `git`.

The documentation shall state that typical users should download the repository ZIP file and extract it.

The script shall not automatically install host-level system packages. If required packages are missing, the script shall print clear manual installation instructions and exit.

### Consequences

Setup remains simple and isolated. Users are protected from accidental host-package pollution. Non-technical users receive explicit guidance instead of silent failures.

## ADR-3: Report Caching and Triage Mode

### Context

Scanning can be time-consuming. Users should not be forced to repeat long scans merely to review results. Reviewing hundreds of potential user-data findings often requires multiple sessions over several days. Users need a safe way to resume their triage work without risking accidental re-scans or drive operations.

### Decision

The application shall support exporting scan results to a structured JSON report.
The application shall support loading a report in "Triage Mode".
In Triage Mode, the application's internal SQLite database becomes mutable *only* for the `user_confirmed` and `user_notes` fields of `USER_DATA_FINDING` records. No scanned source drives are written to.
The report shall include the full evidence package and the current triage state.
The report shall not include file contents.

### Consequences

Users can safely close the application and resume their manual review days later by loading the JSON report. The UI clearly distinguishes active scanning from triage. The application avoids unnecessary re-scans, reduces user stress, and maintains strict read-only safety for the actual source drives.

## ADR-4: Thread-Safe Queue Communication for Asynchronous UI Updates

### Context

Ingestion, manifest parsing, registry parsing, correlation, and heuristic classification are heavy operations. Running them on the Tkinter main thread would freeze the UI.

### Decision

Background work shall execute in worker threads.

Workers shall communicate with the UI exclusively through thread-safe queues.

The UI shall update only from its own thread in response to queued events.

### Consequences

The UI remains responsive. Background processing is decoupled from presentation logic. Progress and error reporting become easier to test.

## ADR-5: Forced Read-Only Isolation and Explicit Unmount Confirmation

### Context

Users may have already mounted a damaged NTFS partition through the desktop file manager, often using the kernel `ntfs3` driver with write access. Continuing to use such a mount could endanger the user’s data.

### Decision

The application shall not operate on externally mounted paths.

If the user selects a block device that is already mounted, the application shall explain why the current mount is unsafe and request explicit confirmation before performing a lazy unmount.

After confirmation, the application shall unmount the partition and remount it using `ntfs-3g` in read-only mode under an isolated temporary mount point.

The application shall use distinct mount subdirectories for distinct sources.

The application shall clean up mounts on exit, failure, and cancellation where possible.

### Consequences

This protects damaged drives from accidental writes. The explicit confirmation prevents surprising non-technical users. The isolated mount point prevents confusion with host-mounted paths.

## ADR-6: Evidence-Centric Enumeration Before Application Correlation

### Context

The application must discover applications from many weak, partial, or conflicting evidence sources. Some evidence will belong to orphaned applications, portable applications, or incomplete installations.

If the parser only produces application records, valuable evidence may be discarded when correlation is ambiguous.

### Decision

The ingestion pipeline shall first collect raw evidence records.

Application records shall be created by correlating evidence after evidence collection.

Evidence shall remain stored even if it is not correlated to an application.

### Consequences

The application preserves forensic value. It can display orphaned evidence, portable candidates, and partially registered applications. Correlation can improve over time without losing raw observations.

## ADR-7: Portable Application Discovery by Read-Only Heuristics

### Context

Some applications are portable and leave little or no Windows registry fingerprint. Users may store portable applications on secondary drives and forget about them.

If the application only checks registry evidence, it may miss these programs and any user data stored beside them.

### Decision

The application shall identify portable application candidates using read-only heuristics based on directory structure, file names, executable bundles, known portable layouts, and manifest evidence.

The application shall not execute scanned binaries.

Portable candidates shall receive confidence levels and shall be distinguishable from registered applications.

### Consequences

Portable applications become visible to users. False positives are possible, so the UI must show confidence and rationale.

## ADR-8: Advisory User-Data Classification Without Content Inspection

### Context

The most important goal of the application is to help users locate potentially irreplaceable self-authored files before wiping drives.

However, the application cannot safely or reliably determine whether a file is truly user-generated by opening or parsing file contents. Content inspection would explode scope, create privacy concerns, and still not guarantee correctness.

### Decision

The application shall classify potential user-generated-content locations using only:

- File names.
- Directory names.
- Paths.
- Extensions.
- Sizes, when available.
- Timestamps, when available.
- File counts, when available.
- Registry path hints.
- Manifest entries.

The application shall not open or parse file contents.

The application shall not use AI or remote classification.

Findings shall be advisory only.

The user shall make the final judgment about whether discovered content is valuable.

### Consequences

The application remains safe, private, and maintainable. Users receive useful guidance without false certainty. The documentation and UI must clearly explain that findings are potential, not guaranteed.

## ADR-9: Multi-Source Sessions With Strict Acquisition Methods

### Context

A recovery session may involve a primary Windows drive and one or more secondary drives. Some secondary drives may contain portable applications, games, projects, or user files.

The data model must support multiple sources without allowing unsafe mounted paths.

### Decision

A scan session shall support multiple sources.

Each source shall record:

- Source type.
- Source role.
- Acquisition method.
- Device path, where known.
- Manifest path, where applicable.
- Mount point, where applicable.
- Read-only status.
- Status and warnings.

Supported acquisition methods shall be limited to:

- `ntfs3g_ro`
- `ntfsls_manifest`

Externally mounted paths shall not be supported.

### Consequences

The application can scan primary and secondary drives while preserving provenance. The data model supports evidence from multiple sources without relying on unsafe mount paths.

## ADR-10: Explicit Secondary Source Advisory

### Context

Users may assume that scanning the primary Windows drive is sufficient. If they used secondary drives for programs, games, documents, or projects, they may overlook those drives and later wipe them.

### Decision

The application shall display a clear advisory near the source-list panel reminding users to add secondary drives that may contain programs or personal files.

The advisory shall state that wiping or reinstalling can make data unrecoverable.

The advisory shall not require technical knowledge to understand.

### Consequences

Users are less likely to overlook secondary data sources. The application remains simple because it does not need to automatically infer which secondary drives are important.