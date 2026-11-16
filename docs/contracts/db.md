# Module Contract: src/db.py — v1.1.0 FROZEN (Tier 1)

Frozen: 2026-11-16 · Supersedes: v1.0.0 FROZEN · Approver: Project Coordinator ______
Refines: SDD §2.17, DDD §1/§4/§7/§10, ADR-3, ADR-18, ADR-21, ADR-22.

## 1. Public API

```python
from typing import Final, Iterator, Sequence

DB_SCHEMA_VERSION: Final[str]          # must equal models.SCHEMA_VERSION

class DatabaseError(RuntimeError): ...
class DatabaseIntegrityError(DatabaseError): ...   # FK violation / malformed row only

class Database:
    @classmethod
    def open(cls, db_path: Path) -> "Database": ...   # creates schema if absent
    def close(self) -> None: ...
    def __enter__(self) -> "Database": ...
    def __exit__(self, *exc) -> None: ...

    # ---- read-only introspection (v1.1.0) ----
    @property
    def path(self) -> Path: ...        # exact session-database file this instance owns
    @property
    def is_closed(self) -> bool: ...   # lifecycle flag; False until close() completes

    # ---- writers (serialized; IDs via models.new_id(); input DTOs never mutated) ----
    def save_session(self, session: ScanSession) -> str: ...
    def update_session_status(self, session_id: str, status: SessionStatus) -> None: ...
    def save_source(self, source: SourceRecord) -> str: ...
    def update_source_status(self, source_id: str, status: SourceStatus,
                             warnings_json: str | None = None) -> None: ...
    def save_user_profile(self, profile: UserProfile) -> str: ...
    def save_evidence(self, evidence: Evidence) -> str: ...
    def save_evidence_batch(self, rows: Sequence[Evidence]) -> tuple[str, ...]: ...
    def save_application(self, app: CorrelatedApplication) -> str: ...
    def link_evidence_to_app(self, app_id: str, evidence_id: str,
                             relevance: Relevance) -> None: ...
    def save_user_data_finding(self, finding: UserDataFinding) -> str: ...
    def save_warning(self, warning: WarningRecord) -> str: ...
    def update_finding_triage(self, finding_id: str, *,
                              user_confirmed: bool | None,
                              user_notes: str | None) -> None: ...

    # ---- readers ----
    def load_session_data(self, session_id: str) -> SessionBundle: ...
    def iter_persisted_evidence(self, session_id: str, *,
                                source_id: str | None = None,
                                batch_size: int = 1000,
                                ) -> Iterator[tuple[PersistedEvidence, ...]]: ...
    def get_summary(self, session_id: str) -> ScanSummary: ...

def init_db(db_path: Path) -> None: ...   # schema-only; SDD §2.17 compat
```

## 2. Postconditions

- `save_*` returns the assigned UUID; if the DTO already carries an ID it is used as-is.
- Dedup is idempotent, never an error: duplicate `evidence_hash`, `(session_id, source_id, identity_hash)`, and `(session_id, source_id, normalized_path)` inserts return the EXISTING row's ID.
- Primary-key and UNIQUE collisions OUTSIDE those three dedup keys raise `DatabaseIntegrityError` — including re-saving a session, source, profile, or warning whose ID already exists, and any insert carrying an ID already present without matching the corresponding dedup key. Dedup never applies to session, source, profile, or warning primary keys. This is the hook `state.py` relies on for ADR-21 hydration-conflict detection.
- `save_evidence_batch`: 1 ≤ len(rows) ≤ 500 else ValueError; one transaction per batch; the returned tuple aligns positionally with `rows` (each slot is the new or pre-existing ID for that row).
- `link_evidence_to_app` is idempotent: re-linking an existing `(app_id, evidence_id)` pair is a silent no-op. Cross-source links — the evidence row and the application row belong to different `source_id`s — raise `DatabaseIntegrityError` (DDD §4 source-scoping).
- `iter_persisted_evidence`: deterministic rowid order; yields tuples ≤ batch_size.
- FK ordering enforced: session before sources, sources before everything else.
- `update_source_status`: `warnings_json=None` leaves the column unchanged; pass an explicit string to replace it.
- `update_finding_triage` replaces both fields with the supplied values; `None` clears the field (sets NULL). Both kwargs are mandatory (no defaults), so callers always supply full state. It is the ONLY mutator of hydrated report data (enforces ADR-3: post-hydration mutability limited to user_confirmed/user_notes). `update_finding_triage` raises `DatabaseError` if `finding_id` does not exist.
- The `update_*` methods raise `DatabaseError` when the target row does not exist; they are never silent no-ops on unknown IDs.
- Readers (`load_session_data`, `get_summary`, `iter_persisted_evidence`) raise `DatabaseError` for an unknown `session_id`.
- `get_summary`: `portable_candidate_count` counts `APP_RECORD` rows whose `fingerprint_status = 'Portable'` (there is no portable-candidate table); the remaining counts are row counts of their respective tables scoped to the session.
- `close()` is idempotent. `__exit__` rolls back any uncommitted transaction when an exception is in flight, then closes; it never suppresses the exception.
- `path` (read-only property, v1.1.0): returns the exact `Path` passed to `Database.open`, un-resolved and never mutated, stable for the instance's lifetime. It never raises, including after `close()`. It exposes no content — only the file path this instance owns.
- `is_closed` (read-only property, v1.1.0): `False` from a successful `open()` until `close()` completes; `True` thereafter. Because `close()` is idempotent, repeated reads after close remain `True`. It never raises.
- Commits promptly. No generic UPDATE API exists.
- `init_db(db_path)` is schema-only and idempotent. It is equivalent to opening and immediately closing a `Database` (it delegates to `Database.open`). It never retains a connection, never mutates existing data, and never resolves paths. `Database.open` is the single source of truth for schema; `init_db` shall not carry independent schema logic.

## 3. Error contract

Raises `DatabaseError` on unrecoverable SQLite failure, on any operation after `close()`, and on unknown IDs per §2 (unknown `session_id` in readers; unknown target rows in `update_*`). Raises `DatabaseIntegrityError` (a `DatabaseError` subclass) on FK violations, cross-source application–evidence links, and primary-key/UNIQUE collisions outside the dedup keys (§2). Never raises on dedup conflicts.

`save_evidence_batch` raises `ValueError` — not `DatabaseError` — for out-of-bounds batch sizes, before touching the connection.

db.py errors are HOST-side. They must never be mapped by callers to `CriticalIoFailureEvent` (that is reserved for source-drive I/O).

The read-only properties `path` and `is_closed` never raise; `path` remains readable after `close()`, and `is_closed` simply reports the closed state.

## 4. Events & warnings

None. db.py emits no UI events and creates no WarningRecord; callers own
wording.

## 5. I/O surface

- One SQLite file located at `<base>/sessions/<session_id>/win10drb.sqlite`, resolved by the coordinator per the `docs/contracts/filesystem-layout.md` contract. The database module receives this absolute path via `Database.open(db_path)` and never resolves paths itself.
- The `path` property (v1.1.0) exposes exactly that single file path and introduces no additional I/O surface.
- The database file is created mode 0600 regardless of umask (filesystem-layout contract, ADR-18); the WAL `-wal`/`-shm` companion files inherit the same mode. The parent directory is assumed to exist; db.py creates no directories.
- WAL journal mode; busy_timeout ≥ 5000 ms; PRAGMA foreign_keys = ON on every connection.
- No other filesystem access. Never touches source mounts or manifests.

## 6. Threading

- All public methods thread-safe via one internal lock around one connection (check_same_thread=False). Connections/cursors never escape the class.
- `iter_persisted_evidence` holds the internal lock only while fetching each batch, not across yields; rowid ordering is stable because no delete API exists.
- The read-only properties `path` and `is_closed` (v1.1.0) are safe for concurrent reads and do not acquire the internal lock: `path` is immutable after construction and `is_closed` reads a single boolean flag.
- No reader bypass: serialization is total at this scale; correctness over throughput.

## 7. Non-contract internals

Index creation order, SQL text, row-mapping helpers, batch page size tuning.

## 8. Acceptance fixtures

tests/test_db.py + tmp SQLite only (NFR-10: no root, no drives). Fixtures must cover at least: dedup idempotency for all three dedup keys; PK/UNIQUE collision raising `DatabaseIntegrityError`; cross-source link rejection and link no-op; unknown-ID/unknown-session raises; batch positional alignment, bounds (`ValueError`), and all-or-nothing transactionality; `warnings_json=None` leave-alone; triage replace/clear; post-`close()` raises; 0600 file mode; concurrent serialized access.

Additionally (v1.1.0): property `path` returns the exact path passed to `Database.open`; `is_closed` is `False` after `open`, becomes `True` after `close`, and remains `True` on repeated reads; both remain readable after `close()` without raising.

## 9. Deviations and amendment record

Deviations from SDD §2.17: none. §1 matches the SDD Core APIs surface exactly. The fence additionally declares `DB_SCHEMA_VERSION`, `DatabaseError`, and `DatabaseIntegrityError` — additive refinements carrying §2/§3 semantics, not structural deviations. (The v0.9 DRAFT claimed deviations against an older SDD revision in which §2.17 listed free functions; that claim was stale and is removed at freeze.) At v1.1.0 the fence additionally declares `Database.path`, `Database.is_closed`, `logger`, and `T` to match the frozen implementation (§9 below).

| Version | Date | Change | Rationale | Approved by |
| --- | --- | --- | --- | --- |
| 1.0.0 | 2026-11-16 | Initial freeze. Reviewer sign-off clarifications folded into §2/§3/§5/§6/§8: link idempotency + DDD §4 source-scoping enforcement; PK/UNIQUE collisions outside dedup keys raise `DatabaseIntegrityError` (ADR-21 hydration hook); `warnings_json=None` leaves the column unchanged; unknown `session_id`/unknown target rows raise `DatabaseError`; `update_finding_triage` replace/clear semantics; iterator lock held per fetch, not across yields; 0600 file mode with WAL companions, no directory creation; batch results align positionally with input; `portable_candidate_count` defined via `APP_RECORD.fingerprint_status`; `close()` idempotent and `__exit__` rolls back on exception; Refines line cites DDD §4, ADR-18, ADR-21, ADR-22. §1 fence is byte-identical to v0.9 DRAFT — no mechanical surface change. Also removed the stale deviation claims inherited from v0.9 DRAFT: the current SDD §2.17 already specifies this API verbatim (§9 records the history). | Ambiguity removed before local-model implementation; pre-freeze edits carry no amendment cost (ADR-17) | Coordinator + Reviewer |
| 1.1.0 | 2026-11-16 |  Additive surface amendment. §1 fence declares two read-only `Database` lifecycle properties (`path`, `is_closed`) introduced by the db.py module-generation step; §2/§3/§5/§6/§8 postconditions added for them. No pre-existing signature changed. | `path` and `is_closed` are genuinely-public read-only accessors needed by `state.py`/the coordinator (owned-file reference for export-path suggestion and lifecycle guarding around `close()`), so they are frozen with explicit postconditions. Classified CONTRACTUAL (sheet amended to match frozen code). | Coordinator + Reviewer |