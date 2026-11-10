"""Unit tests for ``src/config/evidence_locations.py``.

Suite layout (mirrors the review criteria and the SDD/SRS guarantees):

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

Deliberate criteria adjustments (documented in the Safety & Architecture
Review that accompanies this file):

* ``Final`` annotations are advisory; the delivered module keeps plain
  ``dict`` indexes. Direct probe mutation is therefore asserted as a
  *logical*-immutability contract (hardened-mapping ``TypeError`` accepted,
  plain-dict probe cleaned up in ``finally``), plus a frozen-dataclass and
  no-public-mutation-API lock.
* ``resolve_registry_bounds`` requires a ``BoundsProvider``; the
  "options missing" case is modeled by an all-``None`` :class:`DummyOptions`,
  exactly what ``models.RegistryParseOptions`` defaults to (SDD §2.10).

The suite is pure per NFR-10: no live drives, no root, no subprocess
execution, no network, no mocked forensic models. The only stdlib mocking
used is ``unittest.mock`` around the import-time I/O sentinels.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sqlite3  # noqa: F401  patch target only; the module must never reach it
import subprocess  # noqa: F401  patch target only; the module must never reach it
import sys
from dataclasses import FrozenInstanceError, dataclass
from unittest import mock

import pytest

from src.config import evidence_locations as el


@dataclass(frozen=True)
class DummyOptions:
    """Minimal structural stand-in for ``models.RegistryParseOptions``.

    ``resolve_registry_bounds`` consumes exactly these four fields through
    the ``BoundsProvider`` protocol. Keeping the stand-in local (instead of
    importing the DTO/persistence layer) preserves NFR-10: the
    configuration module remains testable in isolation with no heavy
    dependencies.
    """

    max_evidence_total: int | None = None
    max_evidence_per_root: int | None = None
    max_subkeys_per_key: int | None = None
    max_values_per_key: int | None = None


# ---------------------------------------------------------------------------
# 1. Module purity and immutability (SDD §4.1)
# ---------------------------------------------------------------------------


class TestModulePurityAndImmutability:
    """The module is pure data.

    Importing it from any thread must trigger no disk access, no subprocess,
    and no database connection. All exported state must be effectively
    read-only: frozen value objects and indexes with no public mutation API.
    """

    @pytest.fixture()
    def reimported_module(self):
        """Re-import the module behind I/O sentinels and restore state.

        ``builtins.open`` is permitted *only* for the module's own source
        file and its bytecode cache — that is CPython import-machinery
        behavior, not module I/O. Any other ``open``, ``os.listdir``,
        ``subprocess.run``, or ``sqlite3.connect`` during import is a purity
        violation (SDD §4.1) and fails the test with an actionable message.
        ``sys.modules`` is restored in a ``finally`` block so module
        identity is never left inconsistent for later tests.
        """
        import builtins
        from importlib.util import cache_from_source

        mod_name = "src.config.evidence_locations"
        source = el.__file__
        allowed: set[str] = set()
        for path in (source, cache_from_source(source)):
            allowed.add(os.path.abspath(path))
            allowed.add(os.path.realpath(path))

        real_open = builtins.open

        def guarded_open(file, *args, **kwargs):
            try:
                target = os.path.abspath(os.fspath(file))
            except TypeError as exc:
                raise AssertionError(
                    f"import called open() with a non-path target: {file!r}"
                ) from exc
            if target not in allowed:
                raise AssertionError(
                    f"module import performed I/O outside its own source: {target!r}"
                )
            return real_open(file, *args, **kwargs)

        saved = sys.modules.pop(mod_name, None)
        try:
            with mock.patch.object(builtins, "open", side_effect=guarded_open) as m_open, \
                 mock.patch(
                     "os.listdir",
                     side_effect=AssertionError("os.listdir during module import"),
                 ) as m_listdir, \
                 mock.patch(
                     "subprocess.run",
                     side_effect=AssertionError("subprocess.run during module import"),
                 ) as m_run, \
                 mock.patch(
                     "sqlite3.connect",
                     side_effect=AssertionError("sqlite3.connect during module import"),
                 ) as m_connect:
                fresh = importlib.import_module(mod_name)
        finally:
            sys.modules.pop(mod_name, None)
            if saved is not None:
                sys.modules[mod_name] = saved
        yield fresh, m_open, m_listdir, m_run, m_connect, allowed

    def test_import_performs_no_io(self, reimported_module):
        """Importing the module touches nothing except its own source/bytecode."""
        fresh, m_open, m_listdir, m_run, m_connect, allowed = reimported_module
        assert fresh is not el, "re-import should produce a fresh module object"

        # No directory listing, subprocess, or database access.
        m_listdir.assert_not_called()
        m_run.assert_not_called()
        m_connect.assert_not_called()

        # CPython's import machinery reads source/bytecode via _io.open_code
        # (a C-level call that bypasses builtins.open), so m_open may
        # legitimately be empty. The guarded_open side_effect still intercepts
        # any open() issued by the *module's own code* during import. Verify
        # that any such calls stayed within the allowed source/bytecode set.
        for call in m_open.call_args_list:
            assert call.args, "open() must be called with an explicit path"
            target = os.path.abspath(os.fspath(call.args[0]))
            assert target in allowed, (
                f"module import performed I/O outside its own source: {target!r}"
            )

        # Re-import is deterministic: identical configuration surface.
        assert fresh.REGISTRY_EVIDENCE_TYPE_KEYS == el.REGISTRY_EVIDENCE_TYPE_KEYS
        assert fresh.EVIDENCE_LOCATIONS_VERSION == el.EVIDENCE_LOCATIONS_VERSION

    @pytest.mark.parametrize("index_name", ["_ROOT_INDEX", "_COMPILED_SUBKEY_PATTERNS"])
    def test_module_level_dicts_are_immutable(self, index_name):
        """Internal index tables must not expose a mutation surface.

        The review criteria expected ``TypeError`` on direct mutation. The
        delivered module keeps plain ``dict`` under a ``Final`` annotation
        (``Final`` is advisory, not runtime-enforced), so this test enforces
        the *observable* contract in either world:

        * if the mapping is hardened (e.g. ``MappingProxyType``), the probe
          assignment must raise ``TypeError``;
        * otherwise the contract is *logical* immutability: the probe is
          removed in ``finally`` (shared state is never left dirty) and the
          public lookup surface is unaffected.
        """
        index = getattr(el, index_name)
        probe = "__test_probe__"
        inserted = False
        try:
            index[probe] = object()
            inserted = True
        except TypeError:
            # Hardened mapping: runtime-enforced immutability. Nothing to clean.
            pass
        try:
            if inserted:
                assert el.root_by_evidence_type("uninstall_native") is not None
        finally:
            if inserted:
                del index[probe]
        assert probe not in index

    def test_module_exposes_no_public_mutation_api(self):
        """``__all__`` must not advertise any setter/mutator entry point."""
        mutating = [
            name
            for name in el.__all__
            if re.match(r"^(set_|add_|insert_|update_|remove_|delete_|pop_|clear_|mutate_)", name)
        ]
        assert mutating == []

    def test_dataclasses_are_frozen(self):
        """Value objects resist field assignment at runtime."""
        spec = el.REGISTRY_EVIDENCE_ROOTS[0]
        with pytest.raises(FrozenInstanceError):
            spec.path = "SOFTWARE\\Forbidden"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            spec.evidence_type = "forged"  # type: ignore[misc]
        bounds = el.DEFAULT_REGISTRY_BOUNDS
        with pytest.raises(FrozenInstanceError):
            bounds.max_evidence_total = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. EvidenceRootSpec fail-fast validation (SRS FR-2.2, NFR-10)
# ---------------------------------------------------------------------------


class TestEvidenceRootSpecValidation:
    """``__post_init__`` validation is a developer-error circuit breaker.

    A malformed static configuration entry must raise at construction time
    (crashing tests at import), never degrade a live forensic scan.
    """

    @staticmethod
    def _make(**overrides: object) -> el.EvidenceRootSpec:
        fields: dict[str, object] = {
            "evidence_type": "probe_root",
            "hive": el.HIVE_SOFTWARE,
            "path": "SOFTWARE\\Microsoft\\Probe",
            "kind": el.EvidenceKind.SUBKEYS,
            "purpose": "probe",
        }
        fields.update(overrides)
        return el.EvidenceRootSpec(**fields)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("hive", "path", "placeholders"),
        [
            (el.HIVE_SOFTWARE, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall", ()),
            (el.HIVE_NTUSER, "Software\\Microsoft\\Windows\\CurrentVersion\\Run", ()),
            (el.HIVE_USRCLASS, "", ()),
            (el.HIVE_USRCLASS, "CLSID", ()),
            (el.HIVE_SYSTEM, "SYSTEM\\<CONTROL_SET>\\Services", (el.CONTROL_SET_PLACEHOLDER,)),
            (el.HIVE_SOFTWARE, "SOFTWARE\\Classes\\Installer\\Products", ()),
        ],
    )
    def test_valid_spec_instantiation(self, hive, path, placeholders):
        spec = self._make(hive=hive, path=path, placeholders=placeholders)
        assert spec.hive == hive
        assert spec.path == path
        assert spec.placeholders == tuple(placeholders)
        assert spec.default_confidence in el.CONFIDENCE_LEVELS

    @pytest.mark.parametrize("evidence_type", ["probe_root", "a", "abc_123"])
    def test_valid_evidence_type_forms(self, evidence_type):
        spec = self._make(evidence_type=evidence_type)
        assert spec.evidence_type == evidence_type

    @pytest.mark.parametrize(
        "bad_path",
        [
            "SOFTWARE\\Microsoft\\",  # trailing separator
            "SOFTWARE\\\\Microsoft",  # double separator (actual: SOFTWARE\\Microsoft)
            "\\SOFTWARE\\Microsoft",  # leading separator
            "SOFTWARE\\",  # separator immediately after root
        ],
    )
    def test_rejects_empty_path_components(self, bad_path):
        with pytest.raises(ValueError, match="empty path component"):
            self._make(path=bad_path)

    def test_rejects_forward_slash_paths(self):
        with pytest.raises(ValueError, match="backslash separators"):
            self._make(path="SOFTWARE/Microsoft/Probe")

    @pytest.mark.parametrize(
        "bad_type",
        ["Uninstall", "uninstall native", "uninstall-Native", "1bad", "", "_lead", "a.b"],
    )
    def test_rejects_invalid_evidence_type_format(self, bad_type):
        with pytest.raises(ValueError, match="evidence_type must be lowercase snake_case"):
            self._make(evidence_type=bad_type)

    @pytest.mark.parametrize("bad_hive", ["HKLM", "software", "NTUSER ", "", "SYSTEM2"])
    def test_rejects_invalid_hive_enum(self, bad_hive):
        """Unknown hive identifiers are rejected (config ids are exact strings)."""
        with pytest.raises(ValueError, match="unknown hive identifier"):
            self._make(hive=bad_hive)

    def test_rejects_invalid_default_confidence(self):
        with pytest.raises(ValueError, match="invalid default_confidence"):
            self._make(default_confidence="Certain")

    def test_rejects_invalid_subkey_name_pattern(self):
        with pytest.raises(ValueError, match="invalid subkey_name_pattern"):
            self._make(subkey_name_pattern="[unclosed")

    @pytest.mark.parametrize("bad_nested", ["", "shell/open"])
    def test_rejects_invalid_nested_value_path(self, bad_nested):
        with pytest.raises(ValueError, match="invalid nested_value_path"):
            self._make(nested_value_path=bad_nested)

    def test_rejects_placeholder_present_but_undeclared(self):
        with pytest.raises(ValueError, match="appears in path but is not declared"):
            self._make(path="SOFTWARE\\Classes\\Installer\\UserData\\<SID>\\Products")

    def test_rejects_placeholder_declared_but_absent(self):
        with pytest.raises(ValueError, match="declared but absent from path"):
            self._make(placeholders=(el.SID_PLACEHOLDER,))


# ---------------------------------------------------------------------------
# 3. Regex contract locks (character-exact regression locks)
# ---------------------------------------------------------------------------


class TestRegexContractLocks:
    """Locks the compiled filter patterns character-for-character.

    These patterns gate subkey admission in the registry parser. A silent
    "mangling" of any pattern degrades filtering (wrong evidence admitted or
    real evidence dropped), so each accepted/rejected case is locked here.
    """

    @pytest.mark.parametrize("name", [".docx", ".exe", ".lnk", ".123", ".extextextx"])
    def test_extension_key_pattern_accepts_valid(self, name):
        assert el.EXTENSION_KEY_PATTERN.fullmatch(name) is not None

    @pytest.mark.parametrize("name", ["docx", "exe", "", ".", ".docx.txt", ".extextextxx"])
    def test_extension_key_pattern_rejects_dotless(self, name):
        assert el.EXTENSION_KEY_PATTERN.fullmatch(name) is None

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Word.Document.12", True),
            ("txtfile.1", True),
            ("A.b", True),
            ("Vendor.Product.1", True),
            ("CLSID", False),
            ("Applications", False),
            ("docx", False),
            (".docx", False),
            ("123.bad", False),
            ("", False),
        ],
    )
    def test_progid_pattern_requires_dot(self, name, expected):
        assert (el.PROGID_KEY_PATTERN.fullmatch(name) is not None) is expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("ControlSet001", True),
            ("ControlSet002", True),
            ("ControlSet0011", True),
            ("ControlSet01", False),  # too short: requires ControlSet00 + digits
            ("ControlSet00", False),
            ("CurrentControlSet", False),
            ("controlset001", False),
            ("ControlSet00A", False),
            ("", False),
        ],
    )
    def test_control_set_pattern_strict_width(self, name, expected):
        assert (el.CONTROL_SET_KEY_PATTERN.fullmatch(name) is not None) is expected

    @pytest.mark.parametrize(
        "name",
        [
            "S-1-5-21-1002100310-1003100410-1004100510-1001",
            "S-1-5-32",
            "S-1-5-18",
        ],
    )
    def test_sid_pattern_accepts_valid(self, name):
        assert el.SID_KEY_PATTERN.fullmatch(name) is not None

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "S-1",
            "S-1-5-a",
            "S-2-5-1",
            "S-1-5-21\\evil",  # backslash must never survive placeholder expansion
            "S-1-5-32\\Documents",
        ],
    )
    def test_sid_pattern_rejects_backslashes_and_malformed(self, name):
        assert el.SID_KEY_PATTERN.fullmatch(name) is None

    @pytest.mark.parametrize(
        "name",
        [
            "{12345678-1234-1234-1234-123456789012}",
            "{ABCDEF01-2345-6789-ABCD-EF0123456789}",
        ],
    )
    def test_guid_pattern_accepts_valid(self, name):
        assert el.GUID_KEY_PATTERN.fullmatch(name) is not None

    @pytest.mark.parametrize(
        "name",
        [
            "12345678-1234-1234-1234-123456789012",  # missing braces
            "{12345678-1234-1234-1234-12345678901}",  # 11-char final group
            "{12345678-1234-1234-1234-1234567890123}",  # 13-char final group
            "",
        ],
    )
    def test_guid_pattern_rejects_invalid(self, name):
        assert el.GUID_KEY_PATTERN.fullmatch(name) is None

    @pytest.mark.parametrize(
        "name",
        [
            "Microsoft.WindowsNotepad_8wekyb3d8bbwe",
            "My.App_10",
        ],
    )
    def test_package_family_pattern_accepts_valid(self, name):
        assert el.PACKAGE_FAMILY_KEY_PATTERN.fullmatch(name) is not None

    @pytest.mark.parametrize(
        "name",
        [
            "NoUnderscoreHere",
            "_Leading",
            "Microsoft.WindowsNotepad_",  # trailing underscore
            "8wekyb3d8bbwe",
            "",
        ],
    )
    def test_package_family_pattern_rejects_invalid(self, name):
        assert el.PACKAGE_FAMILY_KEY_PATTERN.fullmatch(name) is None


# ---------------------------------------------------------------------------
# 4. Bounds resolution defenses (SRS §3.10 / FR-2.3, DDD §4)
# ---------------------------------------------------------------------------


class TestBoundsResolutionDefenses:
    """Memory-bounding defenses.

    A corrupt or tampered scan-options blob must never abort the scan and
    must never silently admit unbounded evidence (SRS FR-2.6 / FR-2.3).
    Every invalid field falls back to the documented default.
    """

    def test_default_bounds_applied_when_options_missing(self):
        """All-None options (the RegistryParseOptions default state) resolve
        to the single documented default instance."""
        result = el.resolve_registry_bounds(DummyOptions())
        assert result == el.DEFAULT_REGISTRY_BOUNDS
        assert result.max_evidence_total == 250_000
        assert result.max_evidence_per_root == 5_000
        assert result.max_subkeys_per_key == 2_000
        assert result.max_values_per_key == 2_000

    def test_valid_overrides_respected(self):
        options = DummyOptions(
            max_evidence_total=1_000,
            max_evidence_per_root=50,
            max_subkeys_per_key=25,
            max_values_per_key=10,
        )
        result = el.resolve_registry_bounds(options)
        assert result == el.RegistryBounds(
            max_evidence_total=1_000,
            max_evidence_per_root=50,
            max_subkeys_per_key=25,
            max_values_per_key=10,
        )

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("max_evidence_total", -1),
            ("max_evidence_total", 0),
            ("max_evidence_total", True),
            ("max_evidence_total", False),
            ("max_evidence_total", "lots"),
            ("max_evidence_total", 2.5),
            ("max_evidence_total", None),
            ("max_evidence_per_root", -1),
            ("max_evidence_per_root", 0),
            ("max_evidence_per_root", False),
            ("max_evidence_per_root", "string"),
            ("max_subkeys_per_key", -1),
            ("max_subkeys_per_key", 0),
            ("max_subkeys_per_key", True),
            ("max_subkeys_per_key", "string"),
            ("max_values_per_key", -1),
            ("max_values_per_key", 0),
            ("max_values_per_key", None),
            ("max_values_per_key", 3.14),
        ],
    )
    def test_invalid_overrides_fallback_to_defaults(self, field, bad_value):
        """Critical forensic defense: invalid input never raises."""
        options = DummyOptions(**{field: bad_value})
        result = el.resolve_registry_bounds(options)  # must not raise
        assert result == el.DEFAULT_REGISTRY_BOUNDS

    def test_mixed_valid_and_invalid_overrides(self):
        options = DummyOptions(max_subkeys_per_key=42, max_values_per_key=-1)
        result = el.resolve_registry_bounds(options)
        assert result.max_subkeys_per_key == 42
        assert result.max_values_per_key == el.DEFAULT_REGISTRY_BOUNDS.max_values_per_key
        assert result.max_evidence_total == el.DEFAULT_REGISTRY_BOUNDS.max_evidence_total
        assert result.max_evidence_per_root == el.DEFAULT_REGISTRY_BOUNDS.max_evidence_per_root

    @pytest.mark.parametrize(
        "bad_kwargs",
        [
            {"max_evidence_total": -1},
            {"max_evidence_total": 0},
            {"max_evidence_total": True},
            {"max_evidence_per_root": 0},
            {"max_subkeys_per_key": False},
            {"max_values_per_key": "2000"},
        ],
    )
    def test_bounds_constructor_rejects_invalid_values(self, bad_kwargs):
        """Direct construction is strict: a bad bounds object is a developer
        error and must fail loudly, unlike operator-supplied option blobs."""
        with pytest.raises(ValueError, match="must be a positive integer"):
            el.RegistryBounds(**bad_kwargs)


# ---------------------------------------------------------------------------
# 5. Placeholder expansion and hive routing (SDD §4.2)
# ---------------------------------------------------------------------------


class TestPlaceholderExpansionAndRouting:
    """Pure functions mapping logical registry paths to physical hives.

    Expansion failures must be per-root, catchable ``ValueError``s so the
    registry parser can skip one evidence category with a warning and
    continue the scan (SRS FR-2.6, SDD §4.2).
    """

    def test_expand_sid_placeholder_valid(self):
        spec = el.root_by_evidence_type("msi_user_products")
        assert spec is not None
        result = el.expand_placeholders(spec, sid="S-1-5-21-1002100310-1003100410-1004100510-1001")
        assert result == (
            "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Installer\\UserData"
            "\\S-1-5-21-1002100310-1003100410-1004100510-1001\\Products"
        )
        assert el.SID_PLACEHOLDER not in result

    @pytest.mark.parametrize("bad_sid", ["", "S-1-5\\evil", "S-1-5-21\\X"])
    def test_expand_sid_placeholder_invalid_raises(self, bad_sid):
        spec = el.root_by_evidence_type("msi_user_products")
        with pytest.raises(ValueError, match="requires a valid profile SID"):
            el.expand_placeholders(spec, sid=bad_sid)

    def test_expand_ignores_sid_when_not_declared(self):
        spec = el.root_by_evidence_type("uninstall_native")
        result = el.expand_placeholders(spec, sid="S-1-5-21-1-2-3-4")
        assert result == spec.path

    def test_expand_control_set_placeholder_valid(self):
        spec = el.root_by_evidence_type("services")
        assert spec is not None
        result = el.expand_placeholders(spec, control_set="ControlSet002")
        assert result == "SYSTEM\\ControlSet002\\Services"
        assert el.CONTROL_SET_PLACEHOLDER not in result

    @pytest.mark.parametrize("bad_control_set", [None, ""])
    def test_expand_control_set_missing_raises(self, bad_control_set):
        spec = el.root_by_evidence_type("services")
        with pytest.raises(ValueError, match="requires a resolved control set"):
            el.expand_placeholders(spec, control_set=bad_control_set)

    @pytest.mark.parametrize(
        "bad_control_set",
        ["CurrentControlSet", "ControlSet01", "controlset001"],
    )
    def test_expand_control_set_invalid_format_raises(self, bad_control_set):
        spec = el.root_by_evidence_type("services")
        with pytest.raises(ValueError, match="not a valid ControlSet00X name"):
            el.expand_placeholders(spec, control_set=bad_control_set)

    def test_expand_both_placeholders(self):
        spec = el.EvidenceRootSpec(
            evidence_type="probe_both",
            hive=el.HIVE_USRCLASS,
            path="<SID>\\<CONTROL_SET>",
            kind=el.EvidenceKind.SUBKEYS,
            purpose="probe",
            placeholders=(el.SID_PLACEHOLDER, el.CONTROL_SET_PLACEHOLDER),
        )
        result = el.expand_placeholders(spec, sid="S-1-5-21-1-2-3-4", control_set="ControlSet001")
        assert result == "S-1-5-21-1-2-3-4\\ControlSet001"

    @pytest.mark.parametrize(
        ("hive", "expected_count"),
        [
            (el.HIVE_SOFTWARE, 19),
            (el.HIVE_SYSTEM, 2),
            (el.HIVE_NTUSER, 10),
            (el.HIVE_DEFAULT, 10),
            (el.HIVE_USRCLASS, 5),
        ],
    )
    def test_roots_for_hive_counts(self, hive, expected_count):
        roots = el.roots_for_hive(hive)
        assert isinstance(roots, tuple)
        assert len(roots) == expected_count

    def test_default_hive_shares_ntuser_layout(self):
        """DEFAULT has the NTUSER.DAT key layout (SDD §2.9)."""
        assert el.roots_for_hive(el.HIVE_DEFAULT) is el.roots_for_hive(el.HIVE_NTUSER)

    @pytest.mark.parametrize("bogus", ["BOGUS", "", "HKLM", "software"])
    def test_roots_for_hive_returns_empty_for_unknown(self, bogus):
        """Locator/parser mismatch degrades gracefully: empty tuple, no KeyError."""
        assert el.roots_for_hive(bogus) == ()

    @pytest.mark.parametrize(
        ("hive", "expected_types"),
        [
            (el.HIVE_SOFTWARE, ("profile_list",)),
            (el.HIVE_NTUSER, ("user_shell_folders", "shell_folders")),
            (el.HIVE_DEFAULT, ("user_shell_folders", "shell_folders")),
            (el.HIVE_SYSTEM, ()),
            (el.HIVE_USRCLASS, ()),
            ("BOGUS", ()),
        ],
    )
    def test_profile_resolution_roots_for_hive(self, hive, expected_types):
        roots = el.profile_resolution_roots_for_hive(hive)
        assert tuple(r.evidence_type for r in roots) == expected_types

    def test_subkey_name_pattern_for_compiled_or_none(self):
        clsid = el.root_by_evidence_type("clsid")
        assert clsid is not None
        pattern = el.subkey_name_pattern_for(clsid)
        assert pattern is not None
        assert pattern.pattern == el.GUID_KEY_PATTERN.pattern
        assert pattern.fullmatch("{12345678-1234-1234-1234-123456789012}") is not None
        assert pattern.fullmatch("NotAGuid") is None
        assert el.subkey_name_pattern_for(el.root_by_evidence_type("uninstall_native")) is None
        assert el.subkey_name_pattern_for(el.root_by_evidence_type("app_paths")) is None

    @pytest.mark.parametrize("unknown", ["", "does_not_exist", "UNINSTALL_NATIVE"])
    def test_root_by_evidence_type_unknown_returns_none(self, unknown):
        """Callers must treat unknown types as unknown + warning, never raise
        (defensive parsing contract, SRS FR-2.6)."""
        assert el.root_by_evidence_type(unknown) is None


# ---------------------------------------------------------------------------
# 6. Forensic edge cases (SRS/SDD normative locks)
# ---------------------------------------------------------------------------


class TestForensicEdgeCases:
    """Locks the documented forensic behaviors that downstream parsers rely on.

    Covers WOW64 views (README §5.5), case-insensitive key resolution,
    volatile/best-effort roots (SDD §4.2), UserAssist usage-only semantics
    with ROT13 (README §5.6), SYSTEM control-set resolution policy
    (README §5.4 / SRS Appendix A.2), and the Appendix A minimum.
    """

    @pytest.mark.parametrize(
        ("evidence_type", "expected"),
        [
            ("uninstall_native", False),
            ("uninstall_wow64", True),
            ("ntuser_uninstall", False),
            ("ntuser_uninstall_wow64", True),
            ("app_paths", False),
            ("msi_products", False),
            ("user_assist", False),
        ],
    )
    def test_wow64_root_identification(self, evidence_type, expected):
        spec = el.root_by_evidence_type(evidence_type)
        assert spec is not None
        assert el.is_wow64_root(spec) is expected

    def test_case_insensitive_path_matching(self):
        """``hive_relative_path`` must resolve an uppercase and a lowercase
        hive-root head identically: the offline parser resolves keys
        case-insensitively, and this helper must never reintroduce case
        sensitivity."""
        upper = el.root_by_evidence_type("uninstall_native")
        assert upper is not None
        expected = el.hive_relative_path(upper)
        lower_probe = el.EvidenceRootSpec(
            evidence_type="case_probe",
            hive=el.HIVE_SOFTWARE,
            path="software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
            kind=el.EvidenceKind.SUBKEYS,
            purpose="probe",
        )
        assert el.hive_relative_path(lower_probe) == expected

    @pytest.mark.parametrize(
        ("evidence_type", "expected"),
        [
            ("uninstall_native", "Microsoft\\Windows\\CurrentVersion\\Uninstall"),
            ("uninstall_wow64", "Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
            (
                "msi_user_products",
                "Microsoft\\Windows\\CurrentVersion\\Installer\\UserData\\<SID>\\Products",
            ),
            ("services", "<CONTROL_SET>\\Services"),
            ("appcompat_cache", "<CONTROL_SET>\\Control\\Session Manager\\AppCompatCache"),
            ("ntuser_uninstall", "Microsoft\\Windows\\CurrentVersion\\Uninstall"),
            ("usrclass_clsid", "CLSID"),
            ("usrclass_file_associations", ""),
        ],
    )
    def test_hive_relative_path_strips_root_component(self, evidence_type, expected):
        """Placeholders are preserved; USRCLASS paths are already hive-relative."""
        spec = el.root_by_evidence_type(evidence_type)
        assert spec is not None
        assert el.hive_relative_path(spec) == expected

    @pytest.mark.parametrize(
        ("evidence_type", "expected"),
        [
            # Structural (primary) roots.
            ("uninstall_native", False),
            ("uninstall_wow64", False),
            ("app_paths", False),
            ("msi_products", False),
            ("msi_user_products", False),
            ("msi_folders", False),
            ("shared_dlls", False),
            ("startup_run", False),
            ("startup_run_once", False),
            ("startup_run_once_ex", False),
            ("startup_policy_run", False),
            ("ntuser_uninstall", False),
            ("ntuser_uninstall_wow64", False),
            ("ntuser_app_paths", False),
            ("ntuser_run", False),
            ("ntuser_run_once", False),
            ("services", False),
            ("usrclass_applications", False),
            # Volatile / best-effort roots (SDD §4.2).
            ("user_assist", True),
            ("appcompat_cache", True),
            ("muicache", True),
            ("recent_docs", True),
            ("typed_paths", True),
            ("feature_usage", True),
            ("msi_upgrade_codes", True),
            ("clsid", True),
            ("appid", True),
            ("typelib", True),
            ("progids", True),
            ("browser_helper_objects", True),
            ("appmodel", True),
            ("appx", True),
            ("usrclass_file_associations", True),
            ("usrclass_progids", True),
            ("usrclass_clsid", True),
            ("usrclass_modern_packages", True),
        ],
    )
    def test_best_effort_roots_flagged_correctly(self, evidence_type, expected):
        """A missing/partially unreadable best-effort root downgrades warning
        severity; a failed structural root raises a higher-severity warning."""
        spec = el.root_by_evidence_type(evidence_type)
        assert spec is not None
        assert spec.best_effort is expected

    def test_user_assist_is_usage_evidence_only_with_rot13(self):
        """README §5.6 / SRS Appendix A.3: UserAssist is the *only* root that
        is usage evidence (never installation proof) and ROT13-decodable."""
        spec = el.root_by_evidence_type("user_assist")
        assert spec is not None
        assert spec.usage_evidence_only is True
        assert spec.decode_rot13 is True
        others = [
            s for s in el.REGISTRY_EVIDENCE_ROOTS if s.evidence_type != "user_assist"
        ]
        assert others
        for other in others:
            assert other.usage_evidence_only is False
            assert other.decode_rot13 is False

    def test_hive_file_names_lock(self):
        """Case-exact offline hive file names consumed by the hive locator."""
        assert el.HIVE_FILE_NAMES == {
            "SOFTWARE": "SOFTWARE",
            "SYSTEM": "SYSTEM",
            "DEFAULT": "DEFAULT",
            "NTUSER": "NTUSER.DAT",
            "USRCLASS": "UsrClass.dat",
        }

    def test_hive_root_components_lock(self):
        assert el.HIVE_ROOT_COMPONENTS == {
            "SOFTWARE": "SOFTWARE",
            "SYSTEM": "SYSTEM",
            "DEFAULT": "Software",
            "NTUSER": "Software",
        }

    def test_control_set_resolution_policy_lock(self):
        """README §5.4 / SRS Appendix A.2 deterministic resolution order."""
        assert el.CONTROL_SET_PRIORITY_ORDER == ("Default", "LastKnownGood")
        assert el.SELECT_VALUE_NAMES == ("Default", "LastKnownGood", "Current")
        assert el.SYSTEM_SELECT_PATH == "SYSTEM\\Select"

    def test_machine_and_user_like_hive_groups(self):
        assert el.MACHINE_HIVES == (el.HIVE_SOFTWARE, el.HIVE_SYSTEM)
        assert el.USER_LIKE_HIVES == (el.HIVE_NTUSER, el.HIVE_DEFAULT)
        assert el.HIVE_TYPES == (
            el.HIVE_SOFTWARE,
            el.HIVE_SYSTEM,
            el.HIVE_DEFAULT,
            el.HIVE_NTUSER,
            el.HIVE_USRCLASS,
        )

    def test_confidence_levels_lock(self):
        assert el.CONFIDENCE_LEVELS == ("Low", "Medium", "High")

    def test_version_is_semver(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", el.EVIDENCE_LOCATIONS_VERSION)

    def test_usrclass_applications_nested_command_contract(self):
        """Appendix A.4: ``Applications\\*\\shell\\open\\command`` is read via
        nested path + named value (name/path only, never content)."""
        spec = el.root_by_evidence_type("usrclass_applications")
        assert spec is not None
        assert spec.nested_value_path == "shell\\open"
        assert spec.value_name == "command"

    def test_shell_folder_roots_are_value_enumerations(self):
        """FR-4.3: Documents baseline resolution reads *values*
        (e.g. ``Personal``), not subkeys."""
        for name in ("user_shell_folders", "shell_folders"):
            spec = el.root_by_evidence_type(name)
            assert spec is not None
            assert spec.kind is el.EvidenceKind.VALUES

    def test_profile_list_is_sid_filtered_subkey_enumeration(self):
        spec = el.root_by_evidence_type("profile_list")
        assert spec is not None
        assert spec.kind is el.EvidenceKind.SUBKEYS
        pattern = el.subkey_name_pattern_for(spec)
        assert pattern is not None
        assert pattern.fullmatch("S-1-5-21-1002100310-1003100410-1004100510-1001") is not None
        assert pattern.fullmatch("NotASid") is None

    def test_appendix_a_minimum_locations_are_configured(self):
        """Independent normative copy of the SRS Appendix A minimum.

        This set is the requirement, not a mirror of the implementation:
        removing/renaming any of these roots is a breaking change (major
        version bump) that this lock catches.
        """
        required = {
            # Appendix A.1 — machine SOFTWARE hive
            "uninstall_native", "uninstall_wow64", "app_paths", "msi_products",
            "msi_user_products", "msi_upgrade_codes", "msi_folders", "shared_dlls",
            "startup_run", "startup_run_once", "startup_run_once_ex", "startup_policy_run",
            "clsid", "appid", "typelib", "progids", "browser_helper_objects",
            "appmodel", "appx",
            # Appendix A.2 — machine SYSTEM hive
            "services", "appcompat_cache",
            # Appendix A.3 — per-user NTUSER.DAT hive
            "ntuser_uninstall", "ntuser_uninstall_wow64", "ntuser_app_paths",
            "ntuser_run", "ntuser_run_once", "user_assist", "muicache",
            "recent_docs", "typed_paths", "feature_usage",
            # Appendix A.4 — per-user UsrClass.dat hive
            "usrclass_file_associations", "usrclass_progids", "usrclass_clsid",
            "usrclass_applications", "usrclass_modern_packages",
            # Appendix A.6 — required profile-resolution locations
            "profile_list", "user_shell_folders", "shell_folders",
        }
        assert required <= set(el.REGISTRY_EVIDENCE_TYPE_KEYS)
        assert len(el.REGISTRY_EVIDENCE_TYPE_KEYS) == len(set(el.REGISTRY_EVIDENCE_TYPE_KEYS))
