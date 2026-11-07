# Source Directory README

## 1. Python Project Directory Structure

```text
win10-disaster-recovery/
├── setup.sh                        # Bootstrap script
├── requirements.txt                # Runtime Python dependencies
├── requirements-dev.txt            # Development/testing dependencies
├── README.md                       # Root project README
├── src/
│   ├── __init__.py
│   ├── main.py                     # Application entry point
│   ├── models.py                   # DTOs / dataclasses
│   ├── pathnorm.py                 # Windows/offline path normalization
│   ├── mount_manager.py            # Block device discovery and safe mounting
│   ├── db.py                       # SQLite persistence
│   ├── state.py                    # Report export/import
│   ├── coordinator.py              # Background worker coordinator
│   ├── ui.py                       # Tkinter presentation layer
│   ├── correlator.py               # Evidence-to-application correlation
│   ├── config/
│   │   ├── __init__.py
│   │   ├── evidence_locations.py   # Supported evidence roots and bounds
│   │   └── heuristic_patterns.py   # Heuristic and exclusion patterns
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── manifest_generator.py   # ntfsls manifest generation
│   │   ├── manifest_parser.py      # ntfsls manifest reader
│   │   ├── hive_locator.py         # Hive file discovery
│   │   ├── registry_parser.py      # Offline registry evidence parser
│   │   ├── user_profile_parser.py  # User profile and shell-folder resolution
│   │   └── portable_scanner.py     # Portable application discovery
│   └── heuristics/
│       ├── __init__.py
│       ├── user_data_classifier.py # Potential user-data classification
│       └── exclusions.py           # False-positive exclusions
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_mount_manager.py
    ├── test_pathnorm.py
    ├── test_manifest_parser.py
    ├── test_registry_parser.py
    ├── test_user_profile_parser.py
    ├── test_portable_scanner.py
    ├── test_correlator.py
    ├── test_user_data_classifier.py
    ├── test_db.py
    └── test_state.py
```

---

## 2. Implementation Roadmap

### Phase 1: Scaffolding and Core Models

- [x] `setup.sh`
- [x] `requirements.txt`
- [x] `requirements-dev.txt`
- [ ] `src/models.py`
- [ ] `src/pathnorm.py`
- [ ] configuration modules
- [ ] deterministic hash contracts
- [ ] DTO contracts

### Phase 2: Persistence and Mount Safety

- [ ] SQLite schema initialization
- [ ] warning storage
- [ ] source persistence
- [ ] block device discovery
- [ ] safe read-only mounting
- [ ] safe unmount confirmation flow
- [ ] mount cleanup handlers
- [ ] privilege invocation boundaries
- [ ] critical I/O failure handling

### Phase 3: Evidence Ingestion

- [ ] hive locator
- [ ] user profile parser
- [ ] registry evidence parser
- [ ] evidence persistence batching
- [ ] manifest generator
- [ ] manifest parser
- [ ] portable scanner
- [ ] bounded enumeration warnings

### Phase 4: Correlation and Heuristics

- [ ] evidence correlation from persisted evidence
- [ ] source-scoped application identity
- [ ] fingerprint status assignment
- [ ] portable candidate merging
- [ ] user-data classification
- [ ] Documents baseline comparison
- [ ] Visual Studio source detection
- [ ] finding deduplication
- [ ] exclusion handling

### Phase 5: State and Coordination

- [ ] report export
- [ ] report import
- [ ] background worker coordinator
- [ ] typed progress events
- [ ] throttled UI updates
- [ ] cancellation handling
- [ ] critical I/O failure state
- [ ] cleanup coordination

### Phase 6: Presentation

- [ ] source list panel
- [ ] source role selection flow
- [ ] secondary-drive advisory
- [ ] treeview grid with application and finding rows
- [ ] details pane
- [ ] status bar with tooltips and progress indication
- [ ] TRIAGE mode
- [ ] export report flow
- [ ] confirmation dialogs

### Phase 7: Tests

- [ ] model construction-validation tests
- [ ] path normalization tests
- [ ] manifest parser tests
- [ ] registry parser tests with synthetic fixture hives or mocked hive structures
- [ ] user profile parser tests
- [ ] portable scanner tests
- [ ] correlator tests
- [ ] user-data classifier tests
- [ ] database tests
- [ ] report round-trip tests
- [ ] bounded-enumeration tests
- [ ] critical failure-state tests

---

## 3. Quick Start

1. Download the project ZIP file and extract it.
2. Open a terminal in the extracted directory.
3. Run:

```bash
chmod +x setup.sh
./setup.sh
```

4. Activate the virtual environment:

```bash
source Win10DRBPythonVenv/bin/activate
```

5. Run the application:

```bash
python src/main.py
```

---

## 4. Running Tests

Install development dependencies manually into the virtual environment:

```bash
python -m pip install -r requirements-dev.txt
```

Run tests:

```bash
python -m pytest tests/
```

Run tests with coverage:

```bash
python -m pytest --cov=src tests/
```

---

## 5. Technical Boundaries and Resolved Design Constraints

### 5.1 Orphaned Mount Point Cleanup

The application tracks mounted sources and releases them on exit, cancellation, failure, and successful scan completion.

If a crash leaves temporary mounts behind, the mount manager should detect application-owned mount directories on startup where practical and attempt safe cleanup.

### 5.2 `lsblk` JSON Variations

The application explicitly requests required fields and parses defensively.

The parser supports both singular and plural mount-point representations where practical.

### 5.3 Registry Hive Damage

Offline hives may be corrupted or incomplete.

The application catches hive-loading exceptions, records warnings, and continues processing other evidence where possible.

Critical I/O errors are treated separately and stop source access.

### 5.4 SYSTEM Control Set Resolution

Offline `SYSTEM` hive parsing resolves the active control set from `SYSTEM\Select`.

The resolution order is deterministic:

1. `Default`
2. `LastKnownGood`
3. first available numeric control set
4. skip with warning if unavailable

### 5.5 WOW6432Node Handling

Windows 10 may store 32-bit application evidence under WOW6432Node paths.

The application enumerates both native and WOW6432Node locations where applicable.

### 5.6 UserAssist Encoding

UserAssist entries may be ROT13-encoded.

The application decodes carefully and treats results as usage evidence, not installation proof.

### 5.7 AppX and Modern Applications

Modern Windows applications may not map cleanly to traditional uninstall registry keys.

AppX evidence is best-effort and confidence is marked appropriately.

### 5.8 OneDrive and Redirected Documents

Documents may be redirected to OneDrive or another custom path.

The application resolves Documents from user shell folder settings where possible.

When the baseline cannot be resolved, findings are marked unknown.

### 5.9 Manifest-Only Metadata Limitations

Manifest files may not provide full metadata.

The application uses path/name heuristics and lowers confidence where size, timestamp, or count data is unavailable.

### 5.10 Visual Studio Source Directories

The application checks:

```text
<UserProfile>\source
<UserProfile>\source\repos
```

for every discovered user profile.

Non-empty source directories are flagged as potential user-generated developer content.

### 5.11 Secondary Drive Oversight

The application shows a persistent advisory near the source list.

The user must add secondary sources manually.

### 5.12 Evidence Volume Control

Evidence collection is bounded to protect memory, database size, report size, and user comprehension.

When bounds are reached, the application records warnings and continues where possible.

### 5.13 Critical I/O Failures

If the application encounters drive I/O errors after the user has performed drive-health checks, it stops source access immediately and informs the user that the drive may be failing.

The application does not retry automatically.

### 5.14 File Content Prohibition

The application never opens file contents.

File-based heuristics use path, name, extension, size, timestamp, and count metadata only.
