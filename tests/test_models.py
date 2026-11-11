"""Phase-7 exit-criteria regression tests for :mod:`src.models`.

These are the tests the principal engineer's sign-off on the Phase-1
``models.py`` roadmap checkbox depends on.  Every test is pure-memory:
no root, no block devices, no subprocess, no network, no database
(NFR-10 / SDD §5 "Testability").

Run from the project root:

    python -m pytest tests/

Exit-criterion coverage map
---------------------------
1. Event construction smoke        -> TestUiEventConstruction
2. ScanOptions round-trip          -> TestScanOptionsRoundTrip
3. BlockDevice candidacy matrix    -> TestBlockDeviceCandidacy
4. Canonicalization totality fuzz  -> TestCanonicalizationTotality
5. Logical-drive validation        -> TestLogicalDriveValidation
6. identity-key idempotence        -> TestIdentityKeyIdempotence

``TestCodifiedReviewFindings`` additionally pins down the review's
"no other defects found" statements (exhaustive enum sets, exact
``to_row``/``from_row`` column maps, DDD §5 evidence-hash canonicalization,
UTC/UUID identifier conventions) so a future edit cannot silently regress
them.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.models import (
    SCHEMA_VERSION,
    AcquisitionMethod,
    BlockDevice,
    Confidence,
    CorrelatedApplication,
    CriticalIoFailureEvent,
    DiscoveryMethod,
    ErrorEvent,
    Evidence,
    EvidenceBatchPersistedEvent,
    EvidenceType,
    FindingLocationCategory,
    FingerprintStatus,
    IdentityBasis,
    PortableCandidate,
    PortableCandidateEvent,
    ProgressEvent,
    RegistryValue,
    RegistryValueType,
    ScanCompletedEvent,
    ScanFailedEvent,
    ScanOptions,
    ScanSession,
    ScanSummary,
    SeverityLevel,
    SourcePreparedEvent,
    SourceRecord,
    SourceRole,
    SourceStatus,
    SourceType,
    UiEvent,
    UserDataFinding,
    UserDataFindingEvent,
    UserProfile,
    UserProfileParsedEvent,
    WarningCategory,
    WarningEvent,
    WarningRecord,
    WarningSeverity,
    ApplicationCorrelatedEvent,
    PreparedSource,
    compute_evidence_hash,
    compute_identity_hash,
    name_publisher_version_key,
    new_id,
    safe_value_text,
    utc_now_iso,
    value_data_hash,
    canon_lower_path,
    canon_source_relative_path,
    canonical_path_structure,
)

# ---------------------------------------------------------------------------
# Shared module-level fixtures
# ---------------------------------------------------------------------------
# Frozen value objects built once per test session.  They are immutable
# (SDD §5 DTO discipline), so sharing them across tests is thread-safe and
# state-free.

SESSION_ID: str = new_id()
SOURCE_ID: str = new_id()
OTHER_SOURCE_ID: str = new_id()
EVENT_SOURCE_ID: str = "evt-src-1"


def _manifest_source_record(status: SourceStatus = SourceStatus.READY) -> SourceRecord:
    """A fully populated, schema-valid ``SCAN_SOURCE`` DTO (manifest source)."""
    return SourceRecord(
        source_id=SOURCE_ID,
        session_id=SESSION_ID,
        source_type=SourceType.MANIFEST_FILE,
        source_role=SourceRole.SECONDARY_DATA,
        acquisition_method=AcquisitionMethod.NTFSLS_MANIFEST,
        status=status,
        manifest_path="/safe/host/path/manifest.txt",
        fs_type="ntfs",
        label="DATA",
        uuid="11223344-5566-7788-99AA-BBCCDDEEFF00",
        size_bytes=128 * 1024**3,
        read_only=True,
    )


def _user_profile() -> UserProfile:
    return UserProfile(
        session_id=SESSION_ID,
        source_id=SOURCE_ID,
        username="jdoe",
        sid="S-1-5-21-1111111111-2222222222-3333333333-1001",
        profile_path="C:\\Users\\jdoe",
        normalized_profile_path="c:\\users\\jdoe",
        documents_path="C:\\Users\\jdoe\\Documents",
        desktop_path="C:\\Users\\jdoe\\Desktop",
        appdata_local_path="C:\\Users\\jdoe\\AppData\\Local",
        is_default_profile=False,
        is_system_profile=False,
    )


def _correlated_app() -> CorrelatedApplication:
    return CorrelatedApplication(
        session_id=SESSION_ID,
        source_id=SOURCE_ID,
        identity_basis=IdentityBasis.INSTALL_PATH,
        identity_key="C:\\Program Files\\Sample App",
        display_name="Sample App",
        discovery_method=DiscoveryMethod.REGISTRY,
        fingerprint_status=FingerprintStatus.REGISTERED,
        evidence_confidence=Confidence.HIGH,
        publisher="Sample Corp",
        version="1.2.3",
    )


def _portable_candidate() -> PortableCandidate:
    return PortableCandidate(
        source_id=OTHER_SOURCE_ID,
        candidate_path="S1:\\Apps\\7-Zip\\7z.exe",
        normalized_path="s1:\\apps\\7-zip\\7z.exe",
        display_name="7-Zip",
        basis=IdentityBasis.EXECUTABLE_BUNDLE,
        confidence=Confidence.MEDIUM,
        score=75,
        rationale="Executable bundle found on a secondary drive.",
    )


def _user_data_finding() -> UserDataFinding:
    return UserDataFinding(
        session_id=SESSION_ID,
        source_id=SOURCE_ID,
        path="C:\\Users\\jdoe\\Documents\\Photos",
        normalized_path="c:\\users\\jdoe\\documents\\photos",
        location_category=FindingLocationCategory.DOCUMENTS,
        severity_level=SeverityLevel.HIGH,
        confidence=Confidence.MEDIUM,
        rationale="Inside the resolved Documents baseline.",
        inside_documents=True,
        documents_root="C:\\Users\\jdoe\\Documents",
        owner_username="jdoe",
    )


def _warning_record() -> WarningRecord:
    return WarningRecord(
        session_id=SESSION_ID,
        source_id=SOURCE_ID,
        category=WarningCategory.REGISTRY,
        severity=WarningSeverity.WARNING,
        message="Hive SYSTEM could not be fully parsed; 12 keys skipped.",
    )


def _evidence() -> Evidence:
    """A registry evidence record carrying a structured ``RegistryValue``."""
    return Evidence(
        session_id=SESSION_ID,
        source_id=SOURCE_ID,
        evidence_type=EvidenceType.REGISTRY_UNINSTALL,
        confidence=Confidence.HIGH,
        hive_file_path="C:\\Windows\\System32\\config\\SOFTWARE",
        root_hive="SOFTWARE",
        key_path=(
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            r"\{8F36E1B5-6E6A-45F0-938A-C269E436F5E3}"
        ),
        value_name="DisplayName",
        registry_value=RegistryValue(
            name="DisplayName",
            value_type=RegistryValueType.STRING,
            data="Sample App\x00",
        ),
        user_sid="S-1-5-21-1111111111-2222222222-3333333333-1001",
        product_code="{8F36E1B5-6E6A-45F0-938A-C269E436F5E3}",
    )


# Garbage-tolerant registry value fixtures (exit criterion 4).
_VALUE_FIXTURES: list[tuple[str, RegistryValue]] = [
    ("sz-plain", RegistryValue(value_type=RegistryValueType.STRING,
                               data="C:\\Windows\\notepad.exe")),
    ("sz-trailing-nuls", RegistryValue(value_type=RegistryValueType.STRING,
                                       data="abc\x00\x00\x00")),
    ("sz-empty", RegistryValue(value_type=RegistryValueType.STRING, data="")),
    ("sz-none", RegistryValue(value_type=RegistryValueType.STRING, data=None)),
    ("es-expand", RegistryValue(value_type=RegistryValueType.EXPAND_STRING,
                                data="%USERPROFILE%\\Documents")),
    ("msz-tuple", RegistryValue(value_type=RegistryValueType.MULTI_STRING,
                                data=("a\x00", "b", "c"))),
    ("msz-bare-string", RegistryValue(value_type=RegistryValueType.MULTI_STRING,
                                      data="not-a-tuple")),
    ("msz-bare-bytes", RegistryValue(value_type=RegistryValueType.MULTI_STRING,
                                     data=b"\x00\x01raw")),
    ("msz-list", RegistryValue(value_type=RegistryValueType.MULTI_STRING,
                               data=["x", "y"])),
    ("msz-none", RegistryValue(value_type=RegistryValueType.MULTI_STRING, data=None)),
    ("dw-int", RegistryValue(value_type=RegistryValueType.DWORD, data=42)),
    ("dw-numeric-string", RegistryValue(value_type=RegistryValueType.DWORD, data="42")),
    ("dw-garbage-string", RegistryValue(value_type=RegistryValueType.DWORD,
                                        data="garbage")),
    ("dw-none", RegistryValue(value_type=RegistryValueType.DWORD, data=None)),
    ("dw-negative", RegistryValue(value_type=RegistryValueType.DWORD, data=-1)),
    ("dw-overflow", RegistryValue(value_type=RegistryValueType.DWORD, data=2**32 + 5)),
    ("qw-garbage-string", RegistryValue(value_type=RegistryValueType.QWORD, data="bogus")),
    ("qw-overflow", RegistryValue(value_type=RegistryValueType.QWORD, data=2**64 + 7)),
    ("bin-bytes", RegistryValue(value_type=RegistryValueType.BINARY, data=b"\x00\x01\xff")),
    ("bin-str", RegistryValue(value_type=RegistryValueType.BINARY, data="deadbeef")),
    ("bin-none", RegistryValue(value_type=RegistryValueType.BINARY, data=None)),
    ("bin-long", RegistryValue(value_type=RegistryValueType.BINARY, data=b"\x00" * 200)),
    ("none-ignored", RegistryValue(value_type=RegistryValueType.NONE,
                                   data="ignored payload")),
]
_VALUE_FIXTURE_IDS = [label for label, _ in _VALUE_FIXTURES]


# ---------------------------------------------------------------------------
# Exit criterion 1 — event construction smoke
# ---------------------------------------------------------------------------

class TestUiEventConstruction:
    """Every ``UiEvent`` subclass instantiates with its required positionals
    plus the ``source_id=`` keyword (would have caught F-01 at authoring)."""

    @pytest.fixture()
    def events(self) -> dict[str, UiEvent]:
        summary = ScanSummary(
            evidence_count=42,
            application_count=3,
            finding_count=7,
            warning_count=1,
        )
        return {
            # Base class: all fields keyword-only with defaults.
            "UiEvent": UiEvent(source_id=EVENT_SOURCE_ID),
            # Required positionals first, ``source_id=`` always as a keyword
            # (the base class is kw_only, so this is the only legal form).
            "ProgressEvent": ProgressEvent(
                "registry",
                completed=10,
                total=100,
                detail="SYSTEM control set 0x00000003",
                source_id=EVENT_SOURCE_ID,
            ),
            "SourcePreparedEvent": SourcePreparedEvent(
                _manifest_source_record(), source_id=EVENT_SOURCE_ID
            ),
            "EvidenceBatchPersistedEvent": EvidenceBatchPersistedEvent(
                500, 2500, stage="manifest", source_id=EVENT_SOURCE_ID
            ),
            "UserProfileParsedEvent": UserProfileParsedEvent(
                _user_profile(), total_parsed=2, source_id=EVENT_SOURCE_ID
            ),
            "PortableCandidateEvent": PortableCandidateEvent(
                _portable_candidate(), total_found=1, source_id=EVENT_SOURCE_ID
            ),
            "ApplicationCorrelatedEvent": ApplicationCorrelatedEvent(
                _correlated_app(), total_correlated=3, source_id=EVENT_SOURCE_ID
            ),
            "UserDataFindingEvent": UserDataFindingEvent(
                _user_data_finding(), total_found=7, source_id=EVENT_SOURCE_ID
            ),
            "WarningEvent": WarningEvent(_warning_record(), source_id=EVENT_SOURCE_ID),
            "ScanCompletedEvent": ScanCompletedEvent(
                SESSION_ID, summary, source_id=EVENT_SOURCE_ID
            ),
            "ScanFailedEvent": ScanFailedEvent(
                SESSION_ID,
                "Scan stopped early; the results saved so far were preserved.",
                source_id=EVENT_SOURCE_ID,
            ),
            "CriticalIoFailureEvent": CriticalIoFailureEvent(
                "The drive may be failing.",
                device_path="/dev/sdb1",
                source_id=EVENT_SOURCE_ID,
            ),
            "ErrorEvent": ErrorEvent(
                "Manifest file could not be read.",
                category=WarningCategory.MANIFEST,
                source_id=EVENT_SOURCE_ID,
            ),
        }

    def test_every_subclass_constructs_with_source_id_keyword(self, events: dict[str, UiEvent]) -> None:
        # Base + the 12 documented SDD §2.19 subclasses.
        assert len(events) == 13
        for name, event in events.items():
            assert isinstance(event, UiEvent), name
            assert event.source_id == EVENT_SOURCE_ID, name

    def test_event_metadata_is_well_formed(self, events: dict[str, UiEvent]) -> None:
        for name, event in events.items():
            # DDD §1: UTC ISO-8601 emission time.
            assert event.emitted_at.endswith("+00:00"), name
            datetime.fromisoformat(event.emitted_at)  # raises if malformed
            # 36-character UUID, matching every VARCHAR(36) id column.
            assert len(event.event_id) == 36, name
            try:
                uuid.UUID(event.event_id)
            except ValueError as exc:
                pytest.fail(f"{name}: event_id is not a UUID: {exc}")

    def test_required_positionals_are_enforced(self) -> None:
        # The kw_only base layout must not have accidentally swallowed the
        # required subclass positionals: omitting them must still fail.
        with pytest.raises(TypeError):
            ProgressEvent(source_id=EVENT_SOURCE_ID)            # missing stage
        with pytest.raises(TypeError):
            WarningEvent(source_id=EVENT_SOURCE_ID)             # missing warning
        with pytest.raises(TypeError):
            ScanCompletedEvent(source_id=EVENT_SOURCE_ID)       # missing session_id, summary
        with pytest.raises(TypeError):
            CriticalIoFailureEvent(source_id=EVENT_SOURCE_ID)   # missing message


# ---------------------------------------------------------------------------
# Exit criterion 2 — ScanOptions round-trip
# ---------------------------------------------------------------------------

class TestScanOptionsRoundTrip:
    """``from_json(to_json())`` equality, including the three SRS FR-2.3
    bounds, and documented defaults on malformed JSON."""

    def test_round_trip_preserves_all_fields_including_new_bounds(self) -> None:
        opts = ScanOptions(
            evidence_locations_version="3.1.0",
            heuristic_patterns_version="2.4.0",
            max_evidence_rows=123_456,
            max_findings=64,
            max_manifest_entries=77_777,
            max_evidence_per_registry_root=55,
            max_registry_subkeys_per_key=1_234,
            max_registry_values_per_key=4_321,
            max_filesystem_entries_per_source=50_000,
            max_directory_depth=9,
            max_directory_entries=3_000,
            include_wow64=False,
            include_user_hives=True,
        )
        rt = ScanOptions.from_json(opts.to_json())
        assert rt == opts
        # The three SRS FR-2.3 bounds, explicitly.
        assert rt.max_registry_subkeys_per_key == 1_234
        assert rt.max_registry_values_per_key == 4_321
        assert rt.max_filesystem_entries_per_source == 50_000
        # The serialized payload must carry them verbatim (scan_options_json,
        # DDD §4 requires the active enumeration bounds to be persisted).
        payload = json.loads(opts.to_json())
        for key in (
            "max_registry_subkeys_per_key",
            "max_registry_values_per_key",
            "max_filesystem_entries_per_source",
        ):
            assert key in payload, key

    def test_defaults_are_stable_for_absent_input(self) -> None:
        assert ScanOptions.from_json(None) == ScanOptions.from_json("")

    def test_malformed_json_falls_back_to_documented_defaults(self) -> None:
        defaults = ScanOptions.from_json(None)
        assert defaults == ScanOptions.from_json("{not valid json")
        assert defaults == ScanOptions.from_json("[1, 2, 3]")  # JSON, not an object
        assert defaults == ScanOptions.from_json('{"max_evidence_rows": "bogus"}')
        # Documented defaults: dataclass defaults + "unknown" versions.
        assert defaults.evidence_locations_version == "unknown"
        assert defaults.heuristic_patterns_version == "unknown"
        assert defaults.max_evidence_rows == 250_000
        assert defaults.max_findings == 5_000
        assert defaults.max_manifest_entries == 500_000
        assert defaults.max_evidence_per_registry_root == 5_000
        assert defaults.max_registry_subkeys_per_key == 2_000
        assert defaults.max_registry_values_per_key == 2_000
        assert defaults.max_filesystem_entries_per_source == 100_000
        assert defaults.max_directory_depth == 12
        assert defaults.max_directory_entries == 20_000
        assert defaults.include_wow64 is True
        assert defaults.include_user_hives is True

    def test_partial_json_defaults_per_bad_field(self) -> None:
        opts = ScanOptions.from_json(
            '{"max_evidence_rows": "bogus", "max_directory_depth": 7, "include_wow64": "yes"}'
        )
        assert opts.max_evidence_rows == 250_000  # bad int -> documented default
        assert opts.max_directory_depth == 7      # good int -> preserved
        assert opts.include_wow64 is True         # "yes" coerces to True

    def test_scan_session_round_trips_options(self) -> None:
        opts = ScanOptions(
            evidence_locations_version="1.0.0", heuristic_patterns_version="1.0.0"
        )
        session = ScanSession.new_active(opts)
        assert session.options() == opts
        row = session.to_row()
        hydrated = ScanSession.from_row(row)
        assert hydrated.to_row() == row
        assert hydrated.options() == opts
        assert hydrated.schema_version == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Exit criterion 3 — BlockDevice candidacy matrix
# ---------------------------------------------------------------------------

class TestBlockDeviceCandidacy:
    """The ``is_ntfs_candidate`` decision matrix (SDD §2.7 / SRS FR-1.2)."""

    @pytest.mark.parametrize(
        ("dev_type", "fs_type", "child_count", "expected"),
        [
            ("part", "ntfs", 0, True),      # NTFS partition: always a candidate
            ("part", "NTFS", 0, True),      # fs type is case-insensitive
            ("part", "ntfs", 5, True),      # partition child count is irrelevant
            ("disk", "ntfs", 0, True),      # whole disk, direct NTFS, no partitions
            ("disk", "ntfs", 2, False),     # disk with partitions: use the partitions
            ("loop", "ntfs", 0, False),     # loop devices never qualify
            ("rom", "ntfs", 0, False),
            ("disk", "ext4", 0, False),     # wrong filesystem
            ("part", "ext4", 0, False),
            ("disk", None, 0, False),       # unknown filesystem
            ("part", None, 0, False),
            ("part", "", 0, False),
        ],
    )
    def test_is_ntfs_candidate(
        self, dev_type: str, fs_type: str | None, child_count: int, expected: bool
    ) -> None:
        device = BlockDevice(
            device_path="/dev/sda",
            name="sda",
            dev_type=dev_type,
            fs_type=fs_type,
            child_count=child_count,
        )
        assert device.is_ntfs_candidate is expected

    def test_is_ntfs_partition_requires_part_type(self) -> None:
        part = BlockDevice("/dev/sda1", "sda1", "part", fs_type="ntfs")
        disk = BlockDevice("/dev/sda", "sda", "disk", fs_type="ntfs", child_count=0)
        assert part.is_ntfs_partition is True
        assert disk.is_ntfs_partition is False


# ---------------------------------------------------------------------------
# Exit criterion 4 — canonicalization totality fuzz
# ---------------------------------------------------------------------------

class TestCanonicalizationTotality:
    """``value_data_hash`` / ``safe_value_text`` are *total*: garbage DWORD
    strings, str-typed MULTI_SZ, str-typed BINARY, missing payloads — none
    may raise, and digests must be stable across repeated calls (DDD §5,
    SDD §4.2 defensive posture)."""

    @pytest.mark.parametrize(("label", "value"), _VALUE_FIXTURES, ids=_VALUE_FIXTURE_IDS)
    def test_hash_is_total_and_stable(self, label: str, value: RegistryValue) -> None:
        first = value_data_hash(value)
        second = value_data_hash(value)
        assert first == second
        assert re.fullmatch(r"[0-9a-f]{64}", first) is not None

    @pytest.mark.parametrize(("label", "value"), _VALUE_FIXTURES, ids=_VALUE_FIXTURE_IDS)
    def test_safe_value_text_is_total_and_stable(self, label: str, value: RegistryValue) -> None:
        text = safe_value_text(value)
        assert isinstance(text, str)
        assert safe_value_text(value) == text

    def test_absent_value_hashes_to_empty_string(self) -> None:
        # DDD §5: "If value_data is absent, value_data_hash is empty."
        assert value_data_hash(None) == ""
        assert safe_value_text(None) == ""

    def test_garbage_dword_degrades_to_zero(self) -> None:
        assert (
            value_data_hash(RegistryValue(value_type=RegistryValueType.DWORD, data="garbage"))
            == value_data_hash(RegistryValue(value_type=RegistryValueType.DWORD, data=0))
        )

    def test_bare_string_multisz_matches_single_element_tuple(self) -> None:
        bare = RegistryValue(value_type=RegistryValueType.MULTI_STRING, data="abc")
        tupled = RegistryValue(value_type=RegistryValueType.MULTI_STRING, data=("abc",))
        assert value_data_hash(bare) == value_data_hash(tupled)

    def test_str_typed_binary_matches_utf8_bytes(self) -> None:
        as_str = RegistryValue(value_type=RegistryValueType.BINARY, data="deadbeef")
        as_bytes = RegistryValue(
            value_type=RegistryValueType.BINARY, data="deadbeef".encode("utf-8")
        )
        assert value_data_hash(as_str) == value_data_hash(as_bytes)

    def test_binary_display_is_truncated_but_hash_is_not(self) -> None:
        long_blob = RegistryValue(value_type=RegistryValueType.BINARY, data=b"\x00" * 200)
        text = safe_value_text(long_blob)
        assert text.endswith("...")
        assert len(text) == 131  # 128 hex chars + "..."
        assert len(value_data_hash(long_blob)) == 64  # full digest, untruncated


# ---------------------------------------------------------------------------
# Exit criterion 5 — logical-drive validation
# ---------------------------------------------------------------------------

class TestLogicalDriveValidation:
    """``PreparedSource`` logical-drive allowlist (SDD §2.4): exactly ``C:``
    for the primary Windows source and ``S1:``, ``S2:``, ... for secondaries
    in addition order; nothing else may exist."""

    @staticmethod
    def _manifest_source(logical_drive: str) -> PreparedSource:
        return PreparedSource(
            source_id=SOURCE_ID,
            session_id=SESSION_ID,
            source_type=SourceType.MANIFEST_FILE,
            source_role=SourceRole.SECONDARY_DATA,
            logical_drive=logical_drive,
            manifest_path=Path("/safe/host/output/manifest.txt"),
            acquisition_method=AcquisitionMethod.NTFSLS_MANIFEST,
        )

    @staticmethod
    def _mounted_source(logical_drive: str) -> PreparedSource:
        role = SourceRole.WINDOWS_OS if logical_drive == "C:" else SourceRole.SECONDARY_DATA
        return PreparedSource(
            source_id=new_id(),
            session_id=SESSION_ID,
            source_type=SourceType.MOUNTED_BLOCK_DEVICE,
            source_role=role,
            logical_drive=logical_drive,
            mount_point=f"/run/win10drb/mounts/{logical_drive[:-1]}",
            origin_device_path="/dev/sda2",
            fs_type="ntfs",
        )

    @pytest.mark.parametrize("drive", ["C:", "S1:", "S12:"])
    def test_accepts_valid_mounted_logical_drives(self, drive: str) -> None:
        source = self._mounted_source(drive)
        assert source.logical_drive == drive
        assert source.read_only is True

    @pytest.mark.parametrize("drive", ["S1:", "S10:"])
    def test_accepts_valid_manifest_logical_drives(self, drive: str) -> None:
        source = self._manifest_source(drive)
        assert source.logical_drive == drive

    @pytest.mark.parametrize("drive", ["D:", "S0:", "c:", "s1:", "X:", "S1", ""])
    def test_rejects_invalid_logical_drives(self, drive: str) -> None:
        with pytest.raises(ValueError):
            self._manifest_source(drive)

    def test_rejects_writable_source(self) -> None:
        # Zero-write guarantee as a type property (core safety directive):
        # a writable PreparedSource must not be constructible at all.
        with pytest.raises(ValueError):
            PreparedSource(
                source_id=SOURCE_ID,
                session_id=SESSION_ID,
                source_type=SourceType.MOUNTED_BLOCK_DEVICE,
                source_role=SourceRole.SECONDARY_DATA,
                logical_drive="S1:",
                mount_point="/run/win10drb/mounts/S1",
                read_only=False,
            )

    def test_rejects_unpaired_acquisition_method(self) -> None:
        # A mounted source labeled with manifest acquisition violates the
        # DDD SCAN_SOURCE CHECK; it must fail at construction, not in SQLite.
        with pytest.raises(ValueError):
            PreparedSource(
                source_id=SOURCE_ID,
                session_id=SESSION_ID,
                source_type=SourceType.MOUNTED_BLOCK_DEVICE,
                source_role=SourceRole.SECONDARY_DATA,
                logical_drive="S1:",
                mount_point="/run/win10drb/mounts/S1",
                acquisition_method=AcquisitionMethod.NTFSLS_MANIFEST,
            )

    def test_rejects_windows_os_manifest_source(self) -> None:
        # Manifest-only sources are secondary only (DDD §3 / ADR-9).
        with pytest.raises(ValueError):
            PreparedSource(
                source_id=SOURCE_ID,
                session_id=SESSION_ID,
                source_type=SourceType.MANIFEST_FILE,
                source_role=SourceRole.WINDOWS_OS,
                logical_drive="C:",
                manifest_path=Path("/safe/host/output/manifest.txt"),
                acquisition_method=AcquisitionMethod.NTFSLS_MANIFEST,
            )


# ---------------------------------------------------------------------------
# Exit criterion 6 — identity-key idempotence
# ---------------------------------------------------------------------------

class TestIdentityKeyIdempotence:
    """``compute_identity_hash`` over a freshly built key equals the hash
    over the same key hydrated and re-canonicalized (DDD §6)."""

    def test_name_publisher_version_key_is_idempotent_through_hydration(self) -> None:
        fresh_key = name_publisher_version_key("  Notepad++  ", "  Notepad++ Team  ", " 8.6.3 ")
        app = CorrelatedApplication(
            session_id=SESSION_ID,
            source_id=SOURCE_ID,
            identity_basis=IdentityBasis.NAME_PUBLISHER_VERSION,
            identity_key=fresh_key,
            display_name="Notepad++",
            discovery_method=DiscoveryMethod.REGISTRY,
            fingerprint_status=FingerprintStatus.REGISTERED,
            evidence_confidence=Confidence.HIGH,
            publisher="Notepad++ Team",
            version="8.6.3",
        )
        hydrated = CorrelatedApplication.from_row(app.to_row())
        recomputed = compute_identity_hash(
            SOURCE_ID, IdentityBasis.NAME_PUBLISHER_VERSION, hydrated.identity_key
        )
        assert app.identity_hash == hydrated.identity_hash == recomputed

    def test_name_only_key_is_stable_with_or_without_optional_slots(self) -> None:
        without = name_publisher_version_key("Solo", None, None)
        with_empty = name_publisher_version_key("Solo", "", "")
        assert without == with_empty == "Solo"
        assert (
            compute_identity_hash(SOURCE_ID, IdentityBasis.NAME_PUBLISHER_VERSION, without)
            == compute_identity_hash(SOURCE_ID, IdentityBasis.NAME_PUBLISHER_VERSION, with_empty)
        )

    def test_missing_display_name_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            name_publisher_version_key("", "Publisher", "1.0")
        with pytest.raises(ValueError):
            name_publisher_version_key("   ", None, None)

    def test_install_path_basis_is_canonical_across_case_and_separators(self) -> None:
        h_native = compute_identity_hash(
            SOURCE_ID, IdentityBasis.INSTALL_PATH, "C:\\Program Files\\Sample App"
        )
        h_slash = compute_identity_hash(
            SOURCE_ID, IdentityBasis.INSTALL_PATH, "c:/program files/sample app"
        )
        assert h_native == h_slash

    def test_product_code_basis_is_canonical_across_guid_forms(self) -> None:
        h_braced = compute_identity_hash(
            SOURCE_ID, IdentityBasis.PRODUCT_CODE, "{12345678-1234-1234-1234-123456789ABC}"
        )
        h_bare = compute_identity_hash(
            SOURCE_ID, IdentityBasis.PRODUCT_CODE, "12345678123412341234123456789abc"
        )
        assert h_braced == h_bare

    def test_identity_hash_is_source_scoped(self) -> None:
        # DDD §6: the hash includes source_id, so identical keys on different
        # sources must never collapse (SDD §2.14 cross-source rule).
        key = name_publisher_version_key("App", "Pub", "1.0")
        h_a = compute_identity_hash(SOURCE_ID, IdentityBasis.NAME_PUBLISHER_VERSION, key)
        h_b = compute_identity_hash(OTHER_SOURCE_ID, IdentityBasis.NAME_PUBLISHER_VERSION, key)
        assert h_a != h_b


# ---------------------------------------------------------------------------
# F-02 regression lock — path-structure canonicalization
# ---------------------------------------------------------------------------

class TestPathCanonicalization:
    """Direct coverage of ``canonical_path_structure`` and its wrappers.

    Regression lock for F-02: ``canonical_path_structure`` previously used
    ``_PATH_SEPARATOR_RE.sub("\\", text)`` — a lone backslash is an invalid
    ``re.sub`` *replacement template* ("bad escape (end of pattern)"), so
    every call raised ``re.error`` at runtime even though the module compiled
    and imported cleanly.  Every test in this class executes the formerly
    broken line, so this defect class cannot return unnoticed.
    """

    def test_backslash_input_is_idempotent(self) -> None:
        assert canonical_path_structure("C:\\Users\\jdoe\\Documents") == "C:\\Users\\jdoe\\Documents"

    def test_forward_slashes_become_backslashes(self) -> None:
        assert canonical_path_structure("c:/users/jdoe") == "c:\\users\\jdoe"

    def test_separator_runs_collapse_to_single_backslash(self) -> None:
        assert canonical_path_structure("a//b\\\\c") == "a\\b\\c"

    def test_trailing_separators_stripped_and_drive_root_preserved(self) -> None:
        assert canonical_path_structure("C:\\") == "C:"
        assert canonical_path_structure("C:\\Users\\") == "C:\\Users"
        assert canonical_path_structure("c:/users/jdoe/") == "c:\\users\\jdoe"

    def test_unc_prefix_preserved(self) -> None:
        assert canonical_path_structure("\\\\server\\share\\file") == "\\\\server\\share\\file"

    def test_none_yields_empty_string(self) -> None:
        assert canonical_path_structure(None) == ""
        assert canon_lower_path(None) == ""
        assert canon_source_relative_path(None) == ""

    def test_canon_lower_path_lowercases_but_keeps_structure(self) -> None:
        assert canon_lower_path("C:\\Users\\JDOE") == "c:\\users\\jdoe"

    def test_canon_source_relative_path_strips_drive_prefix(self) -> None:
        assert canon_source_relative_path("C:\\Windows\\System32") == "windows\\system32"
        assert canon_source_relative_path("S1:\\Data") == "data"
        assert canon_source_relative_path("windows\\system32") == "windows\\system32"
        assert canon_source_relative_path("C:\\") == ""
        assert canon_source_relative_path("c:") == ""
        assert canon_source_relative_path("S1:\\") == ""


# ---------------------------------------------------------------------------
# Codified review findings (regression locks beyond the six criteria)
# ---------------------------------------------------------------------------

class TestCodifiedReviewFindings:
    """Pins down the review's "no other defects found" statements: exhaustive
    enum sets, exact ``to_row``/``from_row`` column maps, and DDD §5
    evidence-hash canonicalization rules."""

    def test_evidence_type_enum_matches_ddd_exhaustively(self) -> None:
        assert len(EvidenceType) == 25
        expected = {
            "REGISTRY_UNINSTALL", "REGISTRY_WOW64_UNINSTALL", "REGISTRY_APP_PATH",
            "REGISTRY_MSI_PRODUCT", "REGISTRY_MSI_USER_DATA", "REGISTRY_MSI_UPGRADE_CODE",
            "REGISTRY_SHARED_DLL", "REGISTRY_RUN_KEY", "REGISTRY_SERVICE",
            "REGISTRY_APPCOMPAT_CACHE", "REGISTRY_USERASSIST", "REGISTRY_MUICACHE",
            "REGISTRY_COM_CLSID", "REGISTRY_PROGID", "REGISTRY_FILE_ASSOCIATION",
            "REGISTRY_APPX", "REGISTRY_SHELL_EXTENSION", "REGISTRY_SHELL_FOLDER",
            "REGISTRY_USER_PATH_HINT", "FILE_EXECUTABLE", "FILE_PORTABLE_LAYOUT",
            "FILE_SHORTCUT", "FILE_APPX_MANIFEST", "FILE_SOURCE_CODE_DIR",
            "MANIFEST_ENTRY",
        }
        assert {member.value for member in EvidenceType} == expected

    def test_location_category_enum_matches_ddd_exhaustively(self) -> None:
        assert len(FindingLocationCategory) == 19
        expected = {
            "DOCUMENTS", "DESKTOP", "DOWNLOADS", "PICTURES", "MUSIC", "VIDEOS",
            "ONEDRIVE", "INSTALL_DIR", "APPDATA_ROAMING", "APPDATA_LOCAL",
            "APPDATA_LOCALLOW", "SAVED_GAMES", "VIRTUALSTORE", "PROGRAMDATA",
            "SECONDARY_DRIVE", "PORTABLE_DATA_DIR", "SOURCE_CODE",
            "USER_PROFILE_OTHER", "UNKNOWN",
        }
        assert {member.value for member in FindingLocationCategory} == expected

    def test_row_maps_are_stable_round_trip(self) -> None:
        """Hydrating a row and re-serializing it must be byte-identical at the
        row level (exact DDD §4 column maps; no hidden columns leak in or out)."""
        rows = [
            _manifest_source_record().to_row(),
            _user_profile().to_row(),
            _correlated_app().to_row(),
            _user_data_finding().to_row(),
            _warning_record().to_row(),
        ]
        hydrators = (
            SourceRecord.from_row,
            UserProfile.from_row,
            CorrelatedApplication.from_row,
            UserDataFinding.from_row,
            WarningRecord.from_row,
        )
        for row, hydrate in zip(rows, hydrators, strict=True):
            assert hydrate(row).to_row() == row

    def test_evidence_row_round_trip_preserves_hash_and_display_text(self) -> None:
        evidence = _evidence()
        row = evidence.to_row()
        assert evidence.evidence_hash == row["evidence_hash"]
        # Display text derived from the structured value: NULs stripped,
        # meaningful content preserved (DDD §5 value semantics).
        assert evidence.value_data == "Sample App"
        hydrated = Evidence.from_row(row)
        assert hydrated.to_row() == row

    def test_evidence_from_row_rejects_unknown_evidence_type(self) -> None:
        row = dict(_evidence().to_row())
        row["evidence_type"] = "NOT_A_REAL_TYPE"
        with pytest.raises(ValueError):
            Evidence.from_row(row)

    def test_evidence_hash_is_invariant_to_canonical_equivalent_inputs(self) -> None:
        """DDD §5: each canonical field rule must make equivalent inputs hash
        identically, and no rule may leak through."""

        def hashed(**overrides: Any) -> str:
            payload: dict[str, Any] = {
                "source_id": SOURCE_ID,
                "evidence_type": EvidenceType.REGISTRY_UNINSTALL,
                "hive_file_path": "C:\\Windows\\System32\\config\\SOFTWARE",
                "root_hive": "SOFTWARE",
                "key_path": (
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                    r"\{8F36E1B5-6E6A-45F0-938A-C269E436F5E3}"
                ),
                "value_name": "DisplayName",
                "user_sid": "S-1-5-21-1111111111-2222222222-3333333333-1001",
                "product_code": "{8F36E1B5-6E6A-45F0-938A-C269E436F5E3}",
            }
            payload.update(overrides)
            return compute_evidence_hash(**payload)

        base = hashed()
        # Drive prefix stripped and case folded for the hive file path.
        assert hashed(hive_file_path="c:/windows/system32/config/software") == base
        # Root hive uppercased.
        assert hashed(root_hive="software") == base
        # Key path lowercased, backslash form.
        assert hashed(
            key_path=r"software\microsoft\windows\currentversion\uninstall\{8f36e1b5-6e6a-45f0-938a-c269e436f5e3}"
        ) == base
        # Value name lowercased.
        assert hashed(value_name="DISPLAYNAME") == base
        # SID uppercased.
        assert hashed(user_sid="s-1-5-21-1111111111-2222222222-3333333333-1001") == base
        # Source id lowercased.
        assert hashed(source_id=SOURCE_ID.upper()) == base
        # Product code canonicalized across GUID spellings.
        assert hashed(product_code="8f36e1b56e6a45f0938ac269e436f5e3") == base

    def test_new_id_is_36_char_uuid4(self) -> None:
        for _ in range(25):
            value = new_id()
            assert len(value) == 36
            assert uuid.UUID(value).version == 4

    def test_utc_now_iso_is_utc_iso8601(self) -> None:
        stamp = utc_now_iso()
        parsed = datetime.fromisoformat(stamp)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)
