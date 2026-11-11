"""Pure-memory pytest suite for :mod:`src.pathnorm` (SDD §2.4).

Coverage map (test matrix)
==========================
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

Purity contract
===============
Every behavioral test is pure memory: no ``os``, ``subprocess``, ``socket``,
and no filesystem access of any scanned source.  ``pathlib.Path`` appears
only as an inert value that :mod:`src.pathnorm` string-converts lexically.
The single deliberate exception is :class:`TestSourceHygiene`, which reads
the application's *own source file* (never a scanned source) to lock the
compile-time docstring-escape rule.

Bug awareness (F-04 .. F-07)
============================
These tests assert the *corrected* behavior, not the historical bug:

* F-04: a run of two or more leading separators is a UNC share and must
  survive normalization as exactly two backslashes; ``is_unc_path`` fires.
* F-05: ``pn.comparison_form(x)`` equals ``models.canon_lower_path(x)``;
  hash-grade digests must not drift between parse and report hydration.
* F-06: ``source_relative_to_logical`` refuses to prefix UNC shares with a
  logical drive (that would fabricate provenance).
* F-07: ``is_linux_path_under`` anchors containment on the filesystem root.
"""

import re
import warnings
from pathlib import Path

import pytest

from src import models
from src import pathnorm as pn

_SRC_PATHNORM = Path(__file__).resolve().parent.parent / "src" / "pathnorm.py"

# ---------------------------------------------------------------------------
# Battery constants shared by the cross-module parity class
# ---------------------------------------------------------------------------

#: Valid inputs on which display-grade and hash-grade canonicalization must
#: agree *directly* (F-05).  Mirrors and extends the regression battery in
#: :class:`TestF04F05RegressionLocks`.
_RAW_PARITY_INPUTS: tuple[str, ...] = (
    "C:\\Users\\Bob",
    "C:\\Users\\Bob\\Documents\\report.txt",
    "c:\\users\\bob",
    "Users\\Bob",
    "Users/Bob/Desktop",
    "C:",
    "C:\\",
    "S1:\\Programs\\App",
    "S2:\\data",
    "D:\\Windows",
    "file.txt",
    "C:\\dir:sub\\file",
    "C:\\Program Files (x86)\\Common Files",
    "a//\\b",
    "\\server\\share",
    "\\server\\share\\sub",
    "\\\\server",
    "\\\\server\\",
    "\\\\",
    "\\",
    "C:\\Users\\Default",
    "C:\\ProgramData\\Microsoft",
    "C:\\Users\\Bob\\AppData\\Local",
)

#: Adversarial raw inputs for which parity is asserted on their *normalized*
#: forms.  ``pathnorm``'s own contract guarantees that display-grade and
#: hash-grade stages converge on every value this module produces, so this
#: battery is safe even for corrupt spellings (NUL, ADS, stray separators).
_ADVERSARIAL_NORMALIZATION_INPUTS: tuple[str, ...] = (
    "C:\\Users\\Bob",
    "  C:\\Users\\Bob  ",
    "C:\\Us\x00ers\\Bo\x00b",
    "file.txt:stream",
    "C:file.txt:stream",
    ":stream",
    "C:\\dir:sub\\file",
    "C:\\dir\\:",
    "C:\\\\\\Users",
    "c:\\USERS\\bob",
    "C:/Users/Bob",
    "C:\\",
    "C:",
    "\\server\\share",
    "///server/x",
    "/Users/Bob",
    "C:\\Users\\Bob\\",
    "S1:\\data",
    "",
    "   ",
)


# ---------------------------------------------------------------------------
# 1. Core normalization & sanitization
# ---------------------------------------------------------------------------

class TestNormalizationAndSanitization:
    """Rule-by-rule locks for ``normalize_windows_path`` / ``strip_ads``.

    Why these matter: every evidence hash (DDD §5) and dedup key (DDD §3,
    ``UNIQUE(session_id, source_id, normalized_path)``) depends on this
    normalization being total, idempotent, and case-stable on display.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # -- Happy paths: standard Windows spellings ----------------------
            ("C:\\Users\\Bob", "C:\\Users\\Bob"),
            ("C:/Users/Bob", "C:\\Users\\Bob"),
            ("c:\\users\\bob", "C:\\users\\bob"),
            ("C:\\Users//Bob", "C:\\Users\\Bob"),
            ("C:\\\\Users\\\\Bob", "C:\\Users\\Bob"),
            ("C:\\Users\\Bob\\", "C:\\Users\\Bob"),
            ("  C:\\Users\\Bob  ", "C:\\Users\\Bob"),
            ("Users\\Bob\\Desktop", "Users\\Bob\\Desktop"),
            ("s1:\\programs\\app", "S1:\\programs\\app"),
            ("D:\\Windows\\System32", "D:\\Windows\\System32"),
            (
                "C:\\Program Files (x86)\\Common Files",
                "C:\\Program Files (x86)\\Common Files",
            ),
            # -- Drive roots and deep nesting ---------------------------------
            ("C:\\", "C:"),
            ("C:\\\\", "C:"),
            ("C:\\a\\b\\c\\d\\e", "C:\\a\\b\\c\\d\\e"),
            # -- POSIX / mixed inputs ------------------------------------------
            ("/Users/Bob", "Users\\Bob"),
            # ".." is NOT resolved here: display normalization is not a
            # lexical resolver (that is manifest parsing's job, §6 below).
            ("/a//b/../c", "a\\b\\..\\c"),
            ("\\Windows\\System32", "Windows\\System32"),
            # -- Corrupt inputs: sentinels and NUL injection --------------------
            (None, ""),
            ("", ""),
            ("   ", ""),
            ("\t \n", ""),
            ("C:\\Us\x00ers\\Bo\x00b", "C:\\Users\\Bob"),
            # -- Middle-component colons are preserved, never rewritten --------
            # A colon inside a middle component is malformed NTFS input; it
            # must survive verbatim so corrupt feeds cannot be mistaken for a
            # different, legitimate path.
            ("C:\\dir:sub\\file", "C:\\dir:sub\\file"),
            ("C:\\a:b\\c:d\\e", "C:\\a:b\\c:d\\e"),
            # -- ADS stripping: final component only ---------------------------
            ("file.txt:stream", "file.txt"),
            ("C:file.txt:stream", "C:file.txt"),
            (":stream", ""),
            ("C:\\Users\\Bob:stream", "C:\\Users\\Bob"),
            ("C:\\dir\\:", "C:\\dir"),
            ("C:\\file.dat:INDEX", "C:\\file.dat"),
        ],
    )
    def test_normalize_windows_path_value_and_idempotency(
        self, raw: str | None, expected: str
    ) -> None:
        got = pn.normalize_windows_path(raw)
        assert got == expected
        # Idempotency keeps report hydration (DDD §9) byte-stable when hashes
        # are re-derived from stored normalized values.
        assert pn.normalize_windows_path(got) == got

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # -- UNC divergence classes (F-04) ----------------------------------
            ("\\\\server\\share", "\\\\server\\share"),
            ("\\\\server\\share\\sub", "\\\\server\\share\\sub"),
            ("\\\\server\\share\\", "\\\\server\\share"),
            ("\\\\server", "\\\\server"),
            ("\\\\\\server", "\\\\server"),     # 3+ leading -> exactly two
            ("\\\\\\\\server", "\\\\server"),   # 4+ leading -> exactly two
            ("///server/x", "\\\\server\\x"),   # 3+ leading POSIX -> UNC form
            # -- Degenerate / stray leading separators --------------------------
            ("\\\\", ""),                       # bare UNC root -> absent
            ("\\", ""),                         # stray single leading separator
            ("\\server\\share", "server\\share"),  # single leading is NOT UNC
        ],
    )
    def test_unc_and_degenerate_leading_separators(
        self, raw: str, expected: str
    ) -> None:
        got = pn.normalize_windows_path(raw)
        assert got == expected
        assert pn.normalize_windows_path(got) == got

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("C:\\Users\\Bob\\file.txt:stream", "C:\\Users\\Bob\\file.txt"),
            ("file.txt:stream", "file.txt"),
            ("C:file.txt:stream", "C:file.txt"),
            (":stream", ""),
            ("C:\\dir:sub\\file", "C:\\dir:sub\\file"),
            ("\\\\server\\share:stream", "\\\\server\\share"),
            ("C:\\Users\\Bob", "C:\\Users\\Bob"),
            (None, ""),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_strip_ads(self, raw: str | None, expected: str) -> None:
        got = pn.strip_ads(raw)
        assert got == expected
        # ``strip_ads`` exists to document intent at the DDD §5 call site;
        # it must never diverge from ``normalize_windows_path`` (single code
        # path, no second canonicalization).
        assert got == pn.normalize_windows_path(raw)


# ---------------------------------------------------------------------------
# 2. Comparison & equality
# ---------------------------------------------------------------------------

class TestComparisonAndEquality:
    """Case-insensitive comparison (SDD §2.4 rule 2).

    Lowercasing happens only here; display values keep their original case.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("C:\\Users\\Bob", "c:\\users\\bob"),
            ("c:\\USERS\\BOB", "c:\\users\\bob"),
            ("C:/Users/Bob", "c:\\users\\bob"),
            ("C:", "c:"),
            ("C:\\", "c:"),
            ("S1:\\Programs", "s1:\\programs"),
            ("D:\\Windows", "d:\\windows"),
            ("\\\\server\\share", "\\\\server\\share"),
            ("file.txt:stream", "file.txt"),
            ("  C:\\X  ", "c:\\x"),
            (None, ""),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_comparison_form_value_and_idempotency(
        self, raw: str | None, expected: str
    ) -> None:
        got = pn.comparison_form(raw)
        assert got == expected
        assert pn.comparison_form(got) == got

    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            # Case insensitivity.
            ("C:\\Users\\Bob", "c:\\users\\bob", True),
            ("C:/Users/Bob", "C:\\Users\\Bob", True),
            # Trailing separator tolerance.
            ("C:\\Users\\Bob", "C:\\Users\\Bob\\", True),
            ("C:\\Users\\Bob\\", "C:\\Users\\Bob", True),
            # ADS insensitivity.
            ("file.txt:stream", "file.txt", True),
            # UNC and secondary drives compare normally.
            ("\\\\server\\share", "\\\\server\\share", True),
            ("S1:\\a", "s1:\\a", True),
            # Distinct paths stay distinct (prefix trap included).
            ("C:\\Users\\Bob", "C:\\Users\\Bobby", False),
            ("C:\\x", "D:\\x", False),
            ("C:\\Users\\Bob", "C:\\Users\\Bob2", False),
            ("C:\\Users\\Bob", None, False),
        ],
    )
    def test_paths_equal(self, a: str | None, b: str | None, expected: bool) -> None:
        assert pn.paths_equal(a, b) is expected


# ---------------------------------------------------------------------------
# 3. Containment & hierarchy
# ---------------------------------------------------------------------------

class TestContainmentAndHierarchy:
    """Separator-anchored, case-insensitive containment.

    Why separator anchoring matters: a bare string-prefix test would claim
    ``C:\\Users\\Bobby`` is inside ``C:\\Users\\Bob`` and silently merge two
    different users' evidence (DDD §3 uniqueness is keyed on normalized
    paths, so this class of bug corrupts deduplication).
    """

    @pytest.mark.parametrize(
        ("child", "parent", "expected"),
        [
            # Strict nesting.
            ("C:\\Users\\Bob\\Documents", "C:\\Users\\Bob", True),
            ("C:\\a\\b\\c\\d", "C:\\a", True),
            ("c:\\users\\bob\\x", "C:\\USERS\\BOB", True),
            ("C:\\Users\\Bob\\x", "C:\\Users\\Bob\\", True),
            ("C:\\Windows", "C:", True),
            ("\\\\server\\share\\a", "\\\\server\\share", True),
            # The "Bobby" trap: no separator anchor, no containment.
            ("C:\\Users\\Bobby", "C:\\Users\\Bob", False),
            ("C:\\Users\\Bob\\x", "C:\\Users\\Bob2", False),
            # Strictness: a path is not *strictly* under itself.
            ("C:\\Users\\Bob", "C:\\Users\\Bob", False),
            ("C:\\Users\\Bob\\", "C:\\Users\\Bob", False),
            # Drive boundaries.
            ("D:\\Windows", "C:", False),
            ("C:\\Windows", "D:", False),
            # Drive-relative ambiguity never anchors containment.
            ("C:Windows", "C:", False),
            # Siblings and UNC prefix traps.
            ("C:\\Users\\Bob\\Desktop", "C:\\Users\\Bob\\Documents", False),
            ("\\\\server\\shares\\a", "\\\\server\\share", False),
            # Sentinel sides never anchor containment.
            (None, "C:", False),
            ("C:\\x", None, False),
            ("", "", False),
            ("   ", "   ", False),
        ],
    )
    def test_is_path_under(self, child: str | None, parent: str | None, expected: bool) -> None:
        assert pn.is_path_under(child, parent) is expected

    @pytest.mark.parametrize(
        ("child", "parent", "expected"),
        [
            # Inclusive: equality counts.
            ("C:\\Users\\Bob", "C:\\Users\\Bob", True),
            ("C:\\Users\\Bob\\x", "C:\\Users\\Bob", True),
            ("C:\\Users\\Bob\\", "C:\\Users\\Bob", True),
            ("C:\\Windows", "C:", True),
            ("C:", "C:", True),
            ("S1:\\Programs\\App\\x", "S1:", True),
            ("c:\\USERS\\bob", "C:\\Users\\Bob", True),
            # Still anchored and case-insensitive.
            ("C:\\Users\\Bobby", "C:\\Users\\Bob", False),
            ("D:\\x", "C:", False),
            # Sentinel sides never anchor.
            (None, "C:", False),
            ("", "", False),
        ],
    )
    def test_is_path_under_or_equal(self, child: str | None, parent: str | None, expected: bool) -> None:
        assert pn.is_path_under_or_equal(child, parent) is expected

    @pytest.mark.parametrize(
        ("candidate", "documents_root", "expected"),
        [
            # Inside resolved Documents (the root itself counts:
            # under-or-equal semantics, SDD §2.15).
            (
                "C:\\Users\\Bob\\Documents\\report.txt",
                "C:\\Users\\Bob\\Documents",
                True,
            ),
            ("C:\\Users\\Bob\\Documents", "C:\\Users\\Bob\\Documents", True),
            # Redirected Documents on a secondary logical drive.
            ("S1:\\Users\\Bob\\Docs\\x", "S1:\\Users\\Bob\\Docs", True),
            # Outside / prefix traps.
            ("C:\\Users\\Bob\\Desktop\\x", "C:\\Users\\Bob\\Documents", False),
            ("C:\\Users\\Bob\\DocumentsX", "C:\\Users\\Bob\\Documents", False),
            # Unknown baseline (root None/empty): this function returns
            # False; the classifier maps that to the tri-state
            # ``inside_documents = None`` rather than a false negative
            # (SDD §2.15, README §5.8).
            (None, None, False),
            ("C:\\Users\\Bob\\Documents", None, False),
            (None, "C:\\Users\\Bob\\Documents", False),
            ("", "", False),
            # Case-insensitive.
            ("c:\\users\\bob\\documents\\z", "C:\\Users\\Bob\\DOCUMENTS", True),
        ],
    )
    def test_is_inside_documents(
        self, candidate: str | None, documents_root: str | None, expected: bool
    ) -> None:
        assert pn.is_inside_documents(candidate, documents_root) is expected


# ---------------------------------------------------------------------------
# 4. UNC & logical drive routing
# ---------------------------------------------------------------------------

class TestUncAndLogicalDrives:
    """UNC routing (SDD §2.4 rule 5) and logical drive allocation (rule 6).

    Logical drives are the only stable provenance anchor for DDD §5 hashes;
    the allocator must be deterministic and strictly validated.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("\\\\server\\share", True),            # F-04 lock
            ("\\\\server\\share\\sub", True),
            ("\\\\server", True),
            ("\\server\\share", False),             # single leading is not UNC
            ("C:\\x", False),
            ("Users\\Bob", False),
            ("\\\\", False),                        # degenerate root -> absent
            (None, False),
            ("", False),
            ("   ", False),
        ],
    )
    def test_is_unc_path(self, raw: str | None, expected: bool) -> None:
        assert pn.is_unc_path(raw) is expected

    def test_logical_drive_pattern_contract(self) -> None:
        """``LOGICAL_DRIVE_PATTERN`` admits exactly ``C:`` and ``S1:``.. ."""
        rx = re.compile(pn.LOGICAL_DRIVE_PATTERN, re.IGNORECASE)
        for good in ("C:", "S1:", "S2:", "S99:", "S100:"):
            assert rx.match(good) is not None
        for bad in ("S0:", "D:", "S1", "S:", "C1:", "S:1", "X:", ""):
            assert rx.match(bad) is None

    @pytest.mark.parametrize(
        ("drive", "expected"),
        [
            ("C:", "C:"),
            ("c:", "C:"),
            (" S1: ", "S1:"),
            ("s2:", "S2:"),
            ("S10:", "S10:"),
            ("s99:", "S99:"),
        ],
    )
    def test_validate_logical_drive_accepts(self, drive: str, expected: str) -> None:
        assert pn.validate_logical_drive(drive) == expected

    @pytest.mark.parametrize(
        "drive",
        ["D:", "S0:", "S1", "S:", "C1:", "S:1", "X:", "C:\\", "", "   "],
    )
    def test_validate_logical_drive_rejects(self, drive: str) -> None:
        # An invalid logical drive is a caller contract violation (the
        # addition-order allocator in src.db is the only producer), not
        # corrupt data: it must fail loudly, never degrade silently.
        with pytest.raises(ValueError, match="Invalid logical drive"):
            pn.validate_logical_drive(drive)

    @pytest.mark.parametrize(
        ("position", "expected"),
        [
            (0, "C:"),
            (1, "S1:"),
            (2, "S2:"),
            (10, "S10:"),
            (99, "S99:"),
            (100, "S100:"),
        ],
    )
    def test_logical_drive_for_position(self, position: int, expected: str) -> None:
        assert pn.logical_drive_for_position(position) == expected

    @pytest.mark.parametrize("position", [-1, -42, True, False, 0.0, "0", None])
    def test_logical_drive_for_position_rejects(self, position: object) -> None:
        # bools are explicitly excluded: ``isinstance(True, int)`` is True,
        # and letting booleans in would corrupt the addition-order mapping.
        with pytest.raises(ValueError, match="non-negative integer"):
            pn.logical_drive_for_position(position)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("C:\\Users\\Bob", "Users\\Bob"),
            ("C:", ""),
            ("C:\\", ""),
            ("c:\\users", "users"),
            # Any drive letter strips, keeping foreign-drive input stable.
            ("D:\\x", "x"),
            ("S1:", ""),
            ("S2:\\Programs\\Foo", "Programs\\Foo"),
            # Drive-free paths pass through unchanged.
            ("Users\\Bob", "Users\\Bob"),
            # UNC has no drive prefix: passthrough, still unresolved.
            ("\\\\server\\share", "\\\\server\\share"),
            # ADS is stripped before projection.
            ("C:\\Users\\Bob:stream", "Users\\Bob"),
            (None, ""),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_logical_to_source_relative(self, raw: str | None, expected: str) -> None:
        assert pn.logical_to_source_relative(raw) == expected

    @pytest.mark.parametrize(
        ("source_relative", "drive", "expected"),
        [
            ("Users\\Bob", "C:", "C:\\Users\\Bob"),
            ("", "C:", "C:"),
            (None, "C:", "C:"),
            ("   ", "S1:", "S1:"),
            ("S1\\Programs", "S1:", "S1:\\Programs"),
            ("Programs\\App", "S2:", "S2:\\Programs\\App"),
            ("/Users/Bob", "C:", "C:\\Users\\Bob"),
            # Idempotent on its own output.
            ("C:\\Users\\Bob", "C:", "C:\\Users\\Bob"),
            # Defensive remap: an existing foreign prefix is replaced.
            ("C:\\Users\\Bob", "S1:", "S1:\\Users\\Bob"),
            ("c:\\users", "C:", "C:\\users"),
        ],
    )
    def test_source_relative_to_logical(
        self, source_relative: str | None, drive: str, expected: str
    ) -> None:
        assert pn.source_relative_to_logical(source_relative, drive) == expected

    @pytest.mark.parametrize("drive", ["D:", "S0:", "S1", "", "   "])
    def test_source_relative_to_logical_rejects_invalid_drive(self, drive: str) -> None:
        with pytest.raises(ValueError, match="Invalid logical drive"):
            pn.source_relative_to_logical("Users\\Bob", drive)

    @pytest.mark.parametrize(
        "unc",
        ["\\\\server\\share", "\\\\SERVER\\Share", "\\\\server\\share\\"],
    )
    def test_source_relative_to_logical_rejects_unc(self, unc: str) -> None:
        # F-06: prefixing a UNC share with a logical drive would fabricate
        # provenance ("C:\\server\\share"); fail loudly instead.
        with pytest.raises(ValueError, match="Refusing to prefix a UNC path"):
            pn.source_relative_to_logical(unc, "C:")


# ---------------------------------------------------------------------------
# 5. POSIX / mount-side safety
# ---------------------------------------------------------------------------

class TestPosixMountSideSafety:
    """Mount-root containment and the sole mount->canonical mapping route.

    Why this is a safety boundary (SDD §2.4 rule 7, §4.1): raw Linux mount
    paths are transient acquisition state.  Only
    ``map_mount_path_to_source_relative`` may convert them into canonical
    evidence paths, and it must refuse escapes loudly — a silent fallback
    would reference data outside the acquired source and corrupt evidence
    provenance.
    """

    @pytest.mark.parametrize(
        ("child", "parent", "include_self", "expected"),
        [
            # F-07: containment under the filesystem root.
            ("/a/b", "/", False, True),
            ("/x", "/", False, True),
            ("/", "/", True, True),
            ("/", "/", False, False),
            ("/a", "/a", True, True),
            ("/a", "/a", False, False),
            # Normal nesting, dot components, trailing slashes.
            ("/a/b/c", "/a", False, True),
            ("/a/b/c", "/a/b", False, True),
            ("/a/./b", "/a", False, True),
            ("/a/b/", "/a", False, True),
            ("/recovery/mounts/abc/Windows", "/recovery/mounts", False, True),
            # Siblings, shorter prefixes, containment above.
            ("/a/b", "/a/c", False, False),
            ("/abc", "/a", False, False),
            ("/a", "/a/b", False, False),
            # Lexical escapes resolve outside the root: False, never a raise
            # (this is a predicate; the mapper is the loud-fail boundary).
            ("/a/../etc/passwd", "/a", False, False),
            ("/../../x", "/a", False, False),
            # Non-absolute / sentinel inputs: False, never a raise.
            ("relative/path", "/a", False, False),
            (None, "/a", False, False),
            ("/a", None, False, False),
            ("", "/", False, False),
            ("   ", "/a", False, False),
            # Path objects are accepted via pure lexical string conversion.
            (Path("/a/b"), Path("/a"), False, True),
        ],
    )
    def test_is_linux_path_under(
        self,
        child: str | Path | None,
        parent: str | Path | None,
        include_self: bool,
        expected: bool,
    ) -> None:
        assert (
            pn.is_linux_path_under(child, parent, include_self=include_self)
            is expected
        )

    @pytest.mark.parametrize(
        ("mount_path", "mount_root", "expected"),
        [
            (
                "/recovery/mounts/s1/Windows/System32",
                "/recovery/mounts/s1",
                "Windows\\System32",
            ),
            (
                "/recovery/mounts/s1/Users/Bob/Desktop",
                "/recovery/mounts/s1",
                "Users\\Bob\\Desktop",
            ),
            # Spaces and case are preserved: display-grade output.
            (
                "/recovery/mounts/s1/Program Files/x",
                "/recovery/mounts/s1",
                "Program Files\\x",
            ),
            # Single component directly under the root.
            ("/recovery/mounts/s1/File.txt", "/recovery/mounts/s1", "File.txt"),
            # Filesystem root as mount root.
            ("/a/b", "/", "a\\b"),
            # Lexical ``..`` in the root is resolved before comparison.
            ("/recovery/mounts/s1", "/recovery/mounts/s1/..", "s1"),
            # Path objects via pure lexical string conversion.
            (Path("/recovery/mounts/s2/a/b"), Path("/recovery/mounts/s2"), "a\\b"),
        ],
    )
    def test_map_mount_path_to_source_relative(
        self, mount_path: str | Path, mount_root: str | Path, expected: str
    ) -> None:
        assert pn.map_mount_path_to_source_relative(mount_path, mount_root) == expected

    @pytest.mark.parametrize(
        ("mount_path", "mount_root", "message"),
        [
            # ``..`` escapes resolve lexically outside the root.
            (
                "/recovery/mounts/s1/../etc/passwd",
                "/recovery/mounts/s1",
                "outside the mount root",
            ),
            (
                "/recovery/mounts/s1/a/../../..",
                "/recovery/mounts/s1",
                "outside the mount root",
            ),
            # Sibling and unrelated prefixes.
            ("/recovery/mounts/s2/x", "/recovery/mounts/s1", "outside the mount root"),
            ("/etc/passwd", "/recovery/mounts/s1", "outside the mount root"),
            # The root itself has no source-relative form.
            ("/recovery/mounts/s1", "/recovery/mounts/s1", "mount root itself"),
            ("/", "/", "mount root itself"),
            # Inputs that do not normalize to an absolute POSIX path.
            ("recovery/mounts/s1/x", "/recovery/mounts/s1", "absolute POSIX path"),
            ("C:\\Windows", "/recovery/mounts/s1", "absolute POSIX path"),
            (None, "/recovery/mounts/s1", "absolute POSIX path"),
            ("/recovery/mounts/s1/x", None, "absolute POSIX path"),
            ("", "/recovery/mounts/s1", "absolute POSIX path"),
            ("   ", "/recovery/mounts/s1", "absolute POSIX path"),
        ],
    )
    def test_map_mount_path_rejects_escapes_loudly(
        self, mount_path: str | Path | None, mount_root: str | Path | None, message: str
    ) -> None:
        # Loud-fail boundary: every escape must surface as a typed
        # ``ValueError`` that the ingestion layer converts into a
        # ``WarningRecord`` — never a silent remap.
        with pytest.raises(ValueError, match=message):
            pn.map_mount_path_to_source_relative(mount_path, mount_root)


# ---------------------------------------------------------------------------
# 6. Manifest ingestion
# ---------------------------------------------------------------------------

class TestManifestIngestion:
    """Line-by-line manifest mapping (SDD §2.8).

    The parser contract is: one path per line, source-relative Windows-style
    output, ``""`` as the skip sentinel for blanks and comments, malformed
    lines skipped (never fatal), and degenerate ``.``/``..`` components
    dropped lexically.
    """

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("# comment", True),
            ("#comment", True),
            ("  # indented comment", True),
            ("#", True),
            (None, False),
            ("", False),
            ("   ", False),
            ("C:\\x", False),
            ("file # not a comment", False),  # only leading # counts
        ],
    )
    def test_is_manifest_comment(self, line: str | None, expected: bool) -> None:
        assert pn.is_manifest_comment(line) is expected

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            # Source-relative Windows paths: kept as-is.
            ("Users\\Bob\\Desktop", "Users\\Bob\\Desktop"),
            ("Program Files (x86)\\App", "Program Files (x86)\\App"),
            # Drive-qualified: drive stripped.
            ("C:\\Users\\Bob", "Users\\Bob"),
            ("C:\\Users\\Bob\\Documents\\", "Users\\Bob\\Documents"),
            # Foreign drives strip too: stable source-relative form.
            ("D:\\Programs", "Programs"),
            # Drive-relative: drive stripped.
            ("C:Users\\Bob", "Users\\Bob"),
            # Absolute POSIX (user-supplied manifests).
            ("/Users/Bob", "Users\\Bob"),
            ("/a//b/../c", "a\\b\\c"),
            # UNC lines: preserved, treated as unresolved downstream.
            ("\\\\server\\share", "\\\\server\\share"),
            ("\\\\\\\\server", "\\\\server"),
            ("\\\\server\\share\\", "\\\\server\\share"),
            # Degenerate components dropped lexically.
            ("Users/./Bob/../Desktop", "Users\\Bob\\Desktop"),
            (".", ""),
            ("..", ""),
            # Skip sentinels.
            ("", ""),
            ("   ", ""),
            ("# comment", ""),
            (None, ""),
            # Drive-root lines carry no relative form.
            ("C:", ""),
            ("C:\\", ""),
            # ADS stripped before mapping.
            ("file.txt:stream", "file.txt"),
            # Stray single leading separator dropped.
            ("\\x", "x"),
            # Path objects via pure lexical string conversion.
            (Path("/Users/Bob"), "Users\\Bob"),
        ],
    )
    def test_manifest_line_to_source_relative(self, line: str | Path | None, expected: str) -> None:
        got = pn.manifest_line_to_source_relative(line)
        assert got == expected
        if got:
            # Every emitted line is idempotent: re-parsing it changes nothing,
            # which keeps manifest evidence hashes stable across re-runs.
            assert pn.manifest_line_to_source_relative(got) == got


# ---------------------------------------------------------------------------
# 7. Cross-module hash-grade parity (F-05)
# ---------------------------------------------------------------------------

class TestCrossModuleHashParity:
    """F-05 lock: display-grade and hash-grade stages must converge.

    ``pn.comparison_form`` (display-grade, SDD §2.4) and
    ``models.canon_lower_path`` (hash-grade, DDD §5) are independent
    implementations of one canonicalization.  If they drift, DDD §5
    ``evidence_hash`` values computed during ingestion would differ from
    those re-derived during report hydration (DDD §9), silently breaking
    evidence dedup and UNIQUE constraints.
    """

    @pytest.mark.parametrize("raw", _RAW_PARITY_INPUTS)
    def test_comparison_form_matches_canon_lower_path(self, raw: str) -> None:
        assert pn.comparison_form(raw) == models.canon_lower_path(raw)

    @pytest.mark.parametrize("raw", _ADVERSARIAL_NORMALIZATION_INPUTS)
    def test_normalized_outputs_converge_hash_grade(self, raw: str) -> None:
        # The module's own contract: display-grade and hash-grade stages
        # agree on every value this module produces, even when the raw
        # input was corrupt (NUL, ADS, stray separators, whitespace).
        normalized = pn.normalize_windows_path(raw)
        assert pn.comparison_form(normalized) == models.canon_lower_path(normalized)


# ---------------------------------------------------------------------------
# 8. Sentinel totality (None / "" / whitespace)
# ---------------------------------------------------------------------------

class TestTotalitySentinels:
    """Sentinel totality: ``None`` / ``""`` / whitespace must never raise.

    Contract split (defensive-parsing directive):

    * ``str``-returning mappers return the ``""`` absent sentinel;
    * predicates return ``False`` (empty sides never anchor, and
      ``paths_equal`` treats both empty sentinels as equal);
    * the *domain-validation* boundaries — ``validate_logical_drive``,
      ``logical_drive_for_position``, and ``map_mount_path_to_source_relative``
      — raise ``ValueError`` on sentinels by design: an invalid domain is a
      caller contract violation, not corrupt data, and must fail loudly
      rather than degrade silently.
    """

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_normalize_windows_path_sentinels(self, value: str | None) -> None:
        assert pn.normalize_windows_path(value) == ""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_strip_ads_sentinels(self, value: str | None) -> None:
        assert pn.strip_ads(value) == ""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_comparison_form_sentinels(self, value: str | None) -> None:
        assert pn.comparison_form(value) == ""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_is_unc_path_sentinels(self, value: str | None) -> None:
        assert pn.is_unc_path(value) is False

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_logical_to_source_relative_sentinels(self, value: str | None) -> None:
        assert pn.logical_to_source_relative(value) == ""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_manifest_line_to_source_relative_sentinels(self, value: str | None) -> None:
        assert pn.manifest_line_to_source_relative(value) == ""

    @pytest.mark.parametrize("line", [None, "", "   "])
    def test_is_manifest_comment_sentinels(self, line: str | None) -> None:
        assert pn.is_manifest_comment(line) is False

    @pytest.mark.parametrize(
        ("a", "b"),
        [(None, None), (None, ""), ("", "   "), (None, "   ")],
    )
    def test_paths_equal_empty_sides_are_equal(self, a: str | None, b: str | None) -> None:
        # Both empty sentinels normalize to "" and compare equal; callers
        # must treat "" as "absent" and never persist it as a canonical path.
        assert pn.paths_equal(a, b) is True

    @pytest.mark.parametrize(
        ("child", "parent"),
        [(None, None), (None, "C:"), ("C:", None), ("", ""), ("  ", "  ")],
    )
    def test_is_path_under_sentinels(self, child: str | None, parent: str | None) -> None:
        assert pn.is_path_under(child, parent) is False

    @pytest.mark.parametrize(
        ("child", "parent"),
        [(None, None), (None, "C:"), ("C:", None), ("", ""), ("  ", "  ")],
    )
    def test_is_path_under_or_equal_sentinels(self, child: str | None, parent: str | None) -> None:
        assert pn.is_path_under_or_equal(child, parent) is False

    @pytest.mark.parametrize(
        ("candidate", "documents_root"),
        [(None, None), (None, "C:\\x"), ("C:\\x", None), ("", ""), ("  ", "  ")],
    )
    def test_is_inside_documents_sentinels(self, candidate: str | None, documents_root: str | None) -> None:
        assert pn.is_inside_documents(candidate, documents_root) is False

    @pytest.mark.parametrize(
        ("child", "parent"),
        [(None, None), (None, "/"), ("/", None), ("", ""), ("  ", "  ")],
    )
    def test_is_linux_path_under_sentinels(self, child: str | Path | None, parent: str | Path | None) -> None:
        assert pn.is_linux_path_under(child, parent) is False

    @pytest.mark.parametrize("drive", [None, "", "   "])
    def test_validate_logical_drive_sentinels_raise(self, drive: str | None) -> None:
        with pytest.raises(ValueError, match="Invalid logical drive"):
            pn.validate_logical_drive(drive)

    @pytest.mark.parametrize("position", [None, "", "   "])
    def test_logical_drive_for_position_sentinels_raise(self, position: object) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            pn.logical_drive_for_position(position)

    @pytest.mark.parametrize(
        ("mount_path", "mount_root"),
        [(None, None), ("", "/root"), ("  ", "/root"), ("/root", None), ("/root", "  ")],
    )
    def test_map_mount_path_sentinels_raise(self, mount_path: str | Path | None, mount_root: str | Path | None) -> None:
        with pytest.raises(ValueError, match="absolute POSIX path"):
            pn.map_mount_path_to_source_relative(mount_path, mount_root)


# ---------------------------------------------------------------------------
# 9. Regression locks for F-04 .. F-07 (pre-existing, preserved verbatim)
# ---------------------------------------------------------------------------

class TestF04F05RegressionLocks:
    """Regression locks for the UNC detection and hash-grade parity defects.
    These tests MUST fail against the unfixed code and pass after the F-04/F-05
    patches are applied to src/pathnorm.py and src/models.py."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("\\\\server\\share", "\\\\server\\share"),   # F-04: UNC preserved
            ("\\\\\\server", "\\\\server"),               # 3+ leading -> exactly two
            ("\\\\server\\share\\", "\\\\server\\share"), # trailing stripped
            ("\\\\", ""),                                 # degenerate UNC root -> absent
            ("\\Windows\\System32", "Windows\\System32"), # stray single leading dropped
            ("/Users/Bob", "Users\\Bob"),                 # absolute POSIX manifest line
            ("C:\\", "C:"),                               # drive root
            ("file.txt:stream", "file.txt"),              # ADS stripped
        ],
    )
    def test_normalize_windows_path_divergence_classes(self, raw: str, expected: str) -> None:
        assert pn.normalize_windows_path(raw) == expected
        assert pn.normalize_windows_path(expected) == expected  # idempotency

    @pytest.mark.parametrize("raw", ["\\\\server\\share", "\\\\server\\share\\sub"])
    def test_is_unc_path_live(self, raw: str) -> None:
        # F-04: previously dead code, always returned False
        assert pn.is_unc_path(raw) is True

    @pytest.mark.parametrize(
        "raw",
        [
            "\\\\server\\share",
            "\\Windows\\System32",
            "C:\\Users\\Bob",
            "C:\\",
            "a//\\b",
            "\\\\",
            "\\",
        ],
    )
    def test_pathnorm_models_end_result_parity(self, raw: str) -> None:
        """F-04/F-05: display-grade and hash-grade stages must converge."""
        assert pn.comparison_form(raw) == models.canon_lower_path(raw)

    def test_source_relative_to_logical_rejects_unc(self) -> None:
        # F-06: becomes reachable once F-04 lets UNC values survive normalization
        with pytest.raises(ValueError, match="UNC"):
            pn.source_relative_to_logical("\\\\server\\share", "C:")

    def test_linux_path_under_root(self) -> None:
        # F-07: generic test constructed "//" and never matched the root
        assert pn.is_linux_path_under("/a/b", "/") is True
        assert pn.is_linux_path_under("/", "/", include_self=True) is True


# ---------------------------------------------------------------------------
# 10. Source hygiene (pre-existing, preserved verbatim)
# ---------------------------------------------------------------------------

class TestSourceHygiene:
    """Escape-rot lock: docstrings carrying Windows-path prose must stay
    raw (or escaped).  A non-raw docstring containing e.g. ``C:\\Users``
    is a compile-time SyntaxError (``\\U`` unicode escape) that silently
    blocks *collection* of every test module importing src.pathnorm."""

    def test_pathnorm_compiles_without_escape_warnings(self) -> None:
        source = _SRC_PATHNORM.read_text(encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            compile(source, str(_SRC_PATHNORM), "exec")
