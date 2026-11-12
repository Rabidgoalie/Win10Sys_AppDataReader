# Module Contract Governance

Status: ACTIVE · Maintained by: Project Coordinator + Principal Reviewer

## Purpose
Contract sheets freeze the *seams* between modules so the next module can be
generated on local hardware while the current module is under review.
Sheets are normative. `docs/api-ref/` output is generated, non-normative,
and git-ignored.

## Tiers
| Tier | Scope | Policy |
|---|---|---|
| 0 | `models.py`, `pathnorm.py`, `src/config/*`, DDD schema | FROZEN as of Phase 1. Any change requires coordinator + reviewer approval with written rationale in the sheet's §9. |
| 1 | Per-module sheets: public API, error contract, events, I/O surface, threading | Rolling freeze. A sheet moves DRAFT → FROZEN exactly when the *previous* module enters review. |
| 2 | Private helpers, heuristic internals, rationale strings, SQL text | Never frozen. Free to vary at any time. |

## File layout
- One sheet per module: `docs/contracts/<module>.md`, mirroring `src/` names
  (`docs/contracts/ingest/hive_locator.md` ⇄ `src/ingest/hive_locator.py`).
- Cross-cutting sheets (e.g. `filesystem-layout.md`) are permitted.
- Machine-checked content: the §1 fence of each FROZEN sheet.

## Sheet anatomy
1. Status header: version, DRAFT|FROZEN, freeze date, approver.
2. §1 Public API — one fenced Python block. This is what `tests/test_contracts.py` verifies.
3. §2 Postconditions per function.
4. §3 Error contract: raised vs swallowed-to-warning vs critical-I/O escalation.
5. §4 Events and warnings emitted.
6. §5 I/O surface: tables, paths, read-only guarantees.
7. §6 Threading and cancellation.
8. §7 Non-contract internals — explicit free-to-vary list.
9. §8 Acceptance fixtures.
10. §9 Deviations from SDD — recorded, never silent.

## Freeze rules
1. Only the coordinator promotes DRAFT → FROZEN, after reviewer sign-off.
2. The local LLM never edits sheets.
3. Post-freeze changes are amendments: bump minor version, log rationale in §9,
   re-review every module generated against the old revision.
4. Drift is mechanical: `tests/test_contracts.py` imports each implemented
   module and asserts its public surface matches its FROZEN sheet's §1 fence.
5. Every review fix is classified INTERNAL (pipeline continues) or CONTRACTUAL
   (affected sheets amended, affected modules regenerated).