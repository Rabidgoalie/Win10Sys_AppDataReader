"""Versioned, data-driven configuration for offline registry evidence.

Implements SDD §2.5 (``src/config/evidence_locations.py``) and encodes, as
inert data, the normative evidence-location tables of SRS Appendix A:

* every supported registry evidence root (machine, system, per-user,
  per-user class, and profile-resolution roots);
* the registry-side evidence-type vocabulary and per-root metadata;
* the hive-type identifiers consumed by the hive locator and registry
  parser (SDD §2.9 / §2.10);
* the deterministic confidence defaults per evidence root;
* the deterministic enumeration bounds for registry evidence (SRS FR-2.3,
  DDD §4, matching the ``ScanOptions`` defaults);
* the deterministic ``SYSTEM\\Select`` control-set resolution policy
  (SRS Appendix A.2, README §5.4).

Safety contract
---------------
This module is *pure data*. It performs no I/O, no subprocess calls, no
network access, and no filesystem reads or writes of any kind. It never
touches a scanned source drive: it only describes *where* evidence may live
inside offline hives and *how much* may be enumerated. The read-only
guarantees for source media are enforced by ``mount_manager`` and the
ingestion layers that consume this configuration; this module neither
depends on them nor can violate them.

Thread safety
-------------
Every name exported by this module is an immutable object created exactly
once at import time (``Final`` constants, frozen dataclass instances,
tuples, and module-level dicts that are never mutated afterwards). All
consumers may read them from any thread without synchronization; every
helper function here is a pure function with no shared mutable state.

Extensibility (SRS FR-2.2 / NFR-4)
----------------------------------
New evidence locations are added by appending one ``EvidenceRootSpec`` to a
registry tuple below. The registry parser iterates these specs generically,
so no parser redesign is required. Adding a root does not require changing
``_REQUIRED_EVIDENCE_TYPES`` (that set is the Appendix A *minimum*), though
new roots are still fully validated at import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, Mapping, Protocol

__all__ = [
    # Versioning
    "EVIDENCE_LOCATIONS_VERSION",
    # Hive identifiers
    "HIVE_SOFTWARE",
    "HIVE_SYSTEM",
    "HIVE_DEFAULT",
    "HIVE_NTUSER",
    "HIVE_USRCLASS",
    "HIVE_TYPES",
    "HIVE_FILE_NAMES",
    "HIVE_ROOT_COMPONENTS",
    "MACHINE_HIVES",
    "USER_LIKE_HIVES",
    # Confidence vocabulary
    "ConfidenceLevel",
    "CONFIDENCE_LEVELS",
    # Evidence root model
    "EvidenceKind",
    "EvidenceRootSpec",
    # Placeholders and WOW64
    "WOW64_NODE",
    "SID_PLACEHOLDER",
    "CONTROL_SET_PLACEHOLDER",
    # SYSTEM control-set policy (SRS Appendix A.2)
    "SYSTEM_SELECT_PATH",
    "SELECT_VALUE_NAMES",
    "CONTROL_SET_PRIORITY_ORDER",
    # Key-name filters (data-driven pattern configuration)
    "CONTROL_SET_KEY_PATTERN",
    "SID_KEY_PATTERN",
    "GUID_KEY_PATTERN",
    "PROGID_KEY_PATTERN",
    "EXTENSION_KEY_PATTERN",
    "PACKAGE_FAMILY_KEY_PATTERN",
    # Configured roots
    "REGISTRY_EVIDENCE_ROOTS",
    "PROFILE_RESOLUTION_ROOTS",
    "REGISTRY_EVIDENCE_TYPE_KEYS",
    "root_by_evidence_type",
    "roots_for_hive",
    "profile_resolution_roots_for_hive",
    "subkey_name_pattern_for",
    "is_wow64_root",
    # Path helpers
    "hive_relative_path",
    "expand_placeholders",
    # Bounds
    "RegistryBounds",
    "DEFAULT_REGISTRY_BOUNDS",
    "BoundsProvider",
    "resolve_registry_bounds",
]


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

#: Version of the evidence-location configuration. Persisted in
#: ``SCAN_SESSION.scan_options_json`` via ``ScanOptions.evidence_locations_version``
#: and stamped into exported reports (SRS FR-6.1/FR-6.3). Bump the major
#: component whenever a root is removed, renamed, or re-classified; bump the
#: minor component when roots are added or confidence defaults change.
EVIDENCE_LOCATIONS_VERSION: Final[str] = "1.0.0"


# ---------------------------------------------------------------------------
# Hive type identifiers (SDD §2.9, SRS Appendix A)
# ---------------------------------------------------------------------------
#
# These are stable string identifiers owned by this configuration. The
# registry parser is responsible for coercing them into the model's
# ``HiveType`` enum before persistence; keeping the configuration free of a
# hard enum dependency keeps it importable and unit-testable in isolation
# (NFR-10).

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

#: Machine hives located on the primary Windows source (SDD §2.9).
MACHINE_HIVES: Final[tuple[str, ...]] = (HIVE_SOFTWARE, HIVE_SYSTEM)

#: Hives with the per-user layout. The ``DEFAULT`` hive has the same key
#: layout as ``NTUSER.DAT``; per-user roots therefore apply to both. Default
#: and system profiles are marked as such by the profile parser (SRS FR-2.5)
#: and are not treated as normal user data owners.
USER_LIKE_HIVES: Final[tuple[str, ...]] = (HIVE_NTUSER, HIVE_DEFAULT)

#: Mapping of configuration identifiers to offline hive file names
#: (informational; consumed by the hive locator for matching, SDD §2.9).
HIVE_FILE_NAMES: Final[Mapping[str, str]] = {
    HIVE_SOFTWARE: "SOFTWARE",
    HIVE_SYSTEM: "SYSTEM",
    HIVE_DEFAULT: "DEFAULT",
    HIVE_NTUSER: "NTUSER.DAT",
    HIVE_USRCLASS: "UsrClass.dat",
}

#: The root key name *inside* each hive file. For ``SOFTWARE``, ``SYSTEM``
#: and per-user hives, Appendix A paths begin with this component; the
#: registry parser strips it when looking keys up inside a hive (see
#: :func:`hive_relative_path`). ``USRCLASS`` paths in this configuration are
#: already hive-relative, so no root component is defined for it.
HIVE_ROOT_COMPONENTS: Final[Mapping[str, str]] = {
    HIVE_SOFTWARE: "SOFTWARE",
    HIVE_SYSTEM: "SYSTEM",
    HIVE_DEFAULT: "Software",
    HIVE_NTUSER: "Software",
}


# ---------------------------------------------------------------------------
# Confidence vocabulary (SRS FR-2.7 / FR-4.9)
# ---------------------------------------------------------------------------

#: The three confidence levels, using exactly the user-facing spellings
#: mandated by SRS FR-2.7/FR-4.9 and matching the model's ``Confidence``
#: enum values. The registry parser coerces these strings into the model
#: enum before persistence.
ConfidenceLevel = Literal["Low", "Medium", "High"]

CONFIDENCE_LEVELS: Final[tuple[str, ...]] = ("Low", "Medium", "High")


# ---------------------------------------------------------------------------
# Evidence root model
# ---------------------------------------------------------------------------

_EVIDENCE_TYPE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")


class EvidenceKind(StrEnum):
    """How a configured root is enumerated (SDD §2.10).

    The registry parser switches on this value; it is part of the stable
    configuration contract, not a parser detail.
    """

    #: Each immediate subkey of the root is one evidence unit. The parser
    #: reads values inside each admitted subkey, bounded by
    #: ``max_values_per_key`` (e.g. ``Uninstall`` product subkeys).
    SUBKEYS = "subkeys"

    #: Each value under the root key is one evidence unit (e.g. the
    #: ``Run`` key, ``SharedDLLs``).
    VALUES = "values"

    #: The presence of the key itself is the evidence (e.g. optional
    #: AppModel/Appx containers where subkey structure is unstable).
    KEY_ONLY = "key_only"


@dataclass(frozen=True, slots=True)
class EvidenceRootSpec:
    """One supported registry evidence location (SRS Appendix A).

    All fields are inert data. The registry parser must:

    * treat ``path`` as case-insensitive when resolving keys against a hive;
    * expand declared placeholders with :func:`expand_placeholders` and skip
      the root (with a warning, never a crash) when a placeholder cannot be
      resolved;
    * filter enumerated subkey names with :func:`subkey_name_pattern_for`
      when a pattern is configured;
    * respect ``usage_evidence_only`` (UserAssist is usage evidence, never
      installation proof — SRS Appendix A.3);
    * apply ``decode_rot13`` to value data where appropriate and turn decode
      failures into warnings, never exceptions (SRS Appendix A.3, README §5.6);
    * treat ``best_effort`` roots as lower-alarmance: a missing or partially
      unreadable best-effort root downgrades warnings, while a failed
      primary root raises a higher-severity warning;
    * never exceed the configured :class:`RegistryBounds`.
    """

    #: Stable, versioned evidence-type key (lowercase ``snake_case``). This is
    #: the configuration-level identity for the evidence produced from this
    #: root; the registry parser maps it to the model's ``EvidenceType``
    #: enum before persisting ``DISCOVERY_EVIDENCE`` rows (DDD §4).
    evidence_type: str

    #: Hive identifier (one of :data:`HIVE_TYPES`).
    hive: str

    #: Registry key path exactly as written in SRS Appendix A. Backslash
    #: separators only. ``""`` means the hive root itself. May contain the
    #: declared placeholders ``<SID>`` and ``<CONTROL_SET>``.
    path: str

    #: Enumeration strategy for this root.
    kind: EvidenceKind

    #: Human-readable purpose (Appendix A wording), surfaced in reports and
    #: in user-facing rationale text (SRS FR-7.1).
    purpose: str

    #: Best-effort root: missing or partially unreadable is tolerated with a
    #: lower-severity warning (Appendix A "best-effort" locations).
    best_effort: bool = False

    #: Usage evidence only; never treated as installation proof
    #: (``UserAssist`` — SRS Appendix A.3).
    usage_evidence_only: bool = False

    #: Value data may be ROT13-encoded; decode where appropriate, warn on
    #: decode failure (``UserAssist`` — SRS Appendix A.3, README §5.6).
    decode_rot13: bool = False

    #: Default confidence for evidence produced from this root
    #: (SRS FR-2.7). Correlation may raise or lower the final record
    #: confidence, but must not exceed the evidence-level confidence
    #: recorded here without additional corroborating evidence.
    default_confidence: ConfidenceLevel = "Medium"

    #: Placeholders that appear in ``path`` and must be expanded at parse
    #: time. May only be :data:`SID_PLACEHOLDER` / :data:`CONTROL_SET_PLACEHOLDER`.
    placeholders: tuple[str, ...] = ()

    #: Optional ``re.Pattern`` source applied to enumerated *subkey names*
    #: (e.g. ProgID, GUID, package-family-name filters). ``None`` means all
    #: subkeys are admitted (subject to bounds).
    subkey_name_pattern: str | None = None

    #: For ``SUBKEYS`` roots that carry their evidence one level deeper
    #: (``Applications\*\shell\open\command``): the relative sub-path under
    #: each admitted subkey where values are read.
    nested_value_path: str | None = None

    #: Optional specific value name of interest under the root (or under
    #: ``nested_value_path``); ``None`` means all values are evidence units.
    value_name: str | None = None

    def __post_init__(self) -> None:
        # Fail fast on developer configuration errors. These validations run
        # at import time for every spec in this module, so a malformed root
        # can never be handed to the registry parser at scan time.
        if not _EVIDENCE_TYPE_RE.fullmatch(self.evidence_type):
            raise ValueError(
                f"evidence_type must be lowercase snake_case, got {self.evidence_type!r}"
            )
        if self.hive not in HIVE_TYPES:
            raise ValueError(f"unknown hive identifier: {self.hive!r}")
        if self.default_confidence not in CONFIDENCE_LEVELS:
            raise ValueError(
                f"invalid default_confidence: {self.default_confidence!r}"
            )

        path = self.path
        if path:
            if "/" in path:
                raise ValueError(
                    f"registry paths must use backslash separators: {path!r}"
                )
            components = path.split("\\")
            if any(not component for component in components):
                raise ValueError(f"empty path component in: {path!r}")
            root_component = HIVE_ROOT_COMPONENTS.get(self.hive)
            if root_component is not None and components[0].lower() != root_component.lower():
                raise ValueError(
                    f"path {path!r} must begin with hive root component "
                    f"{root_component!r} for hive {self.hive!r}"
                )

        declared = set(self.placeholders)
        allowed = {SID_PLACEHOLDER, CONTROL_SET_PLACEHOLDER}
        if not declared <= allowed:
            raise ValueError(
                f"undeclared placeholder(s) in {self.evidence_type!r}: "
                f"{sorted(declared - allowed)}"
            )
        for placeholder in allowed:
            present = placeholder in path
            if present and placeholder not in declared:
                raise ValueError(
                    f"{placeholder} appears in path but is not declared for "
                    f"{self.evidence_type!r}"
                )
            if not present and placeholder in declared:
                raise ValueError(
                    f"{placeholder} is declared but absent from path for "
                    f"{self.evidence_type!r}"
                )

        if self.subkey_name_pattern is not None:
            try:
                re.compile(self.subkey_name_pattern)
            except re.error as exc:
                raise ValueError(
                    f"invalid subkey_name_pattern for {self.evidence_type!r}: {exc}"
                ) from exc

        if self.nested_value_path is not None:
            if not self.nested_value_path or "/" in self.nested_value_path:
                raise ValueError(
                    f"invalid nested_value_path for {self.evidence_type!r}: "
                    f"{self.nested_value_path!r}"
                )


# ---------------------------------------------------------------------------
# Placeholders, WOW64, and SYSTEM control-set policy (SRS Appendix A.2)
# ---------------------------------------------------------------------------

#: The 32-bit registry view node on 64-bit Windows (README §5.5). WOW64
#: variants are declared as explicit roots (as in Appendix A) so the
#: ``include_wow64`` option can be applied as a simple path filter.
WOW64_NODE: Final[str] = "Wow6432Node"

#: Placeholder for a per-user profile SID (Appendix A.1:
#: ``...\\Installer\\UserData\\<SID>\\Products``).
SID_PLACEHOLDER: Final[str] = "<SID>"

#: Placeholder for the resolved active control set (Appendix A.2:
#: ``SYSTEM\\<ResolvedControlSet>\\...``).
CONTROL_SET_PLACEHOLDER: Final[str] = "<CONTROL_SET>"

#: ``SYSTEM\\Select`` holds the ``Default`` / ``LastKnownGood`` / ``Current``
#: DWORD values used to resolve the active control set offline.
SYSTEM_SELECT_PATH: Final[str] = "SYSTEM\\Select"

SELECT_VALUE_NAMES: Final[tuple[str, ...]] = ("Default", "LastKnownGood", "Current")

#: Deterministic resolution order (SRS Appendix A.2, README §5.4):
#: 1. ``Default`` if valid, 2. ``LastKnownGood`` if valid, 3. first available
#: ``ControlSet00X`` key in numeric order, 4. skip SYSTEM evidence with a
#: warning. The *logic* lives in the registry parser; this module owns the
#: policy data it consumes.
CONTROL_SET_PRIORITY_ORDER: Final[tuple[str, ...]] = ("Default", "LastKnownGood")

#: A valid control-set key name inside the ``SYSTEM`` hive.
CONTROL_SET_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^ControlSet00\d+$")

#: A valid Windows SID (used to filter ``ProfileList`` subkeys).
SID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^S-1-\d+(?:-\d+)*$")

#: A registry GUID key name (CLSID / AppID / MSI product subkeys).
GUID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
)

#: A programmatic identifier (ProgID) key name: starts with a letter and
#: contains at least one dot. Deliberately conservative — it admits
#: ``Vendor.Product.1``-style keys and rejects extension keys (leading dot),
#: container keys (``CLSID``, ``Applications``), and bare names.
PROGID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9._+-]*\.[A-Za-z0-9._+-]*$"
)

#: A per-user file-association key name (a top-level ``.ext`` key in the
#: user's class hive, e.g. ``.docx``).
EXTENSION_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\.[A-Za-z0-9]{1,10}$")

#: An AppX/MSIX package family name (e.g.
#: ``Microsoft.WindowsNotepad_8wekyb3d8bbwe``): alphanumerics/dots with at
#: least one underscore. Used only for best-effort per-user modern-class
#: evidence (Appendix A.4).
PACKAGE_FAMILY_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9.]*_[A-Za-z0-9]+$"
)


# ---------------------------------------------------------------------------
# Configured evidence roots — SRS Appendix A (exact normative paths)
# ---------------------------------------------------------------------------
#
# Order is presentation order only; consumers must not rely on it. Every
# path below is copied verbatim from SRS Appendix A (case included; registry
# lookups are performed case-insensitively by the parser).


#: Machine ``SOFTWARE`` hive roots (Appendix A.1).
_SOFTWARE_ROOTS: Final[tuple[EvidenceRootSpec, ...]] = (
    EvidenceRootSpec(
        evidence_type="uninstall_native",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        kind=EvidenceKind.SUBKEYS,
        purpose="Primary installed application evidence.",
        default_confidence="High",
    ),
    EvidenceRootSpec(
        evidence_type="uninstall_wow64",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        kind=EvidenceKind.SUBKEYS,
        purpose="32-bit installed application evidence on 64-bit Windows.",
        default_confidence="High",
    ),
    EvidenceRootSpec(
        evidence_type="app_paths",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths",
        kind=EvidenceKind.SUBKEYS,
        purpose="Registered executable launch paths.",
        default_confidence="High",
    ),
    EvidenceRootSpec(
        evidence_type="msi_products",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Classes\\Installer\\Products",
        kind=EvidenceKind.SUBKEYS,
        purpose="Windows Installer product evidence.",
        default_confidence="High",
    ),
    EvidenceRootSpec(
        evidence_type="msi_user_products",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\<SID>\\Products",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user Windows Installer product evidence.",
        default_confidence="Medium",
        placeholders=(SID_PLACEHOLDER,),
    ),
    EvidenceRootSpec(
        evidence_type="msi_upgrade_codes",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Classes\\Installer\\UpgradeCodes",
        kind=EvidenceKind.SUBKEYS,
        purpose="Windows Installer upgrade evidence.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="msi_folders",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\Folders",
        kind=EvidenceKind.SUBKEYS,
        purpose="Installer-managed folder evidence.",
        default_confidence="Low",
    ),
    EvidenceRootSpec(
        evidence_type="shared_dlls",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\SharedDLLs",
        kind=EvidenceKind.VALUES,
        purpose="Installer-registered shared DLL evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="startup_run",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
        kind=EvidenceKind.VALUES,
        purpose="Startup registration evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="startup_run_once",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
        kind=EvidenceKind.VALUES,
        purpose="Startup registration evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="startup_run_once_ex",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnceEx",
        kind=EvidenceKind.SUBKEYS,
        purpose="Startup registration evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="startup_policy_run",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer\\Run",
        kind=EvidenceKind.VALUES,
        purpose="Policy-based startup evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="clsid",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Classes\\CLSID",
        kind=EvidenceKind.SUBKEYS,
        purpose="COM registration evidence, best-effort and bounded.",
        default_confidence="Low",
        best_effort=True,
        subkey_name_pattern=GUID_KEY_PATTERN.pattern,
    ),
    EvidenceRootSpec(
        evidence_type="appid",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Classes\\AppID",
        kind=EvidenceKind.SUBKEYS,
        purpose="COM application identifier evidence, best-effort and bounded.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="typelib",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Classes\\TypeLib",
        kind=EvidenceKind.SUBKEYS,
        purpose="Type library evidence, best-effort and bounded.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="progids",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Classes",
        kind=EvidenceKind.SUBKEYS,
        purpose="Programmatic identifier evidence, best-effort and bounded.",
        default_confidence="Low",
        best_effort=True,
        subkey_name_pattern=PROGID_KEY_PATTERN.pattern,
    ),
    EvidenceRootSpec(
        evidence_type="browser_helper_objects",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Browser Helper Objects",
        kind=EvidenceKind.SUBKEYS,
        purpose="Browser helper object evidence.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="appmodel",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AppModel",
        kind=EvidenceKind.KEY_ONLY,
        purpose="Modern application evidence, best-effort.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="appx",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Appx",
        kind=EvidenceKind.SUBKEYS,
        purpose="AppX package evidence, best-effort.",
        default_confidence="Low",
        best_effort=True,
    ),
)


#: Machine ``SYSTEM`` hive roots (Appendix A.2). The control-set placeholder
#: is expanded with the control set resolved from ``SYSTEM\\Select`` per
#: :data:`CONTROL_SET_PRIORITY_ORDER`; if no control set can be resolved the
#: parser skips SYSTEM evidence and records a warning (README §5.4).
_SYSTEM_ROOTS: Final[tuple[EvidenceRootSpec, ...]] = (
    EvidenceRootSpec(
        evidence_type="services",
        hive=HIVE_SYSTEM,
        path="SYSTEM\\<CONTROL_SET>\\Services",
        kind=EvidenceKind.SUBKEYS,
        purpose="Service and driver installation evidence, bounded.",
        default_confidence="Low",
        placeholders=(CONTROL_SET_PLACEHOLDER,),
    ),
    EvidenceRootSpec(
        evidence_type="appcompat_cache",
        hive=HIVE_SYSTEM,
        path="SYSTEM\\<CONTROL_SET>\\Control\\Session Manager\\AppCompatCache",
        kind=EvidenceKind.SUBKEYS,
        purpose="Application compatibility cache evidence, best-effort.",
        default_confidence="Low",
        best_effort=True,
        placeholders=(CONTROL_SET_PLACEHOLDER,),
    ),
)


#: Per-user ``NTUSER.DAT`` hive roots (Appendix A.3). The same roots apply to
#: the ``DEFAULT`` hive (identical key layout); see :data:`USER_LIKE_HIVES`.
#: Shell-folder roots are deliberately listed under
#: :data:`PROFILE_RESOLUTION_ROOTS` (Appendix A.6) rather than here: they are
#: consumed by the profile parser and are not emitted as application evidence.
_NTUSER_ROOTS: Final[tuple[EvidenceRootSpec, ...]] = (
    EvidenceRootSpec(
        evidence_type="ntuser_uninstall",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user installed application evidence.",
        default_confidence="High",
    ),
    EvidenceRootSpec(
        evidence_type="ntuser_uninstall_wow64",
        hive=HIVE_NTUSER,
        path="Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user 32-bit installed application evidence.",
        default_confidence="High",
    ),
    EvidenceRootSpec(
        evidence_type="ntuser_app_paths",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\App Paths",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user executable registration evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="ntuser_run",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        kind=EvidenceKind.VALUES,
        purpose="Per-user startup evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="ntuser_run_once",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
        kind=EvidenceKind.VALUES,
        purpose="Per-user startup evidence.",
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="user_assist",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\UserAssist",
        kind=EvidenceKind.SUBKEYS,
        purpose=(
            "Executed application evidence, best-effort. Usage evidence only, "
            "never installation proof; ROT13-decoded where possible, decode "
            "failures produce warnings."
        ),
        default_confidence="Low",
        best_effort=True,
        usage_evidence_only=True,
        decode_rot13=True,
    ),
    EvidenceRootSpec(
        evidence_type="muicache",
        hive=HIVE_NTUSER,
        path="Software\\Classes\\Local Settings\\Software\\Microsoft\\Windows\\Shell\\MuiCache",
        kind=EvidenceKind.SUBKEYS,
        purpose="Application display-name and path evidence.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="recent_docs",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RecentDocs",
        kind=EvidenceKind.SUBKEYS,
        purpose="Recent document path hints, best-effort.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="typed_paths",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\TypedPaths",
        kind=EvidenceKind.VALUES,
        purpose="Explorer typed-path hints, best-effort.",
        default_confidence="Low",
        best_effort=True,
    ),
    EvidenceRootSpec(
        evidence_type="feature_usage",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FeatureUsage",
        kind=EvidenceKind.SUBKEYS,
        purpose="Application usage hints, best-effort.",
        default_confidence="Low",
        best_effort=True,
    ),
)


#: Per-user ``UsrClass.dat`` hive roots (Appendix A.4). Paths are hive-relative
#: (no hive root component). ``usrclass_applications`` reads
#: ``Applications\<app>\shell\open\command`` via ``nested_value_path`` and
#: ``value_name`` (name/path only; no content inspection).
_USRCLASS_ROOTS: Final[tuple[EvidenceRootSpec, ...]] = (
    EvidenceRootSpec(
        evidence_type="usrclass_file_associations",
        hive=HIVE_USRCLASS,
        path="",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user file association keys.",
        default_confidence="Low",
        best_effort=True,
        subkey_name_pattern=EXTENSION_KEY_PATTERN.pattern,
    ),
    EvidenceRootSpec(
        evidence_type="usrclass_progids",
        hive=HIVE_USRCLASS,
        path="",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user ProgID keys.",
        default_confidence="Low",
        best_effort=True,
        subkey_name_pattern=PROGID_KEY_PATTERN.pattern,
    ),
    EvidenceRootSpec(
        evidence_type="usrclass_clsid",
        hive=HIVE_USRCLASS,
        path="CLSID",
        kind=EvidenceKind.SUBKEYS,
        purpose="Per-user CLSID keys, bounded.",
        default_confidence="Low",
        best_effort=True,
        subkey_name_pattern=GUID_KEY_PATTERN.pattern,
    ),
    EvidenceRootSpec(
        evidence_type="usrclass_applications",
        hive=HIVE_USRCLASS,
        path="Applications",
        kind=EvidenceKind.SUBKEYS,
        purpose=(
            "Executable launch-command evidence "
            "(``Applications\\*\\shell\\open\\command``), name/path only."
        ),
        default_confidence="Low",
        nested_value_path="shell\\open",
        value_name="command",
    ),
    EvidenceRootSpec(
        evidence_type="usrclass_modern_packages",
        hive=HIVE_USRCLASS,
        path="",
        kind=EvidenceKind.SUBKEYS,
        purpose="AppX/MSIX per-user class evidence, best-effort.",
        default_confidence="Low",
        best_effort=True,
        subkey_name_pattern=PACKAGE_FAMILY_KEY_PATTERN.pattern,
    ),
)


#: All configured application-evidence roots, in hive order
#: (machine SOFTWARE, machine SYSTEM, per-user, per-user class).
REGISTRY_EVIDENCE_ROOTS: Final[tuple[EvidenceRootSpec, ...]] = (
    *_SOFTWARE_ROOTS,
    *_SYSTEM_ROOTS,
    *_NTUSER_ROOTS,
    *_USRCLASS_ROOTS,
)


#: Profile-resolution roots (Appendix A.6). These are consumed by the user
#: profile parser (SDD §2.11) for SID/profile-path mapping and shell-folder
#: (Documents baseline) resolution. They are intentionally *not* part of
#: :data:`REGISTRY_EVIDENCE_ROOTS` so the registry parser does not emit them
#: as application evidence (SRS Appendix A.6).
PROFILE_RESOLUTION_ROOTS: Final[tuple[EvidenceRootSpec, ...]] = (
    EvidenceRootSpec(
        evidence_type="profile_list",
        hive=HIVE_SOFTWARE,
        path="SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList",
        kind=EvidenceKind.SUBKEYS,
        purpose="Maps profile SIDs to profile paths (Appendix A.6).",
        default_confidence="Medium",
        subkey_name_pattern=SID_KEY_PATTERN.pattern,
    ),
    EvidenceRootSpec(
        evidence_type="user_shell_folders",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders",
        kind=EvidenceKind.VALUES,
        purpose=(
            "User shell folder resolution; preferred Documents baseline "
            "(SRS FR-4.3, Appendix A.6)."
        ),
        default_confidence="Medium",
    ),
    EvidenceRootSpec(
        evidence_type="shell_folders",
        hive=HIVE_NTUSER,
        path="Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Shell Folders",
        kind=EvidenceKind.VALUES,
        purpose="Legacy fallback shell folder resolution (Appendix A.6).",
        default_confidence="Medium",
    ),
)


#: Every evidence-type key configured in this module (stable, versioned
#: vocabulary for the registry-side ``EvidenceType`` values, DDD §4).
#: Filesystem and manifest evidence-type keys are owned by the ingestion
#: modules that produce them; this module owns the registry-side keys.
REGISTRY_EVIDENCE_TYPE_KEYS: Final[tuple[str, ...]] = tuple(
    spec.evidence_type for spec in (*REGISTRY_EVIDENCE_ROOTS, *PROFILE_RESOLUTION_ROOTS)
)


# ---------------------------------------------------------------------------
# Root lookup helpers (pure, thread-safe)
# ---------------------------------------------------------------------------

# Populated once at import; read-only thereafter (see _validate_configuration).
_ROOT_INDEX: Final[dict[str, EvidenceRootSpec]] = {
    spec.evidence_type: spec
    for spec in (*REGISTRY_EVIDENCE_ROOTS, *PROFILE_RESOLUTION_ROOTS)
}

_COMPILED_SUBKEY_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    spec.evidence_type: re.compile(spec.subkey_name_pattern)
    for spec in (*REGISTRY_EVIDENCE_ROOTS, *PROFILE_RESOLUTION_ROOTS)
    if spec.subkey_name_pattern is not None
}


def root_by_evidence_type(evidence_type: str) -> EvidenceRootSpec | None:
    """Return the configured root for ``evidence_type``, or ``None``.

    Covers both application-evidence and profile-resolution roots. Callers
    receiving ``None`` must treat the type as unknown and record a warning
    rather than raising (defensive parsing contract, SRS FR-2.6).
    """
    return _ROOT_INDEX.get(evidence_type)


def roots_for_hive(hive: str) -> tuple[EvidenceRootSpec, ...]:
    """Application-evidence roots configured for ``hive``.

    ``DEFAULT`` returns the per-user (``NTUSER``) roots because the DEFAULT
    hive shares the NTUSER.DAT layout. An unknown hive identifier returns an
    empty tuple; the registry parser records a warning for that case — a
    configuration/locator mismatch must not crash the scan (SRS FR-2.6,
    SDD §4.2).
    """
    if hive == HIVE_SOFTWARE:
        return _SOFTWARE_ROOTS
    if hive == HIVE_SYSTEM:
        return _SYSTEM_ROOTS
    if hive in USER_LIKE_HIVES:
        return _NTUSER_ROOTS
    if hive == HIVE_USRCLASS:
        return _USRCLASS_ROOTS
    return ()


def profile_resolution_roots_for_hive(hive: str) -> tuple[EvidenceRootSpec, ...]:
    """Profile-resolution roots for ``hive`` (Appendix A.6).

    ``DEFAULT`` resolves to the same per-user shell-folder roots as
    ``NTUSER``. Unknown hives yield an empty tuple (caller warns).
    """
    if hive == HIVE_SOFTWARE:
        return (PROFILE_RESOLUTION_ROOTS[0],)  # profile_list
    if hive in USER_LIKE_HIVES:
        return (PROFILE_RESOLUTION_ROOTS[1], PROFILE_RESOLUTION_ROOTS[2])
    return ()


def subkey_name_pattern_for(spec: EvidenceRootSpec) -> re.Pattern[str] | None:
    """Compiled subkey-name filter for ``spec``, or ``None`` if unfiltered."""
    return _COMPILED_SUBKEY_PATTERNS.get(spec.evidence_type)


def is_wow64_root(spec: EvidenceRootSpec) -> bool:
    """True when the root lives under ``Wow6432Node`` (SRS FR-2.4, README §5.5).

    The registry parser uses this to honor the ``include_wow64`` scan option
    by simple path filtering; WOW64 variants are explicit roots in Appendix A
    rather than being derived dynamically.
    """
    return WOW64_NODE in spec.path


def hive_relative_path(spec: EvidenceRootSpec) -> str:
    """Key path *inside* the hive file, i.e. with the hive root component
    stripped (the form used by the offline hive parser for key lookup).

    ``SOFTWARE``/``SYSTEM``/per-user specs store the Appendix A form whose
    first component is the hive root name (``SOFTWARE``/``SYSTEM``/
    ``Software``); that component is stripped case-insensitively. ``USRCLASS``
    specs are already hive-relative. Placeholders are left in place — expand
    them with :func:`expand_placeholders` before lookup. An empty path stays
    empty (the hive root).
    """
    if not spec.path:
        return ""
    components = spec.path.split("\\")
    head = components[0].lower()
    strip_names = {spec.hive.lower()}
    root_component = HIVE_ROOT_COMPONENTS.get(spec.hive)
    if root_component is not None:
        strip_names.add(root_component.lower())
    if head in strip_names:
        return "\\".join(components[1:])
    return spec.path


def expand_placeholders(
    spec: EvidenceRootSpec,
    *,
    sid: str | None = None,
    control_set: str | None = None,
) -> str:
    """Resolve ``<SID>`` / ``<CONTROL_SET>`` placeholders in ``spec.path``.

    Raises ``ValueError`` when a declared placeholder has no usable value.
    The registry parser must catch this per root, skip that root, and record
    a warning — a missing SID or an unresolved control set degrades one
    evidence category, it must never abort the scan (SRS FR-2.6, SDD §4.2).
    """
    path = spec.path
    if SID_PLACEHOLDER in spec.placeholders:
        if not sid or "\\" in sid:
            raise ValueError(
                f"evidence type {spec.evidence_type!r} requires a valid profile SID"
            )
        path = path.replace(SID_PLACEHOLDER, sid)
    if CONTROL_SET_PLACEHOLDER in spec.placeholders:
        if not control_set:
            raise ValueError(
                f"evidence type {spec.evidence_type!r} requires a resolved control set"
            )
        if not CONTROL_SET_KEY_PATTERN.fullmatch(control_set):
            raise ValueError(
                f"control set {control_set!r} is not a valid ControlSet00X name"
            )
        path = path.replace(CONTROL_SET_PLACEHOLDER, control_set)
    return path


# ---------------------------------------------------------------------------
# Registry enumeration bounds (SRS FR-2.3, SDD §2.5 / §2.10, DDD §4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryBounds:
    """Deterministic enumeration bounds for offline registry evidence.

    Defaults match the ``ScanOptions`` defaults (DDD §4):

    * ``max_evidence_total``     — maximum evidence records per source
      (SRS FR-2.3 "maximum evidence records per source");
    * ``max_evidence_per_root``  — maximum evidence records per configured
      root;
    * ``max_subkeys_per_key``    — maximum registry subkeys examined per key;
    * ``max_values_per_key``     — maximum registry values examined per key.

    Filesystem, manifest, and directory-entry bounds are owned by their own
    configuration surfaces (``heuristic_patterns`` / ``ScanOptions``); this
    class owns the registry-specific bounds only, so each bound has exactly
    one authoritative default.

    When a bound is reached, the parser stops admitting further evidence for
    that category, records a warning, and continues with other categories
    (SRS FR-2.3 / FR-2.6).
    """

    max_evidence_total: int = 250_000
    max_evidence_per_root: int = 5_000
    max_subkeys_per_key: int = 2_000
    max_values_per_key: int = 2_000

    def __post_init__(self) -> None:
        for name in (
            "max_evidence_total",
            "max_evidence_per_root",
            "max_subkeys_per_key",
            "max_values_per_key",
        ):
            value = getattr(self, name)
            # ``bool`` is a subclass of ``int``; reject it explicitly so a
            # malformed options blob cannot silently set a bound to True/False.
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")


#: The single documented default bounds instance (SRS FR-2.3).
DEFAULT_REGISTRY_BOUNDS: Final[RegistryBounds] = RegistryBounds()


class BoundsProvider(Protocol):
    """Structural view of the bound fields of ``models.RegistryParseOptions``.

    Using a protocol (instead of importing the model) keeps this
    configuration module free of any dependency on the persistence/DTO layer,
    while remaining fully statically checkable: ``RegistryParseOptions``
    satisfies this protocol structurally.
    """

    max_evidence_total: int | None
    max_evidence_per_root: int | None
    max_subkeys_per_key: int | None
    max_values_per_key: int | None


def _as_positive_int(value: int | None, fallback: int) -> int:
    """Defensively coerce an optional operator-supplied bound.

    ``None`` (the ``RegistryParseOptions`` default) and any invalid value
    (non-int, bool, or non-positive) fall back to the documented default.
    A corrupt or tampered scan-options blob must never abort a scan
    (defensive parsing contract, SRS FR-2.6 / FR-7.2).
    """
    if value is None:
        return fallback
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return fallback
    return value


def resolve_registry_bounds(options: BoundsProvider) -> RegistryBounds:
    """Resolve operator bounds against the documented defaults.

    ``models.RegistryParseOptions`` fields default to ``None`` (SDD §2.10),
    meaning "use the configured defaults". This function is the *single*
    place where that resolution happens, so the defaults in
    :data:`DEFAULT_REGISTRY_BOUNDS` remain the sole authoritative source.
    Pure function; safe to call from any thread.
    """
    base = DEFAULT_REGISTRY_BOUNDS
    return RegistryBounds(
        max_evidence_total=_as_positive_int(
            options.max_evidence_total, base.max_evidence_total
        ),
        max_evidence_per_root=_as_positive_int(
            options.max_evidence_per_root, base.max_evidence_per_root
        ),
        max_subkeys_per_key=_as_positive_int(
            options.max_subkeys_per_key, base.max_subkeys_per_key
        ),
        max_values_per_key=_as_positive_int(
            options.max_values_per_key, base.max_values_per_key
        ),
    )


# ---------------------------------------------------------------------------
# Import-time configuration validation
# ---------------------------------------------------------------------------

#: The Appendix A *minimum* set of evidence types that must always be
#: configured. New roots may be added (NFR-4) without updating this set;
#: removing or renaming an Appendix A root is a breaking change that must
#: bump the major version of :data:`EVIDENCE_LOCATIONS_VERSION` and will be
#: rejected here.
_REQUIRED_EVIDENCE_TYPES: Final[frozenset[str]] = frozenset({
    # Appendix A.1 — machine SOFTWARE hive
    "uninstall_native",
    "uninstall_wow64",
    "app_paths",
    "msi_products",
    "msi_user_products",
    "msi_upgrade_codes",
    "msi_folders",
    "shared_dlls",
    "startup_run",
    "startup_run_once",
    "startup_run_once_ex",
    "startup_policy_run",
    "clsid",
    "appid",
    "typelib",
    "progids",
    "browser_helper_objects",
    "appmodel",
    "appx",
    # Appendix A.2 — machine SYSTEM hive
    "services",
    "appcompat_cache",
    # Appendix A.3 — per-user NTUSER.DAT hive
    "ntuser_uninstall",
    "ntuser_uninstall_wow64",
    "ntuser_app_paths",
    "ntuser_run",
    "ntuser_run_once",
    "user_assist",
    "muicache",
    "recent_docs",
    "typed_paths",
    "feature_usage",
    # Appendix A.4 — per-user UsrClass.dat hive
    "usrclass_file_associations",
    "usrclass_progids",
    "usrclass_clsid",
    "usrclass_applications",
    "usrclass_modern_packages",
    # Appendix A.6 — required profile-resolution locations
    "profile_list",
    "user_shell_folders",
    "shell_folders",
})


def _validate_configuration() -> None:
    """Fail fast on any configuration defect.

    Runs once at import. A configuration bug is a developer error, not user
    data; failing loudly at import is strictly safer than degrading at scan
    time, and it guarantees the registry parser never sees an inconsistent
    root table (SRS FR-2.2, NFR-10).
    """
    all_specs = (*REGISTRY_EVIDENCE_ROOTS, *PROFILE_RESOLUTION_ROOTS)
    seen: set[str] = set()
    for spec in all_specs:
        if spec.evidence_type in seen:
            raise ValueError(f"duplicate evidence_type: {spec.evidence_type!r}")
        seen.add(spec.evidence_type)
    missing = _REQUIRED_EVIDENCE_TYPES - seen
    if missing:
        raise ValueError(
            "configuration is missing required Appendix A evidence types: "
            + ", ".join(sorted(missing))
        )


_validate_configuration()
