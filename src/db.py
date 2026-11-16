"""SQLite persistence layer for the Windows 10 Disaster Recovery application.

Implements SDD §2.17, DDD §4 / §7 / §10, and ADR-3 / ADR-6 / ADR-18 /
ADR-21 / ADR-22.  This module is the *only* component that touches the
session database file.

Safety boundary — read-only sources (ADR-1, ADR-18)
----------------------------------------------------
The session database always lives under the application-owned XDG state
base (``<base>/sessions/<session_id>/win10drb.sqlite``) and arrives here
already resolved by the coordinator.  ``db.py`` therefore:

* never resolves XDG paths itself;
* never opens, reads, or writes anything other than the exact file passed
  to :meth:`Database.open`;
* never touches mount points, block devices, manifests, or registry hives.

A scanned source drive is unreachable from this module by construction:
even a defect here cannot write to user data.  The ``read_only = 1`` CHECK
constraint on ``SCAN_SOURCE`` additionally persists the read-only
guarantee as data.

Thread safety (SDD §2.17, ADR-22)
---------------------------------
Each ``Database`` owns exactly one ``sqlite3`` connection.  All access —
reads *and* writes — is serialized through a single re-entrant lock, and
every write runs inside an explicit ``BEGIN IMMEDIATE ... COMMIT``
transaction with rollback on error.  This is deliberately stricter than
ADR-22's minimum (which permits concurrent reads) because Python's
``sqlite3`` module does not allow one connection to be used
simultaneously from several threads; the lock, not SQLite's own checks,
is the serialization mechanism (hence ``check_same_thread=False``).

Evidence-first idempotency (ADR-6, ADR-22)
------------------------------------------
``DISCOVERY_EVIDENCE`` rows deduplicate on the deterministic
``evidence_hash`` (DDD §5); ``APP_RECORD`` rows on
``(session_id, source_id, identity_hash)`` (DDD §6); ``USER_DATA_FINDING``
rows on ``(session_id, source_id, normalized_path)`` (DDD §3).  Duplicate
writes return the existing identifier instead of raising, so re-running a
pipeline stage never corrupts a session.

Triage mutability (ADR-3)
-------------------------
After hydration, the only mutation this module exposes is
:meth:`Database.update_finding_triage` (``user_confirmed`` /
``user_notes`` only).  No other post-hydration mutator exists here.

Error taxonomy (ADR-19, ADR-22)
-------------------------------
Everything this module raises is host-side (``ValueError`` /
``RuntimeError``) and is logged, never escalated to a
``CriticalIoFailureEvent``: a failing SQLite file under the state base is
a host problem, not a dying evidence drive.  This module emits no UI
events; event emission is the coordinator's responsibility (ADR-22).
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence, TypeVar

from .models import (
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

__all__ = ["Database", "init_db"]

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────
# DDD §4 — schema (tables).  IF NOT EXISTS keeps open() idempotent so
# restarting the application on an existing session file never fails.
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
# DDD §7 — indexes (all 19 recommended indexes, verbatim).
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
# Column tuples: the single source of truth shared by INSERT/UPSERT
# statements and parameter binding.  They mirror DDD §4 column names
# exactly; models.to_row() is contractually guaranteed to emit exactly
# these keys (models.md §2 invariant 7).
# ─────────────────────────────────────────────────────────────────────

_SESSION_COLUMNS: tuple[str, ...] = (
    "session_id", "schema_version", "created_at", "mode", "status",
    "scan_options_json",
)
_SESSION_UPDATABLE: tuple[str, ...] = (
    # created_at is forensic creation metadata and is never overwritten.
    "schema_version", "mode", "status", "scan_options_json",
)

_SOURCE_COLUMNS: tuple[str, ...] = (
    "source_id", "session_id", "source_type", "source_role",
    "origin_device_path", "manifest_path", "mount_point", "fs_type",
    "label", "uuid", "size_bytes", "acquisition_method", "read_only",
    "status", "warnings_json",
)
_SOURCE_UPDATABLE: tuple[str, ...] = tuple(
    c for c in _SOURCE_COLUMNS if c not in ("source_id", "session_id")
)

_PROFILE_COLUMNS: tuple[str, ...] = (
    "profile_id", "session_id", "source_id", "username", "sid",
    "profile_path", "normalized_profile_path", "ntuser_path",
    "usrclass_path", "documents_path", "desktop_path", "downloads_path",
    "pictures_path", "music_path", "videos_path", "appdata_local_path",
    "appdata_roaming_path", "appdata_locallow_path", "saved_games_path",
    "is_default_profile", "is_system_profile", "parse_warnings_json",
)
_PROFILE_UPDATABLE: tuple[str, ...] = tuple(
    c for c in _PROFILE_COLUMNS if c not in ("profile_id", "session_id")
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
# Private helpers (ADR-17 Tier 2 — non-contract internals)
# ─────────────────────────────────────────────────────────────────────

def _best_effort_chmod(target: Path, mode: int) -> None:
    """Apply ADR-18 permissions best-effort; a failure here must not
    break database opening (e.g. read-only filesystems in edge setups)."""
    try:
        os.chmod(target, mode)
    except OSError:
        logger.debug("Best-effort chmod %o on %s failed; continuing", mode, target)


def _ensure_parent_directory(db_path: Path) -> None:
    """Ensure the session directory exists with ADR-18 owner-only
    permissions.  ``db.py`` never *resolves* the XDG base — it only
    ensures the exact, already-resolved parent handed to us exists."""
    parent = db_path.parent
    existed = parent.exists()
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Unable to create state directory {parent}: {exc}") from exc
    if not existed:
        _best_effort_chmod(parent, 0o700)


def _row_as_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a ``sqlite3.Row`` into a plain ``dict`` so it satisfies the
    ``Mapping[str, Any]`` contract of the models ``from_row`` classmethods
    (a ``sqlite3.Row`` is sequence-like, not a ``Mapping``)."""
    return dict(zip(row.keys(), row, strict=True))


def _params(columns: tuple[str, ...], row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Bind parameters in fixed column order.  A missing key becomes NULL,
    which a NOT NULL column then rejects with an actionable IntegrityError
    rather than a cryptic bind failure."""
    return tuple(row.get(column) for column in columns)


def _insert_values_sql(table: str, columns: tuple[str, ...]) -> str:
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"


def _upsert_sql(
    table: str,
    columns: tuple[str, ...],
    conflict_target: str,
    update_columns: tuple[str, ...] | None = None,
) -> str:
    """Build an idempotent INSERT.  ``update_columns=None`` yields
    ``ON CONFLICT(...) DO NOTHING`` — the ADR-22 rule that duplicate writes
    return the existing identifier and never overwrite stored state."""
    sql = _insert_values_sql(table, columns)
    if update_columns:
        assignments = ", ".join(f"{c} = excluded.{c}" for c in update_columns)
        sql += f" ON CONFLICT({conflict_target}) DO UPDATE SET {assignments}"
    else:
        sql += f" ON CONFLICT({conflict_target}) DO NOTHING"
    return sql


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row is not None else None


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
    """Thread-safe owner of one session SQLite database (ADR-22).

    Construct via :meth:`open`; never instantiate directly.  The connection
    is private: UI widgets and workers only ever see DTOs and the public
    writer/reader methods (SDD §2.17: no connection exposure).
    """

    #: ADR-22: ``save_evidence_batch`` accepts 1..500 rows per call.
    _MAX_BATCH_ROWS: int = 500
    #: Hard memory bound for ``iter_persisted_evidence`` batches.
    _MAX_ITER_BATCH_ROWS: int = 10_000
    #: ADR-22: ``busy_timeout`` >= 5000 ms.
    _BUSY_TIMEOUT_MS: int = 5000

    def __init__(self, conn: sqlite3.Connection, path: Path) -> None:
        # Private constructor; Database.open() performs configuration.
        self._conn = conn
        self._path = Path(path)
        # One lock serializes ALL access to this connection (see module
        # docstring).  RLock so internal helpers may nest safely.
        self._lock = threading.RLock()
        self._closed = False

    # ── lifecycle ────────────────────────────────────────────────────

    @classmethod
    def open(cls, db_path: Path) -> "Database":
        """Open (creating if needed) the session database at ``db_path``.

        Why this boundary exists: the path is taken as-is from the
        coordinator (ADR-18 rule: ``db.py`` never resolves paths itself),
        so the only file this instance can ever touch is the session
        database — never a scanned source, mount point, or manifest.
        """
        path = Path(db_path)
        _ensure_parent_directory(path)
        existed = path.exists()
        try:
            conn = sqlite3.connect(
                str(path),
                timeout=cls._BUSY_TIMEOUT_MS / 1000.0,
                # We serialize every use through self._lock; the lock — not
                # sqlite's same-thread assertion — is our safety mechanism.
                check_same_thread=False,
                # Autocommit at the driver level; write transactions are
                # explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK in _write().
                isolation_level=None,
            )
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Unable to open session database {path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        try:
            # DDD §10: foreign key enforcement on every connection.
            conn.execute("PRAGMA foreign_keys = ON")
            # ADR-22: WAL improves crash safety and concurrent-read behavior.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(f"PRAGMA busy_timeout = {cls._BUSY_TIMEOUT_MS}")
            # Standard WAL companion: crash-safe without fsync-per-commit cost.
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as exc:
            conn.close()
            raise ValueError(f"Unable to configure session database {path}: {exc}") from exc
        if not existed:
            _best_effort_chmod(path, 0o600)
            # WAL sidecar files carry database content too: owner-only.
            for suffix in (".wal", ".shm"):
                sidecar = Path(str(path) + suffix)
                if sidecar.exists():
                    _best_effort_chmod(sidecar, 0o600)
        db = cls(conn, path)
        db._initialize_schema()
        return db

    def close(self) -> None:
        """Close the connection idempotently.  Serialized on the same lock
        so no operation can race the shutdown; the final WAL checkpoint
        keeps the session file as a single portable file (best-effort)."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            conn = self._conn
            try:
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

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
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
        if self._closed:
            raise RuntimeError(
                "Database connection is closed; open a new instance with "
                "Database.open() (a closed session database is never reused)"
            )

    def _write(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``operation`` inside one serialized ``BEGIN IMMEDIATE``
        transaction.  Rollback on any failure; host-side errors surface as
        ``ValueError`` and are *never* escalated to critical I/O failures
        (ADR-19/ADR-22)."""
        with self._lock:
            self._ensure_open()
            conn = self._conn
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                logger.warning("BEGIN IMMEDIATE failed: %s", exc)
                raise ValueError(f"Could not begin write transaction: {exc}") from exc
            try:
                result = operation(conn)
            except sqlite3.Error as exc:
                self._rollback(conn)
                logger.warning("Write transaction failed: %s", exc)
                raise ValueError(f"Write transaction failed: {exc}") from exc
            except BaseException:
                # Intentional ValueError from a validation inside the
                # operation (unknown id, empty hash): roll back, re-raise.
                self._rollback(conn)
                raise
            try:
                conn.execute("COMMIT")
            except sqlite3.Error as exc:
                self._rollback(conn)
                logger.warning("COMMIT failed: %s", exc)
                raise ValueError(f"Could not commit write transaction: {exc}") from exc
            return result

    def _read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run a read under the same serialization lock (see module
        docstring for why reads are also serialized)."""
        with self._lock:
            self._ensure_open()
            try:
                return operation(self._conn)
            except sqlite3.Error as exc:
                logger.warning("Read failed: %s", exc)
                raise ValueError(f"Read failed: {exc}") from exc

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

    def save_session(self, session: ScanSession) -> str:
        """Insert the session row; a re-save refreshes mutable columns but
        never overwrites ``created_at`` (forensic creation metadata)."""

        def _op(conn: sqlite3.Connection) -> str:
            conn.execute(
                _upsert_sql(
                    "SCAN_SESSION", _SESSION_COLUMNS, "session_id", _SESSION_UPDATABLE
                ),
                _params(_SESSION_COLUMNS, session.to_row()),
            )
            return session.session_id

        return self._write(_op)

    def update_session_status(self, session_id: str, status: SessionStatus) -> None:
        """Transition the session state (coordinator-owned state machine).
        Unknown session ids raise a host-side ``ValueError`` — never a
        silent no-op."""

        def _op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "UPDATE SCAN_SESSION SET status = ? WHERE session_id = ?",
                (str(status), session_id),
            )
            if cur.rowcount != 1:
                raise ValueError(f"Unknown session_id {session_id!r}; status update applied to nothing")

        self._write(_op)

    def save_source(self, source: SourceRecord) -> str:
        """Insert the source row; a re-save with the same ``source_id``
        refreshes fields in place.  The DDD type/acquisition pairing CHECK
        and ``read_only = 1`` CHECK are enforced by the schema itself."""

        def _op(conn: sqlite3.Connection) -> str:
            conn.execute(
                _upsert_sql(
                    "SCAN_SOURCE", _SOURCE_COLUMNS, "source_id", _SOURCE_UPDATABLE
                ),
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
        """Update source state.  ``warnings_json=None`` means *keep the
        existing warning history* — source-specific warnings are
        accumulated, never clobbered by a status-only update."""

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
                raise ValueError(f"Unknown source_id {source_id!r}; status update applied to nothing")

        self._write(_op)

    def save_user_profile(self, profile: UserProfile) -> str:
        """Insert the profile row, assigning a new id where the DTO does
        not carry one.  Re-saves refresh resolved path fields in place
        (e.g. Documents baseline learned after an initial insert)."""
        profile_id = profile.profile_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(profile.to_row())
            row["profile_id"] = profile_id
            conn.execute(
                _upsert_sql(
                    "USER_PROFILE", _PROFILE_COLUMNS, "profile_id", _PROFILE_UPDATABLE
                ),
                _params(_PROFILE_COLUMNS, row),
            )
            return profile_id

        return self._write(_op)

    def save_evidence(self, evidence: Evidence) -> str:
        """Persist one evidence row (evidence-first, ADR-6).

        Idempotent on the deterministic ``evidence_hash`` (DDD §5,
        ADR-22): a duplicate returns the existing ``evidence_id`` instead
        of raising.  A missing hash is a contract violation and is
        rejected outright — it would otherwise bypass deduplication via
        the unique column.
        """
        evidence_hash = evidence.evidence_hash
        if not evidence_hash:
            raise ValueError(
                "Evidence is missing its deterministic evidence_hash; "
                "refusing to persist a non-deduplicable evidence row"
            )
        evidence_id = evidence.evidence_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(evidence.to_row())
            row["evidence_id"] = evidence_id
            conn.execute(
                _upsert_sql("DISCOVERY_EVIDENCE", _EVIDENCE_COLUMNS, "evidence_hash"),
                _params(_EVIDENCE_COLUMNS, row),
            )
            cur = conn.execute(
                "SELECT evidence_id FROM DISCOVERY_EVIDENCE WHERE evidence_hash = ?",
                (evidence_hash,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise RuntimeError("Invariant violated: evidence row missing after upsert")
            return str(existing[0])

        return self._write(_op)

    def save_evidence_batch(self, rows: Sequence[Evidence]) -> tuple[str, ...]:
        """Persist 1..500 evidence rows in a single transaction (ADR-22).

        Returns the persisted ``evidence_id`` per input row, in input
        order, with idempotent deduplication on ``evidence_hash``.  The
        per-batch transaction is the DDD §10 "periodic commits during
        long scans" mechanism.
        """
        count = len(rows)
        if count < 1 or count > self._MAX_BATCH_ROWS:
            raise ValueError(
                f"save_evidence_batch requires 1..{self._MAX_BATCH_ROWS} rows "
                f"per call (got {count}); one transaction per batch (ADR-22)"
            )

        def _op(conn: sqlite3.Connection) -> tuple[str, ...]:
            prepared: list[tuple[Any, ...]] = []
            hashes: list[str] = []
            for evidence in rows:
                hash_value = evidence.evidence_hash
                if not hash_value:
                    raise ValueError(
                        "Evidence batch contains a row without evidence_hash; "
                        "refusing to persist a non-deduplicable row"
                    )
                row = dict(evidence.to_row())
                row["evidence_id"] = evidence.evidence_id or new_id()
                prepared.append(_params(_EVIDENCE_COLUMNS, row))
                hashes.append(hash_value)
            conn.executemany(
                _upsert_sql("DISCOVERY_EVIDENCE", _EVIDENCE_COLUMNS, "evidence_hash"),
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
                    raise RuntimeError("Invariant violated: evidence hash missing after batch upsert")
                resolved.append(existing)
            return tuple(resolved)

        return self._write(_op)

    def save_application(self, app: CorrelatedApplication) -> str:
        """Persist one correlated application record.

        Idempotent on the DDD §6 identity tuple
        ``(session_id, source_id, identity_hash)``: re-correlating the same
        identity returns the existing ``app_id`` and never overwrites the
        stored record (ADR-22: no silent overwrites)."""
        identity_hash = app.identity_hash
        if not identity_hash:
            raise ValueError(
                "Application is missing its deterministic identity_hash; "
                "refusing to persist a non-deduplicable application record"
            )
        app_id = app.app_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(app.to_row())
            row["app_id"] = app_id
            conn.execute(
                _upsert_sql(
                    "APP_RECORD",
                    _APP_COLUMNS,
                    "session_id, source_id, identity_hash",
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
                raise RuntimeError("Invariant violated: application row missing after upsert")
            return str(existing[0])

        return self._write(_op)

    def link_evidence_to_app(
        self, app_id: str, evidence_id: str, relevance: Relevance
    ) -> None:
        """Create the APP_EVIDENCE link.

        Why this boundary exists: DDD §3 — an application may only be
        linked to evidence from the *same* source.  The correlator
        guarantees this logically, but the persistence layer re-verifies
        both referents and their source scoping so that a corrupted or
        out-of-order link can never persist cross-source provenance.
        Duplicate links are idempotent (unique ``(app_id, evidence_id)``).
        """

        def _op(conn: sqlite3.Connection) -> None:
            app_source = _scalar(
                conn, "SELECT source_id FROM APP_RECORD WHERE app_id = ?", (app_id,)
            )
            if app_source is None:
                raise ValueError(f"Cannot link evidence: unknown app_id {app_id!r}")
            evidence_source = _scalar(
                conn,
                "SELECT source_id FROM DISCOVERY_EVIDENCE WHERE evidence_id = ?",
                (evidence_id,),
            )
            if evidence_source is None:
                raise ValueError(f"Cannot link evidence: unknown evidence_id {evidence_id!r}")
            if app_source != evidence_source:
                raise ValueError(
                    f"Refusing cross-source link: app {app_id!r} (source {app_source!r}) "
                    f"and evidence {evidence_id!r} (source {evidence_source!r}) belong "
                    "to different sources (DDD §3 source scoping)"
                )
            conn.execute(
                _upsert_sql("APP_EVIDENCE", _LINK_COLUMNS, "app_id, evidence_id"),
                (app_id, evidence_id, str(relevance), utc_now_iso()),
            )

        self._write(_op)

    def save_user_data_finding(self, finding: UserDataFinding) -> str:
        """Persist one user-data finding.

        Idempotent on the DDD unique key
        ``(session_id, source_id, normalized_path)``: re-discovering the
        same location returns the existing ``finding_id`` and never
        overwrites triage state (ADR-21: no silent overwrites of local
        triage data)."""
        finding_id = finding.finding_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(finding.to_row())
            row["finding_id"] = finding_id
            conn.execute(
                _upsert_sql(
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
                raise RuntimeError("Invariant violated: finding row missing after upsert")
            return str(existing[0])

        return self._write(_op)

    def save_warning(self, warning: WarningRecord) -> str:
        """Persist one user-visible warning (typed Warnings per the
        defensive-parsing directives; warnings are the scan's self-report
        of corruption, bounds, and I/O trouble)."""
        warning_id = warning.warning_id or new_id()

        def _op(conn: sqlite3.Connection) -> str:
            row = dict(warning.to_row())
            row["warning_id"] = warning_id
            conn.execute(
                _upsert_sql("SESSION_WARNING", _WARNING_COLUMNS, "warning_id"),
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
        """The *only* post-hydration mutator in this module (ADR-3).

        Why this boundary exists: after a report import (triage mode),
        the session must be mutable only for ``user_confirmed`` and
        ``user_notes``.  No other method of this class writes to
        ``USER_DATA_FINDING`` after hydration; scan-time insert is the
        sole other write path and cannot run against a triage session.
        Committed promptly in its own small transaction (DDD §10).
        """
        confirmed = None if user_confirmed is None else (1 if user_confirmed else 0)

        def _op(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                "UPDATE USER_DATA_FINDING SET user_confirmed = ?, user_notes = ? "
                "WHERE finding_id = ?",
                (confirmed, user_notes, finding_id),
            )
            if cur.rowcount != 1:
                raise ValueError(f"Unknown finding_id {finding_id!r}; triage update applied to nothing")

        self._write(_op)

    # ── readers ──────────────────────────────────────────────────────

    def load_session_data(self, session_id: str) -> SessionBundle:
        """Materialize the full session bundle as DTOs (never raw rows).

        This is the one intentionally full-loading API: it backs report
        export (DDD §8 requires the complete evidence package) and triage
        hydration.  Scan pipelines must use ``iter_persisted_evidence``
        instead, which streams in bounded batches (ADR-13).
        """

        def _op(conn: sqlite3.Connection) -> SessionBundle:
            session_row = _scalar(
                conn, "SELECT rowid FROM SCAN_SESSION WHERE session_id = ?", (session_id,)
            )
            if session_row is None:
                raise ValueError(f"Unknown session_id {session_id!r}")
            session_sql = (
                "SELECT session_id, schema_version, created_at, mode, status, "
                "scan_options_json FROM SCAN_SESSION WHERE session_id = ?"
            )
            session = ScanSession.from_row(_row_as_dict(conn.execute(session_sql, (session_id,)).fetchone()))
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
        """Stream persisted evidence in bounded batches (ADR-13, ADR-22).

        Yields ``tuple[PersistedEvidence, ...]`` in deterministic ``rowid``
        (insertion) order.  The serialization lock is held only while a
        batch is fetched — it is released between yields so UI reads and
        concurrent writer transactions are not starved during the
        multi-minute correlation phase.  The open cursor is safe across
        lock releases because the connection runs in autocommit mode and
        SQLite permits a connection to upgrade its own read lock.
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
                cursor = self._conn.execute(sql, params)
            except sqlite3.Error as exc:
                raise ValueError(f"Could not start evidence cursor for session {session_id!r}: {exc}") from exc
        try:
            while True:
                with self._lock:
                    self._ensure_open()
                    try:
                        batch = cursor.fetchmany(effective)
                    except sqlite3.Error as exc:
                        logger.warning("Evidence iteration failed: %s", exc)
                        raise ValueError(f"Evidence iteration failed: {exc}") from exc
                if not batch:
                    break
                yield tuple(_as_persisted(row) for row in batch)
        finally:
            with self._lock:
                try:
                    cursor.close()
                except sqlite3.Error:
                    logger.debug(
                        "Cursor cleanup failed during evidence iteration", exc_info=True
                    )

    def get_summary(self, session_id: str) -> ScanSummary:
        """Compute session counts with SQL aggregates — no rows are
        materialized.  ``portable_candidate_count`` counts application
        records whose fingerprint is ``Portable``: portable candidates
        are a pipeline working type (models.py) and their persisted form
        is the Portable fingerprint on ``APP_RECORD``."""

        def _op(conn: sqlite3.Connection) -> ScanSummary:
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
                    "SELECT COUNT(*) FROM APP_RECORD WHERE session_id = ? AND fingerprint_status = 'Portable'"
                ),
            )

        return self._read(_op)


def init_db(db_path: Path) -> None:
    """Bootstrap the session database (SDD §2.17, ADR-22 fidelity rule).

    Opens ``db_path``, creates the DDD schema and indexes idempotently,
    and closes the connection again.  The caller (``src/main.py``) then
    opens the long-lived connection with :meth:`Database.open`.  Returns
    ``None`` by contract.
    """
    with Database.open(db_path):
        pass
