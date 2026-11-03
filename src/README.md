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
│   │   ├── evidence_locations.py   # Supported evidence roots
│   │   └── heuristic_patterns.py   # Heuristic and exclusion patterns
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── manifest_generator.py   # ntfsls manifest generation
│   │   ├── manifest_parser.py      # ntfsls manifest reader
│   │   ├── hive_locator.py         # Hive file discovery
│   │   ├── registry_parser.py      # Offline registry evidence parser
│   │   ├── user_profile_parser.py  # User profile and Documents resolution
│   │   └── portable_scanner.py     # Portable application discovery
│   └── heuristics/
│       ├── __init__.py
│       ├── user_data_classifier.py # Potential user-data classification
│       └── exclusions.py           # False-positive exclusions
└── tests/
    ├── __init__.py
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

## 2. Implementation Roadmap

### Phase 1: Scaffolding and Core Models

- `setup.sh`
- `requirements.txt`
- `requirements-dev.txt`
- `src/models.py`
- `src/pathnorm.py`
- configuration modules

### Phase 2: Persistence and Mount Safety

- SQLite schema initialization
- source persistence
- block device discovery
- safe read-only mounting
- mount cleanup handlers
- confirmation flow for already-mounted partitions

### Phase 3: Evidence Ingestion

- hive locator
- user profile parser
- registry evidence parser
- manifest generator
- manifest parser
- portable scanner

### Phase 4: Correlation and Heuristics

- evidence correlation
- fingerprint status assignment
- portable candidate merging
- user-data classification
- Documents baseline comparison
- Visual Studio source detection
- exclusion handling

### Phase 5: State and Coordination

- report export
- report import
- background worker coordinator
- typed progress events
- cancellation handling
- cleanup coordination

### Phase 6: Presentation

- source list panel
- secondary-drive advisory
- treeview grid
- details pane
- status bar with tooltips
- report viewer mode
- export report flow

### Phase 7: Tests

- path normalization tests
- manifest parser tests
- registry parser tests with fixture hives
- user profile parser tests
- portable scanner tests
- correlator tests
- user-data classifier tests
- database tests
- report round-trip tests

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

## 5. Technical Debt and Edge Cases to Monitor

### 5.1 Orphaned Mount Point Cleanup

If the application crashes during an active scan, temporary mounts may remain.

Mitigation:

- Use cleanup handlers.
- Track all mounted sources.
- Attempt release on exit, cancellation, and failure.

### 5.2 `lsblk` JSON Variations

Different util-linux versions may vary slightly.

Mitigation:

- Explicitly request required fields.
- Parse defensively.

### 5.3 Registry Hive Damage

Offline hives may be corrupted or incomplete.

Mitigation:

- Catch hive-loading exceptions.
- Record warnings.
- Continue processing other evidence where possible.

### 5.4 SYSTEM Control Set Resolution

Offline `SYSTEM` hive parsing must resolve the active control set from `SYSTEM\Select`.

Mitigation:

- Implement explicit control-set resolution.
- Do not assume `CurrentControlSet` is directly valid.

### 5.5 WOW6432Node Handling

Windows 10 may store 32-bit application evidence under WOW6432Node paths.

Mitigation:

- Enumerate both native and WOW6432Node locations where applicable.

### 5.6 UserAssist Encoding

UserAssist entries may be ROT13-encoded.

Mitigation:

- Decode carefully and treat results as usage evidence, not installation proof.

### 5.7 AppX and Modern Applications

Modern Windows applications may not map cleanly to traditional uninstall registry keys.

Mitigation:

- Treat AppX evidence as best-effort.
- Mark confidence appropriately.

### 5.8 OneDrive and Redirected Documents

Documents may be redirected to OneDrive or another custom path.

Mitigation:

- Resolve Documents from user shell folder settings where possible.
- Mark findings as unknown when the baseline cannot be resolved.

### 5.9 Manifest-Only Metadata Limitations

Manifest files may not provide full metadata.

Mitigation:

- Use path/name heuristics.
- Lower confidence where size, timestamp, or count data is unavailable.

### 5.10 Visual Studio Source Directories

New developers may not realize that Visual Studio projects are valuable.

Mitigation:

- Check `<UserProfile>\source` and `<UserProfile>\source\repos` for every discovered user profile.
- Flag non-empty source directories as potential user-generated developer content.

### 5.11 Secondary Drive Oversight

Users may forget to scan secondary drives before wiping them.

Mitigation:

- Show a persistent advisory near the source list.
- Require the user to add secondary sources manually.