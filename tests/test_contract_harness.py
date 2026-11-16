"""
Regression tests for the Freeze Rule 4 enforcement harness itself.

Incident (2026-11-17, db.py v1.0.0 pre-review): check_class read only
ast.arguments.args and dropped every keyword-only parameter declared in the
fence, producing false-positive "parameter mismatch" failures for
Database.update_finding_triage and Database.iter_persisted_evidence.

These tests require no root, no drives, and no Windows fixtures (NFR-10).
"""
import ast
import sys
import textwrap
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import test_contracts as harness  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────

def _fence_class(source: str, name: str) -> ast.ClassDef:
    tree = ast.parse(textwrap.dedent(source))
    return next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name
    )


def _fence_function(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    return next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def _class_mismatches(fence_source: str, impl: type, fence_name: str) -> list[str]:
    out: list[str] = []
    harness.check_class(impl, _fence_class(fence_source, fence_name), out, source_node=None)
    return out


def _function_mismatches(fence_source: str, impl, fence_name: str) -> list[str]:
    out: list[str] = []
    harness.check_function(impl, _fence_function(fence_source, fence_name), out)
    return out


# ── the two incident signatures, verbatim from db.md v1.0.0 §1 ───────────

TRIAGE_FENCE = """
class Database:
    def update_finding_triage(self, finding_id: str, *,
                              user_confirmed: bool | None,
                              user_notes: str | None) -> None: ...
"""

ITER_FENCE = """
class Database:
    def iter_persisted_evidence(self, session_id: str, *,
                                source_id: str | None = None,
                                batch_size: int = 1000,
                                ) -> list[str]: ...
"""


class TriageCorrect:
    def update_finding_triage(self, finding_id: str, *,
                              user_confirmed: bool | None,
                              user_notes: str | None) -> None:
        raise NotImplementedError


class IterCorrect:
    def iter_persisted_evidence(self, session_id: str, *,
                                source_id: str | None = None,
                                batch_size: int = 1000):
        raise NotImplementedError


def test_required_keyword_only_method_is_not_a_false_positive():
    """db.md §2: both triage kwargs are mandatory (no defaults)."""
    assert _class_mismatches(TRIAGE_FENCE, TriageCorrect, "Database") == []


def test_optional_keyword_only_method_is_not_a_false_positive():
    assert _class_mismatches(ITER_FENCE, IterCorrect, "Database") == []


# ── genuine drift must still be caught ───────────────────────────────────

class TriageMissingKwarg:
    def update_finding_triage(self, finding_id: str, *,
                              user_confirmed: bool | None) -> None: ...


class TriageExtraKwarg:
    def update_finding_triage(self, finding_id: str, *,
                              user_confirmed: bool | None,
                              user_notes: str | None,
                              force: bool = False) -> None: ...


class TriagePositionalDrift:
    """The '*' was deleted — name list identical, calling contract widened."""
    def update_finding_triage(self, finding_id, user_confirmed, user_notes) -> None: ...


class TriageDefaultDrift:
    """Mandatory kwargs became optional — violates db.md §2."""
    def update_finding_triage(self, finding_id, *,
                              user_confirmed=None, user_notes=None) -> None: ...


class IterRequiredDrift:
    def iter_persisted_evidence(self, session_id: str, *,
                                source_id: str | None = None,
                                batch_size: int): ...


def test_missing_keyword_only_parameter_is_detected():
    out = _class_mismatches(TRIAGE_FENCE, TriageMissingKwarg, "Database")
    assert any("parameter mismatch" in m for m in out)


def test_extra_keyword_only_parameter_is_detected():
    out = _class_mismatches(TRIAGE_FENCE, TriageExtraKwarg, "Database")
    assert any("parameter mismatch" in m for m in out)


def test_keyword_only_to_positional_drift_is_detected():
    out = _class_mismatches(TRIAGE_FENCE, TriagePositionalDrift, "Database")
    assert any("parameter kind mismatch" in m and "KEYWORD_ONLY" in m for m in out)


def test_mandatory_kwarg_gaining_a_default_is_detected():
    out = _class_mismatches(TRIAGE_FENCE, TriageDefaultDrift, "Database")
    assert sum("parameter default mismatch" in m for m in out) == 2


def test_optional_kwarg_losing_a_default_is_detected():
    out = _class_mismatches(ITER_FENCE, IterRequiredDrift, "Database")
    assert any("parameter default mismatch" in m and "batch_size" in m for m in out)


def test_strict_mode_off_restores_name_only_comparison(monkeypatch):
    monkeypatch.setattr(harness, "STRICT_SIGNATURES", False)
    assert _class_mismatches(TRIAGE_FENCE, TriagePositionalDrift, "Database") == []
    assert any(
        "parameter mismatch" in m
        for m in _class_mismatches(TRIAGE_FENCE, TriageMissingKwarg, "Database")
    )


# ── the remaining four AST buckets ───────────────────────────────────────

VARARGS_FENCE = """
class C:
    def f(self, a, /, b, *args, c=1, **kw) -> None: ...
"""


class VarargsCorrect:
    def f(self, a, /, b, *args, c=1, **kw) -> None: ...


class VarargsDropped:
    def f(self, a, /, b, c=1, **kw) -> None: ...


def test_positional_only_varargs_and_kwargs_match():
    assert _class_mismatches(VARARGS_FENCE, VarargsCorrect, "C") == []


def test_fence_vararg_missing_in_code_is_detected():
    """Revision 1 masked this: both sides collapsed to the same name list."""
    out = _class_mismatches(VARARGS_FENCE, VarargsDropped, "C")
    assert any("parameter mismatch" in m for m in out)


MODULE_KWONLY_FENCE = """
def compute_evidence_hash(*, source_id: str, evidence_type: str,
                          key_path: str | None = None) -> str: ...
"""


def compute_evidence_hash(*, source_id: str, evidence_type: str,
                          key_path: str | None = None) -> str:
    raise NotImplementedError


def test_module_function_keyword_only_matches():
    assert _function_mismatches(MODULE_KWONLY_FENCE, compute_evidence_hash,
                                "compute_evidence_hash") == []


# ── descriptor handling ──────────────────────────────────────────────────

DESCRIPTOR_FENCE = """
class C:
    @classmethod
    def open(cls, db_path: str) -> "C": ...

    @staticmethod
    def helper(value: int) -> int: ...

    @property
    def path(self) -> str: ...
"""


class DescriptorCorrect:
    @classmethod
    def open(cls, db_path: str) -> "DescriptorCorrect":
        raise NotImplementedError

    @staticmethod
    def helper(value: int) -> int:
        raise NotImplementedError

    @property
    def path(self) -> str:
        raise NotImplementedError


class DescriptorDrift:
    def open(self, db_path: str) -> "DescriptorDrift":  # classmethod -> instance
        raise NotImplementedError

    @staticmethod
    def helper(value: int) -> int:
        raise NotImplementedError

    @property
    def path(self) -> str:
        raise NotImplementedError


def test_classmethod_staticmethod_property_match():
    assert _class_mismatches(DESCRIPTOR_FENCE, DescriptorCorrect, "C") == []


def test_classmethod_implemented_as_instance_method_is_detected():
    out = _class_mismatches(DESCRIPTOR_FENCE, DescriptorDrift, "C")
    assert any("descriptor mismatch" in m and "open" in m for m in out)


# ── integration lock against the real sheet and the real module ──────────

def test_db_sheet_incident_methods_produce_no_parameter_mismatches():
    """The two reported failures must never reappear.

    Other db.py mismatches are legitimate and out of scope here; this test
    filters strictly to the two incident methods.
    """
    sheet = harness.CONTRACTS_DIR / "db.md"
    if not sheet.exists():
        pytest.skip(f"Contract sheet not present: {sheet}")

    fence_tree = ast.parse(harness.extract_python_fence(sheet))
    fence_db = next(
        n for n in fence_tree.body
        if isinstance(n, ast.ClassDef) and n.name == "Database"
    )
    module = harness.load_module(sheet)
    source_tree = harness.parse_module_source(module)
    source_db = next(
        n for n in source_tree.body
        if isinstance(n, ast.ClassDef) and n.name == "Database"
    )

    out: list[str] = []
    harness.check_class(module.Database, fence_db, out, source_node=source_db)

    incident = [
        m for m in out
        if "update_finding_triage" in m or "iter_persisted_evidence" in m
    ]
    assert incident == [], "Keyword-only false positives regressed:\n" + "\n".join(incident)