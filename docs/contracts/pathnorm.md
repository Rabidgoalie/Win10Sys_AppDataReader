# Module Contract: `src/pathnorm.py` — v1.0.0 FROZEN (Tier 0)

**Freeze Date:** 2026-11-14  
**Approver:** Rabidgoalie (Coordinator)

## 1. Public API
```python
from pathlib import Path
from typing import Final

LOGICAL_DRIVE_PATTERN: Final[str]

def normalize_windows_path(value: str | None) -> str: ...
def strip_ads(value: str | None) -> str: ...
def comparison_form(value: str | None) -> str: ...
def paths_equal(a: str | None, b: str | None) -> bool: ...
def is_path_under(child: str | None, parent: str | None) -> bool: ...
def is_path_under_or_equal(child: str | None, parent: str | None) -> bool: ...
def is_inside_documents(candidate: str | None, documents_root: str | None) -> bool: ...
def is_unc_path(value: str | None) -> bool: ...
def validate_logical_drive(drive: str) -> str: ...
def logical_drive_for_position(position: int) -> str: ...
def logical_to_source_relative(logical_path: str | None) -> str: ...
def source_relative_to_logical(source_relative: str | None, logical_drive: str) -> str: ...
def is_linux_path_under(child: str | Path | None, parent: str | Path | None, include_self: bool = False) -> bool: ...
def map_mount_path_to_source_relative(mount_path: str | Path, mount_root: str | Path) -> str: ...
def is_manifest_comment(line: str | None) -> bool: ...
def manifest_line_to_source_relative(line: str | None) -> str: ...
```

## 2. Postconditions
- **`normalize_windows_path`**: Returns `""` for `None`/empty/whitespace. Converts forward slashes to backslashes, collapses separator runs, removes leading separators (except UNC `\\`), removes trailing backslash (except for drive roots like `C:`), strips ADS suffixes from the final component, and uppercases the drive prefix. Idempotent.
- **`strip_ads`**: Returns the path with any ADS suffix removed from the final component. Idempotent.
- **`comparison_form`**: Returns `normalize_windows_path(value).lower()`. This is the only location where case is lowered.
- **`paths_equal`**: Returns `True` if `comparison_form(a) == comparison_form(b)`.
- **`is_path_under`**: Returns `True` if `child` is strictly nested under `parent` (case-insensitive, separator-anchored).
- **`is_path_under_or_equal`**: Returns `True` if `child` is nested under or identical to `parent`.
- **`is_inside_documents`**: Returns `True` if `candidate` is under or equal to `documents_root` (used for tri-state baseline resolution).
- **`is_unc_path`**: Returns `True` if the normalized path starts with `\\`.
- **`validate_logical_drive`**: Returns the uppercased, validated drive string (e.g., `C:`, `S1:`). 
- **`logical_drive_for_position`**: Returns `C:` for `0`, `S{position}:` for `>0`.
- **`logical_to_source_relative`**: Strips the drive prefix. Returns `""` for a bare drive. Preserves UNC paths unchanged.
- **`source_relative_to_logical`**: Prefixes the source-relative path with the validated logical drive. 
- **`is_linux_path_under`**: Returns `True` if `child` is lexically under `parent` (POSIX absolute paths), optionally including equality.
- **`map_mount_path_to_source_relative`**: Returns a source-relative Windows path. 
- **`is_manifest_comment`**: Returns `True` if the line starts with `#` after stripping NUL bytes and whitespace.
- **`manifest_line_to_source_relative`**: Returns a source-relative path, stripping drive prefixes and normalizing. Returns `""` for blank or `#`-comment lines. Drops `.` and `..` components.

## 3. Error Contract
- **Graceful Degradation**: Pure normalization functions (`normalize_windows_path`, `comparison_form`, etc.) never raise on corrupt input (e.g., `None`, NUL bytes, malformed paths). They degrade gracefully to `""` or safe defaults.
- **Caller Contract Violations (`ValueError`)**: The following functions raise `ValueError` loudly, as they indicate a caller bug, not corrupt data:
  - `validate_logical_drive`: Invalid drive string (not `C:` or `S1:`, `S2:`, etc.).
  - `logical_drive_for_position`: `position` is not a non-negative integer.
  - `source_relative_to_logical`: `source_relative` is a UNC path (refuses to fabricate provenance).
  - `map_mount_path_to_source_relative`: Inputs do not normalize to absolute POSIX paths, `mount_path` equals `mount_root`, or `mount_path` lexically escapes `mount_root`.

## 4. Events and Warnings Emitted
- **None.** This module is pure and side-effect free. 
- *Caller Responsibility*: Ingestion layers must catch `ValueError` from `map_mount_path_to_source_relative` and convert it into a typed `WarningEvent(category='acquisition')` or `CriticalIoFailureEvent` as appropriate, per ADR-19.

## 5. I/O Surface
- **Filesystem/Subprocess/Network/DB**: None. Zero access.
- **Read-Only Guarantee**: Pure string/`Path` manipulation. Cannot violate the zero-write boundary under any circumstance.

## 6. Threading and Cancellation
- **Thread-Safe**: Yes. Contains no shared mutable state (only precompiled `re.Pattern` constants and `Final` strings). Safe to call from any thread without locking.
- **Cancellation**: No `cancel_event` parameter required. Execution time is strictly bounded by path string length (O(N)), making it immune to long-running hangs.

## 7. Non-Contract Internals (Free to Vary)
The following are Tier 2 internals and may be refactored freely as long as §1–§6 are maintained:
- `_drop_nul_and_strip`
- `_strip_ads_last_component`
- `_uppercase_drive_prefix`
- `_normalize_posix_path`
- `_LOGICAL_DRIVE_RE`, `_DRIVE_PREFIX_RE`, `_SEPARATOR_RUN_RE`, `_MISSING_COLON_DRIVE_RE`

## 8. Acceptance Fixtures
`tests/test_pathnorm.py`:
1. Core normalization & sanitization    -> TestNormalizationAndSanitization
2. Comparison & equality                -> TestComparisonAndEquality
3. Containment & hierarchy              -> TestContainmentAndHierarchy
4. UNC & logical drive routing          -> TestUncAndLogicalDrives
5. POSIX / mount-side safety            -> TestPosixMountSideSafety
6. Manifest ingestion                   -> TestManifestIngestion
7. Cross-module hash-grade parity       -> TestCrossModuleHashParity
8. Sentinel totality (None/""/whitespace)-> TestTotalitySentinels
9. F-04..F-07 regression locks          -> TestF04F05RegressionLocks
10. Source hygiene (docstring escapes)  -> TestSourceHygiene

## 9. Deviations from SDD
- **None.** This module strictly enforces SDD §2.4 normative rules and DDD §5 hash-grade canonicalization prerequisites.
