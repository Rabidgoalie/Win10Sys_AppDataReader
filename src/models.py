"""Shared data contracts for the Windows 10 Disaster Recovery application.

Phase 1 deliverables (README roadmap):
    * DTO contracts (SDD §2.3)
    * deterministic hash contracts (DDD §5, §6)
    * database entity mapping surfaces (DDD §3, §4)

Safety posture
--------------
This module is deliberately *inert*: it performs no file, database, network,
or subprocess I/O of any kind, so it cannot write to a scanned source
(core zero-write directive).  All acquisition happens in
:mod:`src.mount_manager`, and all persistence happens in :mod:`src.db`.

DTO discipline
--------------
* Every DTO is a ``frozen`` + ``slots`` dataclass: an immutable value object
  that is safe to share across worker threads and across the worker -> UI
  ``queue.Queue`` boundary (SDD §5 "Observer / Queue Pattern").
* Controlled mutation (for example, attaching a database-issued identifier)
  is performed with ``dataclasses.replace`` through ``with_*`` helpers,
  never in place.  This keeps objects safe to share while a scan is running.
* Database rows are never exposed to UI widgets: ``src.db`` hydrates rows
  into these DTOs through the ``from_row`` classmethods, and the UI consumes
  only DTOs and typed :class:`UiEvent` subclasses (SDD §5 "DTO Boundaries").
* Canonical path fields hold logical Windows-style paths. Raw Linux mount
  paths appear only in transient acquisition fields (``mount_point``,
  ``HiveFile.mount_path``) and are never stored as canonical evidence paths
  (SDD §2.4, DDD §4).
* Registry *values* are metadata (strings, numbers, short binary blobs),
  never file contents (SDD §4.6 / README §5.14).

Hash determinism
----------------
``compute_evidence_hash`` and ``compute_identity_hash`` implement DDD §5 and
§6 exactly: UTF-8 encoding, ASCII unit separator (``0x1F``) field join,
per-field case rules, and SHA-256.  All canonicalization helpers are
idempotent, so re-computing a hash over already-canonical input (as happens
during report hydration) always yields the same digest.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

__all__ = [
    # Constants / utilities
    "SCHEMA_VERSION",
    "new_id",
    "utc_now_iso",
    "canonical_path_structure",
    "canon_lower_path",
    "canon_source_relative_path",
    "canonical_product_code",
    "safe_value_text",
    "value_data_hash",
    "compute_evidence_hash",
    "compute_identity_hash",
    # Domain enums
    "SessionMode",
    "SessionStatus",
    "SourceType",
    "SourceRole",
    "AcquisitionMethod",
    "SourceStatus",
    "EvidenceType",
    "IdentityBasis",
    "FingerprintStatus",
    "Confidence",
    "DiscoveryMethod",
    "Relevance",
    "SeverityLevel",
    "FindingLocationCategory",
    "WarningCategory",
    "WarningSeverity",
    "HiveType",
    "RegistryValueType",
    # Acquisition / ingestion DTOs
    "BlockDevice",
    "PreparedSource",
    "SourceRecord",
    "RegistryValue",
    "Evidence",
    "ManifestEvidence",
    "PersistedEvidence",
    "PortableCandidate",
    "HiveFile",
    "MachineHiveSet",
    "UserHiveSet",
    "HiveSet",
    "RegistryParseOptions",
    "ManifestGenerationResult",
    # Correlation / classification DTOs
    "UserProfile",
    "CorrelatedApplication",
    "ApplicationEvidenceLink",
    "UserDataFinding",
    "WarningRecord",
    # Session / reporting DTOs
    "ScanOptions",
    "ScanSession",
    "ScanSummary",
    "SessionBundle",
    # Typed UI events (SDD §2.19)
    "UiEvent",
    "ProgressEvent",
    "SourcePreparedEvent",
    "EvidenceBatchPersistedEvent",
    "UserProfileParsedEvent",
    "PortableCandidateEvent",
    "ApplicationCorrelatedEvent",
    "UserDataFindingEvent",
    "WarningEvent",
    "ScanCompletedEvent",
    "ScanFailedEvent",
    "CriticalIoFailureEvent",
    "ErrorEvent",
]


# ---------------------------------------------------------------------------
# Constants and small utilities
# ---------------------------------------------------------------------------

SCHEMA_VERSION: str = "1.0.0"
"""Version string for the database/report schema (DDD §1, §8).

Reports validate against this exact value before hydration (DDD §9)."""

_UNIT_SEPARATOR: str = "\x1F"
"""ASCII unit separator.  DDD §5/§6 mandate this exact byte as the field
join character inside both hash payloads; it never appears in the hashed
fields themselves (paths, keys, and identifiers are trimmed of it), so the
digest is unambiguous."""

_DRIVE_PREFIX_RE = re.compile(r"^[a-z][0-9]*:\\")
"""Matches a lowercase drive prefix (``c:\\``, ``s1:\\``) in canonical paths."""

_PATH_SEPARATOR_RE = re.compile(r"[\\/]+")
_GUID_DASHED_RE = re.compile(
    r"^\{?([0-9A-Fa-f]{8})-([0-9A-Fa-f]{4})-([0-9A-Fa-f]{4})-"
    r"([0-9A-Fa-f]{4})-([0-9A-Fa-f]{12})\}?$"
)
_GUID_BARE_RE = re.compile(r"^[0-9A-Fa-f]{32}$")
_LOGICAL_DRIVE_RE = re.compile(r"^[A-Z][0-9]*:$")
"""Valid logical drives: ``C:`` (primary Windows source) and ``S1:``,
``S2:``, ... (secondary sources, in user addition order — SDD §2.4)."""


def new_id() -> str:
    """Return a fresh UUID-4 identifier.

    ``str(uuid.uuid4())`` is exactly 36 characters, matching every
    ``VARCHAR(36)`` identifier column in the DDD.
    """
    return str(uuid.uuid4())


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (DDD §1: UTC timestamps)."""
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _as_str_or_none(value: Any) -> str | None:
    """Defensive coercion for optional text columns."""
    if value is None:
        return None
    return str(value)


def _as_int_or_none(value: Any) -> int | None:
    """Defensive coercion for optional integer columns."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool_or_none(value: Any) -> bool | None:
    """Defensive coercion for ``INTEGER`` 0/1/NULL boolean columns."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "t", "yes")
    return bool(value)


def _coerce_enum(enum_cls: type[StrEnum], value: Any, fallback: StrEnum) -> StrEnum:
    """Coerce a stored string into an enum, falling back safely.

    ``src.db`` is the only caller.  The fallbacks are chosen so a corrupted
    cell degrades to a conservative, user-visible state instead of crashing
    the scan (SDD §4.2 defensive posture).
    """
    if value is None:
        return fallback
    try:
        return enum_cls(str(value))
    except ValueError:
        return fallback


def _load_json_list(text: str | None) -> tuple[str, ...]:
    """Parse a JSON list column defensively; malformed input yields ``()``."""
    if not text:
        return ()
    try:
        loaded = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ()
    if not isinstance(loaded, list):
        return ()
    return tuple(str(item) for item in loaded)


# ---------------------------------------------------------------------------
# Domain enums (exact DDD CHECK values)
# ---------------------------------------------------------------------------

class SessionMode(StrEnum):
    ACTIVE = "active"
    TRIAGE = "triage"


class SessionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceType(StrEnum):
    MOUNTED_BLOCK_DEVICE = "mounted_block_device"
    MANIFEST_FILE = "manifest_file"


class SourceRole(StrEnum):
    WINDOWS_OS = "windows_os"
    SECONDARY_DATA = "secondary_data"


class AcquisitionMethod(StrEnum):
    NTFS3G_RO = "ntfs3g_ro"
    NTFLS_MANIFEST = "ntfsls_manifest"


class SourceStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    ERROR = "error"
    COMPLETE = "complete"


class EvidenceType(StrEnum):
    """Every ``DISCOVERY_EVIDENCE.evidence_type`` value (DDD §4)."""

    REGISTRY_UNINSTALL = "REGISTRY_UNINSTALL"
    REGISTRY_WOW64_UNINSTALL = "REGISTRY_WOW64_UNINSTALL"
    REGISTRY_APP_PATH = "REGISTRY_APP_PATH"
    REGISTRY_MSI_PRODUCT = "REGISTRY_MSI_PRODUCT"
    REGISTRY_MSI_USER_DATA = "REGISTRY_MSI_USER_DATA"
    REGISTRY_MSI_UPGRADE_CODE = "REGISTRY_MSI_UPGRADE_CODE"
    REGISTRY_SHARED_DLL = "REGISTRY_SHARED_DLL"
    REGISTRY_RUN_KEY = "REGISTRY_RUN_KEY"
    REGISTRY_SERVICE = "REGISTRY_SERVICE"
    REGISTRY_APPCOMPAT_CACHE = "REGISTRY_APPCOMPAT_CACHE"
    REGISTRY_USERASSIST = "REGISTRY_USERASSIST"
    REGISTRY_MUICACHE = "REGISTRY_MUICACHE"
    REGISTRY_COM_CLSID = "REGISTRY_COM_CLSID"
    REGISTRY_PROGID = "REGISTRY_PROGID"
    REGISTRY_FILE_ASSOCIATION = "REGISTRY_FILE_ASSOCIATION"
    REGISTRY_APPX = "REGISTRY_APPX"
    REGISTRY_SHELL_EXTENSION = "REGISTRY_SHELL_EXTENSION"
    REGISTRY_SHELL_FOLDER = "REGISTRY_SHELL_FOLDER"
    REGISTRY_USER_PATH_HINT = "REGISTRY_USER_PATH_HINT"
    FILE_EXECUTABLE = "FILE_EXECUTABLE"
    FILE_PORTABLE_LAYOUT = "FILE_PORTABLE_LAYOUT"
    FILE_SHORTCUT = "FILE_SHORTCUT"
    FILE_APPX_MANIFEST = "FILE_APPX_MANIFEST"
    FILE_SOURCE_CODE_DIR = "FILE_SOURCE_CODE_DIR"
    MANIFEST_ENTRY = "MANIFEST_ENTRY"


class IdentityBasis(StrEnum):
    """``APP_RECORD.identity_basis`` values (DDD §4, §6)."""

    PRODUCT_CODE = "product_code"
    UNINSTALL_KEY = "uninstall_key"
    INSTALL_PATH = "install_path"
    NAME_PUBLISHER_VERSION = "name_publisher_version"
    PORTABLE_DIRECTORY = "portable_directory"
    MANIFEST_DIRECTORY = "manifest_directory"
    EXECUTABLE_BUNDLE = "executable_bundle"
    FALLBACK = "fallback"


class FingerprintStatus(StrEnum):
    REGISTERED = "Registered"
    PARTIALLY_REGISTERED = "PartiallyRegistered"
    PORTABLE = "Portable"
    ORPHANED = "Orphaned"
    UNKNOWN = "Unknown"


class Confidence(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class DiscoveryMethod(StrEnum):
    REGISTRY = "registry"
    FILESYSTEM = "filesystem"
    MANIFEST = "manifest"
    PORTABLE = "portable"
    CORRELATED = "correlated"


class Relevance(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    WEAK = "weak"


class SeverityLevel(StrEnum):
    """``USER_DATA_FINDING.severity_level`` values (DDD §4)."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class FindingLocationCategory(StrEnum):
    """``USER_DATA_FINDING.location_category`` values (DDD §4)."""

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
    # Covers Visual Studio (source, source\repos), IntelliJ (IdeaProjects),
    # Rider (RiderProjects), Eclipse (workspace/eclipse-workspace),
    # NetBeans (NetBeansProjects), VS Code/generic (projects, code, dev).
    SOURCE_CODE = "SOURCE_CODE"
    USER_PROFILE_OTHER = "USER_PROFILE_OTHER"
    UNKNOWN = "UNKNOWN"


class WarningCategory(StrEnum):
    ACQUISITION = "acquisition"
    REGISTRY = "registry"
    MANIFEST = "manifest"
    FILESYSTEM = "filesystem"
    CORRELATION = "correlation"
    HEURISTIC = "heuristic"
    IO = "io"
    REPORT = "report"
    GENERAL = "general"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HiveType(StrEnum):
    SOFTWARE = "SOFTWARE"
    SYSTEM = "SYSTEM"
    DEFAULT = "DEFAULT"
    NTUSER = "NTUSER"
    USRCLASS = "USRCLASS"


class RegistryValueType(StrEnum):
    """Registry value types the parser can represent as metadata only."""

    NONE = "REG_NONE"
    STRING = "REG_SZ"
    EXPAND_STRING = "REG_EXPAND_SZ"
    MULTI_STRING = "REG_MULTI_SZ"
    DWORD = "REG_DWORD"
    QWORD = "REG_QWORD"
    BINARY = "REG_BINARY"


# ---------------------------------------------------------------------------
# Path canonicalization (hash-grade; display-grade lives in pathnorm.py)
# ---------------------------------------------------------------------------

def canonical_path_structure(value: str | None) -> str:
    """Normalize path *structure only* (separators), never case.

    * forward slashes become backslashes;
    * runs of separators collapse to a single backslash;
    * leading/trailing separators are removed, preserving drive roots
      (``C:\\`` -> ``C:``);
    * UNC shares keep their leading double separator (``\\\\server\\share``),
      per SDD §2.4 ("UNC paths preserved, treated as unresolved when source
      mapping is impossible").

    This is intentionally *independent* of ``src.pathnorm``: hash inputs must
    stay byte-stable even if display-level normalization rules evolve later.
    """
    if value is None:
        return ""
    text = value.strip().replace("/", "\\")
    text = _PATH_SEPARATOR_RE.sub("\\", text)
    if text.startswith("\\"):
        return "\\\\" + text.lstrip("\\")
    return text.strip("\\")


def canon_lower_path(value: str | None) -> str:
    """Canonical *hash* form of a Windows-style path (DDD §5): structure
    canonicalization plus lowercasing."""
    return canonical_path_structure(value).lower()


def canon_source_relative_path(value: str | None) -> str:
    """Source-relative logical path, lowercased (DDD §5 field 3).

    Accepts either an already source-relative path (``windows\\system32``) or
    a logical drive path (``c:\\windows\\system32``) and strips the drive
    prefix, so both inputs hash identically.
    """
    text = canon_lower_path(value)
    match = _DRIVE_PREFIX_RE.match(text)
    if match:
        text = text[match.end():].strip("\\")
    return text


def canonical_product_code(value: str | None) -> str:
    """Canonical product code (DDD §5 field 10).

    GUID identifiers (braced or not, any case, dashed or bare 32-hex) become
    uppercase dashed GUIDs.  Non-GUID identifiers are preserved as-is
    (trimmed), exactly as the DDD permits.
    """
    if value is None:
        return ""
    text = value.strip()
    if not text:
        return ""
    dashed = _GUID_DASHED_RE.match(text)
    if dashed:
        return "-".join(part.upper() for part in dashed.groups())
    if _GUID_BARE_RE.match(text):
        hexdigits = text.upper()
        return "-".join(
            (
                hexdigits[0:8],
                hexdigits[8:12],
                hexdigits[12:16],
                hexdigits[16:20],
                hexdigits[20:32],
            )
        )
    return text


# ---------------------------------------------------------------------------
# Deterministic hashing contracts (DDD §5, §6)
# ---------------------------------------------------------------------------

def compute_evidence_hash(
    *,
    source_id: str,
    evidence_type: EvidenceType | str,
    hive_file_path: str | None = None,
    root_hive: str | None = None,
    key_path: str | None = None,
    value_name: str | None = None,
    value_data_hash: str | None = None,
    user_sid: str | None = None,
    normalized_path: str | None = None,
    product_code: str | None = None,
) -> str:
    """Deterministic SHA-256 evidence identity (DDD §5).

    Canonical field order (fixed by the DDD):

    1.  ``source_id``            — lowercase UUID string
    2.  ``evidence_type``        — preserved exactly
    3.  ``hive_file_path``       — source-relative logical path, lowercased
    4.  ``root_hive``            — uppercased
    5.  ``key_path``             — backslash form, no leading/trailing backslash, lowercased
    6.  ``value_name``           — lowercased
    7.  ``value_data_hash``      — SHA-256 of the type-prefixed value (empty string when absent)
    8.  ``user_sid``             — uppercased
    9.  ``normalized_path``      — backslash Windows form, lowercased
    10. ``product_code``         — uppercase dashed GUID when a GUID

    Fields are UTF-8 encoded and joined with ASCII unit separator ``0x1F``.
    The result is a lowercase 64-character hex digest, stored in
    ``DISCOVERY_EVIDENCE.evidence_hash`` (UNIQUE) to prevent duplicate
    evidence rows without relying on nullable-column unique constraints.
    """
    fields = (
        (source_id or "").strip().lower(),
        str(evidence_type),
        canon_source_relative_path(hive_file_path),
        (root_hive or "").strip().upper(),
        canon_lower_path(key_path),
        (value_name or "").strip().lower(),
        value_data_hash or "",
        (user_sid or "").strip().upper(),
        canon_lower_path(normalized_path),
        canonical_product_code(product_code),
    )
    return _sha256_hex(_UNIT_SEPARATOR.join(fields).encode("utf-8"))


def _canonical_value_payload(value: "RegistryValue") -> str:
    """Type-prefixed canonical representation of a registry value (DDD §5).

    * strings: trailing NULs stripped, meaningful line breaks preserved;
    * multi-strings: per-element trailing NULs stripped, elements joined
      with ``0x1F``;
    * numerics: canonical decimal strings (DWORD/QWORD masked to width);
    * binary: canonical lowercase hexadecimal.
    """
    vtype = value.value_type
    data = value.data
    if vtype in (RegistryValueType.STRING, RegistryValueType.EXPAND_STRING):
        prefix = "sz" if vtype is RegistryValueType.STRING else "es"
        text = "" if data is None else str(data).rstrip("\x00")
        return f"{prefix}={text}"
    if vtype is RegistryValueType.MULTI_STRING:
        elements = () if data is None else tuple(str(e).rstrip("\x00") for e in data)
        return "msz=" + _UNIT_SEPARATOR.join(elements)
    if vtype is RegistryValueType.DWORD:
        number = 0 if data is None else int(data) & 0xFFFFFFFF
        return f"dw={number}"
    if vtype is RegistryValueType.QWORD:
        number = 0 if data is None else int(data) & 0xFFFFFFFFFFFFFFFF
        return f"qw={number}"
    if vtype is RegistryValueType.BINARY:
        raw = b"" if data is None else bytes(data)
        return f"bin={raw.hex()}"
    return "none="


def value_data_hash(value: "RegistryValue | None") -> str:
    """SHA-256 over the type-prefixed canonical value (DDD §5 field 7).

    Returns the empty string when the value is absent, exactly as the DDD
    specifies.
    """
    if value is None:
        return ""
    return _sha256_hex(_canonical_value_payload(value).encode("utf-8"))


def safe_value_text(value: "RegistryValue | None") -> str:
    """Display-safe textual representation for UI and report export.

    Registry values are metadata, never file contents (README §5.14).
    Binary values are truncated for display to keep UI strings bounded.
    """
    if value is None:
        return ""
    vtype = value.value_type
    data = value.data
    if vtype in (RegistryValueType.STRING, RegistryValueType.EXPAND_STRING):
        return "" if data is None else str(data).rstrip("\x00")
    if vtype is RegistryValueType.MULTI_STRING:
        elements = () if data is None else tuple(str(e).rstrip("\x00") for e in data)
        return " | ".join(elements)
    if vtype in (RegistryValueType.DWORD, RegistryValueType.QWORD):
        return str(0 if data is None else int(data))
    if vtype is RegistryValueType.BINARY:
        raw = b"" if data is None else bytes(data)
        hex_text = raw.hex()
        if len(hex_text) > 128:
            hex_text = hex_text[:128] + "..."
        return hex_text
    return ""


def _canon_identity_key(basis: IdentityBasis, identity_key: str) -> str:
    """Basis-specific ``identity_key`` normalization (DDD §6).

    All branches are idempotent, so hydrating a persisted record and
    re-deriving its key always yields the same digest.
    """
    text = (identity_key or "").strip()
    if not text:
        raise ValueError("identity_key must be non-empty (DDD §6).")
    if basis is IdentityBasis.PRODUCT_CODE:
        return canonical_product_code(text)
    if basis in (
        IdentityBasis.UNINSTALL_KEY,
        IdentityBasis.INSTALL_PATH,
        IdentityBasis.PORTABLE_DIRECTORY,
        IdentityBasis.MANIFEST_DIRECTORY,
        IdentityBasis.EXECUTABLE_BUNDLE,
    ):
        return canon_lower_path(text)
    if basis is IdentityBasis.NAME_PUBLISHER_VERSION:
        parts = [part.strip().lower() for part in text.split(_UNIT_SEPARATOR)]
        return _UNIT_SEPARATOR.join(parts)
    # IdentityBasis.FALLBACK: deterministic normalized evidence-derived key.
    return text.lower()


def compute_identity_hash(
    source_id: str,
    identity_basis: IdentityBasis | str,
    identity_key: str,
) -> str:
    """Deterministic SHA-256 application identity (DDD §6).

    Payload = ``source_id`` (lowercase) + ``0x1F`` + ``identity_basis``
    (exact DDD value) + ``0x1F`` + normalized ``identity_key``, UTF-8
    encoded.  The hash is source-scoped, which structurally prevents
    cross-source application identity collisions (SDD §2.14).
    """
    basis = IdentityBasis(str(identity_basis))
    payload = _UNIT_SEPARATOR.join(
        [
            (source_id or "").strip().lower(),
            basis.value,
            _canon_identity_key(basis, identity_key),
        ]
    )
    return _sha256_hex(payload.encode("utf-8"))


# ---------------------------------------------------------------------------
# Acquisition / ingestion DTOs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BlockDevice:
    """One block device/partition node from ``lsblk --json`` (SDD §2.7).

    ``dev_type`` is the ``lsblk`` ``type`` field (``disk``, ``part``,
    ``loop``, ``rom``, ...).  ``mount_points`` normalizes both the singular
    ``mountpoint`` and plural ``mountpoints`` spellings that different
    ``lsblk`` versions emit (README §5.2).  This DTO is metadata only;
    the mount manager performs all privileged operations.
    """

    device_path: str
    name: str
    dev_type: str
    fs_type: str | None = None
    size_bytes: int | None = None
    label: str | None = None
    uuid: str | None = None
    mount_points: tuple[str, ...] = ()
    transport: str | None = None

    @property
    def is_mounted(self) -> bool:
        return bool(self.mount_points)

    @property
    def is_ntfs_partition(self) -> bool:
        """Candidate source per SRS/SDD §2.7: an NTFS partition only."""
        return self.dev_type == "part" and (self.fs_type or "").lower() == "ntfs"


def _validate_source_pairing(source_type: SourceType, acquisition_method: AcquisitionMethod) -> None:
    """Enforce the DDD ``SCAN_SOURCE`` CHECK constraint in memory.

    Failing fast at construction time keeps invalid records from ever
    reaching SQLite, and guarantees the UI can never display a source
    whose acquisition method implies write access.
    """
    if (source_type is SourceType.MOUNTED_BLOCK_DEVICE) != (
        acquisition_method is AcquisitionMethod.NTFS3G_RO
    ):
        raise ValueError(
            "source_type/acquisition_method mismatch (DDD SCAN_SOURCE CHECK): "
            f"{source_type.value!r} vs {acquisition_method.value!r}"
        )


@dataclass(frozen=True, slots=True)
class PreparedSource:
    """Output of ``mount_manager.prepare_windows_source`` /
    ``prepare_secondary_mount`` (SDD §2.7).

    Safety boundary: a source object *cannot exist* unless it is read-only.
    ``read_only=False`` is rejected at construction, which makes the
    zero-write guarantee a property of the type itself, not of caller
    discipline.  ``logical_drive`` (``C:`` or ``S1:``, ``S2:``, ...) is the
    canonical source-letter used for logical path mapping (SDD §2.4); the
    raw ``mount_point`` is transient acquisition state only.
    """

    source_id: str
    session_id: str
    source_type: SourceType
    source_role: SourceRole
    logical_drive: str
    origin_device_path: str | None = None
    mount_point: str | None = None
    manifest_path: str | None = None
    fs_type: str | None = None
    label: str | None = None
    uuid: str | None = None
    size_bytes: int | None = None
    acquisition_method: AcquisitionMethod = AcquisitionMethod.NTFS3G_RO
    read_only: bool = True

    def __post_init__(self) -> None:
        if not self.read_only:
            raise ValueError(
                "PreparedSource must be read-only; writable acquisition is "
                "prohibited (core zero-write safety boundary)."
            )
        if not _LOGICAL_DRIVE_RE.match(self.logical_drive):
            raise ValueError(
                f"Invalid logical drive {self.logical_drive!r}; expected "
                "'C:' or 'S1:', 'S2:', ..."
            )
        _validate_source_pairing(self.source_type, self.acquisition_method)
        if self.source_role is SourceRole.WINDOWS_OS and (
            self.source_type is not SourceType.MOUNTED_BLOCK_DEVICE
            or self.acquisition_method is not AcquisitionMethod.NTFS3G_RO
        ):
            raise ValueError(
                "A windows_os source must be a read-only ntfs-3g mount "
                "(manifest-only sources are secondary, DDD §3)."
            )
        if self.source_type is SourceType.MOUNTED_BLOCK_DEVICE and not self.mount_point:
            raise ValueError("A prepared mounted source must carry a mount point.")
        if self.source_type is SourceType.MANIFEST_FILE and not self.manifest_path:
            raise ValueError("A prepared manifest source must carry a manifest path.")


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """DTO for the ``SCAN_SOURCE`` table (DDD §4).

    ``logical_drive`` is a *transient, derived* field (not a DDD column):
    ``src.db`` derives ``C:`` / ``S1:`` / ... from source addition order and
    attaches it via :meth:`with_logical_drive`.  ``to_row`` never emits it,
    so the persisted schema matches the DDD exactly.
    """

    source_id: str
    session_id: str
    source_type: SourceType
    source_role: SourceRole
    acquisition_method: AcquisitionMethod
    status: SourceStatus
    origin_device_path: str | None = None
    manifest_path: str | None = None
    mount_point: str | None = None
    fs_type: str | None = None
    label: str | None = None
    uuid: str | None = None
    size_bytes: int | None = None
    read_only: bool = True
    warnings_json: str | None = None
    logical_drive: str | None = None

    def __post_init__(self) -> None:
        if not self.read_only:
            raise ValueError("SourceRecord.read_only must be True (DDD: CHECK read_only = 1).")
        _validate_source_pairing(self.source_type, self.acquisition_method)
        if self.source_role is SourceRole.WINDOWS_OS and (
            self.source_type is not SourceType.MOUNTED_BLOCK_DEVICE
            or self.acquisition_method is not AcquisitionMethod.NTFS3G_RO
        ):
            raise ValueError("A windows_os source must be a read-only ntfs-3g mount.")
        if self.status in (SourceStatus.READY, SourceStatus.COMPLETE):
            if self.source_type is SourceType.MOUNTED_BLOCK_DEVICE and not self.mount_point:
                raise ValueError("Ready/complete mounted source must carry a mount point.")
            if self.source_type is SourceType.MANIFEST_FILE and not self.manifest_path:
                raise ValueError("Ready/complete manifest source must carry a manifest path.")

    @classmethod
    def from_prepared(cls, prepared: PreparedSource, status: SourceStatus = SourceStatus.READY) -> "SourceRecord":
        """Build the persistable record from an acquisition result."""
        return cls(
            source_id=prepared.source_id,
            session_id=prepared.session_id,
            source_type=prepared.source_type,
            source_role=prepared.source_role,
            acquisition_method=prepared.acquisition_method,
            status=status,
            origin_device_path=prepared.origin_device_path,
            manifest_path=prepared.manifest_path,
            mount_point=prepared.mount_point,
            fs_type=prepared.fs_type,
            label=prepared.label,
            uuid=prepared.uuid,
            size_bytes=prepared.size_bytes,
            read_only=True,
            logical_drive=prepared.logical_drive,
        )

    def with_logical_drive(self, logical_drive: str) -> "SourceRecord":
        """Controlled mutation: return a copy with a derived drive letter."""
        return replace(self, logical_drive=logical_drive)

    def to_row(self) -> dict[str, Any]:
        """Exact ``SCAN_SOURCE`` column mapping (DDD §4)."""
        return {
            "source_id": self.source_id,
            "session_id": self.session_id,
            "source_type": self.source_type.value,
            "source_role": self.source_role.value,
            "origin_device_path": self.origin_device_path,
            "manifest_path": self.manifest_path,
            "mount_point": self.mount_point,
            "fs_type": self.fs_type,
            "label": self.label,
            "uuid": self.uuid,
            "size_bytes": self.size_bytes,
            "acquisition_method": self.acquisition_method.value,
            "read_only": 1,
            "status": self.status.value,
            "warnings_json": self.warnings_json,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "SourceRecord":
        """Hydrate a ``SCAN_SOURCE`` row (used only by ``src.db``)."""
        return cls(
            source_id=str(row["source_id"]),
            session_id=str(row["session_id"]),
            source_type=SourceType(str(row["source_type"])),
            source_role=_coerce_enum(SourceRole, row.get("source_role"), SourceRole.SECONDARY_DATA),
            acquisition_method=AcquisitionMethod(str(row["acquisition_method"])),
            status=_coerce_enum(SourceStatus, row.get("status"), SourceStatus.ERROR),
            origin_device_path=_as_str_or_none(row.get("origin_device_path")),
            manifest_path=_as_str_or_none(row.get("manifest_path")),
            mount_point=_as_str_or_none(row.get("mount_path") or row.get("mount_point")),
            fs_type=_as_str_or_none(row.get("fs_type")),
            label=_as_str_or_none(row.get("label")),
            uuid=_as_str_or_none(row.get("uuid")),
            size_bytes=_as_int_or_none(row.get("size_bytes")),
            read_only=True,
            warnings_json=_as_str_or_none(row.get("warnings_json")),
            logical_drive=None,
        )


@dataclass(frozen=True, slots=True)
class RegistryValue:
    """One registry value kept in structured form (metadata only).

    ``data`` is decoded value material: ``str`` for REG_SZ/REG_EXPAND_SZ,
    ``tuple[str, ...]`` for REG_MULTI_SZ, ``int`` for REG_DWORD/REG_QWORD,
    ``bytes`` for REG_BINARY.  Registry values are not file contents
    (README §5.14).  This structure exists so the DDD §5
    ``value_data_hash`` can be computed deterministically; it is
    *in-memory only* and is never a database column.
    """

    name: str = ""  # "(Default)" value is represented as ""
    value_type: RegistryValueType = RegistryValueType.STRING
    data: str | tuple[str, ...] | int | bytes | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    """DTO for the ``DISCOVERY_EVIDENCE`` table (DDD §4).

    Evidence is first-class (SDD §5 "Evidence-First Model"): raw evidence is
    persisted before correlation, so orphaned and partial evidence survives
    even when no application matches it.

    ``evidence_hash`` behavior:
        * leave it empty (default) at construction and it is computed
          deterministically in ``__post_init__`` per DDD §5;
        * ``from_row`` passes the stored hash verbatim, so report
          hydration is byte-stable even though ``registry_value`` is
          in-memory only and not re-derivable from a row.

    ``value_data`` is always a safe display string (never file contents);
    if a structured ``registry_value`` is supplied without display text, the
    display text is derived automatically.
    """

    session_id: str
    source_id: str
    evidence_type: EvidenceType
    confidence: Confidence = Confidence.MEDIUM
    hive_file_path: str | None = None
    root_hive: str | None = None
    key_path: str | None = None
    value_name: str | None = None
    registry_value: RegistryValue | None = None
    value_data: str | None = None
    user_sid: str | None = None
    file_path: str | None = None
    normalized_path: str | None = None
    product_code: str | None = None
    parse_warning: str | None = None
    raw_json: str | None = None
    evidence_id: str | None = None
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if self.registry_value is not None and self.value_data is None:
            object.__setattr__(self, "value_data", safe_value_text(self.registry_value))
        if not self.evidence_hash:
            object.__setattr__(
                self,
                "evidence_hash",
                compute_evidence_hash(
                    source_id=self.source_id,
                    evidence_type=self.evidence_type,
                    hive_file_path=self.hive_file_path,
                    root_hive=self.root_hive,
                    key_path=self.key_path,
                    value_name=self.value_name,
                    value_data_hash=value_data_hash(self.registry_value),
                    user_sid=self.user_sid,
                    normalized_path=self.normalized_path,
                    product_code=self.product_code,
                ),
            )

    def with_id(self, evidence_id: str) -> "Evidence":
        """Controlled mutation: attach the database-issued identifier."""
        return replace(self, evidence_id=evidence_id)

    def to_row(self) -> dict[str, Any]:
        """Exact ``DISCOVERY_EVIDENCE`` column mapping (DDD §4)."""
        return {
            "evidence_id": self.evidence_id,
            "session_id": self.session_id,
            "source_id": self.source_id,
            "evidence_hash": self.evidence_hash,
            "evidence_type": self.evidence_type.value,
            "hive_file_path": self.hive_file_path,
            "root_hive": self.root_hive,
            "key_path": self.key_path,
            "value_name": self.value_name,
            "value_data": self.value_data,
            "user_sid": self.user_sid,
            "file_path": self.file_path,
            "normalized_path": self.normalized_path,
            "product_code": self.product_code,
            "confidence": self.confidence.value,
            "parse_warning": self.parse_warning,
            "raw_json": self.raw_json,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Evidence":
        """Hydrate a ``DISCOVERY_EVIDENCE`` row (used only by ``src.db``).

        Raises ``KeyError``/``ValueError`` on structurally invalid rows;
        ``src.db`` is expected to wrap that in a typed warning rather than
        crash the scan (SDD §4 defensive posture).
        """
        return cls(
            session_id=str(row["session_id"]),
            source_id=str(row["source_id"]),
            evidence_type=EvidenceType(str(row["evidence_type"])),
            hive_file_path=_as_str_or_none(row.get("hive_file_path")),
            root_hive=_as_str_or_none(row.get("root_hive")),
            key_path=_as_str_or_none(row.get("key_path")),
            value_name=_as_str_or_none(row.get("value_name")),
            registry_value=None,
            value_data=_as_str_or_none(row.get("value_data")),
            user_sid=_as_str_or_none(row.get("user_sid")),
            file_path=_as_str_or_none(row.get("file_path")),
            normalized_path=_as_str_or_none(row.get("normalized_path")),
            product_code=_as_str_or_none(row.get("product_code")),
            confidence=_coerce_enum(Confidence, row.get("confidence"), Confidence.MEDIUM),
            parse_warning=_as_str_or_none(row.get("parse_warning")),
            raw_json=_as_str_or_none(row.get("raw_json")),
            evidence_id=_as_str_or_none(row.get("evidence_id")),
            evidence_hash=_as_str_or_none(row.get("evidence_hash")) or "",
        )


#: SDD §2.12: the manifest parser emits ``Evidence`` records of type
#: ``MANIFEST_ENTRY``; the alias keeps the documented API name.
ManifestEvidence = Evidence


@dataclass(frozen=True, slots=True)
class PersistedEvidence:
    """Lightweight reference to a persisted evidence row.

    The portable scanner (SDD §2.13) and correlator (SDD §2.14) consume
    bounded batches of these *after* persistence; neither re-opens source
    drives.  ``display_name`` and ``install_path`` are convenience fields
    derived from the evidence (see :meth:`from_evidence`).
    """

    evidence_id: str
    source_id: str
    evidence_type: EvidenceType
    display_name: str
    confidence: Confidence = Confidence.MEDIUM
    key_path: str | None = None
    file_path: str | None = None
    normalized_path: str | None = None
    product_code: str | None = None
    install_path: str | None = None
    value_data: str | None = None
    user_sid: str | None = None

    @classmethod
    def from_evidence(cls, evidence: Evidence, evidence_id: str) -> "PersistedEvidence":
        """Project a full evidence DTO into its persisted reference form."""
        display = ""
        if evidence.file_path:
            display = canonical_path_structure(evidence.file_path).rsplit("\\", 1)[-1]
        if not display and evidence.value_name:
            display = evidence.value_name.strip()
        if not display and evidence.key_path:
            display = evidence.key_path.strip("\\").rsplit("\\", 1)[-1]
        if not display:
            display = evidence.evidence_type.value

        install_path: str | None = None
        if evidence.raw_json:
            try:
                payload = json.loads(evidence.raw_json)
                if isinstance(payload, Mapping):
                    install_path = _as_str_or_none(payload.get("install_path"))
            except (json.JSONDecodeError, TypeError, ValueError):
                install_path = None  # Defensive: raw_json is optional metadata.

        return cls(
            evidence_id=evidence_id,
            source_id=evidence.source_id,
            evidence_type=evidence.evidence_type,
            display_name=display,
            confidence=evidence.confidence,
            key_path=evidence.key_path,
            file_path=evidence.file_path,
            normalized_path=evidence.normalized_path,
            product_code=evidence.product_code,
            install_path=install_path,
            value_data=evidence.value_data,
            user_sid=evidence.user_sid,
        )


@dataclass(frozen=True, slots=True)
class PortableCandidate:
    """A portable-application candidate emitted by the portable scanner
    (SDD §2.13).  Detection is name/extension/path-structure only —
    never file contents.
    """

    source_id: str
    candidate_path: str
    normalized_path: str
    display_name: str
    basis: IdentityBasis  # portable_directory | manifest_directory | executable_bundle
    confidence: Confidence
    score: int  # portable likelihood, 0..100
    rationale: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("PortableCandidate.score must be within 0..100.")
        if self.basis not in (
            IdentityBasis.PORTABLE_DIRECTORY,
            IdentityBasis.MANIFEST_DIRECTORY,
            IdentityBasis.EXECUTABLE_BUNDLE,
        ):
            raise ValueError(
                "PortableCandidate.basis must be a portable identity basis."
            )


@dataclass(frozen=True, slots=True)
class HiveFile:
    """One located offline hive (SDD §2.9).

    ``logical_path`` is the source-relative logical Windows path (canonical
    for hashing/display).  ``mount_path`` is the transient Linux filesystem
    path used only by the offline parser — it must never be stored as the
    canonical path in evidence (SDD §2.4).  ``readable=False`` marks hives
    that were located but could not be opened (corrupt/truncated), which
    the locator turns into warnings (README §5.3).
    """

    hive_type: HiveType
    logical_path: str
    mount_path: Path
    size_bytes: int | None = None
    readable: bool = True


@dataclass(frozen=True, slots=True)
class MachineHiveSet:
    """Machine hives located on a Windows source (SDD §2.9)."""

    software: HiveFile | None = None
    system: HiveFile | None = None
    default: HiveFile | None = None  # Optional; never treated as a user hive.
    warnings: tuple[str, ...] = ()

    @property
    def missing_required(self) -> tuple[HiveType, ...]:
        """Required machine hives that were not located."""
        missing: list[HiveType] = []
        if self.software is None:
            missing.append(HiveType.SOFTWARE)
        if self.system is None:
            missing.append(HiveType.SYSTEM)
        return tuple(missing)


@dataclass(frozen=True, slots=True)
class UserHiveSet:
    """User hives (NTUSER.DAT / UsrClass.dat) for one profile (SDD §2.9).

    ``is_default_profile`` / ``is_system_profile`` prevent Default and
    system profile hives from being treated as normal user hives unless
    explicitly marked.
    """

    profile_id: str | None = None
    username: str | None = None
    sid: str | None = None
    is_default_profile: bool = False
    is_system_profile: bool = False
    ntuser: HiveFile | None = None
    usrclass: HiveFile | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HiveSet:
    """Combined machine + user hive set consumed by the registry parser
    (SDD §2.10 ``enumerate_registry_evidence``)."""

    machine: MachineHiveSet
    users: tuple[UserHiveSet, ...] = ()

    @property
    def user_count(self) -> int:
        return len(self.users)


@dataclass(frozen=True, slots=True)
class RegistryParseOptions:
    """Operator/scan-level controls for offline registry parsing (SDD §2.10).

    ``None`` bounds mean "use the session's ``ScanOptions`` bounds".
    ``control_set_override`` is for diagnostics; the default deterministic
    resolution order (Default -> LastKnownGood -> first numeric -> skip
    with warning) is implemented in the parser (README §5.4).
    """

    include_wow64: bool = True
    include_user_hives: bool = True
    include_appcompat_cache: bool = True
    decode_userassist_rot13: bool = True
    max_evidence_total: int | None = None
    max_evidence_per_root: int | None = None
    # Per-key bounds; None defers to the session's ScanOptions values
    # (SRS FR-2.3: max subkeys / max values examined per registry key).
    max_subkeys_per_key: int | None = None
    max_values_per_key: int | None = None
    control_set_override: str | None = None


@dataclass(frozen=True, slots=True)
class ManifestGenerationResult:
    """Result of ``manifest_generator.generate_manifest`` (SDD §2.8).

    Manifests are written only to safe host output paths — never to the
    scanned source.
    """

    ok: bool
    device_path: str
    output_path: Path
    entry_count: int = 0
    truncated: bool = False
    duration_seconds: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Correlation / classification DTOs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class UserProfile:
    """DTO for the ``USER_PROFILE`` table (DDD §4).

    Resolved shell-folder paths are logical Windows-style paths.
    ``documents_path`` is the Documents baseline; when it is ``None`` the
    classifier marks inside/outside comparisons as unknown (README §5.8).
    """

    session_id: str
    source_id: str
    username: str | None = None
    sid: str | None = None
    profile_path: str | None = None
    normalized_profile_path: str | None = None
    ntuser_path: str | None = None
    usrclass_path: str | None = None
    documents_path: str | None = None
    desktop_path: str | None = None
    downloads_path: str | None = None
    pictures_path: str | None = None
    music_path: str | None = None
    videos_path: str | None = None
    appdata_local_path: str | None = None
    appdata_roaming_path: str | None = None
    appdata_locallow_path: str | None = None
    saved_games_path: str | None = None
    is_default_profile: bool = False
    is_system_profile: bool = False
    parse_warnings_json: str | None = None
    profile_id: str | None = None

    @property
    def documents_baseline_known(self) -> bool:
        """True when a Documents baseline exists for comparison (README §5.8)."""
        return bool(self.documents_path)

    def parse_warnings(self) -> tuple[str, ...]:
        """Defensively parse the ``parse_warnings_json`` column."""
        return _load_json_list(self.parse_warnings_json)

    def with_id(self, profile_id: str) -> "UserProfile":
        """Controlled mutation: attach the database-issued identifier."""
        return replace(self, profile_id=profile_id)

    def to_row(self) -> dict[str, Any]:
        """Exact ``USER_PROFILE`` column mapping (DDD §4)."""
        return {
            "profile_id": self.profile_id,
            "session_id": self.session_id,
            "source_id": self.source_id,
            "username": self.username,
            "sid": self.sid,
            "profile_path": self.profile_path,
            "normalized_profile_path": self.normalized_profile_path,
            "ntuser_path": self.ntuser_path,
            "usrclass_path": self.usrclass_path,
            "documents_path": self.documents_path,
            "desktop_path": self.desktop_path,
            "downloads_path": self.downloads_path,
            "pictures_path": self.pictures_path,
            "music_path": self.music_path,
            "videos_path": self.videos_path,
            "appdata_local_path": self.appdata_local_path,
            "appdata_roaming_path": self.appdata_roaming_path,
            "appdata_locallow_path": self.appdata_locallow_path,
            "saved_games_path": self.saved_games_path,
            "is_default_profile": int(self.is_default_profile),
            "is_system_profile": int(self.is_system_profile),
            "parse_warnings_json": self.parse_warnings_json,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "UserProfile":
        """Hydrate a ``USER_PROFILE`` row (used only by ``src.db``)."""
        return cls(
            session_id=str(row["session_id"]),
            source_id=str(row["source_id"]),
            username=_as_str_or_none(row.get("username")),
            sid=_as_str_or_none(row.get("sid")),
            profile_path=_as_str_or_none(row.get("profile_path")),
            normalized_profile_path=_as_str_or_none(row.get("normalized_profile_path")),
            ntuser_path=_as_str_or_none(row.get("ntuser_path")),
            usrclass_path=_as_str_or_none(row.get("usrclass_path")),
            documents_path=_as_str_or_none(row.get("documents_path")),
            desktop_path=_as_str_or_none(row.get("desktop_path")),
            downloads_path=_as_str_or_none(row.get("downloads_path")),
            pictures_path=_as_str_or_none(row.get("pictures_path")),
            music_path=_as_str_or_none(row.get("music_path")),
            videos_path=_as_str_or_none(row.get("videos_path")),
            appdata_local_path=_as_str_or_none(row.get("appdata_local_path")),
            appdata_roaming_path=_as_str_or_none(row.get("appdata_roaming_path")),
            appdata_locallow_path=_as_str_or_none(row.get("appdata_locallow_path")),
            saved_games_path=_as_str_or_none(row.get("saved_games_path")),
            is_default_profile=bool(_as_bool_or_none(row.get("is_default_profile")) or False),
            is_system_profile=bool(_as_bool_or_none(row.get("is_system_profile")) or False),
            parse_warnings_json=_as_str_or_none(row.get("parse_warnings_json")),
            profile_id=_as_str_or_none(row.get("profile_id")),
        )


@dataclass(frozen=True, slots=True)
class CorrelatedApplication:
    """DTO for the ``APP_RECORD`` table (DDD §4).

    Application identities are source-scoped (SDD §2.14): the identity hash
    includes ``source_id`` (DDD §6), so evidence from one source can never
    collapse into an application owned by another source.

    ``identity_hash`` is computed deterministically in ``__post_init__``
    (or preserved verbatim when hydrating, via ``from_row``).
    """

    session_id: str
    source_id: str
    identity_basis: IdentityBasis
    identity_key: str
    display_name: str
    discovery_method: DiscoveryMethod
    fingerprint_status: FingerprintStatus
    evidence_confidence: Confidence
    publisher: str | None = None
    version: str | None = None
    install_date: str | None = None
    architecture: str | None = None
    install_path: str | None = None
    normalized_install_path: str | None = None
    portable_score: int | None = None
    notes_json: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    app_id: str | None = None
    identity_hash: str = ""

    def __post_init__(self) -> None:
        if not (self.identity_key or "").strip():
            raise ValueError("identity_key must be non-empty (DDD §6).")
        if not (self.display_name or "").strip():
            raise ValueError("display_name must be non-empty (DDD §4 NOT NULL).")
        if self.portable_score is not None and not 0 <= self.portable_score <= 100:
            raise ValueError("portable_score must be within 0..100 (DDD APP_RECORD CHECK).")
        if not self.identity_hash:
            object.__setattr__(
                self,
                "identity_hash",
                compute_identity_hash(self.source_id, self.identity_basis, self.identity_key),
            )

    def with_id(self, app_id: str) -> "CorrelatedApplication":
        """Controlled mutation: attach the database-issued identifier."""
        return replace(self, app_id=app_id)

    def notes(self) -> dict[str, Any]:
        """Defensively parse the ``notes_json`` column."""
        if not self.notes_json:
            return {}
        try:
            payload = json.loads(self.notes_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def to_row(self) -> dict[str, Any]:
        """Exact ``APP_RECORD`` column mapping (DDD §4)."""
        return {
            "app_id": self.app_id,
            "session_id": self.session_id,
            "source_id": self.source_id,
            "identity_hash": self.identity_hash,
            "identity_basis": self.identity_basis.value,
            "identity_key": self.identity_key,
            "display_name": self.display_name,
            "publisher": self.publisher,
            "version": self.version,
            "install_date": self.install_date,
            "architecture": self.architecture,
            "install_path": self.install_path,
            "normalized_install_path": self.normalized_install_path,
            "discovery_method": self.discovery_method.value,
            "fingerprint_status": self.fingerprint_status.value,
            "evidence_confidence": self.evidence_confidence.value,
            "portable_score": self.portable_score,
            "notes_json": self.notes_json,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CorrelatedApplication":
        """Hydrate an ``APP_RECORD`` row (used only by ``src.db``)."""
        return cls(
            session_id=str(row["session_id"]),
            source_id=str(row["source_id"]),
            identity_basis=IdentityBasis(str(row["identity_basis"])),
            identity_key=str(row["identity_key"]),
            display_name=str(row["display_name"]),
            discovery_method=DiscoveryMethod(str(row["discovery_method"])),
            fingerprint_status=_coerce_enum(
                FingerprintStatus, row.get("fingerprint_status"), FingerprintStatus.UNKNOWN
            ),
            evidence_confidence=_coerce_enum(
                Confidence, row.get("evidence_confidence"), Confidence.MEDIUM
            ),
            publisher=_as_str_or_none(row.get("publisher")),
            version=_as_str_or_none(row.get("version")),
            install_date=_as_str_or_none(row.get("install_date")),
            architecture=_as_str_or_none(row.get("architecture")),
            install_path=_as_str_or_none(row.get("install_path")),
            normalized_install_path=_as_str_or_none(row.get("normalized_install_path")),
            portable_score=_as_int_or_none(row.get("portable_score")),
            notes_json=_as_str_or_none(row.get("notes_json")),
            created_at=_as_str_or_none(row.get("created_at")) or utc_now_iso(),
            app_id=_as_str_or_none(row.get("app_id")),
            identity_hash=_as_str_or_none(row.get("identity_hash")) or "",
        )


@dataclass(frozen=True, slots=True)
class ApplicationEvidenceLink:
    """DTO for the ``APP_EVIDENCE`` table (DDD §4).

    The same-source invariant ("an application may only be linked to
    evidence from the same source") is enforced by ``src.db`` when the link
    is written, because it requires a source lookup that this value object
    deliberately does not perform.
    """

    app_id: str
    evidence_id: str
    relevance: Relevance
    created_at: str = field(default_factory=utc_now_iso)
    link_id: int | None = None

    def to_row(self) -> dict[str, Any]:
        """Exact ``APP_EVIDENCE`` column mapping (DDD §4)."""
        return {
            "link_id": self.link_id,
            "app_id": self.app_id,
            "evidence_id": self.evidence_id,
            "relevance": self.relevance.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ApplicationEvidenceLink":
        """Hydrate an ``APP_EVIDENCE`` row (used only by ``src.db``)."""
        return cls(
            app_id=str(row["app_id"]),
            evidence_id=str(row["evidence_id"]),
            relevance=_coerce_enum(Relevance, row.get("relevance"), Relevance.SUPPORTING),
            created_at=_as_str_or_none(row.get("created_at")) or utc_now_iso(),
            link_id=_as_int_or_none(row.get("link_id")),
        )


@dataclass(frozen=True, slots=True)
class UserDataFinding:
    """DTO for the ``USER_DATA_FINDING`` table (DDD §4).

    A finding is unique within a session and source by ``normalized_path``
    (DDD §4 UNIQUE constraint); the classifier deduplicates on exactly this
    key and preserves merged rationales (SDD §2.15).

    ``inside_documents`` is tri-state (NULL = unknown) so unresolved
    Documents baselines produce *unknown* rather than a false negative
    (README §5.8).  ``user_confirmed`` / ``user_notes`` are written by the
    UI triage flow through ``src.db`` (the only write path).
    """

    session_id: str
    source_id: str
    path: str
    normalized_path: str
    location_category: FindingLocationCategory
    severity_level: SeverityLevel
    confidence: Confidence
    rationale: str
    app_id: str | None = None
    profile_id: str | None = None
    inside_documents: bool | None = None
    documents_root: str | None = None
    owner_username: str | None = None
    nomenclature_match: str | None = None
    extension_match: str | None = None
    file_count: int | None = None
    total_size_bytes: int | None = None
    created_at: str = field(default_factory=utc_now_iso)
    user_confirmed: bool | None = None
    user_notes: str | None = None
    finding_id: str | None = None

    def __post_init__(self) -> None:
        if not (self.path or "").strip() or not (self.normalized_path or "").strip():
            raise ValueError("Finding path and normalized_path must be non-empty.")
        if self.file_count is not None and self.file_count < 0:
            raise ValueError("file_count must be >= 0.")
        if self.total_size_bytes is not None and self.total_size_bytes < 0:
            raise ValueError("total_size_bytes must be >= 0.")

    def with_id(self, finding_id: str) -> "UserDataFinding":
        """Controlled mutation: attach the database-issued identifier."""
        return replace(self, finding_id=finding_id)

    def with_triage(self, user_confirmed: bool, user_notes: str | None) -> "UserDataFinding":
        """Controlled mutation used by the UI triage flow (via ``src.db``)."""
        return replace(self, user_confirmed=user_confirmed, user_notes=user_notes)

    def to_row(self) -> dict[str, Any]:
        """Exact ``USER_DATA_FINDING`` column mapping (DDD §4)."""
        return {
            "finding_id": self.finding_id,
            "session_id": self.session_id,
            "source_id": self.source_id,
            "app_id": self.app_id,
            "profile_id": self.profile_id,
            "path": self.path,
            "normalized_path": self.normalized_path,
            "location_category": self.location_category.value,
            "inside_documents": None if self.inside_documents is None else int(self.inside_documents),
            "documents_root": self.documents_root,
            "owner_username": self.owner_username,
            "nomenclature_match": self.nomenclature_match,
            "extension_match": self.extension_match,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "severity_level": self.severity_level.value,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "user_confirmed": None if self.user_confirmed is None else int(self.user_confirmed),
            "user_notes": self.user_notes,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "UserDataFinding":
        """Hydrate a ``USER_DATA_FINDING`` row (used only by ``src.db``)."""
        return cls(
            session_id=str(row["session_id"]),
            source_id=str(row["source_id"]),
            path=str(row["path"]),
            normalized_path=str(row["normalized_path"]),
            location_category=_coerce_enum(
                FindingLocationCategory, row.get("location_category"), FindingLocationCategory.UNKNOWN
            ),
            severity_level=_coerce_enum(
                SeverityLevel, row.get("severity_level"), SeverityLevel.MEDIUM
            ),
            confidence=_coerce_enum(Confidence, row.get("confidence"), Confidence.MEDIUM),
            rationale=str(row.get("rationale") or ""),
            app_id=_as_str_or_none(row.get("app_id")),
            profile_id=_as_str_or_none(row.get("profile_id")),
            inside_documents=_as_bool_or_none(row.get("inside_documents")),
            documents_root=_as_str_or_none(row.get("documents_root")),
            owner_username=_as_str_or_none(row.get("owner_username")),
            nomenclature_match=_as_str_or_none(row.get("nomenclature_match")),
            extension_match=_as_str_or_none(row.get("extension_match")),
            file_count=_as_int_or_none(row.get("file_count")),
            total_size_bytes=_as_int_or_none(row.get("total_size_bytes")),
            created_at=_as_str_or_none(row.get("created_at")) or utc_now_iso(),
            user_confirmed=_as_bool_or_none(row.get("user_confirmed")),
            user_notes=_as_str_or_none(row.get("user_notes")),
            finding_id=_as_str_or_none(row.get("finding_id")),
        )


@dataclass(frozen=True, slots=True)
class WarningRecord:
    """DTO for the ``SESSION_WARNING`` table (DDD §4).

    Warnings are the *only* user-visible signal of degraded processing
    (corrupt hives, bounded enumeration, unreadable directories).  Critical
    I/O failures additionally raise :class:`CriticalIoFailureEvent` to the
    UI; the warning row preserves the record for the report (SDD §4.5).
    """

    session_id: str
    category: WarningCategory
    severity: WarningSeverity
    message: str
    source_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    warning_id: str | None = None

    def __post_init__(self) -> None:
        if not (self.message or "").strip():
            raise ValueError("Warning message must be non-empty (DDD §4 NOT NULL).")

    def with_id(self, warning_id: str) -> "WarningRecord":
        """Controlled mutation: attach the database-issued identifier."""
        return replace(self, warning_id=warning_id)

    def to_row(self) -> dict[str, Any]:
        """Exact ``SESSION_WARNING`` column mapping (DDD §4)."""
        return {
            "warning_id": self.warning_id,
            "session_id": self.session_id,
            "source_id": self.source_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "WarningRecord":
        """Hydrate a ``SESSION_WARNING`` row (used only by ``src.db``)."""
        return cls(
            session_id=str(row["session_id"]),
            category=_coerce_enum(WarningCategory, row.get("category"), WarningCategory.GENERAL),
            severity=_coerce_enum(WarningSeverity, row.get("severity"), WarningSeverity.WARNING),
            message=str(row.get("message") or ""),
            source_id=_as_str_or_none(row.get("source_id")),
            created_at=_as_str_or_none(row.get("created_at")) or utc_now_iso(),
            warning_id=_as_str_or_none(row.get("warning_id")),
        )


# ---------------------------------------------------------------------------
# Session / reporting DTOs
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ScanOptions:
    """Session scan options, persisted as ``SCAN_SESSION.scan_options_json``
    (DDD §4).  The enumeration bounds here are what the bounded-processing
    pattern (SDD §5) consumes downstream in ``src.db`` and the coordinator.
    """

    evidence_locations_version: str
    heuristic_patterns_version: str
    max_evidence_rows: int = 250_000
    max_findings: int = 5_000
    max_manifest_entries: int = 500_000
    max_evidence_per_registry_root: int = 5_000
    # SRS FR-2.3: per-key registry bounds (subkeys/values examined per key).
    max_registry_subkeys_per_key: int = 2_000
    max_registry_values_per_key: int = 2_000
    # SRS FR-2.3: filesystem entries examined per source.
    max_filesystem_entries_per_source: int = 100_000
    max_directory_depth: int = 12
    max_directory_entries: int = 20_000
    include_wow64: bool = True
    include_user_hives: bool = True

    def to_json(self) -> str:
        """Canonical compact JSON (sorted keys) for stable reports."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str | None) -> "ScanOptions":
        """Defensive parse: malformed/absent input falls back to safe defaults
        rather than raising (README §5.2 defensive-parsing posture)."""
        data: dict[str, Any] = {}
        if text:
            try:
                loaded = json.loads(text)
                if isinstance(loaded, Mapping):
                    data = dict(loaded)
            except (json.JSONDecodeError, TypeError, ValueError):
                data = {}

        def _int(key: str, default: int) -> int:
            raw = data.get(key)
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default

        def _bool(key: str, default: bool) -> bool:
            parsed = _as_bool_or_none(data.get(key))
            return default if parsed is None else parsed

        return cls(
            evidence_locations_version=str(data.get("evidence_locations_version") or "unknown"),
            heuristic_patterns_version=str(data.get("heuristic_patterns_version") or "unknown"),
            max_evidence_rows=_int("max_evidence_rows", 250_000),
            max_findings=_int("max_findings", 5_000),
            max_manifest_entries=_int("max_manifest_entries", 500_000),
            max_evidence_per_registry_root=_int("max_evidence_per_registry_root", 5_000),
            max_registry_subkeys_per_key=_int("max_registry_subkeys_per_key", 2_000),
            max_registry_values_per_key=_int("max_registry_values_per_key", 2_000),
            max_filesystem_entries_per_source=_int(
                "max_filesystem_entries_per_source", 100_000
            ),
            max_directory_depth=_int("max_directory_depth", 12),
            max_directory_entries=_int("max_directory_entries", 20_000),
            include_wow64=_bool("include_wow64", True),
            include_user_hives=_bool("include_user_hives", True),
        )


@dataclass(frozen=True, slots=True)
class ScanSession:
    """DTO for the ``SCAN_SESSION`` table (DDD §4)."""

    session_id: str
    mode: SessionMode = SessionMode.ACTIVE
    status: SessionStatus = SessionStatus.PENDING
    schema_version: str = SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    scan_options_json: str | None = None

    @classmethod
    def new_active(cls, options: ScanOptions | None = None) -> "ScanSession":
        """Create a fresh active session with fresh UUID and UTC timestamp."""
        return cls(
            session_id=new_id(),
            mode=SessionMode.ACTIVE,
            status=SessionStatus.PENDING,
            scan_options_json=options.to_json() if options is not None else None,
        )

    def options(self) -> ScanOptions | None:
        """Defensively parse ``scan_options_json``; ``None`` when absent."""
        if not self.scan_options_json:
            return None
        return ScanOptions.from_json(self.scan_options_json)

    def to_row(self) -> dict[str, Any]:
        """Exact ``SCAN_SESSION`` column mapping (DDD §4)."""
        return {
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "mode": self.mode.value,
            "status": self.status.value,
            "scan_options_json": self.scan_options_json,
        }

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ScanSession":
        """Hydrate a ``SCAN_SESSION`` row (used only by ``src.db``)."""
        return cls(
            session_id=str(row["session_id"]),
            mode=_coerce_enum(SessionMode, row.get("mode"), SessionMode.ACTIVE),
            status=_coerce_enum(SessionStatus, row.get("status"), SessionStatus.FAILED),
            schema_version=_as_str_or_none(row.get("schema_version")) or SCHEMA_VERSION,
            created_at=_as_str_or_none(row.get("created_at")) or utc_now_iso(),
            scan_options_json=_as_str_or_none(row.get("scan_options_json")),
        )


@dataclass(frozen=True, slots=True)
class ScanSummary:
    """Bounded aggregate counters carried by completion/failure events.

    Counters only — never row data — so a single event stays small no
    matter how large the session is (SDD §2.19 throttling).
    """

    evidence_count: int = 0
    application_count: int = 0
    finding_count: int = 0
    warning_count: int = 0
    profile_count: int = 0
    portable_candidate_count: int = 0


@dataclass(frozen=True, slots=True)
class SessionBundle:
    """Complete session state used by ``db.load_session_data`` and
    ``state.import_report`` (SDD §2.17, §2.18).

    Memory note: this is a *materialized snapshot* used only for report
    export/import.  The live scan never builds one; it streams bounded
    batches through the persistence layer (SDD §5 "Bounded Processing").
    """

    session: ScanSession
    sources: tuple[SourceRecord, ...] = ()
    user_profiles: tuple[UserProfile, ...] = ()
    applications: tuple[CorrelatedApplication, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    app_evidence_links: tuple[ApplicationEvidenceLink, ...] = ()
    user_data_findings: tuple[UserDataFinding, ...] = ()
    warnings: tuple[WarningRecord, ...] = ()


# ---------------------------------------------------------------------------
# Typed UI events (SDD §2.19)
# ---------------------------------------------------------------------------

# kw_only=True is load-bearing: every UiEvent field carries a default, while
# subclass events declare required fields (ProgressEvent.stage,
# WarningEvent.warning, ScanCompletedEvent.session_id, ...).  Without kw_only
# on the base, class creation raises
#     TypeError: non-default argument follows default argument
# and the module fails to import.  Keyword-only base fields keep the generated
# signatures legal, e.g.:
#     ProgressEvent("registry", source_id=..., *, event_id=..., emitted_at=...)
@dataclass(frozen=True, slots=True, kw_only=True)
class UiEvent:
    """Base of all worker -> UI messages (SDD §5 Observer/Queue pattern).

    The UI reads these exclusively from a ``queue.Queue`` on the Tkinter
    thread.  Events are immutable value objects carrying DTOs or counters —
    never widgets, cursors, connections, or live resources — so they are
    safe to enqueue from any worker thread.
    """

    event_id: str = field(default_factory=new_id)
    emitted_at: str = field(default_factory=utc_now_iso)
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProgressEvent(UiEvent):
    """Throttled progress; the coordinator coalesces per-row updates into
    these (SDD §2.19: never one UI event per evidence row)."""

    stage: str
    completed: int = 0
    total: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SourcePreparedEvent(UiEvent):
    """A source finished safe, read-only preparation."""

    source: SourceRecord


@dataclass(frozen=True, slots=True)
class EvidenceBatchPersistedEvent(UiEvent):
    """A bounded batch of evidence rows was committed (SDD §2.19)."""

    batch_size: int
    total_persisted: int
    stage: str = "evidence"


@dataclass(frozen=True, slots=True)
class UserProfileParsedEvent(UiEvent):
    """One user profile was parsed and persisted."""

    profile: UserProfile
    total_parsed: int = 0


@dataclass(frozen=True, slots=True)
class PortableCandidateEvent(UiEvent):
    """One portable candidate was discovered from persisted evidence."""

    candidate: PortableCandidate
    total_found: int = 0


@dataclass(frozen=True, slots=True)
class ApplicationCorrelatedEvent(UiEvent):
    """One application identity was correlated and persisted."""

    application: CorrelatedApplication
    total_correlated: int = 0


@dataclass(frozen=True, slots=True)
class UserDataFindingEvent(UiEvent):
    """One deduplicated user-data finding was persisted."""

    finding: UserDataFinding
    total_found: int = 0


@dataclass(frozen=True, slots=True)
class WarningEvent(UiEvent):
    """A persisted warning that the user should see (SDD §4.2/§4.3)."""

    warning: WarningRecord


@dataclass(frozen=True, slots=True)
class ScanCompletedEvent(UiEvent):
    """The active scan finished successfully; mounts are being released."""

    session_id: str
    summary: ScanSummary


@dataclass(frozen=True, slots=True)
class ScanFailedEvent(UiEvent):
    """The scan failed without a critical I/O condition (SDD §4.5).

    The message must be calm and non-blaming (SDD §4.6); already-persisted
    results are preserved in the session.
    """

    session_id: str | None
    message: str
    summary: ScanSummary | None = None


@dataclass(frozen=True, slots=True)
class CriticalIoFailureEvent(UiEvent):
    """A drive-level I/O failure occurred (README §5.13).

    The coordinator stops source access immediately and does *not* retry;
    the UI presents the calm critical-failure state.
    """

    message: str
    device_path: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorEvent(UiEvent):
    """Generic non-I/O error notification for the status bar/tooltip."""

    message: str
    category: WarningCategory = WarningCategory.GENERAL
