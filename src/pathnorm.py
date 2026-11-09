r"""Windows/offline path normalization for the Windows 10 Disaster Recovery
application (SDD §2.4; display-grade inputs for the DDD §5 hash contract).

Why this module exists
======================
Evidence arrives in three spellings that must converge on one canonical
form before hashing, deduplication, and display:

* raw Linux mount paths from the read-only ``ntfs-3g`` acquisition
  (``/.../recovery/mounts/<id>/Windows/System32``);
* ``ntfsls`` manifest lines (source-relative: ``Windows\System32``) or
  user-supplied manifests (``C:\Windows\System32``, ``/Windows/System32``);
* logical Windows paths stored on evidence rows (``C:\Windows\System32``).

Normative rules enforced (SDD §2.4)
===================================
1.  Backslash separators: forward slashes converted, runs collapsed.
2.  Drive prefixes uppercased; component case otherwise preserved.
    Lowercasing happens only in :func:`comparison_form` and in the hash
    inputs built by :mod:`src.models` — never in display values.
3.  Trailing backslash removed except for drive roots (``C:\`` -> ``C:``).
4.  NTFS alternate-data-stream suffixes removed for comparison and
    hashing.  NTFS forbids ``:`` in file/directory names, so a colon in
    the final component is either the drive prefix or an ADS separator.
5.  UNC shares preserved (``\\server\share``); parsers treat them as
    *unresolved* wherever source mapping is impossible.
6.  The primary Windows source maps to ``C:``; secondary sources map to
    ``S1:``, ``S2:``, ... in addition order.  ``S0:`` is invalid.
7.  Raw Linux mount paths are never stored as canonical evidence paths.
    :func:`map_mount_path_to_source_relative` is the only sanctioned
    conversion, and it refuses paths that escape the mount root.

Relationship to :mod:`src.models`
=================================
``models.canonical_path_structure`` / ``canon_lower_path`` /
``canon_source_relative_path`` are hash-grade primitives: byte-stable DDD
§5/§6 digest inputs that intentionally ignore display rules.  This module
produces the *display-grade* canonical values that parsers store in
``normalized_path``, ``hive_file_path``, and ``file_path`` *before* the
models helpers lowercase them for hashing.  Because
:func:`normalize_windows_path` strips ADS suffixes, every stored path is
already ADS-free, which is what makes the DDD §5 digest stable across paths
that differ only by an ADS marker (SDD §2.4 rule 4).

Safety posture
==============
This module is pure and side-effect free: it performs no filesystem,
subprocess, network, or database access, so it cannot violate the
zero-write boundary and is safe to call from any thread without locking.
The single deliberate exception is that
:func:`map_mount_path_to_source_relative` raises ``ValueError`` when a path
escapes the mount root: a caller bug that would reference data outside the
acquired source must fail loudly and be converted into a typed warning by
the ingestion layer, never silently accepted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

__all__ = [
    "LOGICAL_DRIVE_PATTERN",
    "normalize_windows_path",
    "strip_ads",
    "comparison_form",
    "paths_equal",
    "is_path_under",
    "is_path_under_or_equal",
    "is_inside_documents",
    "is_unc_path",
    "validate_logical_drive",
    "logical_drive_for_position",
    "logical_to_source_relative",
    "source_relative_to_logical",
    "is_linux_path_under",
    "map_mount_path_to_source_relative",
    "is_manifest_comment",
    "manifest_line_to_source_relative",
]

# ---------------------------------------------------------------------------
# Patterns (immutable module state only)
# ---------------------------------------------------------------------------

#: SDD §2.4 rule 6: exactly ``C:`` (primary) or ``S1:``, ``S2:``, ...
#: (secondaries, in addition order).  ``S0:`` and any other letter are
#: invalid; the same constraint is re-enforced at ``PreparedSource``
#: construction in ``src.models``.
LOGICAL_DRIVE_PATTERN: Final[str] = r"^(?:C|S[1-9][0-9]*):$"

_LOGICAL_DRIVE_RE: Final[re.Pattern[str]] = re.compile(
    LOGICAL_DRIVE_PATTERN, re.IGNORECASE
)

#: A drive prefix at the start of a path: letter + optional digits + colon
#: (covers ``C:``, ``S1:``, and degenerate inputs such as ``D:``).
_DRIVE_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z][0-9]*:")

#: Runs of backslashes (after forward-slash conversion) collapse to one.
_SEPARATOR_RUN_RE: Final[re.Pattern[str]] = re.compile(r"\\+")


# ---------------------------------------------------------------------------
# Private helpers (total: never raise on corrupt input)
# ---------------------------------------------------------------------------

def _drop_nul_and_strip(value: str | None) -> str:
    """Defensive input cleaning shared by all entry points.

    NUL bytes are dropped (NTFS names never contain them; their presence
    indicates a corrupt feed), surrounding whitespace is trimmed, and
    ``None`` maps to ``""`` so every public function is total.
    """
    if value is None:
        return ""
    text = str(value)
    if "\x00" in text:
        text = text.replace("\x00", "")
    return text.strip()


def _strip_ads_last_component(text: str) -> str:
    """Remove an ADS suffix from the final path component only.

    NTFS forbids ``:`` in directory and file names, so after the optional
    drive prefix a colon inside the *final* component is unambiguously an
    alternate-data-stream separator (SDD §2.4 rule 4).  Colons in middle
    components are malformed input: they are preserved as-is (never
    silently rewritten) so a corrupt feed cannot be mistaken for a
    different, legitimate path.  Idempotent.
    """
    if not text:
        return text
    head, sep, last = text.rpartition("\\")
    colon = last.find(":")
    if colon < 0:
        return text
    if sep == "":
        # Single component: the first colon may be the drive prefix.
        drive = _DRIVE_PREFIX_RE.match(text)
        if drive is not None and colon < drive.end():
            later = text.find(":", drive.end())
            return text[:later] if later >= 0 else text
        # No drive prefix: the whole component is a degenerate ADS marker.
        return text[:colon]
    stripped_last = last[:colon]
    if stripped_last:
        return head + sep + stripped_last
    # The ADS marker sat directly on the separator; drop it entirely so the
    # result never regains a trailing backslash.
    return head


def _uppercase_drive_prefix(text: str) -> str:
    """Uppercase the leading drive letter only (SDD §2.4 rule 2).

    Component case is deliberately untouched; lowercasing is a
    comparison/hash concern, not a display one.
    """
    if _DRIVE_PREFIX_RE.match(text) is not None:
        return text[0].upper() + text[1:]
    return text


def _normalize_posix_path(value: str | Path | None) -> str | None:
    """Lexically normalize a POSIX path *without touching the filesystem*.

    Returns the normalized absolute path, or ``None`` when the input is
    empty, not absolute, or escapes above ``/`` through ``..``.  Symlink
    resolution is deliberately out of scope: the mount manager validates
    the real mount point with ``stat`` before any mapping (SDD §4.1), and
    this helper only refuses provable lexical escapes.
    """
    text = _drop_nul_and_strip(value)
    if not text.startswith("/"):
        return None
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                return None  # escaped above the filesystem root
    return "/" + "/".join(parts)


# ---------------------------------------------------------------------------
# Display-grade Windows normalization
# ---------------------------------------------------------------------------

def normalize_windows_path(value: str | None) -> str:
    """Display-grade canonical Windows path (SDD §2.4).

    Returns ``""`` for ``None``/empty/whitespace input (the "absent"
    sentinel).  Rules applied, in order:

    1.  NUL dropped, surrounding whitespace trimmed;
    2.  forward slashes converted to backslashes, runs collapsed to one;
    3.  leading separators removed, except a UNC share's leading double
        separator, which is preserved as exactly two backslashes;
    4.  trailing backslash removed (``C:\`` becomes the drive root ``C:``);
    5.  ADS suffix removed from the final component;
    6.  drive prefix uppercased; component case otherwise preserved.

    The result is idempotent: normalizing an already-normalized path is a
    no-op, which keeps report hydration (DDD §9) byte-stable when hashes
    are re-derived from stored values.
    """
    text = _drop_nul_and_strip(value)
    if not text:
        return ""
    text = text.replace("/", "\\")
    # NOTE: the replacement is a re template — r"\\ " decodes to exactly one
    # literal backslash.  A naive single-backslash replacement string would
    # raise "bad escape (end of pattern)" at runtime.
    text = _SEPARATOR_RUN_RE.sub(r"\\", text)
    if text.startswith("\\\\"):
        # UNC share: preserve exactly two leading backslashes.
        text = "\\\\" + text[2:].lstrip("\\")
    else:
        # A single leading separator is stray (device-path artifact); drop
        # it so rooted forms stay root-relative.
        text = text.lstrip("\\")
    if text.endswith("\\"):
        text = text[:-1]
    text = _strip_ads_last_component(text)
    text = _uppercase_drive_prefix(text)
    if text == "\\":
        # Degenerate bare UNC root; treat as absent.
        return ""
    return text


def strip_ads(value: str | None) -> str:
    """Canonical path with any ADS suffix removed (idempotent).

    Exposed explicitly so ingestion code can read the SDD §2.4 rule at the
    call site when preparing DDD §5 hash inputs.  ``normalize_windows_path``
    already applies this step, so the result equals the display-canonical
    form; keeping the name public documents intent without a second code
    path.
    """
    return _strip_ads_last_component(normalize_windows_path(value))


# ---------------------------------------------------------------------------
# Case-insensitive comparison
# ---------------------------------------------------------------------------

def comparison_form(value: str | None) -> str:
    """Case-insensitive comparison form of a Windows path.

    Display normalization (ADS-free, drive uppercased) followed by
    lowercasing.  This is the *only* place in this module where case is
    lowered (SDD §2.4 rule 2); display strings keep their original case.
    Idempotent, so dedup keys stay stable across repeated normalization.

    Note: ``src.models.canon_lower_path`` is the hash-grade variant.  The
    two agree on every value this module produces because stored paths are
    already ADS-free.
    """
    return normalize_windows_path(value).lower()


def paths_equal(a: str | None, b: str | None) -> bool:
    """Case-insensitive path equality (SDD §2.4 rule 2).

    ``None`` and ``""`` both normalize to ``""`` and compare equal to each
    other; callers must treat the empty sentinel as "absent" and never
    persist it as a canonical evidence path.
    """
    return comparison_form(a) == comparison_form(b)


# ---------------------------------------------------------------------------
# Containment (separator-anchored, case-insensitive)
# ---------------------------------------------------------------------------

def is_path_under(child: str | None, parent: str | None) -> bool:
    """True when ``child`` is *strictly* nested under ``parent``.

    The test is case-insensitive and separator-anchored: ``C:\Users\Bob``
    is NOT under ``C:\Users\Bobby`` because the match requires
    ``parent + '\\'`` as a prefix, not a bare string prefix.  A bare drive
    root (``C:``) contains everything on that drive (``C:\...``) but nothing
    on another drive.  Drive-relative forms (``C:x``) are ambiguous and
    never anchor containment.  Empty/None sides never anchor containment.
    """
    c = comparison_form(child)
    p = comparison_form(parent)
    if not c or not p:
        return False
    return c != p and c.startswith(p + "\\")


def is_path_under_or_equal(child: str | None, parent: str | None) -> bool:
    """True when ``child`` is nested under ``parent`` or identical to it."""
    c = comparison_form(child)
    p = comparison_form(parent)
    if not c or not p:
        return False
    return c == p or c.startswith(p + "\\")


def is_inside_documents(candidate: str | None, documents_root: str | None) -> bool:
    """Documents-baseline containment for the user-data classifier
    (SDD §2.15, README §5.8).

    The Documents root itself counts as inside its own Documents area
    (under-or-equal semantics).  When ``documents_root`` is ``None`` or
    empty the baseline is *unknown*: the classifier must record
    ``inside_documents = None`` (tri-state) rather than a false negative —
    see ``UserProfile.documents_baseline_known``.
    """
    return is_path_under_or_equal(candidate, documents_root)


def is_unc_path(value: str | None) -> bool:
    """True for UNC shares (``\\server\\share``), preserved per SDD §2.4
    rule 5 and treated as unresolved wherever source mapping is impossible.
    """
    return normalize_windows_path(value).startswith("\\\\")


# ---------------------------------------------------------------------------
# Logical-drive mapping (SDD §2.4 rule 6)
# ---------------------------------------------------------------------------

def validate_logical_drive(drive: str) -> str:
    """Validate and uppercase a logical drive name (SDD §2.4 rule 6).

    Accepts only ``C:`` and ``S1:``, ``S2:``, ... (any case, surrounding
    whitespace ignored).  Raises ``ValueError`` on anything else: an
    invalid logical drive is a caller contract violation (the addition-
    order allocator in ``src.db`` is the only producer), not corrupt data,
    so it must fail loudly rather than degrade silently.
    """
    text = _drop_nul_and_strip(drive).upper()
    if _LOGICAL_DRIVE_RE.match(text) is None:
        raise ValueError(
            f"Invalid logical drive {drive!r}: expected 'C:' or 'S1:', "
            "'S2:', ..."
        )
    return text


def logical_drive_for_position(position: int) -> str:
    """Deterministic addition-order logical drive (SDD §2.4 rule 6).

    ``0`` -> ``C:`` (primary Windows source), ``1`` -> ``S1:``,
    ``2`` -> ``S2:``, and so on.  ``src.db`` calls this with the zero-based
    index of the source in addition order; the same call sequence always
    yields the same drive, which keeps logical paths — and therefore DDD
    §5 evidence hashes — reproducible across re-runs and report hydration.
    """
    if not isinstance(position, int) or isinstance(position, bool) or position < 0:
        raise ValueError("position must be a non-negative integer.")
    return "C:" if position == 0 else f"S{position}:"


def logical_to_source_relative(logical_path: str | None) -> str:
    """Strip the drive prefix from a logical path (case-preserving).

    ``C:\Users\Bob`` -> ``Users\Bob``; ``C:`` -> ``""``; UNC paths have no
    drive prefix and are returned unchanged (still unresolved, SDD §2.4
    rule 5).  Drives are stripped *regardless of letter*, so a path that
    slipped in with a foreign drive (e.g. a user-supplied manifest line)
    still maps to a stable source-relative form.  Used to build the
    source-relative ``hive_file_path`` field hashed per DDD §5 field 3.
    """
    text = normalize_windows_path(logical_path)
    drive = _DRIVE_PREFIX_RE.match(text)
    if drive is None:
        return text
    return text[drive.end():]


def source_relative_to_logical(
    source_relative: str | None,
    logical_drive: str,
) -> str:
    """Prefix a source-relative path with its logical drive.

    ``Users\\Bob`` + ``C:`` -> ``C:\\Users\\Bob``; ``""``/``None`` -> the
    bare drive root (``C:``).  If the input is already drive-qualified the
    existing prefix is replaced (defensive remap), which keeps the function
    idempotent on its own output.  Raises ``ValueError`` on an invalid
    logical drive (see :func:`validate_logical_drive`).
    """
    drive = validate_logical_drive(logical_drive)
    rel = logical_to_source_relative(source_relative)
    if not rel:
        return drive
    return f"{drive}\\{rel}"


# ---------------------------------------------------------------------------
# POSIX (mount-side) mapping — the only route to canonical evidence paths
# ---------------------------------------------------------------------------

def is_linux_path_under(
    child: str | Path | None,
    parent: str | Path | None,
    include_self: bool = False,
) -> bool:
    """Lexical containment test for POSIX paths (mount-root validation).

    The mount manager uses this to (a) create temporary mount points only
    under the application-owned recovery directory and (b) refuse
    externally mounted paths.  Purely lexical: it never follows symlinks or
    stats the filesystem — the caller performs the real-device verification
    separately, per SDD §4.1.
    """
    c = _normalize_posix_path(child)
    p = _normalize_posix_path(parent)
    if c is None or p is None:
        return False
    if c == p:
        return include_self
    return c.startswith(p + "/")


def map_mount_path_to_source_relative(
    mount_path: str | Path,
    mount_root: str | Path,
) -> str:
    r"""Convert a path inside a read-only mount point to a source-relative
    logical Windows path (SDD §2.4 rule 7).

    This is the *only* sanctioned route from a raw Linux mount path to a
    canonical evidence path.  The raw ``mount_point`` string is transient
    acquisition state and must never be stored on evidence or findings.

    Raises ``ValueError`` (never returns a silent fallback) when:

    * either side does not normalize to an absolute POSIX path;
    * ``mount_path`` equals ``mount_root`` (the root itself has no
      source-relative form); or
    * ``mount_path`` escapes the root through ``..``, a sibling, or an
      unrelated prefix.

    Refusing the escape is the safety boundary: a caller bug that mapped
    data outside the acquired source would silently corrupt evidence
    provenance, so it must fail loudly and be turned into a typed
    ``WarningRecord`` by the ingestion layer (defensive-parsing directive).
    Lexical checks only — the mount manager guarantees the root is a real,
    application-owned directory and that symlinks are not followed.
    """
    child = _normalize_posix_path(mount_path)
    root = _normalize_posix_path(mount_root)
    if child is None or root is None:
        raise ValueError(
            "Refusing to map mount path: input does not normalize to an "
            "absolute POSIX path."
        )
    if child == root:
        raise ValueError(
            "Refusing to map the mount root itself: evidence paths must be "
            "entries *under* the root."
        )
    if not child.startswith(root + "/"):
        raise ValueError(
            "Refusing to map a path outside the mount root "
            f"({mount_path!r} is not inside {mount_root!r})."
        )
    rel = child[len(root) + 1:]
    return normalize_windows_path(rel)


# ---------------------------------------------------------------------------
# Manifest-line mapping (SDD §2.8)
# ---------------------------------------------------------------------------

def is_manifest_comment(line: str | None) -> bool:
    """True when the line is a ``#`` comment (leading ``#`` after trim).

    Blank lines are *not* comments here; ``manifest_line_to_source_relative``
    returns ``""`` for both blanks and comments, which is the skip sentinel
    for the line-by-line parser.
    """
    return _drop_nul_and_strip(line).startswith("#")


def manifest_line_to_source_relative(line: str | None) -> str:
    r"""Map one manifest line to a source-relative logical path (SDD §2.8).

    Supported line shapes (defensive, best-effort):

    * source-relative Windows paths: ``Users\Bob\Desktop``  (as-is)
    * drive-qualified Windows paths: ``C:\Users\Bob``       (drive stripped)
    * drive-relative Windows paths:  ``C:Users\Bob``        (drive stripped)
    * absolute POSIX paths (user-supplied manifests): ``/Users/Bob``
    * UNC-style lines: preserved and treated as *unresolved* by the parser
      (SDD §2.4 rule 5)

    Returns ``""`` for blank or ``#``-comment lines.  Degenerate ``.``/``..``
    components are dropped lexically: they cannot be represented
    source-relative and cannot exist on a healthy NTFS volume.
    """
    text = _drop_nul_and_strip(line)
    if not text or text.startswith("#"):
        return ""
    rel = logical_to_source_relative(normalize_windows_path(text))
    if rel.startswith("\\\\"):
        # UNC share: keep exactly the two leading backslashes, then clean.
        body = rel[2:]
        parts = [part for part in body.split("\\") if part not in (".", "..")]
        return "\\\\" + "\\".join(parts)
    parts = [part for part in rel.split("\\") if part not in (".", "..")]
    return "\\".join(parts)
