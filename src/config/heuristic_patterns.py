"""Heuristic pattern configuration for user-data and portable-app discovery.

Implements the SDD §2.6 configuration duties (with SRS FR-3 / FR-4 constraints):

* potential user-data folder patterns (shell folders, AppData, VirtualStore,
  ProgramData, per-user programs);
* developer/IDE source-directory patterns (Visual Studio, IntelliJ, Rider,
  Eclipse, NetBeans, VS Code / generic);
* OneDrive path patterns (path-only detection, README §5.8);
* portable-application patterns (directory names, executable names, layouts);
* default exclusion pattern data consumed by ``src.heuristics.exclusions``
  (SDD §2.16);
* severity and confidence defaults (FR-4.8 / FR-4.9);
* deterministic category precedence rules (FR-4.7);
* enumeration bounds for filesystem and manifest heuristics (SRS §3.10, NFR-5).

Safety boundaries (why they exist)
----------------------------------
* **No I/O of any kind.** This module is pure, frozen data plus pure helper
  functions. It never opens files, never touches a mount point, and never
  spawns a subprocess. Consequently it cannot write to a scanned source and
  requires no privilege elevation (SRS §3.1, §3.7).
* **Name/path/extension signals only.** Every pattern is evaluated against
  path structure, directory/file names, and extensions. No pattern opens,
  reads, or inspects file contents (SRS §3.3, README §5.14). Portable
  candidates are never executed.
* **Advisory-only wording.** Rationale strings are deliberately framed as
  "may / potential / common" so that downstream findings can never be read
  as certainty (SRS §3.4, FR-4.1, NFR-6).
* **Bounded by design.** ``HeuristicBounds`` mirrors the session-level
  ``ScanOptions`` defaults so that Live Session memory, SQLite size, report
  size, and UI comprehension stay bounded (SRS §3.10, NFR-5).
* **Fail-fast configuration validation.** ``_validate_configuration()`` runs
  at import time, so a defective heuristic table (duplicate names, unknown
  severity, incomplete precedence, non-lowercased exclusion segment) can
  never reach the classifier at runtime.

The module is versioned; ``ScanOptions.heuristic_patterns_version`` stores
``HEURISTIC_PATTERNS_VERSION`` in the session so exported reports remain
auditable against the exact pattern set that produced them.

Consumers: ``src.heuristics.user_data_classifier`` (folder/developer/OneDrive
patterns, severity/confidence defaults, precedence) and
``src.heuristics.exclusions`` (exclusion rule data).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Iterable

__all__ = [
    "HEURISTIC_PATTERNS_VERSION",
    "SEVERITY_ORDER",
    "CONFIDENCE_ORDER",
    "ALLOWED_SEVERITIES",
    "ALLOWED_CONFIDENCES",
    "LocationCategory",
    "FolderAnchor",
    "FolderMatchRule",
    "ExclusionCategory",
    "PortableLayoutKind",
    "UserFolderPattern",
    "PortablePattern",
    "ExclusionRule",
    "HeuristicBounds",
    "SEVERITY_DEFAULTS",
    "CONFIDENCE_DEFAULTS",
    "CATEGORY_PRECEDENCE",
    "USER_DATA_FOLDER_PATTERNS",
    "DEVELOPER_FOLDER_PATTERNS",
    "ONEDRIVE_FOLDER_PATTERNS",
    "ALL_FOLDER_PATTERNS",
    "PORTABLE_PATTERNS",
    "DEFAULT_EXCLUSION_RULES",
    "DEFAULT_HEURISTIC_BOUNDS",
    "EXECUTABLE_EXTENSIONS",
    "SHORTCUT_EXTENSIONS",
    "APP_PACKAGE_EXTENSIONS",
    "ONEDRIVE_BASE_SEGMENT",
    "is_onedrive_segment",
    "has_executable_extension",
    "has_shortcut_extension",
    "has_app_package_extension",
    "severity_rank",
    "confidence_rank",
    "higher_severity",
    "higher_confidence",
    "category_precedence_rank",
    "choose_category",
    "patterns_for_category",
    "default_severity_for",
    "default_confidence_for",
    "resolve_heuristic_bounds",
]


# ---------------------------------------------------------------------------
# Version stamp
# ---------------------------------------------------------------------------

# Version stamp for this heuristic table. Stored in the session's
# ScanOptions (``heuristic_patterns_version``) so a report can be audited
# against the exact pattern set that produced it (SDD §2.6, FR-6.1).
HEURISTIC_PATTERNS_VERSION: Final[str] = "1.0.0"


# ---------------------------------------------------------------------------
# Level vocabulary (severity / confidence)
# ---------------------------------------------------------------------------

# FR-4.8: severity is a closed, deterministic scale. The strings intentionally
# match the DDD ``USER_DATA_FINDING.severity_level`` values so the classifier
# can coerce them onto ``models.SeverityLevel`` one-to-one.
SEVERITY_ORDER: Final[tuple[str, ...]] = ("Low", "Medium", "High")

# FR-4.9: confidence is a closed, deterministic scale mirroring
# ``models.Confidence`` values.
CONFIDENCE_ORDER: Final[tuple[str, ...]] = ("Low", "Medium", "High")

ALLOWED_SEVERITIES: Final[frozenset[str]] = frozenset(SEVERITY_ORDER)
ALLOWED_CONFIDENCES: Final[frozenset[str]] = frozenset(CONFIDENCE_ORDER)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LocationCategory(StrEnum):
    """``USER_DATA_FINDING.location_category`` vocabulary (DDD §4 mirror).

    Every FR-4.4 candidate category has exactly one member. Values are
    intentionally aligned with the DDD category vocabulary so
    ``src.heuristics.user_data_classifier`` can map them one-to-one onto
    ``models.FindingLocationCategory`` without guessing.
    """

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
    """What a folder pattern's segments are measured against.

    ``PROFILE`` segments are relative to the user profile root
    (e.g. ``C:\\Users\\Alice``); ``DRIVE`` segments are relative to the
    logical drive root (``C:`` for the primary source, ``S1:``/``S2:`` for
    secondaries, per SDD §2.4 rule 6). Anchoring keeps patterns source-
    neutral and independent of raw mount paths.
    """

    PROFILE = "profile"
    DRIVE = "drive"


class FolderMatchRule(StrEnum):
    """How the classifier may match candidate paths against a folder pattern.

    The classifier performs the actual path comparison via ``src.pathnorm``
    (case-insensitive, separator-normalized); this module only declares the
    *rule* so matching logic stays in one place.
    """

    # Candidate path is exactly the directory itself (e.g. the Documents folder).
    DIR_EXACT = "dir_exact"
    # Candidate path is the directory or strictly under it (e.g. OneDrive).
    DIR_OR_UNDER = "dir_or_under"
    # Candidate path is strictly under the directory (e.g. AppData\\Local);
    # findings are emitted at the app-subfolder level, not at the container.
    ANY_UNDER = "any_under"


class ExclusionCategory(StrEnum):
    """Default exclusion categories (SDD §2.16).

    Exactly the eight normative categories: recycle bins, volume metadata
    directories, temporary caches, package caches, version-control metadata,
    virtual environment directories, compiler caches, and obvious system
    restore/recovery areas.
    """

    RECYCLE_BIN = "recycle_bin"
    VOLUME_METADATA = "volume_metadata"
    TEMP_CACHE = "temp_cache"
    PACKAGE_CACHE = "package_cache"
    VCS_METADATA = "vcs_metadata"
    VIRTUAL_ENV = "virtual_env"
    COMPILER_CACHE = "compiler_cache"
    SYSTEM_RECOVERY = "system_recovery"


class PortableLayoutKind(StrEnum):
    """How a portable-application pattern fires (SRS FR-3.2, name-only)."""

    # Matches a directory name (e.g. names containing "portable").
    DIR_NAME = "dir_name"
    # Matches an executable file name (name/extension only, never executed).
    EXE_NAME = "exe_name"
    # Matches a directory *layout*: an executable alongside a data subfolder
    # (both children identified by name only).
    LAYOUT = "layout"


# ---------------------------------------------------------------------------
# Pattern dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserFolderPattern:
    """One potential user-data folder heuristic (SDD §2.6, SRS FR-4.4).

    ``segments`` are path components relative to ``anchor`` (no separators).
    Matching is case-insensitive and is performed by the classifier through
    ``src.pathnorm``; this module never touches the filesystem.

    ``default_severity`` / ``default_confidence`` are advisory defaults
    (FR-4.8 / FR-4.9); the classifier may lower confidence further when only
    manifest evidence is available, counts/sizes are missing, or the source
    is an unresolved secondary (FR-4.9).
    """

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
    """One portable-application heuristic (SRS FR-3.2, ADR-7).

    ``pattern_text`` is a regular expression applied by the portable scanner
    to *lowercased directory or file names* — never to path contents, never
    to file bytes (SRS §3.3). ``score`` feeds the deterministic portable
    score on ``PortableCandidate``; ``default_confidence`` maps to the
    FR-3.3 confidence tiers (strong / possible / weak).
    """

    name: str
    kind: PortableLayoutKind
    pattern_text: str
    score: int
    default_confidence: str
    rationale: str

    def __post_init__(self) -> None:
        # Compile exactly once at configuration-definition time so the scanner
        # never pays per-candidate regex compilation cost (bounded CPU,
        # NFR-1/NFR-5).
        object.__setattr__(self, "_compiled", re.compile(self.pattern_text))

    @property
    def compiled(self) -> "re.Pattern[str]":
        """The precompiled pattern (thread-safe: immutable once built)."""
        return self._compiled


@dataclass(frozen=True)
class ExclusionRule:
    """One default exclusion rule consumed by ``src.heuristics.exclusions``.

    ``exact_segments`` excludes a path if *any* lowercased path segment
    equals one of the names. ``consecutive_segments`` excludes a path if any
    consecutive run of segments matches. ``blocks_traversal=True`` tells the
    scanner not to descend into matching directories at all, which is the
    primary memory/budget protection for known-noisy subtrees (SDD §2.16,
    NFR-5). Segment names are stored lowercased and validated as such.
    """

    name: str
    category: ExclusionCategory
    exact_segments: frozenset[str] = frozenset()
    consecutive_segments: tuple[tuple[str, ...], ...] = ()
    blocks_traversal: bool = True
    rationale: str = ""


# ---------------------------------------------------------------------------
# Extension vocabulary (name-only signals, SRS §3.3)
# ---------------------------------------------------------------------------

# True executables, identified by extension only. PE headers are never parsed
# (SRS §3.3: "Executable evidence shall not parse PE headers").
EXECUTABLE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".exe", ".com", ".bat", ".cmd", ".scr"}
)

# Shortcut files (Start Menu / Desktop evidence, Appendix A.5). Targets are
# never parsed (SRS §3.3: "Shortcut evidence shall not parse .lnk targets");
# only the .lnk file name is used as evidence.
SHORTCUT_EXTENSIONS: Final[frozenset[str]] = frozenset({".lnk"})

# Installer/package containers, by name only.
APP_PACKAGE_EXTENSIONS: Final[frozenset[str]] = frozenset({".msi", ".msix"})


# ---------------------------------------------------------------------------
# Severity / confidence defaults (FR-4.8, FR-4.9)
# ---------------------------------------------------------------------------

# Deterministic per-category defaults. Rationale for the scheme:
# * High severity = content that is typically irreplaceable *and* easily
#   overlooked (photos, video, saved games, OneDrive, developer sources).
# * Medium = commonly holds user data but is less irreplaceable or more
#   likely to be remembered (desktop, downloads, music, AppData).
# * Low = primarily software/system data or the Documents baseline itself
#   (which the user already knows to protect).
SEVERITY_DEFAULTS: Final[dict[LocationCategory, str]] = {
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

# Deterministic per-category defaults. Shell folders are High because the
# folder *identity* is unambiguous (registry-resolved or conventional name);
# confidence refers to evidence strength, not to file value (SRS §3.4).
# Categories fed mostly by manifest-only or path-only evidence default lower
# per FR-4.9.
CONFIDENCE_DEFAULTS: Final[dict[LocationCategory, str]] = {
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


# ---------------------------------------------------------------------------
# Category precedence (FR-4.7: deterministic single-category selection)
# ---------------------------------------------------------------------------

# Precedence order for merged findings: the most specific, most easily
# overlooked category wins when several patterns match one normalized path.
# Developer content and OneDrive are first because they are the highest-value,
# highest-oversight-risk categories; the catch-all (UserOther) is last.
CATEGORY_PRECEDENCE: Final[tuple[LocationCategory, ...]] = (
    LocationCategory.SOURCE_CODE,
    LocationCategory.ONEDRIVE,
    LocationCategory.SAVED_GAMES,
    LocationCategory.VIRTUALSTORE,
    LocationCategory.DOCUMENTS,
    LocationCategory.DESKTOP,
    LocationCategory.DOWNLOADS,
    LocationCategory.PICTURES,
    LocationCategory.MUSIC,
    LocationCategory.VIDEOS,
    LocationCategory.APPDATA_LOCAL,
    LocationCategory.APPDATA_ROAMING,
    LocationCategory.APPDATA_LOCALLOW,
    LocationCategory.PORTABLE_DATA_DIR,
    LocationCategory.INSTALL_DIR,
    LocationCategory.SECONDARY_DRIVE,
    LocationCategory.PROGRAMDATA,
    LocationCategory.USER_PROFILE_OTHER,
    LocationCategory.UNKNOWN,
)


# ---------------------------------------------------------------------------
# User-data folder patterns (SDD §2.6, SRS FR-4.4)
# ---------------------------------------------------------------------------

USER_DATA_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]] = (
    UserFolderPattern(
        name="user_documents",
        category=LocationCategory.DOCUMENTS,
        anchor=FolderAnchor.PROFILE,
        segments=("Documents",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Low",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the user's Documents folder, the default baseline for "
            "personal files. Listed so the user can confirm it is covered by "
            "their preservation plan."
        ),
    ),
    UserFolderPattern(
        name="user_desktop",
        category=LocationCategory.DESKTOP,
        anchor=FolderAnchor.PROFILE,
        segments=("Desktop",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the user's Desktop folder. Desktop files are frequently "
            "missed when only Documents is preserved."
        ),
    ),
    UserFolderPattern(
        name="user_downloads",
        category=LocationCategory.DOWNLOADS,
        anchor=FolderAnchor.PROFILE,
        segments=("Downloads",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the user's Downloads folder. Downloads accumulate "
            "personal files over time and are commonly overlooked."
        ),
    ),
    UserFolderPattern(
        name="user_pictures",
        category=LocationCategory.PICTURES,
        anchor=FolderAnchor.PROFILE,
        segments=("Pictures",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the user's Pictures folder. Photo collections are "
            "typically irreplaceable and easy to overlook."
        ),
    ),
    UserFolderPattern(
        name="user_music",
        category=LocationCategory.MUSIC,
        anchor=FolderAnchor.PROFILE,
        segments=("Music",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the user's Music folder. May contain self-authored or "
            "personally curated audio."
        ),
    ),
    UserFolderPattern(
        name="user_videos",
        category=LocationCategory.VIDEOS,
        anchor=FolderAnchor.PROFILE,
        segments=("Videos",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the user's Videos folder. Personal video is typically "
            "irreplaceable and easy to overlook."
        ),
    ),
    UserFolderPattern(
        name="saved_games",
        category=LocationCategory.SAVED_GAMES,
        anchor=FolderAnchor.PROFILE,
        segments=("Saved Games",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="High",
        requires_non_empty=False,
        rationale=(
            "Matches the 'Saved Games' folder. Save files are user-created "
            "and rarely included in default preservation plans."
        ),
    ),
    UserFolderPattern(
        name="appdata_local",
        category=LocationCategory.APPDATA_LOCAL,
        anchor=FolderAnchor.PROFILE,
        segments=("AppData", "Local"),
        match_rule=FolderMatchRule.ANY_UNDER,
        default_severity="Medium",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Under AppData\\Local, per-application user data and settings "
            "live. Name-only, bounded scan; contents are not inspected."
        ),
    ),
    UserFolderPattern(
        name="appdata_roaming",
        category=LocationCategory.APPDATA_ROAMING,
        anchor=FolderAnchor.PROFILE,
        segments=("AppData", "Roaming"),
        match_rule=FolderMatchRule.ANY_UNDER,
        default_severity="Medium",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Under AppData\\Roaming, per-application user data and settings "
            "live. Name-only, bounded scan; contents are not inspected."
        ),
    ),
    UserFolderPattern(
        name="appdata_locallow",
        category=LocationCategory.APPDATA_LOCALLOW,
        anchor=FolderAnchor.PROFILE,
        segments=("AppData", "LocalLow"),
        match_rule=FolderMatchRule.ANY_UNDER,
        default_severity="Low",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Under AppData\\LocalLow, plugin and browser user data live. "
            "Lower likelihood of irreplaceable content."
        ),
    ),
    UserFolderPattern(
        name="virtual_store",
        category=LocationCategory.VIRTUALSTORE,
        anchor=FolderAnchor.PROFILE,
        segments=("AppData", "Local", "VirtualStore"),
        match_rule=FolderMatchRule.DIR_OR_UNDER,
        default_severity="Medium",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Matches the per-user VirtualStore folder, where Windows "
            "redirects settings for legacy applications."
        ),
    ),
    UserFolderPattern(
        name="user_programs",
        category=LocationCategory.INSTALL_DIR,
        anchor=FolderAnchor.PROFILE,
        segments=("AppData", "Local", "Programs"),
        match_rule=FolderMatchRule.ANY_UNDER,
        default_severity="Low",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Under AppData\\Local\\Programs, per-user application installs "
            "live; per-application data subfolders may hold user settings."
        ),
    ),
    UserFolderPattern(
        name="program_data",
        category=LocationCategory.PROGRAMDATA,
        anchor=FolderAnchor.DRIVE,
        segments=("ProgramData",),
        match_rule=FolderMatchRule.ANY_UNDER,
        default_severity="Low",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Matches the machine-wide ProgramData folder. Mostly application "
            "data; per-user content is unlikely but possible."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Developer / IDE source-directory patterns (SDD §2.6, FR-4.5, README §5.10)
# ---------------------------------------------------------------------------

# All developer patterns are profile-anchored and require the directory to be
# non-empty before being flagged (README §5.10). Weak/generic names get lower
# confidence per FR-4.9.
DEVELOPER_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]] = (
    UserFolderPattern(
        name="vs_source",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("source",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="Medium",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\source, the conventional Visual Studio "
            "source root. Non-empty source directories are flagged as "
            "potential user-authored developer content (README §5.10)."
        ),
    ),
    UserFolderPattern(
        name="vs_source_repos",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("source", "repos"),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="Medium",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\source\\repos, the default Visual Studio "
            "repository root."
        ),
    ),
    UserFolderPattern(
        name="intellij_idea_projects",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("IdeaProjects",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="Medium",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\IdeaProjects, the default IntelliJ IDEA "
            "project root."
        ),
    ),
    UserFolderPattern(
        name="rider_projects",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("RiderProjects",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="Medium",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\RiderProjects, the default Rider/ReSharper "
            "project root."
        ),
    ),
    UserFolderPattern(
        name="eclipse_workspace",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("workspace",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="Low",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\workspace, a common Eclipse workspace root. "
            "The name is generic, so confidence is reduced."
        ),
    ),
    UserFolderPattern(
        name="eclipse_workspace_alt",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("eclipse-workspace",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="Medium",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\eclipse-workspace, an alternate Eclipse "
            "workspace root."
        ),
    ),
    UserFolderPattern(
        name="netbeans_projects",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("NetBeansProjects",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="High",
        default_confidence="Medium",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\NetBeansProjects, the default NetBeans "
            "project root."
        ),
    ),
    UserFolderPattern(
        name="generic_projects",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("projects",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Medium",
        default_confidence="Low",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\projects, a generic project directory. The "
            "name is generic, so confidence is reduced."
        ),
    ),
    UserFolderPattern(
        name="generic_code",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("code",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Low",
        default_confidence="Low",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\code, a generic code directory. Weak name "
            "match; advisory only."
        ),
    ),
    UserFolderPattern(
        name="generic_dev",
        category=LocationCategory.SOURCE_CODE,
        anchor=FolderAnchor.PROFILE,
        segments=("dev",),
        match_rule=FolderMatchRule.DIR_EXACT,
        default_severity="Low",
        default_confidence="Low",
        requires_non_empty=True,
        rationale=(
            "Matches <profile>\\dev, a generic development directory. Weak "
            "name match; advisory only."
        ),
    ),
)


# ---------------------------------------------------------------------------
# OneDrive patterns (SDD §2.6, README §5.8 — path-only detection)
# ---------------------------------------------------------------------------

# Base folder name for OneDrive detection (case-insensitive). Organization
# suffixed folders ("OneDrive - <org>") are handled by is_onedrive_segment().
ONEDRIVE_BASE_SEGMENT: Final[str] = "OneDrive"

ONEDRIVE_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]] = (
    UserFolderPattern(
        name="onedrive_profile",
        category=LocationCategory.ONEDRIVE,
        anchor=FolderAnchor.PROFILE,
        segments=(ONEDRIVE_BASE_SEGMENT,),
        match_rule=FolderMatchRule.DIR_OR_UNDER,
        default_severity="High",
        default_confidence="Medium",
        requires_non_empty=False,
        rationale=(
            "Matches a 'OneDrive' (or 'OneDrive - <organization>') folder "
            "under the user profile. OneDrive commonly stores redirected "
            "user documents; path-only evidence, so confidence is reduced."
        ),
    ),
    UserFolderPattern(
        name="onedrive_drive",
        category=LocationCategory.ONEDRIVE,
        anchor=FolderAnchor.DRIVE,
        segments=(ONEDRIVE_BASE_SEGMENT,),
        match_rule=FolderMatchRule.DIR_OR_UNDER,
        default_severity="High",
        default_confidence="Low",
        requires_non_empty=False,
        rationale=(
            "Matches a 'OneDrive' folder at the drive root of a scanned "
            "source. Path-only evidence; confidence reduced for unresolved "
            "locations."
        ),
    ),
)

# Combined folder-pattern table used by the classifier and by validation.
ALL_FOLDER_PATTERNS: Final[tuple[UserFolderPattern, ...]] = (
    USER_DATA_FOLDER_PATTERNS
    + DEVELOPER_FOLDER_PATTERNS
    + ONEDRIVE_FOLDER_PATTERNS
)


# ---------------------------------------------------------------------------
# Portable-application patterns (SRS FR-3)
# ---------------------------------------------------------------------------

# Pattern text is applied to *lowercased* directory or file names by the
# portable scanner. Scores are deterministic contributions to the
# PortableCandidate.score; confidence maps to the FR-3.3 tiers.
PORTABLE_PATTERNS: Final[tuple[PortablePattern, ...]] = (
    PortablePattern(
        name="portable_apps_suite",
        kind=PortableLayoutKind.DIR_NAME,
        pattern_text=r"^portableapps\.com($|\s)",
        score=40,
        default_confidence="High",
        rationale=(
            "Matches the well-known PortableApps.com suite layout by "
            "directory name."
        ),
    ),
    PortablePattern(
        name="portable_dir_name",
        kind=PortableLayoutKind.DIR_NAME,
        pattern_text=r"portable",
        score=20,
        default_confidence="Medium",
        rationale=(
            "Directory name contains 'portable', a common naming convention "
            "for self-contained applications."
        ),
    ),
    PortablePattern(
        name="portable_exe_name",
        kind=PortableLayoutKind.EXE_NAME,
        pattern_text=r"portable.*\.exe$",
        score=30,
        default_confidence="Medium",
        rationale=(
            "Executable name contains 'portable' and ends in .exe; suggests a "
            "self-contained build. Name/extension only; the executable is "
            "never executed or inspected."
        ),
    ),
    PortablePattern(
        name="portable_layout",
        kind=PortableLayoutKind.LAYOUT,
        pattern_text=r"^(app)?data$",
        score=35,
        default_confidence="Medium",
        rationale=(
            "Directory contains an executable alongside a matching data "
            "subfolder, matching common portable-application layouts. Both "
            "children are identified by name only."
        ),
    ),
    PortablePattern(
        name="generic_secondary_exe",
        kind=PortableLayoutKind.EXE_NAME,
        pattern_text=r"\.exe$",
        score=5,
        default_confidence="Low",
        rationale=(
            "Executable on a secondary source without a registry "
            "fingerprint; weak indicator of a portable or unregistered "
            "application."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Default exclusion rules (SDD §2.16)
# ---------------------------------------------------------------------------

# Data only: matching/short-circuiting logic lives in
# src.heuristics.exclusions. blocks_traversal=True is the main budget and
# noise protection: known-noisy subtrees are never descended into.
DEFAULT_EXCLUSION_RULES: Final[tuple[ExclusionRule, ...]] = (
    ExclusionRule(
        name="recycle_bin",
        category=ExclusionCategory.RECYCLE_BIN,
        exact_segments=frozenset({"$recycle.bin", "recycle.bin"}),
        blocks_traversal=True,
        rationale=(
            "Recycle Bin entries are already-deleted files; outside the "
            "read-only recovery scope."
        ),
    ),
    ExclusionRule(
        name="volume_metadata",
        category=ExclusionCategory.VOLUME_METADATA,
        exact_segments=frozenset({"system volume information", "$avir"}),
        blocks_traversal=True,
        rationale=(
            "Hidden volume metadata (shadow copies, alternate versions) is "
            "not user content."
        ),
    ),
    ExclusionRule(
        name="temp_cache",
        category=ExclusionCategory.TEMP_CACHE,
        exact_segments=frozenset({"temp", "tmp", "cache", "prefetch"}),
        blocks_traversal=True,
        rationale=(
            "Temporary and prefetch caches are regenerable and produce noisy "
            "false positives."
        ),
    ),
    ExclusionRule(
        name="package_cache",
        category=ExclusionCategory.PACKAGE_CACHE,
        exact_segments=frozenset({".nuget", ".npm"}),
        consecutive_segments=(("pip", "cache"), ("npm", "cache"), ("cargo", "registry")),
        blocks_traversal=True,
        rationale=(
            "Package manager caches hold reproducible downloads and are not "
            "user content."
        ),
    ),
    ExclusionRule(
        name="vcs_metadata",
        category=ExclusionCategory.VCS_METADATA,
        exact_segments=frozenset({".git", ".svn", ".hg", ".vs", ".idea", ".gradle"}),
        blocks_traversal=True,
        rationale=(
            "Version control and IDE project metadata are regenerable "
            "artifacts, not user content."
        ),
    ),
    ExclusionRule(
        name="virtual_env",
        category=ExclusionCategory.VIRTUAL_ENV,
        exact_segments=frozenset({"venv", ".venv"}),
        blocks_traversal=True,
        rationale="Python virtual environments contain only installed packages.",
    ),
    ExclusionRule(
        name="compiler_cache",
        category=ExclusionCategory.COMPILER_CACHE,
        exact_segments=frozenset(
            {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
             "obj", "out", "build"}
        ),
        blocks_traversal=True,
        rationale="Build and compiler artifacts are regenerable from source.",
    ),
    ExclusionRule(
        name="system_recovery",
        category=ExclusionCategory.SYSTEM_RECOVERY,
        exact_segments=frozenset({"recovery"}),
        consecutive_segments=(("windows", "recovery"),),
        blocks_traversal=True,
        rationale="OS recovery and system restore metadata is not user content.",
    ),
)


# ---------------------------------------------------------------------------
# Enumeration bounds for filesystem / manifest heuristics (SRS §3.10, NFR-5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HeuristicBounds:
    """Bounded enumeration limits for filesystem/manifest heuristics.

    These defaults mirror ``models.ScanOptions`` (``max_filesystem_entries_per_source``,
    ``max_directory_depth``, ``max_directory_entries``, ``max_manifest_entries``,
    ``max_findings``) and are the *documented source* of the session defaults.
    At runtime the session's ``ScanOptions`` remains the authority; this
    dataclass exists so the limits are versioned, testable, and visible in
    reports (SRS §3.10, FR-2.3, NFR-5). Bounding protects Live Session memory,
    SQLite size, report size, and user comprehension — it is never permission
    to inspect file contents.
    """

    max_filesystem_entries_per_source: int = 100_000
    max_directory_depth: int = 12
    max_directory_entries: int = 20_000
    max_manifest_entries: int = 500_000
    max_user_data_findings: int = 5_000

    def __post_init__(self) -> None:
        if not 1 <= self.max_directory_depth <= 64:
            raise ValueError(
                f"max_directory_depth must be between 1 and 64, "
                f"got {self.max_directory_depth!r}"
            )
        for name in (
            "max_filesystem_entries_per_source",
            "max_directory_entries",
            "max_manifest_entries",
            "max_user_data_findings",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")


DEFAULT_HEURISTIC_BOUNDS: Final[HeuristicBounds] = HeuristicBounds()


# ---------------------------------------------------------------------------
# Pure helper functions (no I/O; safe to call from any thread)
# ---------------------------------------------------------------------------

def is_onedrive_segment(segment: str) -> bool:
    """True for ``OneDrive`` and ``OneDrive - <organization>`` folder names.

    Case-insensitive and tolerant of surrounding whitespace. Path-only
    detection per README §5.8; never opens or reads anything.
    """
    text = (segment or "").strip().lower()
    base = ONEDRIVE_BASE_SEGMENT.lower()
    return text == base or text.startswith(base + " -")


def _name_has_extension(name: str, extensions: frozenset[str]) -> bool:
    """Defensive file-name extension check (name only, never a path)."""
    text = (name or "").strip().lower()
    if not text:
        return False
    dot = text.rfind(".")
    if dot <= 0:
        return False
    return text[dot:] in extensions


def has_executable_extension(name: str) -> bool:
    """True when a file *name* ends in a known executable extension (SRS §3.3)."""
    return _name_has_extension(name, EXECUTABLE_EXTENSIONS)


def has_shortcut_extension(name: str) -> bool:
    """True when a file *name* is a shortcut (.lnk); targets are never parsed."""
    return _name_has_extension(name, SHORTCUT_EXTENSIONS)


def has_app_package_extension(name: str) -> bool:
    """True when a file *name* is an installer/package container."""
    return _name_has_extension(name, APP_PACKAGE_EXTENSIONS)


def severity_rank(severity: str) -> int:
    """Ordinal rank of a severity value; raises ValueError on unknown input.

    Defensive: callers may pass data read from reports, so unknown levels are
    rejected loudly instead of silently sorting wrong (FR-4.8).
    """
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITY_ORDER}"
        ) from None


def confidence_rank(confidence: str) -> int:
    """Ordinal rank of a confidence value; raises ValueError on unknown input."""
    try:
        return CONFIDENCE_ORDER.index(confidence)
    except ValueError:
        raise ValueError(
            f"unknown confidence {confidence!r}; expected one of {CONFIDENCE_ORDER}"
        ) from None


def higher_severity(a: str, b: str) -> str:
    """FR-4.7 merge rule: keep the highest severity among matched heuristics."""
    return a if severity_rank(a) >= severity_rank(b) else b


def higher_confidence(a: str, b: str) -> str:
    """FR-4.7 merge rule: keep the highest confidence among matched heuristics."""
    return a if confidence_rank(a) >= confidence_rank(b) else b


def category_precedence_rank(category: LocationCategory) -> int:
    """Deterministic precedence rank (0 = highest precedence, FR-4.7)."""
    return CATEGORY_PRECEDENCE.index(category)


def choose_category(candidates: Iterable[LocationCategory]) -> LocationCategory:
    """FR-4.7: pick the single winning category for a merged finding.

    Deterministic: the candidate with the best (lowest) precedence rank wins;
    equal categories collapse naturally. Raises ValueError on an empty
    candidate set, which is a caller bug that must not reach the UI.
    """
    best: LocationCategory | None = None
    for candidate in candidates:
        if best is None or category_precedence_rank(candidate) < category_precedence_rank(best):
            best = candidate
    if best is None:
        raise ValueError("choose_category requires at least one candidate")
    return best


def patterns_for_category(category: LocationCategory) -> tuple[UserFolderPattern, ...]:
    """All folder patterns for ``category`` (empty if the category is not
    folder-driven — e.g. SecondaryApp/PortableAppData, which the classifier
    derives from application records instead)."""
    return tuple(p for p in ALL_FOLDER_PATTERNS if p.category is category)


def default_severity_for(category: LocationCategory) -> str:
    """Deterministic default severity (FR-4.8) for ``category``."""
    return SEVERITY_DEFAULTS[category]


def default_confidence_for(category: LocationCategory) -> str:
    """Deterministic default confidence (FR-4.9) for ``category``."""
    return CONFIDENCE_DEFAULTS[category]


def _as_positive_int(value: int | None, fallback: int) -> int:
    """Defensively coerce an operator-supplied bound; invalid input → fallback.

    Mirrors ``evidence_locations._as_positive_int``: ``bool`` is rejected
    explicitly because it is an ``int`` subclass, and any non-positive or
    non-int value falls back to the documented default rather than crashing
    a scan session.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return fallback
    return value


def resolve_heuristic_bounds(
    *,
    max_filesystem_entries_per_source: int | None = None,
    max_directory_depth: int | None = None,
    max_directory_entries: int | None = None,
    max_manifest_entries: int | None = None,
    max_user_data_findings: int | None = None,
) -> HeuristicBounds:
    """Resolve operator-supplied bounds against the documented defaults.

    Returns a new frozen ``HeuristicBounds``; invalid or missing values are
    replaced by ``DEFAULT_HEURISTIC_BOUNDS`` values, so a bad operator
    setting can never produce an unbounded scan (SRS §3.10).
    """
    defaults = DEFAULT_HEURISTIC_BOUNDS
    return HeuristicBounds(
        max_filesystem_entries_per_source=_as_positive_int(
            max_filesystem_entries_per_source,
            defaults.max_filesystem_entries_per_source,
        ),
        max_directory_depth=_as_positive_int(
            max_directory_depth, defaults.max_directory_depth
        ),
        max_directory_entries=_as_positive_int(
            max_directory_entries, defaults.max_directory_entries
        ),
        max_manifest_entries=_as_positive_int(
            max_manifest_entries, defaults.max_manifest_entries
        ),
        max_user_data_findings=_as_positive_int(
            max_user_data_findings, defaults.max_user_data_findings
        ),
    )


# ---------------------------------------------------------------------------
# Import-time configuration validation (fail fast)
# ---------------------------------------------------------------------------

def _validate_configuration() -> None:
    """Fail fast at import time on any heuristic configuration defect.

    The heuristic table is data-driven (SDD §2.6, NFR-4). A defective table —
    duplicate names, unknown severity, a category missing from the
    precedence, a non-lowercased exclusion segment, or a non-positive bound —
    would silently corrupt classifier output on a stressed user's machine.
    Detecting defects at import time converts them into loud, local,
    actionable failures instead of runtime surprises.
    """
    problems: list[str] = []

    if not HEURISTIC_PATTERNS_VERSION:
        problems.append("HEURISTIC_PATTERNS_VERSION is empty")

    if set(SEVERITY_ORDER) != {"Low", "Medium", "High"}:
        problems.append("SEVERITY_ORDER must be exactly ('Low', 'Medium', 'High')")
    if set(CONFIDENCE_ORDER) != {"Low", "Medium", "High"}:
        problems.append("CONFIDENCE_ORDER must be exactly ('Low', 'Medium', 'High')")

    seen_pattern_names: set[str] = set()
    for pattern in ALL_FOLDER_PATTERNS:
        where = f"folder pattern {pattern.name!r}"
        if not pattern.name:
            problems.append(f"{where}: empty name")
            continue
        if pattern.name in seen_pattern_names:
            problems.append(f"{where}: duplicate pattern name")
        seen_pattern_names.add(pattern.name)
        if not pattern.segments:
            problems.append(f"{where}: empty segments")
        for segment in pattern.segments:
            if (
                not segment
                or segment != segment.strip()
                or "\\" in segment
                or "/" in segment
            ):
                problems.append(f"{where}: invalid segment {segment!r}")
        if pattern.default_severity not in ALLOWED_SEVERITIES:
            problems.append(f"{where}: unknown severity {pattern.default_severity!r}")
        if pattern.default_confidence not in ALLOWED_CONFIDENCES:
            problems.append(f"{where}: unknown confidence {pattern.default_confidence!r}")
        if not pattern.rationale.strip():
            problems.append(f"{where}: empty rationale")

    for pattern in DEVELOPER_FOLDER_PATTERNS:
        if pattern.category is not LocationCategory.SOURCE_CODE:
            problems.append(
                f"developer pattern {pattern.name!r} must use the DeveloperContent category"
            )
        if pattern.anchor is not FolderAnchor.PROFILE or not pattern.requires_non_empty:
            problems.append(
                f"developer pattern {pattern.name!r} must be profile-anchored "
                "and require non-emptiness"
            )

    for pattern in ONEDRIVE_FOLDER_PATTERNS:
        if pattern.category is not LocationCategory.ONEDRIVE:
            problems.append(
                f"OneDrive pattern {pattern.name!r} must use the OneDrive category"
            )

    seen_portable_names: set[str] = set()
    for pattern in PORTABLE_PATTERNS:
        where = f"portable pattern {pattern.name!r}"
        if not pattern.name:
            problems.append(f"{where}: empty name")
            continue
        if pattern.name in seen_portable_names:
            problems.append(f"{where}: duplicate pattern name")
        seen_portable_names.add(pattern.name)
        if not isinstance(pattern.score, int) or isinstance(pattern.score, bool) or pattern.score <= 0:
            problems.append(f"{where}: score must be a positive integer")
        if pattern.default_confidence not in ALLOWED_CONFIDENCES:
            problems.append(f"{where}: unknown confidence {pattern.default_confidence!r}")
        if not pattern.rationale.strip():
            problems.append(f"{where}: empty rationale")

    seen_exclusion_names: set[str] = set()
    for rule in DEFAULT_EXCLUSION_RULES:
        where = f"exclusion rule {rule.name!r}"
        if not rule.name:
            problems.append(f"{where}: empty name")
            continue
        if rule.name in seen_exclusion_names:
            problems.append(f"{where}: duplicate rule name")
        seen_exclusion_names.add(rule.name)
        for segment in rule.exact_segments:
            if not segment or segment != segment.strip() or segment != segment.lower():
                problems.append(
                    f"{where}: exact segment must be a non-empty lowercase name: {segment!r}"
                )
        for run in rule.consecutive_segments:
            if not run:
                problems.append(f"{where}: empty consecutive-segment run")
                continue
            for segment in run:
                if not segment or segment != segment.strip() or segment != segment.lower():
                    problems.append(
                        f"{where}: consecutive segment must be a non-empty lowercase name: {segment!r}"
                    )
        if not rule.rationale.strip():
            problems.append(f"{where}: empty rationale")

    if len(set(CATEGORY_PRECEDENCE)) != len(CATEGORY_PRECEDENCE):
        problems.append("CATEGORY_PRECEDENCE contains duplicates")
    if set(CATEGORY_PRECEDENCE) != set(LocationCategory):
        problems.append("CATEGORY_PRECEDENCE must cover every LocationCategory exactly once")

    if set(SEVERITY_DEFAULTS) != set(LocationCategory):
        problems.append("SEVERITY_DEFAULTS must define a severity for every LocationCategory")
    for category, severity in SEVERITY_DEFAULTS.items():
        if severity not in ALLOWED_SEVERITIES:
            problems.append(
                f"SEVERITY_DEFAULTS[{category.name}]: unknown severity {severity!r}"
            )
    if set(CONFIDENCE_DEFAULTS) != set(LocationCategory):
        problems.append("CONFIDENCE_DEFAULTS must define a confidence for every LocationCategory")
    for category, confidence in CONFIDENCE_DEFAULTS.items():
        if confidence not in ALLOWED_CONFIDENCES:
            problems.append(
                f"CONFIDENCE_DEFAULTS[{category.name}]: unknown confidence {confidence!r}"
            )

    bounds = DEFAULT_HEURISTIC_BOUNDS
    if not isinstance(bounds.max_directory_depth, int) or not 1 <= bounds.max_directory_depth <= 64:
        problems.append("max_directory_depth must be an integer between 1 and 64")
    for name in (
        "max_filesystem_entries_per_source",
        "max_directory_entries",
        "max_manifest_entries",
        "max_user_data_findings",
    ):
        value = getattr(bounds, name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            problems.append(f"{name} must be a positive integer")

    if problems:
        raise ValueError(
            "heuristic_patterns configuration defect: " + "; ".join(problems)
        )


# Validate the table exactly once, at import time.
_validate_configuration()
