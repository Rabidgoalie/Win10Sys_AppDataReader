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
- Subdirectory mirroring is load-bearing for discovery (`docs/contracts/config/evidence_locations.md` ⇄ `src/config/evidence_locations.py`); targeted runs therefore use node IDs like `test_contract_sheet[config/evidence_locations.md]`.
- Cross-cutting sheets (e.g. `filesystem-layout.md`) are permitted.
- Machine-checked content: the §1 fence of each FROZEN sheet.

## Sheet anatomy
1. **Status header**: MUST be exactly `# Module Contract: <module_name> — <version> <status>` (e.g., `# Module Contract: pathnorm — v1.0.0 DRAFT`). The enforcement script strictly parses this exact string to extract version and status.
   > The separator is an em-dash (U+2014), not a hyphen; the version is the first whitespace token after it; status is FROZEN only if the literal `FROZEN` appears right of the dash — any other header parses as DRAFT, and DRAFT sheets are skipped (not failed) by the enforcement test.
2. **`## 1. Public API`**: One fenced Python block. This is what `tests/test_contracts.py` verifies. The section heading MUST start with `## 1.` for the script to locate the fence.
   - §1 must contain exactly one ` ```python` fence, closed before the next `##` heading; only the first fence inside §1 is machine-read.
   - The fence is parsed with `ast`, never executed: imports are ignored, and every public module-level symbol (constants, functions, classes) defined by the source must appear in the fence — the reverse check fails undeclared surface; `_`-prefixed names are excluded in both directions.
   - Function parameter names/order (including keyword-only) are compared against `inspect.signature`; enum member names and values and dataclass field-name sets are compared exactly.
3. **`## 2. Postconditions`**: Per function.
4. **`## 3. Error contract`**: Raised vs swallowed-to-warning vs critical-I/O escalation.
5. **`## 4. Events and warnings emitted`**.
6. **`## 5. I/O surface`**: Tables, paths, read-only guarantees.
7. **`## 6. Threading and cancellation`**.
8. **`## 7. Non-contract internals`**: Explicit free-to-vary list.
9. **`## 8. Acceptance fixtures`**.
10. **`## 9. Deviations from SDD`**: Recorded, never silent.

## Freeze rules
1. Only the coordinator promotes DRAFT → FROZEN, after reviewer sign-off.
2. The local LLM never edits sheets.
3. Post-freeze changes are amendments: bump minor version, log rationale in §9,
   re-review every module generated against the old revision.
4. Drift is mechanical: `tests/test_contracts.py` imports each implemented
   module and asserts its public surface matches its FROZEN sheet's §1 fence.
   > Discovery is existence-gated (`docs/contracts/<mod>.md` ⇄ `src/<mod>.py`) and parametrized at collection time; IDE test explorers cache collection results and do not re-discover when non-test files change. After adding or freezing a sheet, refresh test discovery (or run `pytest --collect-only`) before trusting the explorer tree.
5. Every review fix is classified INTERNAL (pipeline continues) or CONTRACTUAL
   (affected sheets amended, affected modules regenerated).

### Retired/Rejected Alternative
**Generated API summaries.** An earlier design auto-generated per-module API reference documents from runtime introspection. These were retired with the adoption of rolling contract freeze (ADR-17): they duplicate the §1 fence without authority, omit semantic contracts (§2–§9), and by construction expose Tier 2 internals (_-prefixed helpers, dataclass dunder methods) that governance declares free to vary. `tests/test_contracts.py` provides mechanical enforcement instead.