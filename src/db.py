"""SQLite persistence layer for the Windows 10 Disaster Recovery application.

Implements ``docs/contracts/db.md`` v1.0.0 (Tier 1, FROZEN), which refines
SDD §2.17, DDD §1/§4/§7/§10, and ADR-3 / ADR-18 / ADR-21 / ADR-22.  This
module is the *only* component that touches the session database file.

Safety boundary — read-only sources (ADR-1, ADR-18, db.md §5)
-------------------------------------------------------------
The session database lives at ``<base>/sessions/<session_id>/win10drb.sqlite``
and arrives here already resolved by the coordinator (filesystem-layout
contract).  ``db.py`` therefore:

* never resolves XDG paths itself;
* never creates directories — the parent directory is assumed to exist;
* touches exactly one file: the one passed to :meth:`Database.open`;
* never touches mount points, block devices, manifests, or registry hives.

A scanned source drive is unreachable from this module by construction:
even a defect here cannot write to user data.  The ``read_only = 1`` CHECK
on ``SCAN_SOURCE`` additionally persists the read-only guarantee as data.

Filesystem mode (db.md §5, ADR-18)
----------------------------------
The database file is created ``0600`` **regardless of umask** via
``os.open(..., 0o600)`` + ``os.fchmod(fd, 0o600)``; the WAL ``-wal``/``-shm``
companions are enforced to ``0600`` (best-effort after creation).  No other
filesystem access exists in this module.

Thread safety (SDD §2.17, ADR-22, db.md §6)
-------------------------------------------
Each ``Database`` owns exactly one ``sqlite3`` connection (``check_same_thread=
False``) and **all** access — reads and writes — is serialized through one
internal lock; connections and cursors never escape the class.  Every write
runs inside an explicit ``BEGIN IMMEDIATE ... COMMIT`` transaction with
rollback on error.  ``iter_persisted_evidence`` holds the lock only while
fetching each batch, never across yields (db.md §6).

Evidence-first idempotency (ADR-6, ADR-22, db.md §2)
----------------------------------------------------
Exactly three dedup keys exist, and dedup *never raises and never
overwrites* (returns the existing row's ID):

* ``DISCOVERY_EVIDENCE.evidence_hash`` (DDD §5);
* ``APP_RECORD(session_id, source_id, identity_hash)`` (DDD §6);
* ``USER_DATA_FINDING(session_id, source_id, normalized_path)`` (DDD §3).

Dedup **never applies** to the primary keys of session, source, profile,
or warning rows: re-saving any of those IDs is a ``DatabaseIntegrityError``.
That collision hook is what ``state.py`` relies on for ADR-21
hydration-conflict detection.

Error taxonomy (db.md §1/§3, ADR-19, ADR-22)
--------------------------------------------
This module raises a small typed hierarchy, all host-side:

* :class:`DatabaseError` — unrecoverable SQLite failures, any operation
  after ``close()``, unknown ``session_id`` in readers, unknown target rows
  in ``update_*`` methods.
* :class:`DatabaseIntegrityError` (a ``DatabaseError``) — FK violations,
  cross-source application–evidence links, malformed rows (e.g. a missing
  ``evidence_hash``), and primary-key/UNIQUE collisions outside the three
  dedup keys.
* ``ValueError`` — caller-contract argument violations only (out-of-bounds
  batch size, ``batch_size < 1``), raised before any connection access.

These are HOST-side errors: callers must never map them to
``CriticalIoFailureEvent`` — that event is reserved for source-drive I/O.
This module emits no UI events and creates no ``WarningRecord`` (db.md §4).
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Final, Iterator, Mapping, Sequence, TypeVar

from .models import (
    SCHEMA_VERSION,
    ApplicationEvidenceLink,
    CorrelatedApplication,
    Evidence,
    PersistedEvidence,
    Relevance,
    ScanSession,
    ScanSummary,
    SessionBundle,
    SessionStatus,
    SourceRecord,
    SourceStatus,
    UserDataFinding,
    UserProfile,
    WarningRecord,
    new_id,
    utc_now_iso,
)

__all__ = [
    "DB_SCHEMA_VERSION",
    "Database",
    "DatabaseError",
    "DatabaseIntegrityError",
    "init_db",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# db.md §1: DB_SCHEMA_VERSION must equal models.SCHEMA_VERSION.  The DDD
# schema version and the database DDL version move together; keeping them
# as the same object makes drift impossible.
DB_SCHEMA_VERSION: Final[str] = SCHEMA_VERSION


# ─────────────────────────────────────────────────────────────────────
# Typed host-side error hierarchy (db.md §1/§3)
# ─────────────────────────────────────────────────────────────────────

class DatabaseError(RuntimeError):
    """Base class for all host-side database errors raised by this module.

    Raised for: unrecoverable SQLite failures (open/configure/read/write/
    commit), any operation attempted after ``close()``, unknown
    ``session_id`` in readers, and unknown target rows in ``update_*``
    methods (db.md §2/§3).

    Why this boundary exists: db.md §3 — database errors are HOST-side and
    must never be mapped to ``CriticalIoFailureEvent``; that event is
    reserved for source-drive I/O (ADR-19/ADR-22).  A failing session file
    under the state base is never evidence of a dying user drive.
    """


class DatabaseIntegrityError(DatabaseError):
    """A database-integrity violation (db.md §1: "FK violation / malformed
    row only"; §3 extends this to the dedup-key collision rule).

    Raised for:
    * foreign-key violations (e.g. a source saved before its session);
    * cross-source application–evidence links (DDD §4 source scoping);
    * primary-key/UNIQUE collisions *outside* the three idempotent dedup
      keys — including re-saving a session, source, profile, or warning
      whose ID already exists, and any insert carrying an ID already
      present without matching its dedup key;
    * malformed rows (e.g. evidence without an ``evidence_hash``).

    ``state.py`` catches this exception to fail a report import with an
    actionable error on hydration conflict (ADR-21, db.md §2).
    """


# ─────────────────────────────────────────────────────────────────────
# DDD §4 — schema (tables).  IF NOT EXISTS keeps open() idempotent (db.md
# §2); Database.open is the single source of truth for schema — init_db
# carries no schema logic of its own.
# ─────────────────────────────────────────────────────────────────────

_SCHEMA_TABLES: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS SCAN_SESSION (
        session_id        VARCHAR(36) PRIMARY KEY,
        schema_version    VARCHAR(16) NOT NULL,
        created_at        TEXT        NOT NULL,
        mode              VARCHAR(20) NOT NULL
                          CHECK (mode IN ('active', 'triage')),
        status            VARCHAR(20) NOT NULL
                          CHECK (status IN ('pending', 'running',
                                            'completed', 'failed', 'cancelled')),
        scan_options_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS SCAN_SOURCE (
        source_id           VARCHAR(36) PRIMARY KEY,
        session_id          VARCHAR(36) NOT NULL
                           REFERENCES SCAN_SESSION(session_id),
        source_type         VARCHAR(32) NOT NULL
                           CHECK (source_type IN ('mounted_block_device',
                                                  'manifest_file')),
        source_role         VARCHAR(32) NOT NULL
                           CHECK (source_role IN ('windows_os',
                                                  'secondary_data')),
        origin_device_path  TEXT,
        manifest_path       TEXT,
        mount_point         TEXT,
        fs_type             TEXT,
        label               TEXT,
        uuid                TEXT,
        size_bytes          INTEGER,
        acquisition_method  VARCHAR(32) NOT NULL
                           CHECK (acquisition_method IN ('ntfs3g_ro',
                                                          'ntfsls_manifest')),
        read_only           INTEGER NOT NULL DEFAULT 1
                           CHECK (read_only = 1),
        status              VARCHAR(20) NOT NULL
                           CHECK (status IN ('pending', 'ready',
                                             'error', 'complete')),
        warnings_json       TEXT,
        CHECK (
            (source_type = 'mounted_block_device' AND acquisition_method = 'ntfs3g_ro')
            OR
            (source_type = 'manifest_file' AND acquisition_method = 'ntfsls_manifest')
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS USER_PROFILE (
        profile_id              VARCHAR(36) PRIMARY KEY,
        session_id              VARCHAR(36) NOT NULL
                               REFERENCES SCAN_SESSION(session_id),
        source_id               VARCHAR(36) NOT NULL
                               REFERENCES SCAN_SOURCE(source_id),
        username                TEXT,
        sid                     TEXT,
        profile_path            TEXT,
        normalized_profile_path TEXT,
        ntuser_path             TEXT,
        usrclass_path           TEXT,
        documents_path          TEXT,
        desktop_path            TEXT,
        downloads_path          TEXT,
        pictures_path           TEXT,
        music_path              TEXT,
        videos_path             TEXT,
        appdata_local_path      TEXT,
        appdata_roaming_path    TEXT,
        appdata_locallow_path   TEXT,
        saved_games_path        TEXT,
        is_default_profile      INTEGER NOT NULL DEFAULT 0,
        is_system_profile       INTEGER NOT NULL DEFAULT 0,
        parse_warnings_json     TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS APP_RECORD (
        app_id                  VARCHAR(36) PRIMARY KEY,
        session_id              VARCHAR(36) NOT NULL
                               REFERENCES SCAN_SESSION(session_id),
        source_id               VARCHAR(36) NOT NULL
                               REFERENCES SCAN_SOURCE(source_id),
        identity_hash           VARCHAR(64) NOT NULL,
        identity_basis          TEXT NOT NULL
                               CHECK (identity_basis IN
                                      ('product_code', 'uninstall_key',
                                       'install_path', 'name_publisher_version',
                                       'portable_directory', 'manifest_directory',
                                       'executable_bundle', 'fallback')),
        identity_key            TEXT NOT NULL,
        display_name            TEXT NOT NULL,
        publisher               TEXT,
        version                 TEXT,
        install_date            TEXT,
        architecture            TEXT,
        install_path            TEXT,
        normalized_install_path TEXT,
        discovery_method        TEXT NOT NULL
                               CHECK (discovery_method IN
                                      ('registry', 'filesystem', 'manifest',
                                       'portable', 'correlated')),
        fingerprint_status      TEXT NOT NULL
                               CHECK (fingerprint_status IN
                                      ('Registered', 'PartiallyRegistered',
                                       'Portable', 'Orphaned', 'Unknown')),
        evidence_confidence     TEXT NOT NULL
                               CHECK (evidence_confidence IN
                                      ('Low', 'Medium', 'High')),
        portable_score          INTEGER
                               CHECK (portable_score IS NULL
                                      OR (portable_score >= 0
                                          AND portable_score <= 100)),
        notes_json              TEXT,
        created_at              TEXT NOT NULL,
        UNIQUE (session_id, source_id, identity_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS DISCOVERY_EVIDENCE (
        evidence_id     VARCHAR(36) PRIMARY KEY,
        session_id      VARCHAR(36) NOT NULL
                       REFERENCES SCAN_SESSION(session_id),
        source_id       VARCHAR(36) NOT NULL
                       REFERENCES SCAN_SOURCE(source_id),
        evidence_hash   VARCHAR(64) NOT NULL UNIQUE,
        evidence_type   TEXT NOT NULL,
        hive_file_path  TEXT,
        root_hive       TEXT,
        key_path        TEXT,
        value_name      TEXT,
        value_data      TEXT,
        user_sid        TEXT,
        file_path       TEXT,
        normalized_path TEXT,
        product_code    TEXT,
        confidence      TEXT NOT NULL
                       CHECK (confidence IN ('Low', 'Medium', 'High')),
        parse_warning   TEXT,
        raw_json        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS APP_EVIDENCE (
        link_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id      VARCHAR(36) NOT NULL REFERENCES APP_RECORD(app_id),
        evidence_id VARCHAR(36) NOT NULL
                   REFERENCES DISCOVERY_EVIDENCE(evidence_id),
        relevance   TEXT NOT NULL
                   CHECK (relevance IN ('primary', 'supporting', 'weak')),
        created_at  TEXT NOT NULL,
        UNIQUE (app_id, evidence_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS USER_DATA_FINDING (
        finding_id          VARCHAR(36) PRIMARY KEY,
        session_id          VARCHAR(36) NOT NULL
                           REFERENCES SCAN_SESSION(session_id),
        source_id           VARCHAR(36) NOT NULL
                           REFERENCES SCAN_SOURCE(source_id),
        app_id              VARCHAR(36) REFERENCES APP_RECORD(app_id),
        profile_id          VARCHAR(36) REFERENCES USER_PROFILE(profile_id),
        path                TEXT NOT NULL,
        normalized_path     TEXT NOT NULL,
        location_category   TEXT NOT NULL,
        inside_documents    INTEGER
                           CHECK (inside_documents IS NULL
                                  OR inside_documents IN (0, 1)),
        documents_root      TEXT,
        owner_username      TEXT,
        nomenclature_match  TEXT,
        extension_match     TEXT,
        file_count          INTEGER,
        total_size_bytes    INTEGER,
        severity_level      TEXT NOT NULL
                           CHECK (severity_level IN ('Low', 'Medium', 'High')),
        confidence          TEXT NOT NULL
                           CHECK (confidence IN ('Low', 'Medium', 'High')),
        rationale           TEXT NOT NULL,
        created_at          TEXT NOT NULL,
        user_confirmed      INTEGER
                           CHECK (user_confirmed IS NULL
                                  OR user_confirmed IN (0, 1)),
        user_notes          TEXT,
        UNIQUE (session_id, source_id, normalized_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS SESSION_WARNING (
        warning_id  VARCHAR(36) PRIMARY KEY,
        session_id  VARCHAR(36) NOT NULL
                   REFERENCES SCAN_SESSION(session_id),
        source_id   VARCHAR(36) REFERENCES SCAN_SOURCE(source_id),
        category    TEXT NOT NULL
                   CHECK (category IN
                          ('acquisition', 'registry', 'manifest', 'filesystem',
                           'correlation', 'heuristic', 'io', 'report', 'general')),
        severity    TEXT NOT NULL
                   CHECK (severity IN ('info', 'warning', 'critical')),
        message     TEXT NOT NULL,
        created_at  TEXT NOT NULL
    )
    """,
)

# ─────────────────────────────────────────────────────────────────────
# DDD §7 — all 19 recommended indexes, verbatim (creation order is
# non-contract, db.md §7).
# ─────────────────────────────────────────────────────────────────────

_SCHEMA_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_source_session ON SCAN_SOURCE(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_profile_session ON USER_PROFILE(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_profile_source ON USER_PROFILE(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_app_session ON APP_RECORD(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_app_source ON APP_RECORD(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_app_session_name ON APP_RECORD(session_id, display_name)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_session ON DISCOVERY_EVIDENCE(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_source ON DISCOVERY_EVIDENCE(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_type ON DISCOVERY_EVIDENCE(evidence_type)",
    "CREATE INDEX IF NOT EXISTS idx_app_evidence_app ON APP_EVIDENCE(app_id)",
    "CREATE INDEX IF NOT EXISTS idx_app_evidence_evidence ON APP_EVIDENCE(evidence_id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_session ON USER_DATA_FINDING(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_app ON USER_DATA_FINDING(app_id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_profile ON USER_DATA_FINDING(profile_id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_source ON USER_DATA_FINDING(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_severity ON USER_DATA_FINDING(severity_level)",
    "CREATE INDEX IF NOT EXISTS idx_finding_inside_documents ON USER_DATA_FINDING(inside_documents)",
    "CREATE INDEX IF NOT EXISTS idx_warning_session ON SESSION_WARNING(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_warning_source ON SESSION_WARNING(source_id)",
)

# ─────────────────────────────────────────────────────────────────────
# Column tuples: single source of truth shared by INSERT statements and
# parameter binding.  They mirror DDD §4 column names exactly;
# models.to_row() is contractually guaranteed to emit exactly these keys.
# ─────────────────────────────────────────────────────────────────────

_SESSION_COLUMNS: tuple[str, ...] = (
    "session_id", "schema_version", "created_at", "mode", "status",
    "scan_options_json",
)

_SOURCE_COLUMNS: tuple[str, ...] = (
    "source_id", "session_id", "source_type", "source_role",
    "origin_device_path", "manifest_path", "mount_point", "fs_type",
    "label", "uuid", "size_bytes", "acquisition_method", "read_only",
    "status", "warnings_json",
)

_PROFILE_COLUMNS: tuple[str, ...] = (
    "profile_id", "session_id", "source_id", "username", "sid",
    "profile_path", "normalized_profile_path", "ntuser_path",
    "usrclass_path", "documents_path", "desktop_path", "downloads_path",
    "pictures_path", "music_path", "videos_path", "appdata_local_path",
    "appdata_roaming_path", "appdata_locallow_path", "saved_games_path",
    "is_default_profile", "is_system_profile", "parse_warnings_json",
)

_APP_COLUMNS: tuple[str, ...] = (
    "app_id", "session_id", "source_id", "identity_hash", "identity_basis",
    "identity_key", "display_name", "publisher", "version", "install_date",
    "architecture", "install_path", "normalized_install_path",
    "discovery_method", "fingerprint_status", "evidence_confidence",
    "portable_score", "notes_json", "created_at",
)

_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "evidence_id", "session_id", "source_id", "evidence_hash",
    "evidence_type", "hive_file_path", "root_hive", "key_path",
    "value_name", "value_data", "user_sid", "file_path",
    "normalized_path", "product_code", "confidence", "parse_warning",
    "raw_json",
)

_LINK_COLUMNS: tuple[str, ...] = (
    "app_id", "evidence_id", "relevance", "created_at",
)

_FINDING_COLUMNS: tuple[str, ...] = (
    "finding_id", "session_id", "source_id", "app_id", "profile_id",
    "path", "normalized_path", "location_category", "inside_documents",
    "documents_root", "owner_username", "nomenclature_match",
    "extension_match", "file_count", "total_size_bytes", "severity_level",
    "confidence", "rationale", "created_at", "user_confirmed",
    "user_notes",
)

_WARNING_COLUMNS: tuple[str, ...] = (
    "warning_id", "session_id", "source_id", "category", "severity",
    "message", "created_at",
)


# ─────────────────────────────────────────────────────────────────────
# Private helpers (db.md §7 — non-contract internals)
# ─────────────────────────────────────────────────────────────────────

def _enforce_companion_modes(db_path: Path) -> None:
    """Best-effort ``0600`` on the WAL ``-wal``/``-shm`` companions
    (db.md §5: they must inherit the same owner-only mode).  They may
    not yet exist at every call site; absence is not an error."""
    for suffix in (".wal", ".shm"):
        companion = Path(str(db_path) + suffix)
        if not companion.exists():
            continue
        try:
            os.chmod(companion, 0o600)
        except OSError:
            logger.debug("Best-effort chmod 0600 on %s failed; continuing", companion)


def _row_as_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a ``sqlite3.Row`` into a plain ``dict`` so it satisfies the
    ``Mapping[str, Any]`` contract of the models ``from_row`` classmethods
    (a ``sqlite3.Row`` is sequence-like, not a ``Mapping``)."""
    return dict(zip(row.keys(), row, strict=True))


def _params(columns: tuple[str, ...], row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Bind parameters in fixed column order.  A missing key becomes NULL,
    which a NOT NULL column then rejects with an actionable
    ``DatabaseIntegrityError`` rather than a cryptic bind failure."""
    return tuple(row.get(column) for column in columns)


def _insert_values_sql(table: str, columns: tuple[str, ...]) -> str:
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"


def _dedup_insert_sql(table: str, columns: tuple[str, ...], conflict_target: str) -> str:
    """Idempotent INSERT: ``ON CONFLICT(<dedup key>) DO NOTHING``.

    db.md §2: dedup never raises and never overwrites — a conflicting row
    simply leaves the stored row untouched and the caller re-selects the
    existing ID.
    """
    return (
        _insert_values_sql(table, columns)
        + f" ON CONFLICT({conflict_target}) DO NOTHING"
    )


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def _require_session(conn: sqlite3.Connection, session_id: str) -> None:
    """db.md §2: readers raise ``DatabaseError`` for an unknown
    ``session_id`` — never a silent empty result."""
    if _scalar(conn, "SELECT rowid FROM SCAN_SESSION WHERE session_id = ?", (session_id,)) is None:
        raise DatabaseError(f"Unknown session_id {session_id!r}")


def _all_as(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...],
    factory: Callable[[Mapping[str, Any]], object],
) -> list[Any]:
    return [factory(_row_as_dict(row)) for row in conn.execute(sql, params).fetchall()]


def _as_persisted(row: sqlite3.Row) -> PersistedEvidence:
    """Materialize one persisted-evidence row into the correlation-facing
    DTO without ever exposing the raw row or file contents."""
    evidence = Evidence.from_row(_row_as_dict(row))
    return PersistedEvidence.from_evidence(evidence, evidence.evidence_id)


# ─────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────

class Database:
    """Thread-safe owner of one session SQLite database (ADR-22, db.md §6).

    Construct via :meth:`open`; never instantiate directly.  The connection
    and all cursors are private: UI widgets and workers only ever see DTOs
    and the public writer/reader methods (SDD §2.17, db.md §6:
    connections/cursors never escape the class).
    """

    #: db.md §2: ``save_evidence_batch`` accepts 1..500 rows per call.
    _MAX_BATCH_ROWS: int = 500
    #: Hard memory bound for ``iter_persisted_evidence`` batches.
    _MAX_ITER_BATCH_ROWS: int = 10_000
    #: db.md §5: ``busy_timeout`` >= 5000 ms.
    _BUSY_TIMEOUT_MS: int = 5000

    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        # Private constructor; Database.open() performs all configuration.
        self._conn = conn
        self._path = Path(path)
        # The single serialization lock (db.md §6: total serialization at
        # this scale — correctness over throughput).
        self._lock = threading.RLock()
        self._closed = False

    # ── lifecycle ────────────────────────────────────────────────────

    @classmethod
    def open(cls, db_path: Path) -> "Database":
        """Open (creating if absent) the session database at ``db_path``
        and ensure the DDD schema exists (db.md §1: "creates schema if
        absent").

        Why this boundary exists (db.md §5): the path is taken as-is from
        the coordinator and never resolved here.  The parent directory is
        *assumed to exist* — the filesystem-layout contract creates it;
        ``db.py`` creates no directories.  The file is created ``0600``
        regardless of umask.  The only file this instance can ever touch
        is this one — never a scanned source, mount point, or manifest.
        """
        path = Path(db_path)
        try:
            fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        except FileNotFoundError as exc:
            raise DatabaseError(
                f"Parent directory for session database {path} does not exist; "
                "the filesystem-layout contract requires the coordinator to create "
                "<base>/sessions/<session_id> before Database.open "
                "(db.py creates no directories)"
            ) from exc
        except OSError as exc:
            raise DatabaseError(f"Unable to open session database {path}: {exc}") from exc
        try:
            # fchmod is exact: it enforces 0600 regardless of the process
            # umask (db.md §5).  Failure is unrecoverable — fail the open.
            os.fchmod(fd, 0o600)
        except OSError as exc:
            os.close(fd)
            raise DatabaseError(f"Could not enforce mode 0600 on {path}: {exc}") from exc
        try:
            fh = os.fdopen(fd, "r+b")
        except OSError as exc:
            os.close(fd)
            raise DatabaseError(f"Unable to attach to session database file {path}: {exc}") from exc
        try:
            conn = sqlite3.connect(
                fh,
                timeout=cls._BUSY_TIMEOUT_MS / 1000.0,
                # db.md §6: one lock around one connection; the lock — not
                # sqlite's same-thread assertion — is our safety mechanism.
                check_same_thread=False,
                # Autocommit at the driver level; write transactions are
                # explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK in _write().
                isolation_level=None,
            )
        except sqlite3.Error as exc:
            fh.close()
            raise DatabaseError(f"Unable to open session database {path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        try:
            # DDD §10 / db.md §5: foreign key enforcement on every connection.
            conn.execute("PRAGMA foreign_keys = ON")
            # WAL journal mode (db.md §5).
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(f"PRAGMA busy_timeout = {cls._BUSY_TIMEOUT_MS}")
            # Standard WAL companion: crash-safe without fsync-per-commit cost.
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as exc:
            conn.close()
            raise DatabaseError(f"Unable to configure session database {path}: {exc}") from exc
        db = cls(conn, path)
        db._initialize_schema()
        _enforce_companion_modes(path)
        return db

    def close(self) -> None:
        """Close the connection; idempotent (db.md §2).

        Rolls back any in-flight transaction first (db.md §2: ``__exit__``
        must never leave one open), then checkpoints WAL best-effort and
        closes.  Serialized on the same lock so no operation can race the
        shutdown.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            conn = self._conn
            try:
                if conn.in_transaction:
                    self._rollback(conn)
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.Error:
                    logger.debug("wal_checkpoint on close failed; continuing")
                if not conn.closed:
                    conn.close()
            except sqlite3.Error:
                logger.warning(
                    "Error while closing session database %s", self._path, exc_info=True
                )

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        # close() rolls back any in-flight transaction; the exception (if
        # any) is never suppressed (db.md §2).
        self.close()

    @property
    def path(self) -> Path:
        """The exact session database file this instance owns (ADR-18)."""
        return self._path

    @property
    def is_closed(self) -> bool:
        return self._closed

    # ── private access primitives ────────────────────────────────────

    def _ensure_open(self) -> None:
        # db.md §3: any operation after close() raises DatabaseError.
        if self._closed:
            raise DatabaseError(
                "Database connection is closed; all operations after close() are "
                "refused (db.md §3). Open a new instance with Database.open()."
            )

    def _write(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``operation`` inside one serialized ``BEGIN IMMEDIATE``
        transaction (db.md §2: commits promptly).  Error mapping per
        db.md §3: ``sqlite3.IntegrityError`` -> ``DatabaseIntegrityError``;
        any other SQLite failure -> ``DatabaseError``; intentional
        ``Database*Error`` from the operation is rolled back and
        re-raised unchanged."""
        with self._lock:
            self._ensure_open()
            conn = self._conn
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                logger.warning("BEGIN IMMEDIATE failed: %s", exc)
                raise DatabaseError(f"Could not begin write transaction: {exc}") from exc
            try:
                result = operation(conn)
            except sqlite3.IntegrityError as exc:
                self._rollback(conn)
                logger.warning("Integrity violation: %s", exc)
                raise DatabaseIntegrityError(f"Integrity violation: {exc}") from exc
            except sqlite3.Error as exc:
                self._rollback(conn)
                logger.warning("Write transaction failed: %s", exc)
                raise DatabaseError(f"SQLite failure during write: {exc}") from exc
            except BaseException:
                # Intentional DatabaseError / DatabaseIntegrityError raised
                # inside the operation: roll back, re-raise unchanged.
                self._rollback(conn)
                raise
            try:
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                self._rollback(conn)
                logger.warning("COMMIT failed: %s", exc)
                raise DatabaseError(f"Could not commit write transaction: {exc}") from exc
            return result

    def _read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run a read under the same serialization lock (db.md §6: total
        serialization; connections/cursors never escape the class)."""
        with self._lock:
            self._ensure_open()
            try:
                return operation(self._conn)
            except sqlite3.Error as exc:
                logger.warning("Read failed: %s", exc)
                raise DatabaseError(f"SQLite failure during read: {exc}") from exc

    def _rollback(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            logger.debug("ROLLBACK failed; connection may be unusable", exc_info=True)

    def _initialize_schema(self) -> None:
        def _create(conn: sqlite3.Connection) -> None:
            for statement in (*_SCHEMA_TABLES, *_SCHEMA_INDEXES):
                conn.execute(statement)

        self._write(_create)

    # ── writers ──────────────────────────────────────────────────────
    # db.md §2: serialized; IDs via models.new_id(); input DTOs never
    # mutated (only fresh dicts from to_row() are touched).

    def save_session(self, session: ScanSession) -> str:
        """Insert the session row; returns its ``session_id`` (db.md §2:
        the DTO's ID is used as-is).

        Re-saving an existing ``session_id`` raises
        ``DatabaseIntegrityError`` — dedup never applies to session PKs
        (db.md §2).  This is the root of the FK order: the session must
        exist before any source.
        """

        def _op(conn: sqlite3.Connection) -> str:
            conn.execute(
                _insert_values_sql("SCAN_SESSION", _SESSION_COLUMNS),
                _params(_SESSION_COLUMNS, session.to_row()),
            )
            return session.session_id

        return self._write(_op)

    def update_session_status(self, session_id: str, status: SessionStatus) -> None:
        """Transition the session state (coordinator-owned state machine).
        Unknown ``session_id`` raises ``DatabaseError`` (db.md §2/§3:
        never a silent no-op)."""

        def _op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "UPDATE SCAN_SESSION SET status = ? WHERE session_id = ?",
                (str(status), session_id),
            )
            if cur.rowcount != 1:
                raise DatabaseError(
                    f"Unknown session_id {session_id!r}; status update applied to nothing"
                )

        self._write(_op)

    def save_source(self, source: SourceRecord) -> str:
        """Insert the source row; returns its ``source_id``.

        Re-saving an existing ``source_id`` raises
        ``DatabaseIntegrityError`` (no PK dedup, db.md §2).  Requires the
        parent session to exist (FK ordering, db.md §2).  The DDD
        type/acquisition pairing CHECK and ``read_only = 1`` CHECK are
        enforced by the schema itself.
        """

        def _op(conn: sqlite3.Connection) -> str:
            conn.execute(
                _insert_values_sql("SCAN_SOURCE", _SOURCE_COLUMNS),
                _params(_SOURCE_COLUMNS, source.to_row()),
            )
            return source.source_id

        return self._write(_op)

    def update_source_status(
        self,
        source_id: str,
        status: SourceStatus,
        warnings_json: str | None = None,
    ) -> None:
        """Update source state.  ``warnings_json=None`` leaves the column
        unchanged (db.md §2) — source-specific warning history is
        accumulated, never clobbered by a status-only update; pass an
        explicit string to replace it.  Unknown ``source_id`` raises
        ``DatabaseError``."""

        def _op(conn: sqlite3.Connection) -> None:
            if warnings_json is None:
                cur = conn.execute(
                    "UPDATE SCAN_SOURCE SET status = ? WHERE source_id = ?",
                    (str(status), source_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE SCAN_SOURCE SET status = ?, warnings_json = ? WHERE source_id = ?",
                    (str(status), warnings_json, source_id),
                )
            if cur.rowcount != 1:
                raise DatabaseError(
                    f"Unknown source_id {source_id!r}; status update applied to nothing"
                )

        self._write(_op)

    def save_user_profile(self, profile: UserProfile) -> str:
        """Insert the profile row, assigning a new id where the DTO does
        not carry one (db.md §2).  Re-saving an existing ``profile_id``
        raises ``DatabaseIntegrityError`` (no PK dedup)."""
        profile_id = profile.profile_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(profile.to_row())
            row["profile_id"] = profile_id
            conn.execute(
                _insert_values_sql("USER_PROFILE", _PROFILE_COLUMNS),
                _params(_PROFILE_COLUMNS, row),
            )
            return profile_id

        return self._write(_op)

    def save_evidence(self, evidence: Evidence) -> str:
        """Persist one evidence row (evidence-first, ADR-6).

        Idempotent on the deterministic ``evidence_hash`` (DDD §5): a
        duplicate returns the EXISTING row's ``evidence_id`` and never
        raises or overwrites (db.md §2).  A missing hash is a malformed
        row -> ``DatabaseIntegrityError``; an insert carrying an ID
        already present with a different hash is a collision ->
        ``DatabaseIntegrityError``.
        """
        evidence_hash = evidence.evidence_hash
        if not evidence_hash:
            raise DatabaseIntegrityError(
                "Evidence row carries no evidence_hash (malformed row); "
                "refusing to persist a non-deduplicable evidence row"
            )
        evidence_id = evidence.evidence_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            # db.md §2: an ID already present without matching the dedup
            # key is a PK collision, not a dedup.
            if evidence.evidence_id is not None:
                holder = _scalar(
                    conn,
                    "SELECT evidence_hash FROM DISCOVERY_EVIDENCE WHERE evidence_id = ?",
                    (evidence.evidence_id,),
                )
                if holder is not None and holder != evidence_hash:
                    raise DatabaseIntegrityError(
                        f"evidence_id {evidence.evidence_id!r} already exists "
                        "with a different evidence_hash"
                    )
            row = dict(evidence.to_row())
            row["evidence_id"] = evidence_id
            conn.execute(
                _dedup_insert_sql("DISCOVERY_EVIDENCE", _EVIDENCE_COLUMNS, "evidence_hash"),
                _params(_EVIDENCE_COLUMNS, row),
            )
            cur = conn.execute(
                "SELECT evidence_id FROM DISCOVERY_EVIDENCE WHERE evidence_hash = ?",
                (evidence_hash,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise DatabaseError("Invariant violated: evidence row missing after dedup insert")
            return str(existing[0])

        return self._write(_op)

    def save_evidence_batch(self, rows: Sequence[Evidence]) -> tuple[str, ...]:
        """Persist 1..500 evidence rows in a single transaction (db.md §2:
        one transaction per batch -> all-or-nothing).

        Returns a tuple positionally aligned with ``rows``: each slot is
        the new or pre-existing ``evidence_id`` for that row (dedup is
        idempotent, db.md §2).  Out-of-bounds sizes raise ``ValueError``
        — not ``DatabaseError`` — before touching the connection
        (db.md §3).
        """
        count = len(rows)
        if count < 1 or count > self._MAX_BATCH_ROWS:
            raise ValueError(
                f"save_evidence_batch requires 1..{self._MAX_BATCH_ROWS} rows "
                f"per call (got {count}); one transaction per batch (db.md §2/§3)"
            )

        def _op(conn: sqlite3.Connection) -> tuple[str, ...]:
            prepared: list[tuple[Any, ...]] = []
            hashes: list[str] = []
            for evidence in rows:
                hash_value = evidence.evidence_hash
                if not hash_value:
                    raise DatabaseIntegrityError(
                        "Evidence batch contains a row without evidence_hash (malformed row)"
                    )
                if evidence.evidence_id is not None:
                    holder = _scalar(
                        conn,
                        "SELECT evidence_hash FROM DISCOVERY_EVIDENCE WHERE evidence_id = ?",
                        (evidence.evidence_id,),
                    )
                    if holder is not None and holder != hash_value:
                        raise DatabaseIntegrityError(
                            f"evidence_id {evidence.evidence_id!r} already exists "
                            "with a different evidence_hash"
                        )
                row = dict(evidence.to_row())
                row["evidence_id"] = evidence.evidence_id or new_id()
                prepared.append(_params(_EVIDENCE_COLUMNS, row))
                hashes.append(hash_value)
            conn.executemany(
                _dedup_insert_sql("DISCOVERY_EVIDENCE", _EVIDENCE_COLUMNS, "evidence_hash"),
                prepared,
            )
            # Resolve identifiers (dedup may have mapped a row onto an
            # existing id) in one bounded SELECT.
            cur = conn.execute(
                "SELECT evidence_hash, evidence_id FROM DISCOVERY_EVIDENCE "
                f"WHERE evidence_hash IN ({', '.join('?' for _ in hashes)})",
                tuple(hashes),
            )
            by_hash = {str(h): str(i) for h, i in cur.fetchall()}
            resolved: list[str] = []
            for h in hashes:
                existing = by_hash.get(h)
                if existing is None:
                    raise DatabaseError("Invariant violated: evidence hash missing after batch upsert")
                resolved.append(existing)
            return tuple(resolved)

        return self._write(_op)

    def save_application(self, app: CorrelatedApplication) -> str:
        """Persist one correlated application record.

        Idempotent on the DDD §6 identity tuple
        ``(session_id, source_id, identity_hash)``: re-correlating the same
        identity returns the EXISTING ``app_id`` and never overwrites
        (db.md §2).  An ID already present for a different identity tuple
        is a collision -> ``DatabaseIntegrityError``.
        """
        identity_hash = app.identity_hash
        if not identity_hash:
            raise DatabaseIntegrityError(
                "Application row carries no identity_hash (malformed row); "
                "refusing to persist a non-deduplicable application record"
            )
        app_id = app.app_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            if app.app_id is not None:
                holder = conn.execute(
                    "SELECT session_id, source_id, identity_hash FROM APP_RECORD WHERE app_id = ?",
                    (app.app_id,),
                ).fetchone()
                if holder is not None and (holder[0], holder[1], holder[2]) != (
                    app.session_id,
                    app.source_id,
                    identity_hash,
                ):
                    raise DatabaseIntegrityError(
                        f"app_id {app.app_id!r} already exists for a different "
                        "(session_id, source_id, identity_hash)"
                    )
            row = dict(app.to_row())
            row["app_id"] = app_id
            conn.execute(
                _dedup_insert_sql(
                    "APP_RECORD", _APP_COLUMNS, "session_id, source_id, identity_hash"
                ),
                _params(_APP_COLUMNS, row),
            )
            cur = conn.execute(
                "SELECT app_id FROM APP_RECORD "
                "WHERE session_id = ? AND source_id = ? AND identity_hash = ?",
                (app.session_id, app.source_id, identity_hash),
            )
            existing = cur.fetchone()
            if existing is None:
                raise DatabaseError("Invariant violated: application row missing after dedup insert")
            return str(existing[0])

        return self._write(_op)

    def link_evidence_to_app(
        self, app_id: str, evidence_id: str, relevance: Relevance
    ) -> None:
        """Create the APP_EVIDENCE link.

        Idempotent: re-linking an existing ``(app_id, evidence_id)`` pair is
        a silent no-op (db.md §2).  Unknown referents (would violate FKs)
        and cross-source links (DDD §4 source scoping) raise
        ``DatabaseIntegrityError`` — the persistence layer re-verifies
        source scoping so a corrupted or out-of-order link can never
        persist cross-source provenance.
        """

        def _op(conn: sqlite3.Connection) -> None:
            app_source = _scalar(
                conn, "SELECT source_id FROM APP_RECORD WHERE app_id = ?", (app_id,)
            )
            if app_source is None:
                raise DatabaseIntegrityError(
                    f"Cannot link evidence: unknown app_id {app_id!r} (would violate FK)"
                )
            evidence_source = _scalar(
                conn,
                "SELECT source_id FROM DISCOVERY_EVIDENCE WHERE evidence_id = ?",
                (evidence_id,),
            )
            if evidence_source is None:
                raise DatabaseIntegrityError(
                    f"Cannot link evidence: unknown evidence_id {evidence_id!r} "
                    "(would violate FK)"
                )
            if app_source != evidence_source:
                raise DatabaseIntegrityError(
                    f"Refusing cross-source link: app {app_id!r} (source {app_source!r}) "
                    f"and evidence {evidence_id!r} (source {evidence_source!r}) belong "
                    "to different sources (DDD §4 source scoping)"
                )
            conn.execute(
                _dedup_insert_sql("APP_EVIDENCE", _LINK_COLUMNS, "app_id, evidence_id"),
                (app_id, evidence_id, str(relevance), utc_now_iso()),
            )

        self._write(_op)

    def save_user_data_finding(self, finding: UserDataFinding) -> str:
        """Persist one user-data finding.

        Idempotent on the DDD unique key
        ``(session_id, source_id, normalized_path)``: re-discovering the
        same location returns the EXISTING ``finding_id`` and never
        overwrites triage state (db.md §2).  An ID already present for a
        different key is a collision -> ``DatabaseIntegrityError``.
        """
        finding_id = finding.finding_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            if finding.finding_id is not None:
                holder = conn.execute(
                    "SELECT session_id, source_id, normalized_path FROM USER_DATA_FINDING "
                    "WHERE finding_id = ?",
                    (finding.finding_id,),
                ).fetchone()
                if holder is not None and (holder[0], holder[1], holder[2]) != (
                    finding.session_id,
                    finding.source_id,
                    finding.normalized_path,
                ):
                    raise DatabaseIntegrityError(
                        f"finding_id {finding.finding_id!r} already exists for a "
                        "different (session_id, source_id, normalized_path)"
                    )
            row = dict(finding.to_row())
            row["finding_id"] = finding_id
            conn.execute(
                _dedup_insert_sql(
                    "USER_DATA_FINDING",
                    _FINDING_COLUMNS,
                    "session_id, source_id, normalized_path",
                ),
                _params(_FINDING_COLUMNS, row),
            )
            cur = conn.execute(
                "SELECT finding_id FROM USER_DATA_FINDING "
                "WHERE session_id = ? AND source_id = ? AND normalized_path = ?",
                (finding.session_id, finding.source_id, finding.normalized_path),
            )
            existing = cur.fetchone()
            if existing is None:
                raise DatabaseError("Invariant violated: finding row missing after dedup insert")
            return str(existing[0])

        return self._write(_op)

    def save_warning(self, warning: WarningRecord) -> str:
        """Insert the warning row; returns its ``warning_id`` (new id where
        the DTO does not carry one).

        Re-saving an existing ``warning_id`` raises
        ``DatabaseIntegrityError`` — dedup never applies to warning PKs
        (db.md §2).
        """
        warning_id = warning.warning_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(warning.to_row())
            row["warning_id"] = warning_id
            conn.execute(
                _insert_values_sql("SESSION_WARNING", _WARNING_COLUMNS),
                _params(_WARNING_COLUMNS, row),
            )
            return warning_id

        return self._write(_op)

    def update_finding_triage(
        self,
        finding_id: str,
        *,
        user_confirmed: bool | None,
        user_notes: str | None,
    ) -> None:
        """The ONLY mutator of hydrated report data (ADR-3, db.md §2).

        Replaces both fields with the supplied values; ``None`` clears the
        field (sets NULL).  Both kwargs are mandatory — callers always
        supply full state.  Raises ``DatabaseError`` if ``finding_id``
        does not exist (db.md §2/§3).  Committed promptly in its own
        small transaction.
        """
        confirmed = None if user_confirmed is None else (1 if user_confirmed else 0)

        def _op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "UPDATE USER_DATA_FINDING SET user_confirmed = ?, user_notes = ? "
                "WHERE finding_id = ?",
                (confirmed, user_notes, finding_id),
            )
            if cur.rowcount != 1:
                raise DatabaseError(
                    f"Unknown finding_id {finding_id!r}; triage update applied to nothing"
                )

        self._write(_op)

    # ── readers ──────────────────────────────────────────────────────

    def load_session_data(self, session_id: str) -> SessionBundle:
        """Materialize the full session bundle as DTOs (never raw rows).

        Raises ``DatabaseError`` for an unknown ``session_id`` (db.md §2).
        This is the one intentionally full-loading API: it backs report
        export (DDD §8 requires the complete evidence package) and triage
        hydration.  Scan pipelines must use ``iter_persisted_evidence``
        instead, which streams in bounded batches (ADR-13).
        """

        def _op(conn: sqlite3.Connection) -> SessionBundle:
            _require_session(conn, session_id)
            session = ScanSession.from_row(
                _row_as_dict(
                    conn.execute(
                        "SELECT * FROM SCAN_SESSION WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                )
            )
            sources = _all_as(
                conn,
                "SELECT * FROM SCAN_SOURCE WHERE session_id = ? ORDER BY rowid",
                (session_id,),
                SourceRecord.from_row,
            )
            profiles = _all_as(
                conn,
                "SELECT * FROM USER_PROFILE WHERE session_id = ? ORDER BY rowid",
                (session_id,),
                UserProfile.from_row,
            )
            applications = _all_as(
                conn,
                "SELECT * FROM APP_RECORD WHERE session_id = ? ORDER BY rowid",
                (session_id,),
                CorrelatedApplication.from_row,
            )
            evidence = _all_as(
                conn,
                "SELECT * FROM DISCOVERY_EVIDENCE WHERE session_id = ? ORDER BY rowid",
                (session_id,),
                Evidence.from_row,
            )
            links = _all_as(
                conn,
                "SELECT * FROM APP_EVIDENCE WHERE app_id IN "
                "(SELECT app_id FROM APP_RECORD WHERE session_id = ?) ORDER BY rowid",
                (session_id,),
                ApplicationEvidenceLink.from_row,
            )
            findings = _all_as(
                conn,
                "SELECT * FROM USER_DATA_FINDING WHERE session_id = ? ORDER BY rowid",
                (session_id,),
                UserDataFinding.from_row,
            )
            warnings = _all_as(
                conn,
                "SELECT * FROM SESSION_WARNING WHERE session_id = ? ORDER BY rowid",
                (session_id,),
                WarningRecord.from_row,
            )
            return SessionBundle(
                session=session,
                sources=tuple(sources),
                user_profiles=tuple(profiles),
                applications=tuple(applications),
                evidence=tuple(evidence),
                app_evidence_links=tuple(links),
                user_data_findings=tuple(findings),
                warnings=tuple(warnings),
            )

        return self._read(_op)

    def iter_persisted_evidence(
        self,
        session_id: str,
        *,
        source_id: str | None = None,
        batch_size: int = 1000,
    ) -> Iterator[tuple[PersistedEvidence, ...]]:
        """Stream persisted evidence in bounded batches (ADR-13, db.md §2).

        Raises ``ValueError`` for ``batch_size < 1`` (before any
        connection access) and ``DatabaseError`` for an unknown
        ``session_id`` (db.md §2).  Yields tuples of at most
        ``batch_size`` ``PersistedEvidence`` in deterministic ``rowid``
        order.  Per db.md §6 the internal lock is held only while fetching
        each batch, never across yields — so UI reads and writer
        transactions are not starved during the correlation phase;
        ``rowid`` ordering is stable because no delete API exists.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        effective = min(batch_size, self._MAX_ITER_BATCH_ROWS)
        sql = "SELECT * FROM DISCOVERY_EVIDENCE WHERE session_id = ?"
        params: tuple[Any, ...] = (session_id,)
        if source_id is not None:
            sql += " AND source_id = ?"
            params = (session_id, source_id)
        sql += " ORDER BY rowid"

        with self._lock:
            self._ensure_open()
            try:
                _require_session(self._conn, session_id)
                cursor = self._conn.execute(sql, params)
            except sqlite3.Error as exc:
                raise DatabaseError(
                    f"Could not start evidence cursor for session {session_id!r}: {exc}"
                ) from exc
        try:
            while True:
                with self._lock:
                    self._ensure_open()
                    try:
                        batch = cursor.fetchmany(effective)
                    except sqlite3.Error as exc:
                        logger.warning("Evidence iteration failed: %s", exc)
                        raise DatabaseError(
                            f"SQLite failure during evidence iteration: {exc}"
                        ) from exc
                if not batch:
                    break
                yield tuple(_as_persisted(row) for row in batch)
        finally:
            with self._lock:
                try:
                    cursor.close()
                except sqlite3.Error:
                    logger.debug("Cursor cleanup failed during evidence iteration", exc_info=True)

    def get_summary(self, session_id: str) -> ScanSummary:
        """Compute session counts with SQL aggregates — no rows are
        materialized.  Raises ``DatabaseError`` for an unknown
        ``session_id`` (db.md §2).

        ``portable_candidate_count`` counts ``APP_RECORD`` rows whose
        ``fingerprint_status = 'Portable'`` (db.md §2: there is no
        portable-candidate table); the remaining counts are row counts of
        their respective tables scoped to the session.
        """

        def _op(conn: sqlite3.Connection) -> ScanSummary:
            _require_session(conn, session_id)

            def count(sql: str, extra: tuple[Any, ...] = ()) -> int:
                row = conn.execute(sql, (session_id, *extra)).fetchone()
                return int(row[0]) if row is not None else 0

            return ScanSummary(
                evidence_count=count(
                    "SELECT COUNT(*) FROM DISCOVERY_EVIDENCE WHERE session_id = ?"
                ),
                application_count=count(
                    "SELECT COUNT(*) FROM APP_RECORD WHERE session_id = ?"
                ),
                finding_count=count(
                    "SELECT COUNT(*) FROM USER_DATA_FINDING WHERE session_id = ?"
                ),
                warning_count=count(
                    "SELECT COUNT(*) FROM SESSION_WARNING WHERE session_id = ?"
                ),
                profile_count=count(
                    "SELECT COUNT(*) FROM USER_PROFILE WHERE session_id = ?"
                ),
                portable_candidate_count=count(
                    "SELECT COUNT(*) FROM APP_RECORD WHERE session_id = ? "
                    "AND fingerprint_status = 'Portable'"
                ),
            )

        return self._read(_op)


def init_db(db_path: Path) -> None:
    """Schema-only bootstrap (db.md §2; SDD §2.17 compatibility).

    Equivalent to opening and immediately closing a ``Database`` — it
    delegates entirely to :meth:`Database.open`, carries no independent
    schema logic, never retains a connection, never mutates existing data,
    and never resolves paths.  Idempotent.  The caller (``src/main.py``)
    then opens the long-lived connection with ``Database.open(db_path)``.
    """
    with Database.open(db_path):
        pass
