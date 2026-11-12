# Module Contract: src/db.py — v0.9 DRAFT
Refines: SDD §2.17, DDD §1/§7/§10, ADR-3. Deviation: SDD lists free functions;
this contract wraps them in a `Database` class owning the serialized connection.
Module-level `init_db()` retained for SDD fidelity and tests.

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
- Dedup is idempotent, never an error: duplicate `evidence_hash`,
  `(session_id, source_id, identity_hash)`, and
  `(session_id, source_id, normalized_path)` inserts return the EXISTING row's ID.
- `save_evidence_batch`: 1 ≤ len(rows) ≤ 500 else ValueError; one transaction per batch.
- `iter_persisted_evidence`: deterministic rowid order; yields tuples ≤ batch_size.
- FK ordering enforced: session before sources, sources before everything else.
- `update_finding_triage` is the ONLY mutator of hydrated report data (enforces
  ADR-3: post-hydration mutability limited to user_confirmed/user_notes).
  Commits promptly. No generic UPDATE API exists.

## 3. Error contract
- Raises `DatabaseError` on unrecoverable SQLite failure; `DatabaseIntegrityError`
  on FK violations. Never raises on dedup conflicts.
- db.py errors are HOST-side. They must never be mapped by callers to
  `CriticalIoFailureEvent` (that is reserved for source-drive I/O).
- Operations after `close()` raise `DatabaseError`.

## 4. Events & warnings
None. db.py emits no UI events and creates no WarningRecord; callers own wording.

## 5. I/O surface
- One SQLite file located at `<base>/sessions/<session_id>/win10drb.sqlite`, resolved by the coordinator per the `docs/contracts/filesystem-layout.md` contract. The database module receives this absolute path via `Database.open(db_path)` and never resolves paths itself.
- WAL journal mode; busy_timeout ≥ 5000 ms; PRAGMA foreign_keys = ON on every connection.
- No other filesystem access. Never touches source mounts or manifests.

## 6. Threading
- All public methods thread-safe via one internal lock around one connection
  (check_same_thread=False). Connections/cursors never escape the class.
- No reader bypass: serialization is total at this scale; correctness over throughput.

## 7. Non-contract internals
Index creation order, SQL text, row-mapping helpers, batch page size tuning.

## 8. Acceptance fixtures
tests/test_db.py + tmp SQLite only (NFR-10: no root, no drives).

## 9. Deviations
- Class-based API vs SDD §2.17 free functions (rationale: lifecycle + test isolation).
- Adds `update_source_status`, `update_session_status`, `update_finding_triage`,
  `iter_persisted_evidence`, `get_summary` — implied by SDD §2.13/§2.19, UIDD triage,
  and `ScanCompletedEvent`, but absent from the SDD list. Recorded here so they are
  deliberate, not accidental.