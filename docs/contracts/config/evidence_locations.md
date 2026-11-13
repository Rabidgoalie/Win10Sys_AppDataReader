# Module Contract: src/config/evidence_locations.py — v1.0.0 FROZEN (Tier 0)

> **Status:** FROZEN · **Tier:** 0 (frozen baseline; amendment requires coordinator + reviewer sign-off with rationale in §9)
> **Owner:** Principal Reviewer · **Baseline:** shipped `src/config/evidence_locations.py` (Implementation Phase 1)
> **Normative references:** SDD §2.5, SRS Appendix A, SRS FR-2.2/FR-2.3/FR-2.4/FR-2.6/FR-2.7/FR-4.3/FR-4.9/FR-6.1/FR-6.3/FR-7.1/FR-7.2, DDD §4, ADR-6, ADR-13, ADR-17, ADR-19, README §5.4–§5.6

---

## 1. Public API

```python
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, Mapping, Protocol

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

EVIDENCE_LOCATIONS_VERSION: Final[str] = "1.0.0"

# ---------------------------------------------------------------------------
# Hive type identifiers
# ---------------------------------------------------------------------------

HIVE_SOFTWARE: Final[str] = "SOFTWARE"
HIVE_SYSTEM: Final[str] = "SYSTEM"
HIVE_DEFAULT: Final[str] = "DEFAULT"
HIVE_NTUSER: Final[str] = "NTUSER"
HIVE_USRCLASS: Final[str] = "USRCLASS"

HIVE_TYPES: Final[tuple[str, ...]] = (
    HIVE_SOFTWARE,
    HIVE_SYSTEM,
    HIVE_DEFAULT,
    HIVE_NTUSER,
    HIVE_USRCLASS,
)

MACHINE_HIVES: Final[tuple[str, ...]] = (HIVE_SOFTWARE, HIVE_SYSTEM)

USER_LIKE_HIVES: Final[tuple[str, ...]] = (HIVE_NTUSER, HIVE_DEFAULT)

HIVE_FILE_NAMES: Final[Mapping[str, str]] = {
    HIVE_SOFTWARE: "SOFTWARE",
    HIVE_SYSTEM: "SYSTEM",
    HIVE_DEFAULT: "DEFAULT",
    HIVE_NTUSER: "NTUSER.DAT",
    HIVE_USRCLASS: "UsrClass.dat",
}

HIVE_ROOT_COMPONENTS: Final[Mapping[str, str]] = {
    HIVE_SOFTWARE: "SOFTWARE",
    HIVE_SYSTEM: "SYSTEM",
    HIVE_DEFAULT: "Software",
    HIVE_NTUSER: "Software",
}

# ---------------------------------------------------------------------------
# Confidence vocabulary
# ---------------------------------------------------------------------------

ConfidenceLevel = Literal["Low", "Medium", "High"]

CONFIDENCE_LEVELS: Final[tuple[str, ...]] = ("Low", "Medium", "High")

# ---------------------------------------------------------------------------
# Evidence root model
# ---------------------------------------------------------------------------

class EvidenceKind(StrEnum):
    SUBKEYS = "subkeys"
    VALUES = "values"
    KEY_ONLY = "key_only"

@dataclass(frozen=True, slots=True)
class EvidenceRootSpec:
    evidence_type: str
    hive: str
    path: str
    kind: EvidenceKind
    purpose: str
    best_effort: bool = False
    usage_evidence_only: bool = False
    decode_rot13: bool = False
    default_confidence: ConfidenceLevel = "Medium"
    placeholders: tuple[str, ...] = ()
    subkey_name_pattern: str | None = None
    nested_value_path: str | None = None
    value_name: str | None = None

# ---------------------------------------------------------------------------
# Placeholders, WOW64, and SYSTEM control-set policy
# ---------------------------------------------------------------------------

WOW64_NODE: Final[str] = "Wow6432Node"
SID_PLACEHOLDER: Final[str] = "<SID>"
CONTROL_SET_PLACEHOLDER: Final[str] = "<CONTROL_SET>"

SYSTEM_SELECT_PATH: Final[str] = "SYSTEM\\Select"

SELECT_VALUE_NAMES: Final[tuple[str, ...]] = ("Default", "LastKnownGood", "Current")

CONTROL_SET_PRIORITY_ORDER: Final[tuple[str, ...]] = ("Default", "LastKnownGood")

CONTROL_SET_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^ControlSet00\d+$")
SID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^S-1-\d+(?:-\d+)*$")
GUID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)
PROGID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9._+-]*\.[A-Za-z0-9._+-]*$"
)
EXTENSION_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\.[A-Za-z0-9]{1,10}$")
PACKAGE_FAMILY_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9.]*_[A-Za-z0-9]+$"
)

# ---------------------------------------------------------------------------
# Configured evidence roots
# ---------------------------------------------------------------------------

REGISTRY_EVIDENCE_ROOTS: Final[tuple[EvidenceRootSpec, ...]]
PROFILE_RESOLUTION_ROOTS: Final[tuple[EvidenceRootSpec, ...]]
REGISTRY_EVIDENCE_TYPE_KEYS: Final[tuple[str, ...]]

# ---------------------------------------------------------------------------
# Root lookup helpers
# ---------------------------------------------------------------------------

def root_by_evidence_type(evidence_type: str) -> EvidenceRootSpec | None: ...

def roots_for_hive(hive: str) -> tuple[EvidenceRootSpec, ...]: ...

def profile_resolution_roots_for_hive(hive: str) -> tuple[EvidenceRootSpec, ...]: ...

def subkey_name_pattern_for(spec: EvidenceRootSpec) -> re.Pattern[str] | None: ...

def is_wow64_root(spec: EvidenceRootSpec) -> bool: ...

def hive_relative_path(spec: EvidenceRootSpec) -> str: ...

def expand_placeholders(
    spec: EvidenceRootSpec,
    *,
    sid: str | None = None,
    control_set: str | None = None,
) -> str: ...

# ---------------------------------------------------------------------------
# Registry enumeration bounds
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RegistryBounds:
    max_evidence_total: int = 250_000
    max_evidence_per_root: int = 5_000
    max_subkeys_per_key: int = 2_000
    max_values_per_key: int = 2_000

DEFAULT_REGISTRY_BOUNDS: Final[RegistryBounds]

class BoundsProvider(Protocol):
    max_evidence_total: int | None
    max_evidence_per_root: int | None
    max_subkeys_per_key: int | None
    max_values_per_key: int | None

def resolve_registry_bounds(options: BoundsProvider) -> RegistryBounds: ...
```

---

## 2. Postconditions

### 2.1 Versioning

- `EVIDENCE_LOCATIONS_VERSION` is the stable semantic version of the evidence-location configuration. It is persisted in `SCAN_SESSION.scan_options_json` via `ScanOptions.evidence_locations_version` and stamped into exported reports (SRS FR-6.1/FR-6.3). Major bumps denote root removal/renaming/reclassification; minor bumps denote additive root additions or confidence-default changes.

### 2.2 Hive identifiers

- `HIVE_SOFTWARE`, `HIVE_SYSTEM`, `HIVE_DEFAULT`, `HIVE_NTUSER`, `HIVE_USRCLASS` are the five canonical hive identifiers consumed by the hive locator (SDD §2.9) and registry parser (SDD §2.10). They are stable string tokens; the registry parser is responsible for coercing them into the model's `HiveType` enum before persistence.
- `HIVE_TYPES` is the exhaustive tuple of all hive identifiers in canonical order.
- `MACHINE_HIVES` enumerates hives located on the primary Windows source (`SOFTWARE`, `SYSTEM`).
- `USER_LIKE_HIVES` enumerates hives sharing the per-user layout (`NTUSER`, `DEFAULT`). The `DEFAULT` hive shares the `NTUSER.DAT` key layout; per-user roots therefore apply to both. Default and system profiles are marked as such by the profile parser (SRS FR-2.5) and are not treated as normal user-data owners.
- `HIVE_FILE_NAMES` maps each configuration identifier to its offline hive file name (informational; consumed by the hive locator for matching).
- `HIVE_ROOT_COMPONENTS` maps each hive identifier to the root key name *inside* the hive file. `USRCLASS` is absent because its configured paths are already hive-relative.

### 2.3 Confidence vocabulary

- `ConfidenceLevel` is the `Literal["Low", "Medium", "High"]` type alias matching the model's `Confidence` enum values (SRS FR-2.7 / FR-4.9).
- `CONFIDENCE_LEVELS` is the exhaustive tuple of confidence spellings in ascending order.

### 2.4 Evidence root model

- `EvidenceKind` is the `StrEnum` describing how a configured root is enumerated:
  - `SUBKEYS` — each immediate subkey of the root is one evidence unit (e.g. `Uninstall` product subkeys).
  - `VALUES` — each value under the root key is one evidence unit (e.g. `Run`, `SharedDLLs`).
  - `KEY_ONLY` — the presence of the key itself is the evidence (e.g. optional `AppModel`/`Appx` containers).
- `EvidenceRootSpec` is the frozen, slotted dataclass describing one supported registry evidence location (SRS Appendix A). All fields are inert data. The registry parser must:
  - treat `path` as case-insensitive when resolving keys against a hive;
  - expand declared placeholders with `expand_placeholders` and skip the root (with a warning, never a crash) when a placeholder cannot be resolved;
  - filter enumerated subkey names with `subkey_name_pattern_for` when a pattern is configured;
  - respect `usage_evidence_only` (UserAssist is usage evidence, never installation proof — SRS Appendix A.3);
  - apply `decode_rot13` to value data where appropriate and turn decode failures into warnings, never exceptions (SRS Appendix A.3, README §5.6);
  - treat `best_effort` roots as lower-alarmance: a missing or partially unreadable best-effort root downgrades warnings, while a failed primary root raises a higher-severity warning;
  - never exceed the configured `RegistryBounds`.
- Construction-time validation (`__post_init__`) rejects malformed specs (invalid `evidence_type` format, unknown hive, invalid confidence, forward-slash path separators, empty path components, mismatched hive root component, undeclared or unused placeholders, invalid regex patterns, invalid `nested_value_path`). These are developer errors and must fail loudly at import.

### 2.5 Placeholders and control-set policy

- `WOW64_NODE` is the 32-bit registry view node on 64-bit Windows (`Wow6432Node`). WOW64 variants are declared as explicit roots so the `include_wow64` option can be applied as a simple path filter.
- `SID_PLACEHOLDER` (`<SID>`) and `CONTROL_SET_PLACEHOLDER` (`<CONTROL_SET>`) are the only permitted placeholders in `EvidenceRootSpec.path`.
- `SYSTEM_SELECT_PATH` is the path to `SYSTEM\Select`, which holds the `Default`/`LastKnownGood`/`Current` DWORD values used to resolve the active control set offline.
- `SELECT_VALUE_NAMES` enumerates the three value names consulted during control-set resolution.
- `CONTROL_SET_PRIORITY_ORDER` is the deterministic resolution order (SRS Appendix A.2, README §5.4): `Default` if valid, then `LastKnownGood` if valid, then the first available `ControlSet00X` key in numeric order, otherwise skip SYSTEM evidence with a warning.
- `CONTROL_SET_KEY_PATTERN`, `SID_KEY_PATTERN`, `GUID_KEY_PATTERN`, `PROGID_KEY_PATTERN`, `EXTENSION_KEY_PATTERN`, `PACKAGE_FAMILY_KEY_PATTERN` are compiled regex patterns used to filter enumerated subkey names (ProgID, GUID, package-family-name, SID, control-set, and extension keys respectively).

### 2.6 Configured evidence roots

- `REGISTRY_EVIDENCE_ROOTS` is the exhaustive tuple of all configured application-evidence roots, in hive order (machine `SOFTWARE`, machine `SYSTEM`, per-user `NTUSER.DAT`, per-user `UsrClass.dat`). Order is presentation order only; consumers must not rely on it. Every path is copied verbatim from SRS Appendix A.
- `PROFILE_RESOLUTION_ROOTS` enumerates profile-resolution roots (Appendix A.6). These are consumed by the user profile parser (SDD §2.11) for SID/profile-path mapping and shell-folder (Documents baseline) resolution. They are intentionally *not* part of `REGISTRY_EVIDENCE_ROOTS` so the registry parser does not emit them as application evidence.
- `REGISTRY_EVIDENCE_TYPE_KEYS` is the stable, versioned vocabulary of all evidence-type keys configured in this module (registry-side only; filesystem and manifest evidence-type keys are owned by their ingestion modules).

### 2.7 Root lookup helpers

- `root_by_evidence_type(evidence_type)` returns the configured root for `evidence_type`, or `None`. Covers both application-evidence and profile-resolution roots. Callers receiving `None` must treat the type as unknown and record a warning rather than raising (defensive parsing contract, SRS FR-2.6).
- `roots_for_hive(hive)` returns the application-evidence roots configured for `hive`. `DEFAULT` returns the per-user (`NTUSER`) roots because the DEFAULT hive shares the NTUSER.DAT layout. An unknown hive identifier returns an empty tuple; the registry parser records a warning for that case.
- `profile_resolution_roots_for_hive(hive)` returns the profile-resolution roots for `hive` (Appendix A.6). `DEFAULT` resolves to the same per-user shell-folder roots as `NTUSER`. Unknown hives yield an empty tuple.
- `subkey_name_pattern_for(spec)` returns the compiled subkey-name filter for `spec`, or `None` if unfiltered.
- `is_wow64_root(spec)` returns `True` when the root lives under `Wow6432Node` (SRS FR-2.4, README §5.5).
- `hive_relative_path(spec)` returns the key path *inside* the hive file, i.e. with the hive root component stripped (the form used by the offline hive parser for key lookup). `SOFTWARE`/`SYSTEM`/per-user specs store the Appendix A form whose first component is the hive root name; that component is stripped case-insensitively. `USRCLASS` specs are already hive-relative. Placeholders are left in place — expand them with `expand_placeholders` before lookup. An empty path stays empty (the hive root).
- `expand_placeholders(spec, *, sid=None, control_set=None)` resolves `<SID>` / `<CONTROL_SET>` placeholders in `spec.path`. Raises `ValueError` when a declared placeholder has no usable value. The registry parser must catch this per root, skip that root, and record a warning — a missing SID or an unresolved control set degrades one evidence category, it must never abort the scan (SRS FR-2.6, SDD §4.2).

### 2.8 Registry enumeration bounds

- `RegistryBounds` is the frozen, slotted dataclass holding deterministic enumeration bounds for offline registry evidence. Defaults match the `ScanOptions` defaults (DDD §4):
  - `max_evidence_total` — maximum evidence records per source (SRS FR-2.3);
  - `max_evidence_per_root` — maximum evidence records per configured root;
  - `max_subkeys_per_key` — maximum registry subkeys examined per key;
  - `max_values_per_key` — maximum registry values examined per key.
- Construction-time validation rejects non-positive integers, booleans, and non-integers.
- `DEFAULT_REGISTRY_BOUNDS` is the single documented default bounds instance (SRS FR-2.3).
- `BoundsProvider` is a structural `Protocol` describing the bound fields of `models.RegistryParseOptions`. Using a protocol (instead of importing the model) keeps this configuration module free of any dependency on the persistence/DTO layer, while remaining fully statically checkable.
- `resolve_registry_bounds(options)` resolves operator bounds against the documented defaults. `models.RegistryParseOptions` fields default to `None` (SDD §2.10), meaning "use the configured defaults". This function is the *single* place where that resolution happens, so the defaults in `DEFAULT_REGISTRY_BOUNDS` remain the sole authoritative source. `None` and any invalid value (non-int, bool, or non-positive) fall back to the documented default. A corrupt or tampered scan-options blob must never abort a scan (defensive parsing contract, SRS FR-2.6 / FR-7.2).

---

## 3. Error contract

- **Module import:** The module performs import-time validation (`_validate_configuration`) and constructs all `EvidenceRootSpec` instances, each of which runs `__post_init__` validation. Any configuration defect (duplicate `evidence_type`, missing Appendix A root, malformed path, invalid placeholder, invalid regex, etc.) raises `ValueError` at import. This is a developer error, not user data; failing loudly at import is strictly safer than degrading at scan time (SRS FR-2.2, NFR-10).
- **`EvidenceRootSpec` construction:** Raises `ValueError` for any malformed field (see §2.4). These are developer errors caught at import.
- **`RegistryBounds` construction:** Raises `ValueError` for non-positive integers, booleans, or non-integers. These are developer errors caught at import or when constructing custom bounds.
- **`expand_placeholders`:** Raises `ValueError` when a declared placeholder (`<SID>` or `<CONTROL_SET>`) has no usable value (missing `sid`, missing `control_set`, invalid `sid` containing backslash, or `control_set` not matching `CONTROL_SET_KEY_PATTERN`). The registry parser must catch this per root, skip that root, and record a warning — a missing SID or an unresolved control set degrades one evidence category, it must never abort the scan (SRS FR-2.6, SDD §4.2).
- **All other public functions and constants:** Total. No exceptions raised. Unknown hive identifiers in `roots_for_hive` / `profile_resolution_roots_for_hive` return empty tuples; unknown `evidence_type` in `root_by_evidence_type` returns `None`. Callers record warnings for these cases (defensive parsing contract, SRS FR-2.6).
- **No I/O, no subprocess, no network:** The module never touches a scanned source drive, never reads or writes files, never invokes subprocesses, never accesses the network. All read-only guarantees for source media are enforced by `mount_manager` and the ingestion layers that consume this configuration; this module neither depends on them nor can violate them.

---

## 4. Events and warnings emitted

**None.** This module is pure data and pure functions. It emits no events, no warnings, no logs. Event emission is the coordinator's responsibility (ADR-4, ADR-22). Warnings about unknown evidence types, unknown hives, or placeholder expansion failures are emitted by the registry parser (SDD §2.10) when it consumes this configuration.

---

## 5. I/O surface

**None.** This module performs no I/O of any kind:

- No filesystem reads or writes.
- No subprocess invocations.
- No network access.
- No database access.
- No registry hive reads.

It is an inert data module that describes *where* evidence may live inside offline hives and *how much* may be enumerated. The read-only guarantees for source media are enforced by `mount_manager` (SDD §2.7) and the ingestion layers (SDD §2.8–§2.13) that consume this configuration; this module neither depends on them nor can violate them.

---

## 6. Threading and cancellation

- **Immutable state:** Every name exported by this module is an immutable object created exactly once at import time (`Final` constants, frozen dataclass instances, tuples, module-level dicts that are never mutated afterwards, compiled regex patterns). All consumers may read them from any thread without synchronization.
- **Pure functions:** Every helper function in this module is a pure function with no shared mutable state. They are safe to call from any thread, including the Tkinter UI thread, background worker threads, and test threads.
- **No `cancel_event`:** None of the public functions accept or require a `cancel_event` parameter. They are bounded tightly enough (dictionary lookups, tuple iteration, regex matching, string replacement) not to require one (SDD §4.7, ADR-15).
- **No blocking:** No function performs I/O, waits on locks, or blocks. All functions return immediately.

---

## 7. Non-contract internals (Tier 2 — free to vary)

The following names are explicitly **not** part of the public API contract. They may be renamed, refactored, or removed without amendment to this sheet:

- `_EVIDENCE_TYPE_RE` — compiled regex for validating `evidence_type` format.
- `_SOFTWARE_ROOTS`, `_SYSTEM_ROOTS`, `_NTUSER_ROOTS`, `_USRCLASS_ROOTS` — per-hive tuples of `EvidenceRootSpec` (concatenated into `REGISTRY_EVIDENCE_ROOTS`).
- `_ROOT_INDEX` — dictionary mapping `evidence_type` to `EvidenceRootSpec` (used by `root_by_evidence_type`).
- `_COMPILED_SUBKEY_PATTERNS` — dictionary mapping `evidence_type` to compiled `re.Pattern` (used by `subkey_name_pattern_for`).
- `_REQUIRED_EVIDENCE_TYPES` — frozenset of Appendix A minimum evidence types (used by `_validate_configuration`).
- `_validate_configuration` — import-time validation function.
- `_as_positive_int` — helper for defensive coercion of optional bounds (used by `resolve_registry_bounds`).

All `_`-prefixed names are Tier 2 internals. The public API is exactly the set of names declared in §1.

---

## 8. Acceptance fixtures

`tests/test_evidence_locations.py`:
1. ``TestModulePurityAndImmutability``
   SDD §4.1 — the configuration module is pure data: zero I/O on import,
   no public mutation surface, frozen value objects.
2. ``TestEvidenceRootSpecValidation``
   Fail-fast ``__post_init__`` validation — a developer typo must crash the
   test suite at import time, never a live forensic scan (SRS FR-2.2).
3. ``TestRegexContractLocks``
   Character-exact regression locks for every compiled filter pattern.
4. ``TestBoundsResolutionDefenses``
   SRS §3.10 / FR-2.3 — a corrupt scan-options blob must never raise and
   must never admit unbounded evidence; invalid fields fall back to the
   documented safe defaults.
5. ``TestPlaceholderExpansionAndRouting``
   SDD §4.2 — pure mapping from logical registry paths to physical hive
   structure; per-root degradation must raise a catchable ``ValueError``
   so the parser can skip one root with a warning, never crash the scan.
6. ``TestForensicEdgeCases``
   Normative locks: WOW64 views, case-insensitive key resolution,
   best-effort/volatile roots, UserAssist usage-only + ROT13 semantics,
   SYSTEM control-set resolution policy, hive file names, and the
   Appendix A minimum location set.

---

## 9. Deviations from SDD / SRS

**None.** This module is a faithful, exhaustive encoding of SDD §2.5 and SRS Appendix A as inert data. Every evidence root, placeholder, confidence default, and enumeration bound is copied verbatim from the normative specifications. No deviations, no omissions, no reinterpretations.

- SDD §2.5 (evidence configuration) → fully implemented as `EvidenceRootSpec` instances in `REGISTRY_EVIDENCE_ROOTS` and `PROFILE_RESOLUTION_ROOTS`.
- SRS Appendix A (supported registry evidence locations) → every table row is encoded as an `EvidenceRootSpec` with the exact path, purpose, and confidence default specified.
- SRS FR-2.3 (bounded evidence enumeration) → implemented as `RegistryBounds` with deterministic defaults matching `ScanOptions`.
- SRS FR-2.4 (registry evidence locations) → all hive types and WOW64 variants are explicitly declared.
- SRS FR-2.6 (evidence retention) → defensive parsing contract (unknown types/hives return `None`/empty tuples, never raise) is enforced by `root_by_evidence_type`, `roots_for_hive`, and `profile_resolution_roots_for_hive`.
- SRS FR-2.7 (application correlation) → `ConfidenceLevel` and `CONFIDENCE_LEVELS` match the model's `Confidence` enum values exactly.
- SRS FR-4.3 (Documents baseline resolution) → `PROFILE_RESOLUTION_ROOTS` includes `user_shell_folders` and `shell_folders` for shell-folder resolution.
- SRS FR-4.9 (confidence model) → `default_confidence` field on `EvidenceRootSpec` provides deterministic per-root confidence defaults.
- SRS FR-6.1/FR-6.3 (report export/import) → `EVIDENCE_LOCATIONS_VERSION` is persisted in `SCAN_SESSION.scan_options_json` and stamped into exported reports.
- SRS FR-7.1/FR-7.2 (evidence transparency / graceful failure) → defensive parsing contract ensures unknown types/hives degrade gracefully with warnings, never crashes.
- SRS Appendix A.2 (SYSTEM control-set resolution) → `SYSTEM_SELECT_PATH`, `SELECT_VALUE_NAMES`, `CONTROL_SET_PRIORITY_ORDER`, and `CONTROL_SET_KEY_PATTERN` encode the deterministic resolution policy.
- SRS Appendix A.3 (UserAssist) → `user_assist` root has `usage_evidence_only=True` and `decode_rot13=True`.
- SRS Appendix A.6 (profile-resolution locations) → `PROFILE_RESOLUTION_ROOTS` enumerates `profile_list`, `user_shell_folders`, and `shell_folders`, intentionally excluded from `REGISTRY_EVIDENCE_ROOTS` so they are not emitted as application evidence.
- ADR-6 (evidence-centric enumeration) → this module provides the configuration surface that enables evidence-first discovery; the registry parser iterates `REGISTRY_EVIDENCE_ROOTS` generically.
- ADR-13 (bounded evidence admission) → `RegistryBounds` provides deterministic, documented bounds.
- ADR-17 (tiered contract governance) → this sheet is Tier 0 (frozen baseline); any change requires coordinator + reviewer approval with written rationale in this §9.
- ADR-19 (regipy exception taxonomy) → this module does not catch exceptions; it provides the configuration that the registry parser uses to decide whether to warn or escalate.
- README §5.4–§5.6 (control-set resolution, WOW64 handling, UserAssist ROT13) → all encoded as inert data in this module.