# Module Contract: `src/models.py` — v1.0.0 FROZEN (Tier 0)

Frozen: 2026-11-13 · Approver: Project Coordinator ______
Baseline: the as-implemented Phase 1 surface (verified against
`docs/api-ref/models.md` produced by `gen_api.py` from the shipped module).
Change control: `docs/contracts/README.md`, Freeze Rules 1–5. Any change to
this surface is an amendment: version bump + §9 rationale + coordinator and
reviewer sign-off. `SCHEMA_VERSION` moves only if DDD tables or the DDD §8
report structure change — runtime-only types do not move it.

## 1. Public API (machine-checked by `tests/test_contracts.py`)

Checked surface: names, enum member sets and values, dataclass field-name
sets and types, and module-function signatures. Dataclass-generated dunders
and method bodies are non-contract (§7).

```python
# ── Module constants ────────────────────────────────────────────────────
SCHEMA_VERSION: str

# ── Enumerations ────────────────────────────────────────────────────────
class AcquisitionMethod(StrEnum):
    NTFS3G_RO = 'ntfs3g_ro'; NTFSLS_MANIFEST = 'ntfsls_manifest'

class Confidence(StrEnum):
    LOW = 'Low'; MEDIUM = 'Medium'; HIGH = 'High'

class DiscoveryMethod(StrEnum):
    REGISTRY = 'registry'; FILESYSTEM = 'filesystem'; MANIFEST = 'manifest'; PORTABLE = 'portable'; CORRELATED = 'correlated'

class FingerprintStatus(StrEnum):
    REGISTERED = 'Registered'; PARTIALLY_REGISTERED = 'PartiallyRegistered'; PORTABLE = 'Portable'; ORPHANED = 'Orphaned'; UNKNOWN = 'Unknown'

class HiveType(StrEnum):
    SOFTWARE = 'SOFTWARE'; SYSTEM = 'SYSTEM'; DEFAULT = 'DEFAULT'; NTUSER = 'NTUSER'; USRCLASS = 'USRCLASS'

class Relevance(StrEnum):
    PRIMARY = 'primary'; SUPPORTING = 'supporting'; WEAK = 'weak'

class SessionMode(StrEnum):
    ACTIVE = 'active'; TRIAGE = 'triage'

class SessionStatus(StrEnum):
    PENDING = 'pending'; RUNNING = 'running'; COMPLETED = 'completed'; FAILED = 'failed'; CANCELLED = 'cancelled'

class SeverityLevel(StrEnum):
    LOW = 'Low'; MEDIUM = 'Medium'; HIGH = 'High'

class SourceRole(StrEnum):
    WINDOWS_OS = 'windows_os'; SECONDARY_DATA = 'secondary_data'

class SourceStatus(StrEnum):
    PENDING = 'pending'; READY = 'ready'; ERROR = 'error'; COMPLETE = 'complete'

class SourceType(StrEnum):
    MOUNTED_BLOCK_DEVICE = 'mounted_block_device'; MANIFEST_FILE = 'manifest_file'

class WarningCategory(StrEnum):
    ACQUISITION = 'acquisition'; REGISTRY = 'registry'; MANIFEST = 'manifest'; FILESYSTEM = 'filesystem'; CORRELATION = 'correlation'; HEURISTIC = 'heuristic'; IO = 'io'; REPORT = 'report'; GENERAL = 'general'

class WarningSeverity(StrEnum):
    INFO = 'info'; WARNING = 'warning'; CRITICAL = 'critical'

class RegistryValueType(StrEnum):
    NONE = 'REG_NONE'; STRING = 'REG_SZ'; EXPAND_STRING = 'REG_EXPAND_SZ'; MULTI_STRING = 'REG_MULTI_SZ'; DWORD = 'REG_DWORD'; QWORD = 'REG_QWORD'; BINARY = 'REG_BINARY'

class IdentityBasis(StrEnum):
    PRODUCT_CODE = 'product_code'; UNINSTALL_KEY = 'uninstall_key'; INSTALL_PATH = 'install_path'
    NAME_PUBLISHER_VERSION = 'name_publisher_version'; PORTABLE_DIRECTORY = 'portable_directory'
    MANIFEST_DIRECTORY = 'manifest_directory'; EXECUTABLE_BUNDLE = 'executable_bundle'; FALLBACK = 'fallback'

class EvidenceType(StrEnum):
    REGISTRY_UNINSTALL = 'REGISTRY_UNINSTALL'; REGISTRY_WOW64_UNINSTALL = 'REGISTRY_WOW64_UNINSTALL'; REGISTRY_APP_PATH = 'REGISTRY_APP_PATH'
    REGISTRY_MSI_PRODUCT = 'REGISTRY_MSI_PRODUCT'; REGISTRY_MSI_USER_DATA = 'REGISTRY_MSI_USER_DATA'; REGISTRY_MSI_UPGRADE_CODE = 'REGISTRY_MSI_UPGRADE_CODE'
    REGISTRY_SHARED_DLL = 'REGISTRY_SHARED_DLL'; REGISTRY_RUN_KEY = 'REGISTRY_RUN_KEY'; REGISTRY_SERVICE = 'REGISTRY_SERVICE'
    REGISTRY_APPCOMPAT_CACHE = 'REGISTRY_APPCOMPAT_CACHE'; REGISTRY_USERASSIST = 'REGISTRY_USERASSIST'; REGISTRY_MUICACHE = 'REGISTRY_MUICACHE'
    REGISTRY_COM_CLSID = 'REGISTRY_COM_CLSID'; REGISTRY_PROGID = 'REGISTRY_PROGID'; REGISTRY_FILE_ASSOCIATION = 'REGISTRY_FILE_ASSOCIATION'
    REGISTRY_APPX = 'REGISTRY_APPX'; REGISTRY_SHELL_EXTENSION = 'REGISTRY_SHELL_EXTENSION'; REGISTRY_SHELL_FOLDER = 'REGISTRY_SHELL_FOLDER'
    REGISTRY_USER_PATH_HINT = 'REGISTRY_USER_PATH_HINT'
    FILE_EXECUTABLE = 'FILE_EXECUTABLE'; FILE_PORTABLE_LAYOUT = 'FILE_PORTABLE_LAYOUT'; FILE_SHORTCUT = 'FILE_SHORTCUT'; FILE_APPX_MANIFEST = 'FILE_APPX_MANIFEST'; FILE_SOURCE_CODE_DIR = 'FILE_SOURCE_CODE_DIR'
    MANIFEST_ENTRY = 'MANIFEST_ENTRY'

class FindingLocationCategory(StrEnum):
    DOCUMENTS = 'DOCUMENTS'; DESKTOP = 'DESKTOP'; DOWNLOADS = 'DOWNLOADS'; PICTURES = 'PICTURES'; MUSIC = 'MUSIC'; VIDEOS = 'VIDEOS'; ONEDRIVE = 'ONEDRIVE'
    INSTALL_DIR = 'INSTALL_DIR'; APPDATA_ROAMING = 'APPDATA_ROAMING'; APPDATA_LOCAL = 'APPDATA_LOCAL'; APPDATA_LOCALLOW = 'APPDATA_LOCALLOW'
    SAVED_GAMES = 'SAVED_GAMES'; VIRTUALSTORE = 'VIRTUALSTORE'; PROGRAMDATA = 'PROGRAMDATA'; SECONDARY_DRIVE = 'SECONDARY_DRIVE'
    PORTABLE_DATA_DIR = 'PORTABLE_DATA_DIR'; SOURCE_CODE = 'SOURCE_CODE'; USER_PROFILE_OTHER = 'USER_PROFILE_OTHER'; UNKNOWN = 'UNKNOWN'

# ── Value/metadata primitives ───────────────────────────────────────────
@dataclass(frozen=True)
class RegistryValue:
    name: str = ""; value_type: RegistryValueType = RegistryValueType.STRING; data: str | tuple[str, ...] | int | bytes | None = None

@dataclass(frozen=True)
class BlockDevice:
    device_path: str; name: str; dev_type: str
    fs_type: str | None = None; size_bytes: int | None = None; label: str | None = None; uuid: str | None = None
    mount_points: tuple[str, ...] = (); transport: str | None = None; part_label: str | None = None; child_count: int = 0
    @property
    def is_mounted(self) -> bool: ...
    @property
    def is_ntfs_partition(self) -> bool: ...
    @property
    def is_ntfs_candidate(self) -> bool: ...

# ── Persistence DTOs ────────────────────────────────────────────────────
@dataclass(frozen=True)
class ScanSession:
    session_id: str; mode: SessionMode = SessionMode.ACTIVE; status: SessionStatus = SessionStatus.PENDING
    schema_version: str = SCHEMA_VERSION; created_at: str = ...; scan_options_json: str | None = None
    @classmethod
    def new_active(cls, options: ScanOptions | None = None) -> ScanSession: ...
    def options(self) -> ScanOptions | None: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ScanSession: ...

@dataclass(frozen=True)
class ScanOptions:
    evidence_locations_version: str; heuristic_patterns_version: str
    max_evidence_rows: int = 250000; max_findings: int = 5000; max_manifest_entries: int = 500000
    max_evidence_per_registry_root: int = 5000; max_registry_subkeys_per_key: int = 2000
    max_registry_values_per_key: int = 2000; max_filesystem_entries_per_source: int = 100000
    max_directory_depth: int = 12; max_directory_entries: int = 20000
    include_wow64: bool = True; include_user_hives: bool = True
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, text: str | None) -> ScanOptions: ...

@dataclass(frozen=True)
class SourceRecord:
    source_id: str; session_id: str; source_type: SourceType; source_role: SourceRole
    acquisition_method: AcquisitionMethod; status: SourceStatus
    origin_device_path: str | None = None; manifest_path: str | None = None; mount_point: str | None = None
    fs_type: str | None = None; label: str | None = None; uuid: str | None = None; size_bytes: int | None = None
    read_only: bool = True; warnings_json: str | None = None; logical_drive: str | None = None
    @classmethod
    def from_prepared(cls, prepared: PreparedSource, status: SourceStatus = SourceStatus.READY) -> SourceRecord: ...
    def with_logical_drive(self, logical_drive: str) -> SourceRecord: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> SourceRecord: ...

@dataclass(frozen=True)
class UserProfile:
    session_id: str; source_id: str
    username: str | None = None; sid: str | None = None
    profile_path: str | None = None; normalized_profile_path: str | None = None
    ntuser_path: str | None = None; usrclass_path: str | None = None
    documents_path: str | None = None; desktop_path: str | None = None; downloads_path: str | None = None
    pictures_path: str | None = None; music_path: str | None = None; videos_path: str | None = None
    appdata_local_path: str | None = None; appdata_roaming_path: str | None = None
    appdata_locallow_path: str | None = None; saved_games_path: str | None = None
    is_default_profile: bool = False; is_system_profile: bool = False
    parse_warnings_json: str | None = None; profile_id: str | None = None
    @property
    def documents_baseline_known(self) -> bool: ...
    def parse_warnings(self) -> tuple[str, ...]: ...
    def with_id(self, profile_id: str) -> UserProfile: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> UserProfile: ...

@dataclass(frozen=True)
class Evidence:
    session_id: str; source_id: str; evidence_type: EvidenceType
    confidence: Confidence = Confidence.MEDIUM
    hive_file_path: str | None = None; root_hive: str | None = None
    key_path: str | None = None; value_name: str | None = None
    registry_value: RegistryValue | None = None; value_data: str | None = None
    user_sid: str | None = None; file_path: str | None = None; normalized_path: str | None = None
    product_code: str | None = None; parse_warning: str | None = None; raw_json: str | None = None
    evidence_id: str | None = None; evidence_hash: str = ""
    def with_id(self, evidence_id: str) -> Evidence: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Evidence: ...

ManifestEvidence = Evidence  # Type alias, not a subclass

@dataclass(frozen=True)
class CorrelatedApplication:
    session_id: str; source_id: str
    identity_basis: IdentityBasis; identity_key: str; display_name: str
    discovery_method: DiscoveryMethod; fingerprint_status: FingerprintStatus
    evidence_confidence: Confidence
    publisher: str | None = None; version: str | None = None; install_date: str | None = None
    architecture: str | None = None; install_path: str | None = None; normalized_install_path: str | None = None
    portable_score: int | None = None; notes_json: str | None = None
    created_at: str = ...; app_id: str | None = None; identity_hash: str = ""
    def notes(self) -> dict[str, Any]: ...
    def with_id(self, app_id: str) -> CorrelatedApplication: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CorrelatedApplication: ...

@dataclass(frozen=True)
class ApplicationEvidenceLink:
    app_id: str; evidence_id: str; relevance: Relevance
    created_at: str = ...; link_id: int | None = None
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ApplicationEvidenceLink: ...

@dataclass(frozen=True)
class UserDataFinding:
    session_id: str; source_id: str; path: str; normalized_path: str
    location_category: FindingLocationCategory
    severity_level: SeverityLevel; confidence: Confidence; rationale: str
    app_id: str | None = None; profile_id: str | None = None
    inside_documents: bool | None = None; documents_root: str | None = None
    owner_username: str | None = None; nomenclature_match: str | None = None; extension_match: str | None = None
    file_count: int | None = None; total_size_bytes: int | None = None
    created_at: str = ...
    user_confirmed: bool | None = None; user_notes: str | None = None
    finding_id: str | None = None
    def with_id(self, finding_id: str) -> UserDataFinding: ...
    def with_triage(self, user_confirmed: bool, user_notes: str | None) -> UserDataFinding: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> UserDataFinding: ...

@dataclass(frozen=True)
class WarningRecord:
    session_id: str; category: WarningCategory; severity: WarningSeverity
    message: str; source_id: str | None = None; created_at: str = ...; warning_id: str | None = None
    def with_id(self, warning_id: str) -> WarningRecord: ...
    def to_row(self) -> dict[str, Any]: ...
    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> WarningRecord: ...

# ── Pipeline working types ──────────────────────────────────────────────
@dataclass(frozen=True)
class PreparedSource:
    source_id: str; session_id: str; source_type: SourceType; source_role: SourceRole; logical_drive: str
    origin_device_path: str | None = None; mount_point: str | None = None; manifest_path: str | None = None
    fs_type: str | None = None; label: str | None = None; uuid: str | None = None; size_bytes: int | None = None
    acquisition_method: AcquisitionMethod = AcquisitionMethod.NTFS3G_RO; read_only: bool = True

@dataclass(frozen=True)
class PersistedEvidence:
    evidence_id: str; source_id: str; evidence_type: EvidenceType
    display_name: str; confidence: Confidence = Confidence.MEDIUM
    key_path: str | None = None; file_path: str | None = None; normalized_path: str | None = None
    product_code: str | None = None; install_path: str | None = None; value_data: str | None = None
    user_sid: str | None = None
    @classmethod
    def from_evidence(cls, evidence: Evidence, evidence_id: str) -> PersistedEvidence: ...

@dataclass(frozen=True)
class PortableCandidate:
    source_id: str; candidate_path: str; normalized_path: str; display_name: str
    basis: IdentityBasis; confidence: Confidence; score: int; rationale: str
    evidence_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class HiveFile:
    hive_type: HiveType; logical_path: str; mount_path: Path; size_bytes: int | None = None; readable: bool = True

@dataclass(frozen=True)
class MachineHiveSet:
    software: HiveFile | None = None; system: HiveFile | None = None; default: HiveFile | None = None
    warnings: tuple[str, ...] = ()
    @property
    def missing_required(self) -> tuple[HiveType, ...]: ...

@dataclass(frozen=True)
class UserHiveSet:
    profile_id: str | None = None; username: str | None = None; sid: str | None = None
    is_default_profile: bool = False; is_system_profile: bool = False
    ntuser: HiveFile | None = None; usrclass: HiveFile | None = None; warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class HiveSet:
    machine: MachineHiveSet; users: tuple[UserHiveSet, ...] = ()
    @property
    def user_count(self) -> int: ...

@dataclass(frozen=True)
class RegistryParseOptions:
    include_wow64: bool = True; include_user_hives: bool = True; include_appcompat_cache: bool = True
    decode_userassist_rot13: bool = True
    max_evidence_total: int | None = None; max_evidence_per_root: int | None = None
    max_subkeys_per_key: int | None = None; max_values_per_key: int | None = None
    control_set_override: str | None = None

@dataclass(frozen=True)
class ManifestGenerationResult:
    ok: bool; device_path: str; output_path: Path
    entry_count: int = 0; truncated: bool = False; duration_seconds: float = 0.0; error: str | None = None

@dataclass(frozen=True)
class ScanSummary:
    evidence_count: int = 0; application_count: int = 0; finding_count: int = 0
    warning_count: int = 0; profile_count: int = 0; portable_candidate_count: int = 0

@dataclass(frozen=True)
class SessionBundle:
    session: ScanSession
    sources: tuple[SourceRecord, ...] = (); user_profiles: tuple[UserProfile, ...] = ()
    applications: tuple[CorrelatedApplication, ...] = (); evidence: tuple[Evidence, ...] = ()
    app_evidence_links: tuple[ApplicationEvidenceLink, ...] = ()
    user_data_findings: tuple[UserDataFinding, ...] = (); warnings: tuple[WarningRecord, ...] = ()

# ── Worker → UI event vocabulary ──────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class UiEvent:
    event_id: str = ...; emitted_at: str = ...; source_id: str | None = None

class ProgressEvent(UiEvent):
    stage: str; completed: int = 0; total: int | None = None; detail: str | None = None

class SourcePreparedEvent(UiEvent):
    source: SourceRecord

class EvidenceBatchPersistedEvent(UiEvent):
    batch_size: int; total_persisted: int; stage: str = "evidence"

class UserProfileParsedEvent(UiEvent):
    profile: UserProfile; total_parsed: int = 0

class PortableCandidateEvent(UiEvent):
    candidate: PortableCandidate; total_found: int = 0

class ApplicationCorrelatedEvent(UiEvent):
    application: CorrelatedApplication; total_correlated: int = 0

class UserDataFindingEvent(UiEvent):
    finding: UserDataFinding; total_found: int = 0

class WarningEvent(UiEvent):
    warning: WarningRecord

class ScanCompletedEvent(UiEvent):
    session_id: str; summary: ScanSummary

class ScanFailedEvent(UiEvent):
    session_id: str | None; message: str; summary: ScanSummary | None = None

class CriticalIoFailureEvent(UiEvent):
    message: str; device_path: str | None = None

class ErrorEvent(UiEvent):
    message: str; category: WarningCategory = WarningCategory.GENERAL

# ── Module functions ────────────────────────────────────────────────────
def new_id() -> str: ...
def utc_now_iso() -> str: ...
def compute_evidence_hash(*, source_id: str, evidence_type: EvidenceType | str,
    hive_file_path: str | None = None, root_hive: str | None = None,
    key_path: str | None = None, value_name: str | None = None,
    value_data_hash: str | None = None, user_sid: str | None = None,
    normalized_path: str | None = None, product_code: str | None = None) -> str: ...
def value_data_hash(value: RegistryValue | None) -> str: ...
def compute_identity_hash(source_id: str, identity_basis: IdentityBasis | str,
    identity_key: str) -> str: ...
def name_publisher_version_key(display_name: str, publisher: str | None,
    version: str | None) -> str: ...
def safe_value_text(value: RegistryValue | None) -> str: ...
def canon_lower_path(value: str | None) -> str: ...
def canon_source_relative_path(value: str | None) -> str: ...
def canonical_path_structure(value: str | None) -> str: ...
def canonical_product_code(value: str | None) -> str: ...
```

## 2. Semantic invariants
1. Every DTO is a frozen dataclass. Mutation is expressed as `with_*` methods returning new instances; inputs are never modified.
2. `UiEvent` base fields are keyword-only by construction, so subclasses may declare positional payload fields safely.
3. Hash functions implement DDD §5/§6 exactly: SHA-256, UTF-8, ASCII `0x1F` joins, documented canonical field order, empty string for absent fields. Determinism is a contract property — identical inputs always yield identical hashes.
4. `Evidence.__post_init__` computes `evidence_hash` when empty; `CorrelatedApplication.__post_init__` computes `identity_hash` and canonicalizes `identity_key` per basis (DDD §6).
5. `SourceRecord.__post_init__` enforces the DDD `SCAN_SOURCE` type/acquisition pairing CHECK in memory.
6. ID fields (`*_id: str | None`) are assigned by the persistence layer via `new_id()`; `with_id()` returns the persisted copy. DTOs constructed by ingestion modules may carry `None`.
7. `to_row()` outputs key sets exactly matching DDD §4 column names; enums serialize as their string values; booleans as 0/1 where the DDD column is INTEGER.
8. Timestamps are UTC ISO-8601 via `utc_now_iso()`; IDs are UUID-4 via `new_id()`.
9. Enum values mirror DDD §4 CHECK constraints verbatim. Adding, removing, or renaming a member is a Tier 0 amendment and, where the member is persisted, a `SCHEMA_VERSION` decision.

## 3. Error contract
1. Construction-time validation (`__post_init__`, pairing checks, basis/score bounds) raises `ValueError` with an actionable message.
2. Canonicalization and hash helpers are total for documented inputs; defensive coercers fall back to safe defaults and never raise for stored-data shapes.
3. This module performs no I/O and raises no I/O exceptions. It never emits events or warnings; it only defines their types.

## 4. Event vocabulary
The `UiEvent` subclasses above are the complete worker → UI vocabulary. Emission is the coordinator's responsibility (SDD §2.19); consumption is the UI's (SDD §2.20, UIDD §10). Adding an event type is a Tier 0 amendment and obligates a review of the coordinator emission map and the UI dispatch branches.

## 5. I/O surface
None. `models.py` shall never touch the filesystem, network, subprocesses, or the database. This invariant is part of the freeze: it is what makes DTOs safe to construct on any thread.

## 6. Threading
All DTOs and events are frozen and hashable; crossing thread boundaries via the coordinator's queue is their intended use (ADR-4). No internal mutable state exists.

## 7. Non-contract internals (free to vary)
Underscore-prefixed helpers; dataclass-generated dunders; JSON column encoding details inside `to_row()`/`options()`/`parse_warnings()` (output shape is contract, internals are not); enum member declaration order (values are contract, order is not); docstring wording.

## 8. Acceptance fixtures
`tests/test_models.py` (no root, no drives — NFR-10): hash determinism and canonicalization vectors (DDD §5/§6); pairing validation; `to_row()` column parity with DDD §4; `with_*` immutability; enum vocabulary parity with DDD §4 CHECKs; event base-field defaults.

## 9. Amendment record
| Version | Date | Change | Rationale | Approved by |
|---|---|---|---|---|
| 1.0.0 | 2026-11-13 | Initial freeze of the as-implemented Phase 1 surface | Phase 1 concluded; rolling-freeze governance begins | Coordinator + Reviewer |
