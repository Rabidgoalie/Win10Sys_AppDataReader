# Module Contract: src/config/heuristic_patterns.py — v1.0.0 FROZEN (Tier 0)

## 1. Public API

```python
from typing import Final, Iterable
from enum import StrEnum
from dataclasses import dataclass
import re

HEURISTIC_PATTERNS_VERSION: Final[str]
SEVERITY_ORDER: Final[tuple[str, ...]]
CONFIDENCE_ORDER: Final[tuple[str, ...]]
ALLOWED_SEVERITIES: Final[frozenset[str]]
ALLOWED_CONFIDENCES: Final[frozenset[str]]

class LocationCategory(StrEnum):
    DOCUMENTS = "DOCUMENTS"
    DESKTOP = "DESKTOP"
    DOWNLOADS = "DOWNLOADS"
    PICTURES = "PICTURES"
    MUSIC = "MUSIC"
    VIDEOS = "VIDEOS"
    ONEDRIVE = "ONEDRIVE"
    INSTALL_DIR = "INSTALL_DIR"
    APPDATA_ROAMING = "APPDATA_ROAMING"
    APPDATA_LOCAL = "APPDATA_LOCAL"
    APPDATA_LOCALLOW = "APPDATA_LOCALLOW"
    SAVED_GAMES = "SAVED_GAMES"
    VIRTUALSTORE = "VIRTUALSTORE"
    PROGRAMDATA = "PROGRAMDATA"
    SECONDARY_DRIVE = "SECONDARY_DRIVE"
    PORTABLE_DATA_DIR = "PORTABLE_DATA_DIR"
    SOURCE_CODE = "SOURCE_CODE"
    USER_PROFILE_OTHER = "USER_PROFILE_OTHER"
    UNKNOWN = "UNKNOWN"

class FolderAnchor(StrEnum):
    PROFILE = "profile"
    DRIVE = "drive"

class FolderMatchRule(StrEnum):
    DIR_EXACT = "dir_exact"
    DIR_OR_UNDER = "dir_or_under"
    ANY_UNDER = "any_under"

class ExclusionCategory(StrEnum):
    RECYCLE_BIN = "recycle_bin"
    VOLUME_METADATA = "volume_metadata"
    TEMP_CACHE = "temp_cache"
    PACKAGE_CACHE = "package_cache"
    VCS_METADATA = "vcs_metadata"
    VIRTUAL_ENV = "virtual_env"
    COMPILER_CACHE = "compiler_cache"
    SYSTEM_RECOVERY = "system_recovery"

class PortableLayoutKind(StrEnum):
    DIR_NAME = "dir_name"
    EXE_NAME = "exe_name"
    LAYOUT = "layout"

@dataclass(frozen=True)
class UserFolderPattern:
    name: str
    category: LocationCategory
    anchor: FolderAnchor
    segments: tuple[str, ...]
    match_rule: FolderMatchRule
    default_severity: str
    default_confidence: str
    requires_non_empty: bool
    rationale: str

@dataclass(frozen=True)
class PortablePattern:
    name: str
    kind: PortableLayoutKind
    pattern_text: str
    score: int
    default_confidence: str
    rationale: str

    @property
    def compiled(self) -> "re.Pattern[str]": ...

@dataclass(frozen=True)
class ExclusionRule:
    name: str
    category: ExclusionCategory
    exact_segments: frozenset[str] = frozenset()
    consecutive_segments: tuple[tuple[str, ...], ...] = ()
    blocks_traversal: bool = True
    rationale: str = ""

EXECUTABLE_EXTENSIONS: Final[frozenset[str]]
SHORTCUT_EXTENSIONS: Final[frozenset[str]]
APP_PACKAGE_EXTENSIONS: Final[frozenset[str]]
ONEDRIVE_BASE_SEGMENT: Final[str]
SEVERITY_DEFAULTS: Final[dict[LocationCategory, str]]
CONFIDENCE_DEFAULTS: Final[dict[LocationCategory, str]]
CATEGORY_PRECEDENCE: Final[tuple[LocationCategory, ...]]
USER_DATA_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]]
DEVELOPER_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]]
ONEDRIVE_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]]
ALL_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]]
PORTABLE_PATTERNS: Final[tuple[PortablePattern, ...]]
DEFAULT_EXCLUSION_RULES: Final[tuple[ExclusionRule, ...]]

@dataclass(frozen=True)
class HeuristicBounds:
    max_filesystem_entries_per_source: int = 100_000
    max_directory_depth: int = 12
    max_directory_entries: int = 20_000
    max_manifest_entries: int = 500_000
    max_user_data_findings: int = 5_000

DEFAULT_HEURISTIC_BOUNDS: Final[HeuristicBounds]

def is_onedrive_segment(segment: str) -> bool: ...
def has_executable_extension(name: str) -> bool: ...
def has_shortcut_extension(name: str) -> bool: ...
def has_app_package_extension(name: str) -> bool: ...
def severity_rank(severity: str) -> int: ...
def confidence_rank(confidence: str) -> int: ...
def higher_severity(a: str, b: str) -> str: ...
def higher_confidence(a: str, b: str) -> str: ...
def category_precedence_rank(category: LocationCategory) -> int: ...
def choose_category(candidates: Iterable[LocationCategory]) -> LocationCategory: ...
def patterns_for_category(category: LocationCategory) -> tuple[UserFolderPattern, ...]: ...
def default_severity_for(category: LocationCategory) -> str: ...
def default_confidence_for(category: LocationCategory) -> str: ...
def resolve_heuristic_bounds(
    *,
    max_filesystem_entries_per_source: int | None = None,
    max_directory_depth: int | None = None,
    max_directory_entries: int | None = None,
    max_manifest_entries: int | None = None,
    max_user_data_findings: int | None = None,
) -> HeuristicBounds: ...
```

## 2. Postconditions
- `HEURISTIC_PATTERNS_VERSION` is a constant string `"1.0.0"`.
- `SEVERITY_ORDER` and `CONFIDENCE_ORDER` are tuples of strings `("Low", "Medium", "High")`.
- `ALLOWED_SEVERITIES` and `ALLOWED_CONFIDENCES` are frozensets of the respective order tuples.
- Enums (`LocationCategory`, `FolderAnchor`, `FolderMatchRule`, `ExclusionCategory`, `PortableLayoutKind`) provide exact string values as defined in the API fence.
- `UserFolderPattern`, `PortablePattern`, `ExclusionRule`, and `HeuristicBounds` are frozen dataclasses with the specified fields. `PortablePattern.compiled` returns a precompiled `re.Pattern[str]`.
- `EXECUTABLE_EXTENSIONS`, `SHORTCUT_EXTENSIONS`, and `APP_PACKAGE_EXTENSIONS` are frozensets of lowercase extension strings.
- `SEVERITY_DEFAULTS` and `CONFIDENCE_DEFAULTS` map every `LocationCategory` to a valid severity/confidence string.
- `CATEGORY_PRECEDENCE` is a tuple of all `LocationCategory` members in deterministic precedence order.
- `USER_DATA_FOLDER_PATTERNS`, `DEVELOPER_FOLDER_PATTERNS`, `ONEDRIVE_FOLDER_PATTERNS`, `ALL_FOLDER_PATTERNS`, `PORTABLE_PATTERNS`, and `DEFAULT_EXCLUSION_RULES` are tuples of their respective dataclass instances, fully populated.
- `DEFAULT_HEURISTIC_BOUNDS` is an instance of `HeuristicBounds` with positive integer defaults.
- Helper functions return deterministic results based strictly on their inputs and the module's constants. `resolve_heuristic_bounds` returns a new `HeuristicBounds` instance, substituting invalid or missing inputs with defaults.

## 3. Error contract
- The module performs zero I/O and has no side effects. It contains no state-modifying operations that could fail due to external system conditions.
- `severity_rank` and `confidence_rank` raise `ValueError` if an unknown or malformed severity/confidence string is provided.
- `choose_category` raises `ValueError` if the `candidates` iterable is empty.
- `resolve_heuristic_bounds` defensively coerces invalid types (including `bool`) and non-positive integers to documented defaults; it does not raise.
- `_validate_configuration` (internal) acts as an import-time fail-fast mechanism, raising `ValueError` immediately if any structural configuration invariant is violated.

## 4. Events and warnings emitted
- None. This module is pure configuration and helper functions. It emits no events and logs no warnings.

## 5. I/O surface
- None. The module performs zero I/O. It does not read from or write to the filesystem, network, or any external resource. It is strictly memory-resident and read-only by construction.

## 6. Threading and cancellation
- The module is entirely stateless and immutable after import. All dataclasses are frozen (`frozen=True`), and constants are typed as `Final`.
- It is inherently thread-safe. No locks, `cancel_event`, or synchronization primitives are required or used. Functions can be called concurrently from any thread without risk of race conditions.

## 7. Non-contract internals
- `_name_has_extension`: Helper for extension checking.
- `_as_positive_int`: Helper for defensive bound coercion.
- `_validate_configuration`: Import-time validation function.
- Any future additions prefixed with `_` are free to vary without contract amendment.

## 8. Acceptance fixtures
`tests/test_heuristic_patterns.py`:
- Closed severity/confidence vocabularies (FR-4.8 / FR-4.9).
- Deterministic, total category precedence used by finding merges (FR-4.7).
- Name/extension-only signals — the helpers never touch file bytes
  (SRS §3.3: no file-content inspection; PE headers never parsed).
- Path-only OneDrive detection (README §5.8).
- Bounded enumeration defaults and defensive bound resolution (SRS §3.10,
  NFR-5): a bad operator setting must fall back to documented defaults,
  never produce an unbounded scan.
- Fail-fast import-time configuration validation: a defective heuristic
  table must fail loudly at import, never silently corrupt classifier
  output on a stressed user's machine (SDD §2.6).

## 9. Deviations from SDD/SRS
- None. The module strictly implements SDD §2.6 and SRS FR-3 / FR-4 constraints, including the exact category names, precedence rules, and enumeration bounds specified in the requirements.