"""Comprehensive pytest suite for ``src/config/heuristic_patterns.py``.

Scope
-----
The module under test is *pure*: frozen configuration data plus pure helper
functions. It performs zero I/O, zero subprocess calls, and zero network
operations, so this suite runs entirely in memory — no live drives, no root
privileges, and no filesystem mocking are required (SRS NFR-10; README §5).

What the tests pin down
-----------------------
* Closed severity/confidence vocabularies (FR-4.8 / FR-4.9).
* Deterministic, total category precedence used by finding merges (FR-4.7).
* Name/extension-only signals — the helpers never touch file bytes
  (SRS §3.3: no file-content inspection; PE headers never parsed).
* Path-only OneDrive detection (README §5.8).
* Bounded enumeration defaults and defensive bound resolution (SRS §3.10,
  NFR-5): a bad operator setting must fall back to documented defaults,
  never produce an unbounded scan.
* Fail-fast import-time configuration validation: a defective heuristic
  table must fail loudly at import, never silently corrupt classifier
  output on a stressed user's machine (SDD §2.6).
"""

from __future__ import annotations

import importlib
import re
from collections import Counter
from dataclasses import FrozenInstanceError

import pytest

from src.config import heuristic_patterns as hp
from src.config.heuristic_patterns import (
    ALL_FOLDER_PATTERNS,
    ALLOWED_CONFIDENCES,
    ALLOWED_SEVERITIES,
    APP_PACKAGE_EXTENSIONS,
    CATEGORY_PRECEDENCE,
    CONFIDENCE_DEFAULTS,
    CONFIDENCE_ORDER,
    DEFAULT_EXCLUSION_RULES,
    DEFAULT_HEURISTIC_BOUNDS,
    DEVELOPER_FOLDER_PATTERNS,
    EXECUTABLE_EXTENSIONS,
    ExclusionCategory,
    ExclusionRule,
    FolderAnchor,
    FolderMatchRule,
    HEURISTIC_PATTERNS_VERSION,
    HeuristicBounds,
    LocationCategory,
    ONEDRIVE_BASE_SEGMENT,
    ONEDRIVE_FOLDER_PATTERNS,
    PORTABLE_PATTERNS,
    PortableLayoutKind,
    PortablePattern,
    SEVERITY_DEFAULTS,
    SEVERITY_ORDER,
    SHORTCUT_EXTENSIONS,
    USER_DATA_FOLDER_PATTERNS,
    UserFolderPattern,
    category_precedence_rank,
    choose_category,
    confidence_rank,
    default_confidence_for,
    default_severity_for,
    has_app_package_extension,
    has_executable_extension,
    has_shortcut_extension,
    higher_confidence,
    higher_severity,
    is_onedrive_segment,
    patterns_for_category,
    resolve_heuristic_bounds,
    severity_rank,
)

# ---------------------------------------------------------------------------
# Pinned expected values (FR-4.8 / FR-4.9 deterministic defaults)
# ---------------------------------------------------------------------------
# These mirror the module's documented defaults. They are intentionally
# written out (not read back from the module) so that a silent configuration
# change fails loudly here, forcing a deliberate configuration review rather
# than quietly re-classifying a user's findings on their machine.

_EXPECTED_SEVERITY: dict[LocationCategory, str] = {
    LocationCategory.INSTALL_DIR: "Low",
    LocationCategory.PORTABLE_DATA_DIR: "Medium",
    LocationCategory.SECONDARY_DRIVE: "Medium",
    LocationCategory.APPDATA_LOCAL: "Medium",
    LocationCategory.APPDATA_ROAMING: "Medium",
    LocationCategory.APPDATA_LOCALLOW: "Low",
    LocationCategory.SAVED_GAMES: "High",
    LocationCategory.VIRTUALSTORE: "Medium",
    LocationCategory.PROGRAMDATA: "Low",
    LocationCategory.DESKTOP: "Medium",
    LocationCategory.DOWNLOADS: "Medium",
    LocationCategory.PICTURES: "High",
    LocationCategory.MUSIC: "Medium",
    LocationCategory.VIDEOS: "High",
    LocationCategory.DOCUMENTS: "Low",
    LocationCategory.ONEDRIVE: "High",
    LocationCategory.SOURCE_CODE: "High",
    LocationCategory.USER_PROFILE_OTHER: "Low",
    LocationCategory.UNKNOWN: "Low",
}

_EXPECTED_CONFIDENCE: dict[LocationCategory, str] = {
    LocationCategory.INSTALL_DIR: "Low",
    LocationCategory.PORTABLE_DATA_DIR: "Medium",
    LocationCategory.SECONDARY_DRIVE: "Low",
    LocationCategory.APPDATA_LOCAL: "Medium",
    LocationCategory.APPDATA_ROAMING: "Medium",
    LocationCategory.APPDATA_LOCALLOW: "Medium",
    LocationCategory.SAVED_GAMES: "High",
    LocationCategory.VIRTUALSTORE: "Medium",
    LocationCategory.PROGRAMDATA: "Medium",
    LocationCategory.DESKTOP: "High",
    LocationCategory.DOWNLOADS: "High",
    LocationCategory.PICTURES: "High",
    LocationCategory.MUSIC: "High",
    LocationCategory.VIDEOS: "High",
    LocationCategory.DOCUMENTS: "High",
    LocationCategory.ONEDRIVE: "Medium",
    LocationCategory.SOURCE_CODE: "Medium",
    LocationCategory.USER_PROFILE_OTHER: "Low",
    LocationCategory.UNKNOWN: "Low",
}

_ALL_BOUNDS_FIELDS: tuple[str, ...] = (
    "max_filesystem_entries_per_source",
    "max_directory_depth",
    "max_directory_entries",
    "max_manifest_entries",
    "max_user_data_findings",
)


# ---------------------------------------------------------------------------
# 1. Import-time validation (fail-fast configuration)
# ---------------------------------------------------------------------------

def test_import_time_validation_succeeded():
    """``_validate_configuration()`` runs at import time and raises
    ``ValueError`` on any table defect. Reaching this test at all proves the
    shipped static configuration is valid; calling the validator again
    confirms the live module state still passes (it is a pure, idempotent
    check — safe to re-run from any thread)."""
    module = importlib.import_module("src.config.heuristic_patterns")
    assert module is hp
    module._validate_configuration()  # must not raise


def test_heuristic_patterns_version_is_semver_like():
    """The version stamp is stored in the session's ScanOptions so reports
    are auditable against the exact pattern set that produced them
    (SDD §2.6, FR-6.1). It must be a non-empty, semver-shaped string."""
    assert isinstance(HEURISTIC_PATTERNS_VERSION, str)
    assert HEURISTIC_PATTERNS_VERSION.strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", HEURISTIC_PATTERNS_VERSION)


# ---------------------------------------------------------------------------
# 2. Enums and constants
# ---------------------------------------------------------------------------

def test_location_category_members_are_exact():
    """Every FR-4.4 candidate category has exactly one member; an extra or
    missing member would silently change classifier coverage."""
    expected = {
        "DOCUMENTS",
        "DESKTOP",
        "DOWNLOADS",
        "PICTURES",
        "MUSIC",
        "VIDEOS",
        "ONEDRIVE",
        "INSTALL_DIR",
        "APPDATA_ROAMING",
        "APPDATA_LOCAL",
        "APPDATA_LOCALLOW",
        "SAVED_GAMES",
        "VIRTUALSTORE",
        "PROGRAMDATA",
        "SECONDARY_DRIVE",
        "PORTABLE_DATA_DIR",
        "SOURCE_CODE",
        "USER_PROFILE_OTHER",
        "UNKNOWN",
    }
    assert {m.name for m in LocationCategory} == expected
    # Values are upper-snake identical to the names in this vocabulary.
    assert {m.value for m in LocationCategory} == expected
    assert len(LocationCategory) == 19


def test_folder_anchor_members():
    assert {m.name for m in FolderAnchor} == {"PROFILE", "DRIVE"}
    assert {m.value for m in FolderAnchor} == {"profile", "drive"}
    assert isinstance(FolderAnchor.PROFILE, str)  # StrEnum: string-valued


def test_folder_match_rule_members():
    assert {m.name for m in FolderMatchRule} == {
        "DIR_EXACT",
        "DIR_OR_UNDER",
        "ANY_UNDER",
    }
    assert {m.value for m in FolderMatchRule} == {
        "dir_exact",
        "dir_or_under",
        "any_under",
    }


def test_exclusion_category_members():
    """Exactly the eight normative SDD §2.16 exclusion categories."""
    expected = {
        "RECYCLE_BIN",
        "VOLUME_METADATA",
        "TEMP_CACHE",
        "PACKAGE_CACHE",
        "VCS_METADATA",
        "VIRTUAL_ENV",
        "COMPILER_CACHE",
        "SYSTEM_RECOVERY",
    }
    assert {m.name for m in ExclusionCategory} == expected
    assert {m.value for m in ExclusionCategory} == {n.lower() for n in expected}
    assert len(ExclusionCategory) == 8


def test_portable_layout_kind_members():
    assert {m.name for m in PortableLayoutKind} == {"DIR_NAME", "EXE_NAME", "LAYOUT"}
    assert {m.value for m in PortableLayoutKind} == {
        "dir_name",
        "exe_name",
        "layout",
    }


def test_severity_and_confidence_order():
    """FR-4.8 / FR-4.9: closed three-level scales, ordered Low < Medium < High."""
    assert SEVERITY_ORDER == ("Low", "Medium", "High")
    assert CONFIDENCE_ORDER == ("Low", "Medium", "High")
    assert ALLOWED_SEVERITIES == frozenset({"Low", "Medium", "High"})
    assert ALLOWED_CONFIDENCES == frozenset({"Low", "Medium", "High"})


def test_name_signal_vocabulary():
    """SRS §3.3: executables, shortcuts, and packages are identified by
    extension *name only*. Pinning the exact sets prevents a drift that
    would silently widen or narrow evidence admission."""
    assert EXECUTABLE_EXTENSIONS == frozenset({".exe", ".com", ".bat", ".cmd", ".scr"})
    assert SHORTCUT_EXTENSIONS == frozenset({".lnk"})
    assert APP_PACKAGE_EXTENSIONS == frozenset({".msi", ".msix"})
    assert ONEDRIVE_BASE_SEGMENT == "OneDrive"


# ---------------------------------------------------------------------------
# 3. Dataclasses
# ---------------------------------------------------------------------------

def _sample_folder_pattern() -> UserFolderPattern:
    return UserFolderPattern(
        name="test_pattern",
        category=LocationCategory.DESKTOP,
        anchor=FolderAnchor.PROFILE,
        segments=("Desktop",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="High",
        requires_non_empty=False,
        rationale="Test pattern rationale.",
    )


def test_user_folder_pattern_stores_fields():
    p = _sample_folder_pattern()
    assert p.name == "test_pattern"
    assert p.category is LocationCategory.DESKTOP
    assert p.anchor is FolderAnchor.PROFILE
    assert p.segments == ("Desktop",)
    assert p.match_rule is FolderMatchRule.DIR_EXACT
    assert p.default_severity == "Medium"
    assert p.default_confidence == "High"
    assert p.requires_non_empty is False
    assert p.rationale == "Test pattern rationale."


def test_user_folder_pattern_is_immutable_and_hashable():
    """Configuration DTOs are frozen: a scanner thread must never be able to
    mutate a pattern mid-scan, and value equality makes deduplication
    deterministic."""
    p = _sample_folder_pattern()
    with pytest.raises(FrozenInstanceError):
        p.name = "mutated"
    assert p == _sample_folder_pattern()
    assert hash(p) == hash(_sample_folder_pattern())


def test_portable_pattern_stores_fields_and_precompiles_regex():
    """``__post_init__`` compiles the pattern exactly once so the portable
    scanner never pays per-candidate regex compilation cost (bounded CPU,
    NFR-1/NFR-5). The scanner applies patterns to *lowercased* names, so the
    match tests use lowercased input."""
    p = PortablePattern(
        name="portable_test",
        kind=PortableLayoutKind.LAYOUT,
        pattern_text=r"^(app)?data$",
        score=35,
        default_confidence="Medium",
        rationale="layout test",
    )
    assert p.name == "portable_test"
    assert p.kind is PortableLayoutKind.LAYOUT
    assert p.score == 35
    assert p.default_confidence == "Medium"
    assert p.rationale == "layout test"
    assert isinstance(p.compiled, re.Pattern)
    assert p.compiled.pattern == r"^(app)?data$"
    assert p.compiled is p.compiled  # stable object; never recompiled
    assert p.compiled.fullmatch("appdata") is not None
    assert p.compiled.fullmatch("appdatax") is None


def test_portable_pattern_regex_match_semantics():
    p = PortablePattern(
        name="name_match",
        kind=PortableLayoutKind.DIR_NAME,
        pattern_text=r"portable",
        score=10,
        default_confidence="Medium",
        rationale="test",
    )
    # Patterns are applied to lowercased names by the scanner.
    assert p.compiled.search("my portable app") is not None
    assert p.compiled.search("MY PORTABLE APP") is None


def test_portable_pattern_rejects_invalid_regex():
    """A malformed pattern must fail at configuration time, not halfway
    through a scan on a user's machine."""
    with pytest.raises(re.error):
        PortablePattern(
            name="bad",
            kind=PortableLayoutKind.EXE_NAME,
            pattern_text=r"(unclosed",
            score=1,
            default_confidence="Low",
            rationale="test",
        )


def test_portable_pattern_is_immutable():
    p = PortablePattern(
        name="frozen",
        kind=PortableLayoutKind.DIR_NAME,
        pattern_text=r"portable",
        score=10,
        default_confidence="Medium",
        rationale="test",
    )
    with pytest.raises(FrozenInstanceError):
        p.score = 99


def test_exclusion_rule_defaults():
    """Defaults must be safe: traversal-blocking on by default, no segments,
    empty rationale acceptable at construction (shipped rules always set it)."""
    rule = ExclusionRule(name="r", category=ExclusionCategory.TEMP_CACHE)
    assert rule.exact_segments == frozenset()
    assert rule.consecutive_segments == ()
    assert rule.blocks_traversal is True
    assert rule.rationale == ""


def test_exclusion_rule_explicit_values_and_immutability():
    rule = ExclusionRule(
        name="pip_cache",
        category=ExclusionCategory.PACKAGE_CACHE,
        exact_segments=frozenset({"pip"}),
        consecutive_segments=(("pip", "cache"),),
        blocks_traversal=False,
        rationale="test",
    )
    assert rule.exact_segments == frozenset({"pip"})
    assert rule.consecutive_segments == (("pip", "cache"),)
    assert rule.blocks_traversal is False
    with pytest.raises(FrozenInstanceError):
        rule.blocks_traversal = True


def test_heuristic_bounds_defaults():
    """Documented source of the session defaults (SRS §3.10, NFR-5)."""
    b = HeuristicBounds()
    assert b.max_filesystem_entries_per_source == 100_000
    assert b.max_directory_depth == 12
    assert b.max_directory_entries == 20_000
    assert b.max_manifest_entries == 500_000
    assert b.max_user_data_findings == 5_000
    assert b == DEFAULT_HEURISTIC_BOUNDS


@pytest.mark.parametrize("depth", [0, -3, 65, 100])
def test_heuristic_bounds_rejects_out_of_range_depth(depth):
    """Traversal depth outside 1..64 would either disable depth bounding or
    unbound a Live Session's memory use (NFR-5) — reject loudly."""
    with pytest.raises(ValueError, match="max_directory_depth"):
        HeuristicBounds(max_directory_depth=depth)


def test_heuristic_bounds_accepts_boundary_depths():
    assert HeuristicBounds(max_directory_depth=1).max_directory_depth == 1
    assert HeuristicBounds(max_directory_depth=64).max_directory_depth == 64


def test_heuristic_bounds_rejects_non_integer_depth_type():
    """Documented edge case: the validator compares depth numerically, so a
    string is a hard TypeError — never silently coerced into an unbounded or
    mis-bounded scan."""
    with pytest.raises(TypeError):
        HeuristicBounds(max_directory_depth="12")


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("max_filesystem_entries_per_source", 0),
        ("max_filesystem_entries_per_source", -1),
        # bool is a subclass of int; True/False must be rejected explicitly
        # or a config file could smuggle an "on/off" flag in as a bound.
        ("max_filesystem_entries_per_source", True),
        ("max_filesystem_entries_per_source", False),
        ("max_directory_entries", 0),
        ("max_directory_entries", -7),
        ("max_manifest_entries", False),
        ("max_user_data_findings", 0),
    ],
)
def test_heuristic_bounds_rejects_non_positive_or_bool_counts(field, bad):
    with pytest.raises(ValueError, match=field):
        HeuristicBounds(**{field: bad})


# ---------------------------------------------------------------------------
# 4. Extension helpers (name-only signals, SRS §3.3)
# ---------------------------------------------------------------------------
# These helpers operate on *names only* and never open a file. They are
# defensively None-safe so that report data or malformed manifest lines can
# never crash a scan on a stressed user's machine.

@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("setup.exe", True),
        ("SETUP.EXE", True),            # case-insensitive
        ("launcher.com", True),
        ("run.bat", True),
        ("script.cmd", True),
        ("inject.scr", True),
        ("multi.part.v2.exe", True),    # multiple dots: right-most extension wins
        ("my .exe", True),              # trailing extension after space (module behaviour)
        ("readme.txt", False),
        ("setup", False),               # no extension at all
        (".exe", False),                # bare extension, no file name
        ("setup.exe.bak", False),       # right-most extension is .bak
        (".", False),
        ("", False),
        (None, False),                  # None-safe defensive branch
        ("   ", False),
    ],
)
def test_has_executable_extension(name, expected):
    assert has_executable_extension(name) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("launcher.lnk", True),
        ("LAUNCHER.LNK", True),
        ("nested.folder.link.lnk", True),
        ("readme.txt", False),
        (".lnk", False),                # bare extension, no file name
        ("setup.lnk.bak", False),
        ("", False),
        (None, False),
    ],
)
def test_has_shortcut_extension(name, expected):
    # .lnk names are used as Start Menu / Desktop evidence; the targets are
    # never parsed (SRS §3.3).
    assert has_shortcut_extension(name) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("setup.msi", True),
        ("APP.MSIX", True),
        ("package.msix", True),
        ("package.msix.lnk", False),    # right-most extension is a shortcut, not a package
        (".msi", False),
        ("readme.txt", False),
        ("", False),
        (None, False),
    ],
)
def test_has_app_package_extension(name, expected):
    assert has_app_package_extension(name) is expected


# ---------------------------------------------------------------------------
# 5. OneDrive helper (path-only detection, README §5.8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        ("OneDrive", True),
        ("onedrive", True),                    # case-insensitive
        ("OnEDrive", True),
        ("  OneDrive  ", True),               # surrounding whitespace tolerated
        ("OneDrive - Contoso", True),         # organization suffix form
        ("ONEDRIVE - CONTOSO", True),
        ("OneDrive -", True),                 # module's prefix rule for the org-suffix form
        ("OneDriveX", False),
        ("My OneDrive", False),
        ("One Drive", False),
        ("OneDrive2", False),
        ("OneDrive-", False),                 # no space after the dash: not the org form
        ("", False),
        (None, False),
    ],
)
def test_is_onedrive_segment(segment, expected):
    assert is_onedrive_segment(segment) is expected


# ---------------------------------------------------------------------------
# 6. Ranking and merging helpers (FR-4.8 / FR-4.9 / FR-4.7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("value", "rank"), [("Low", 0), ("Medium", 1), ("High", 2)])
def test_severity_rank(value, rank):
    assert severity_rank(value) == rank


@pytest.mark.parametrize(("value", "rank"), [("Low", 0), ("Medium", 1), ("High", 2)])
def test_confidence_rank(value, rank):
    assert confidence_rank(value) == rank


@pytest.mark.parametrize("bad", ["Critical", "low", "HIGH", "", None])
def test_severity_rank_unknown_raises(bad):
    """Report data is untrusted: an unknown level must be rejected loudly
    instead of silently sorting findings wrong (FR-4.8)."""
    with pytest.raises(ValueError, match="unknown severity"):
        severity_rank(bad)


@pytest.mark.parametrize("bad", ["Certain", "high", "0", None])
def test_confidence_rank_unknown_raises(bad):
    with pytest.raises(ValueError, match="unknown confidence"):
        confidence_rank(bad)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Low", "High", "High"),
        ("High", "Low", "High"),
        ("Low", "Medium", "Medium"),
        ("Medium", "Low", "Medium"),
        ("High", "Medium", "High"),
        ("Medium", "High", "High"),
        ("Low", "Low", "Low"),
        ("Medium", "Medium", "Medium"),
        ("High", "High", "High"),
    ],
)
def test_higher_severity(a, b, expected):
    """FR-4.7 merge rule: highest severity wins, argument order irrelevant."""
    assert higher_severity(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Low", "High", "High"),
        ("High", "Low", "High"),
        ("Low", "Medium", "Medium"),
        ("Medium", "Low", "Medium"),
        ("High", "Medium", "High"),
        ("Medium", "High", "High"),
        ("Low", "Low", "Low"),
        ("Medium", "Medium", "Medium"),
        ("High", "High", "High"),
    ],
)
def test_higher_confidence(a, b, expected):
    """FR-4.7 merge rule: highest confidence wins, argument order irrelevant."""
    assert higher_confidence(a, b) == expected


# ---------------------------------------------------------------------------
# 7. Category precedence (FR-4.7 deterministic single-category selection)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", list(LocationCategory))
def test_category_precedence_rank_matches_table_position(category):
    assert category_precedence_rank(category) == CATEGORY_PRECEDENCE.index(category)


def test_category_precedence_is_a_total_order():
    """Precedence must be a deterministic total order over the full category
    set: developer content and OneDrive first (highest oversight risk),
    the UNKNOWN catch-all last."""
    assert len(CATEGORY_PRECEDENCE) == len(LocationCategory) == 19
    assert len(set(CATEGORY_PRECEDENCE)) == 19
    assert set(CATEGORY_PRECEDENCE) == set(LocationCategory)
    assert CATEGORY_PRECEDENCE[0] is LocationCategory.SOURCE_CODE
    assert CATEGORY_PRECEDENCE[-1] is LocationCategory.UNKNOWN
    assert [category_precedence_rank(c) for c in CATEGORY_PRECEDENCE] == list(range(19))


def test_choose_category_single_candidate():
    assert (
        choose_category([LocationCategory.DOCUMENTS])
        is LocationCategory.DOCUMENTS
    )


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        (
            (
                LocationCategory.DOCUMENTS,
                LocationCategory.SOURCE_CODE,
                LocationCategory.ONEDRIVE,
            ),
            LocationCategory.SOURCE_CODE,  # rank 0 beats 4 and 1
        ),
        (
            (
                LocationCategory.APPDATA_LOCAL,
                LocationCategory.PROGRAMDATA,
                LocationCategory.SECONDARY_DRIVE,
            ),
            LocationCategory.APPDATA_LOCAL,  # rank 10 beats 16 and 15
        ),
        (
            (
                LocationCategory.VIRTUALSTORE,
                LocationCategory.SAVED_GAMES,
                LocationCategory.DESKTOP,
            ),
            LocationCategory.SAVED_GAMES,  # rank 2 beats 3 and 5
        ),
        (
            (
                LocationCategory.USER_PROFILE_OTHER,
                LocationCategory.UNKNOWN,
            ),
            LocationCategory.USER_PROFILE_OTHER,  # rank 17 beats 18
        ),
        (
            (LocationCategory.ONEDRIVE, LocationCategory.DOCUMENTS),
            LocationCategory.ONEDRIVE,  # rank 1 beats 4
        ),
    ],
)
def test_choose_category_picks_highest_precedence(candidates, expected):
    assert choose_category(candidates) is expected


def test_choose_category_accepts_generator():
    """Streaming input must work: the classifier may pass generators rather
    than materialized lists (memory bounding, NFR-5)."""
    winner = choose_category(
        (c for c in (LocationCategory.PICTURES, LocationCategory.MUSIC))
    )
    assert winner is LocationCategory.PICTURES  # rank 7 beats 8


@pytest.mark.parametrize("empty", [[], (), iter([])])
def test_choose_category_empty_raises(empty):
    """An empty candidate set is a caller bug that must not reach the UI."""
    with pytest.raises(ValueError, match="at least one candidate"):
        choose_category(empty)


# ---------------------------------------------------------------------------
# 8. Pattern tables and patterns_for_category
# ---------------------------------------------------------------------------

def test_all_folder_patterns_is_concatenation_of_tables():
    assert (
        ALL_FOLDER_PATTERNS
        == USER_DATA_FOLDER_PATTERNS
        + DEVELOPER_FOLDER_PATTERNS
        + ONEDRIVE_FOLDER_PATTERNS
    )
    assert len(USER_DATA_FOLDER_PATTERNS) == 13
    assert len(DEVELOPER_FOLDER_PATTERNS) == 10
    assert len(ONEDRIVE_FOLDER_PATTERNS) == 2
    assert len(ALL_FOLDER_PATTERNS) == 25


@pytest.mark.parametrize(
    ("category", "expected_names"),
    [
        (LocationCategory.DOCUMENTS, ("user_documents",)),
        (LocationCategory.DESKTOP, ("user_desktop",)),
        (LocationCategory.DOWNLOADS, ("user_downloads",)),
        (LocationCategory.PICTURES, ("user_pictures",)),
        (LocationCategory.MUSIC, ("user_music",)),
        (LocationCategory.VIDEOS, ("user_videos",)),
        (LocationCategory.SAVED_GAMES, ("saved_games",)),
        (LocationCategory.APPDATA_LOCAL, ("appdata_local",)),
        (LocationCategory.APPDATA_ROAMING, ("appdata_roaming",)),
        (LocationCategory.APPDATA_LOCALLOW, ("appdata_locallow",)),
        (LocationCategory.VIRTUALSTORE, ("virtual_store",)),
        (LocationCategory.INSTALL_DIR, ("user_programs",)),
        (LocationCategory.PROGRAMDATA, ("program_data",)),
        (LocationCategory.ONEDRIVE, ("onedrive_profile", "onedrive_drive")),
        (
            LocationCategory.SOURCE_CODE,
            (
                "vs_source",
                "vs_source_repos",
                "intellij_idea_projects",
                "rider_projects",
                "eclipse_workspace",
                "eclipse_workspace_alt",
                "netbeans_projects",
                "generic_projects",
                "generic_code",
                "generic_dev",
            ),
        ),
    ],
)
def test_patterns_for_category_expected_subset(category, expected_names):
    patterns = patterns_for_category(category)
    assert isinstance(patterns, tuple)
    assert [p.name for p in patterns] == list(expected_names)
    assert all(p.category is category for p in patterns)


@pytest.mark.parametrize(
    "category",
    [
        LocationCategory.SECONDARY_DRIVE,
        LocationCategory.PORTABLE_DATA_DIR,
        LocationCategory.USER_PROFILE_OTHER,
        LocationCategory.UNKNOWN,
    ],
)
def test_patterns_for_category_non_folder_categories_empty(category):
    """These categories are not folder-driven: the classifier derives them
    from application records or secondary-source context, not from a static
    folder table."""
    assert patterns_for_category(category) == ()


def test_folder_patterns_partition_by_category():
    """Every shipped pattern belongs to exactly one category bucket and the
    buckets jointly cover the whole table (no orphans, no double claims)."""
    per_category = Counter(
        p.name for category in LocationCategory for p in patterns_for_category(category)
    )
    assert per_category == Counter(p.name for p in ALL_FOLDER_PATTERNS)
    assert sum(per_category.values()) == len(ALL_FOLDER_PATTERNS) == 25


def test_developer_patterns_are_profile_anchored_and_require_non_empty():
    """FR-4.5 / README §5.10: IDE source directories are only meaningful
    under a user profile and only when non-empty; flagging an empty
    ``source`` folder would be noise for a stressed user."""
    for p in DEVELOPER_FOLDER_PATTERNS:
        assert p.category is LocationCategory.SOURCE_CODE
        assert p.anchor is FolderAnchor.PROFILE
        assert p.requires_non_empty is True


def test_onedrive_patterns_use_onedrive_category():
    for p in ONEDRIVE_FOLDER_PATTERNS:
        assert p.category is LocationCategory.ONEDRIVE


# ---------------------------------------------------------------------------
# 9. Deterministic severity / confidence defaults (FR-4.8 / FR-4.9)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", list(LocationCategory))
def test_default_severity_for_all_categories(category):
    assert default_severity_for(category) == _EXPECTED_SEVERITY[category]
    assert default_severity_for(category) in ALLOWED_SEVERITIES


@pytest.mark.parametrize("category", list(LocationCategory))
def test_default_confidence_for_all_categories(category):
    assert default_confidence_for(category) == _EXPECTED_CONFIDENCE[category]
    assert default_confidence_for(category) in ALLOWED_CONFIDENCES


def test_defaults_tables_cover_full_category_set():
    """Every category must have an explicit default; a missing key would
    raise KeyError mid-classification instead of failing at import time."""
    assert set(SEVERITY_DEFAULTS) == set(LocationCategory)
    assert set(CONFIDENCE_DEFAULTS) == set(LocationCategory)
    assert all(v in ALLOWED_SEVERITIES for v in SEVERITY_DEFAULTS.values())
    assert all(v in ALLOWED_CONFIDENCES for v in CONFIDENCE_DEFAULTS.values())


# ---------------------------------------------------------------------------
# 10. Bounds resolution (SRS §3.10, NFR-5)
# ---------------------------------------------------------------------------

def test_resolve_heuristic_bounds_all_none_returns_defaults():
    resolved = resolve_heuristic_bounds()
    assert isinstance(resolved, HeuristicBounds)
    assert resolved == DEFAULT_HEURISTIC_BOUNDS


def test_resolve_heuristic_bounds_valid_overrides():
    resolved = resolve_heuristic_bounds(
        max_filesystem_entries_per_source=5_000,
        max_directory_depth=8,
        max_directory_entries=1_000,
        max_manifest_entries=250_000,
        max_user_data_findings=100,
    )
    assert resolved.max_filesystem_entries_per_source == 5_000
    assert resolved.max_directory_depth == 8
    assert resolved.max_directory_entries == 1_000
    assert resolved.max_manifest_entries == 250_000
    assert resolved.max_user_data_findings == 100


def test_resolve_heuristic_bounds_partial_override_keeps_other_defaults():
    resolved = resolve_heuristic_bounds(max_directory_depth=24)
    assert resolved.max_directory_depth == 24
    for field in _ALL_BOUNDS_FIELDS:
        if field == "max_directory_depth":
            continue
        assert getattr(resolved, field) == getattr(DEFAULT_HEURISTIC_BOUNDS, field)


@pytest.mark.parametrize("field", list(_ALL_BOUNDS_FIELDS))
@pytest.mark.parametrize("value", [0, -1, True, False, None])
def test_resolve_heuristic_bounds_defensive_fallback(field, value):
    """``_as_positive_int`` mirrors the session-config defence: ``bool`` is
    rejected explicitly because it is an ``int`` subclass, and any
    non-positive or missing value falls back to the documented default
    rather than crashing the scan or silently unbounding it (SRS §3.10).
    Note: for ``max_directory_depth`` every invalid value here falls back to
    the default 12; valid boundary values (1, 64) are exercised separately
    in the HeuristicBounds tests."""
    resolved = resolve_heuristic_bounds(**{field: value})
    assert getattr(resolved, field) == getattr(DEFAULT_HEURISTIC_BOUNDS, field)


def test_resolve_heuristic_bounds_boundary_values_accepted():
    resolved = resolve_heuristic_bounds(max_directory_depth=1)
    assert resolved.max_directory_depth == 1
    resolved = resolve_heuristic_bounds(max_directory_depth=64)
    assert resolved.max_directory_depth == 64


def test_resolve_heuristic_bounds_returns_frozen_instance():
    resolved = resolve_heuristic_bounds(max_directory_depth=20)
    with pytest.raises(FrozenInstanceError):
        resolved.max_directory_depth = 30


# ---------------------------------------------------------------------------
# 11. Static configuration invariants (import-time validation regression)
# ---------------------------------------------------------------------------
# These re-assert the invariants that ``_validate_configuration()`` enforces
# at import time. They guard against future drift in the shipped tables and
# keep the fail-fast contract observable from the test suite.

def test_no_duplicate_pattern_or_rule_names():
    folder_names = [p.name for p in ALL_FOLDER_PATTERNS]
    assert len(folder_names) == len(set(folder_names))
    portable_names = [p.name for p in PORTABLE_PATTERNS]
    assert len(portable_names) == len(set(portable_names))
    exclusion_names = {r.name for r in DEFAULT_EXCLUSION_RULES}
    assert len(exclusion_names) == len(DEFAULT_EXCLUSION_RULES)


def test_folder_patterns_are_well_formed():
    """Segments must be plain, unseparated, trimmed names: patterns are
    matched component-wise by the classifier through src.pathnorm, so a
    separator inside a segment would silently break matching."""
    for p in ALL_FOLDER_PATTERNS:
        assert p.name and p.rationale.strip()
        assert p.segments
        for segment in p.segments:
            assert segment
            assert segment == segment.strip()
            assert "\\" not in segment
            assert "/" not in segment
        assert p.default_severity in ALLOWED_SEVERITIES
        assert p.default_confidence in ALLOWED_CONFIDENCES
        assert p.category in LocationCategory
        assert p.anchor in FolderAnchor
        assert p.match_rule in FolderMatchRule


def test_portable_patterns_compile_and_have_positive_scores():
    """Scores feed the deterministic PortableCandidate score; a non-positive
    or bool score would corrupt confidence tiers (FR-3.3)."""
    for p in PORTABLE_PATTERNS:
        assert isinstance(p.compiled, re.Pattern)
        assert isinstance(p.score, int)
        assert not isinstance(p.score, bool)
        assert p.score > 0
        assert p.default_confidence in ALLOWED_CONFIDENCES
        assert p.kind in PortableLayoutKind


def test_exclusion_rules_have_lowercase_segments_and_rationale():
    """Matching is performed against lowercased path segments, so the rule
    data itself must already be lowercase or it can never fire — a silent
    false-negative for every user."""
    for rule in DEFAULT_EXCLUSION_RULES:
        assert rule.name and rule.rationale.strip()
        assert rule.category in ExclusionCategory
        for segment in rule.exact_segments:
            assert segment == segment.lower()
            assert segment == segment.strip()
        for run in rule.consecutive_segments:
            assert run
            for segment in run:
                assert segment == segment.lower()
                assert segment == segment.strip()


def test_precedence_and_defaults_are_complete_and_duplicate_free():
    assert set(CATEGORY_PRECEDENCE) == set(LocationCategory)
    assert len(set(CATEGORY_PRECEDENCE)) == len(CATEGORY_PRECEDENCE)
    assert len(SEVERITY_ORDER) == 3
    assert len(CONFIDENCE_ORDER) == 3
