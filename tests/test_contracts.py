"""
Mechanical enforcement of governance Freeze Rule 4:
Implemented modules must match the §1 fence of their FROZEN contract sheets.

Harness revision 2 — 2026-11-17
-------------------------------
Parameter comparison is performed by ONE shared extractor used by both
``check_function`` and ``check_class``.

Revision 1 compared only ``ast.arguments.args`` inside ``check_class``, which
silently dropped every keyword-only parameter declared after a bare ``*`` in
the fence.  Because ``inspect.signature()`` reports keyword-only parameters,
every frozen method with keyword-only arguments produced a FALSE POSITIVE
"parameter mismatch" whose expected list was a strict prefix of the actual
list.  Observed against db.md v1.0.0 §1 for Database.update_finding_triage and
Database.iter_persisted_evidence; both implementations were correct.
``check_function`` had already been patched for this; ``check_class`` had not.
The duplication is now removed so the two paths cannot drift again.

The shared extractor covers all five AST parameter buckets (posonlyargs, args,
vararg, kwonlyargs, kwarg).  In strict mode it additionally compares parameter
KIND and default PRESENCE, so that removing a ``*`` separator — which would
silently widen a keyword-only API to positional — is reported as drift instead
of passing unnoticed.
"""
import ast
import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass, is_dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "docs" / "contracts"
SRC_DIR = REPO_ROOT / "src"

# Ensure src is importable
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Governance knob.
#
# True  → compare parameter NAMES + KINDS + DEFAULT PRESENCE + descriptor kind
#         (staticmethod / classmethod / property) + async parity both ways.
# False → revision-1 semantics (names only), but with the keyword-only bug
#         fixed.  This is a rollback lever, NOT a tuning preference.
#
# Setting this to False weakens Freeze Rule 4 enforcement and MUST be recorded
# as an ADR-17 amendment with coordinator + reviewer sign-off.  A newly
# surfaced kind/default/descriptor mismatch is a real deviation that revision 1
# masked; resolve it by fixing the code or amending the sheet, never by
# flipping this switch.
# ─────────────────────────────────────────────────────────────────────────────
STRICT_SIGNATURES: bool = True


def discover_sheets() -> list[Path]:
    sheets = []
    for md_file in CONTRACTS_DIR.rglob("*.md"):
        if md_file.name == "README.md":
            continue
        # Skip cross-cutting sheets that don't mirror a src/ module
        rel_path = md_file.relative_to(CONTRACTS_DIR)
        py_path = SRC_DIR / rel_path.with_suffix(".py")
        if py_path.exists():
            sheets.append(md_file)
    return sheets


def parse_sheet_status(sheet_path: Path) -> tuple[str, str]:
    """Returns (status, version) from the first header line."""
    with sheet_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("# Module Contract:"):
                parts = line.split("—")
                if len(parts) >= 2:
                    right = parts[1].strip()
                    tokens = right.split()
                    version = tokens[0] if tokens else "unknown"
                    status = "FROZEN" if "FROZEN" in right else "DRAFT"
                    return status, version
    return "DRAFT", "unknown"


def parse_module_source(module: Any) -> ast.Module | None:
    """Parse the module's actual source file.

    Source AST (not dir()/getmembers()) is used deliberately: it separates
    names the module defines from names it imports, and excludes members
    synthesized at runtime (e.g. @dataclass dunders), so Tier 2 surface can
    never be mistaken for declared API surface.
    """
    file_path = getattr(module, "__file__", None)
    if not file_path:
        return None
    return ast.parse(Path(file_path).read_text(encoding="utf-8"))


def extract_python_fence(sheet_path: Path) -> str:
    """Extracts the first ```python fence inside the section headed ## 1."""
    with sheet_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    in_section_1 = False
    in_fence = False
    fence_lines = []

    for line in lines:
        if line.startswith("## 1."):
            in_section_1 = True
            continue
        if in_section_1 and line.startswith("## "):
            break

        if in_section_1:
            if line.strip().startswith("```python"):
                in_fence = True
                continue
            if in_fence:
                if line.strip().startswith("```"):
                    break
                fence_lines.append(line)

    return "".join(fence_lines)


def load_module(sheet_path: Path) -> Any:
    rel_path = sheet_path.relative_to(CONTRACTS_DIR)
    module_name = str(rel_path.with_suffix("")).replace("/", ".").replace("\\", ".")
    dotted_path = f"src.{module_name}"

    try:
        return importlib.import_module(dotted_path)
    except ImportError:
        py_path = SRC_DIR / rel_path.with_suffix(".py")
        spec = importlib.util.spec_from_file_location(dotted_path, py_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[dotted_path] = module
        spec.loader.exec_module(module)
        return module


def get_ast_names(tree: ast.Module) -> dict[str, ast.AST]:
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names[node.target.id] = node
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names[node.name] = node
    return names


def get_class_members(node: ast.ClassDef) -> dict[str, ast.AST]:
    members = {}
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            members[stmt.target.id] = stmt
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            members[stmt.name] = stmt
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    members[target.id] = stmt
    return members


# ─────────────────────────────────────────────────────────────────────────────
# Shared parameter model — single source of truth for BOTH check_class and
# check_function.  Revision 1's duplicated extractors are the root cause of the
# keyword-only false positives; do not re-fork this logic.
# ─────────────────────────────────────────────────────────────────────────────

_POSITIONAL_KINDS = frozenset({"POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"})
_RECEIVER_NAMES = frozenset({"self", "cls"})
_DESCRIPTOR_DECORATORS = ("staticmethod", "classmethod", "property")


@dataclass(frozen=True)
class _Param:
    """One declared parameter, normalized across AST and runtime views."""
    name: str
    kind: str          # inspect._ParameterKind.name
    has_default: bool


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _fence_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Param]:
    """Flatten ALL five AST parameter buckets into declaration order.

    ``ast.arguments.args`` holds only positional-or-keyword parameters.
    Everything after a bare ``*`` lives in ``kwonlyargs``; everything before
    ``/`` lives in ``posonlyargs``.  Reading ``args`` alone (revision 1) is the
    defect this function exists to prevent.

    ``defaults`` aligns to the TAIL of ``posonlyargs + args``.
    ``kw_defaults`` aligns 1:1 with ``kwonlyargs`` and uses None for 'required'.
    """
    a = node.args
    posonly = list(a.posonlyargs)
    positional = posonly + list(a.args)
    first_defaulted = len(positional) - len(a.defaults)

    out: list[_Param] = []
    for idx, arg in enumerate(positional):
        kind = "POSITIONAL_ONLY" if idx < len(posonly) else "POSITIONAL_OR_KEYWORD"
        out.append(_Param(arg.arg, kind, idx >= first_defaulted))
    if a.vararg is not None:
        out.append(_Param(a.vararg.arg, "VAR_POSITIONAL", False))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults, strict=True):
        out.append(_Param(arg.arg, "KEYWORD_ONLY", default is not None))
    if a.kwarg is not None:
        out.append(_Param(a.kwarg.arg, "VAR_KEYWORD", False))
    return out


def _runtime_params(obj: Any) -> list[_Param]:
    """Mirror of _fence_params for a live callable (may raise for builtins)."""
    sig = inspect.signature(obj)
    return [
        _Param(p.name, p.kind.name, p.default is not inspect.Parameter.empty)
        for p in sig.parameters.values()
    ]


def _strip_receiver(params: list[_Param]) -> list[_Param]:
    """Drop a leading self/cls POSITIONALLY, not by name-filtering every slot.

    Revision 1 removed every parameter literally named 'self' or 'cls',
    which would silently swallow a legitimately named argument.
    """
    if params and params[0].name in _RECEIVER_NAMES and params[0].kind in _POSITIONAL_KINDS:
        return params[1:]
    return params


def _compare_params(
    label: str,
    fence_params: list[_Param],
    actual_params: list[_Param],
    mismatches: list[str],
) -> None:
    fence_names = [p.name for p in fence_params]
    actual_names = [p.name for p in actual_params]
    if fence_names != actual_names:
        mismatches.append(
            f"{label} parameter mismatch: expected {fence_names}, got {actual_names}"
        )
        return  # avoid cascading kind/default noise on a renamed/missing param

    if not STRICT_SIGNATURES:
        return

    for fp, ap in zip(fence_params, actual_params, strict=True):
        if fp.kind != ap.kind:
            mismatches.append(
                f"{label} parameter kind mismatch for {fp.name!r}: "
                f"fence declares {fp.kind}, code declares {ap.kind}"
            )
        if fp.has_default != ap.has_default:
            fence_side = "declares a default" if fp.has_default else "requires the argument"
            code_side = "declares a default" if ap.has_default else "requires the argument"
            mismatches.append(
                f"{label} parameter default mismatch for {fp.name!r}: "
                f"fence {fence_side}, code {code_side}"
            )


def _check_method(
    cls: type,
    name: str,
    fence_node: ast.FunctionDef | ast.AsyncFunctionDef,
    mismatches: list[str],
) -> None:
    """Signature comparison for one class member declared as a def in the fence.

    ``inspect.getattr_static`` avoids invoking descriptors and lets us unwrap
    staticmethod/classmethod/property explicitly, so receiver stripping is
    driven by the actual descriptor kind rather than by parameter spelling.
    Non-inspectable members (builtins, exotic descriptors) are skipped exactly
    as revision 1 skipped them; missing members are reported by check_class.
    """
    label = f"Class {cls.__name__}.{name}"
    raw = inspect.getattr_static(cls, name, None)
    if raw is None:
        return  # annotation-only declaration; nothing to introspect

    if isinstance(raw, staticmethod):
        target, strip_runtime, runtime_descriptor = raw.__func__, False, "staticmethod"
    elif isinstance(raw, classmethod):
        target, strip_runtime, runtime_descriptor = raw.__func__, True, "classmethod"
    elif isinstance(raw, property):
        if raw.fget is None:
            return
        target, strip_runtime, runtime_descriptor = raw.fget, True, "property"
    elif inspect.isfunction(raw):
        target, strip_runtime, runtime_descriptor = raw, True, None
    else:
        return  # not a plain function/descriptor we can compare

    fence_decorators = _decorator_names(fence_node)

    if isinstance(fence_node, ast.AsyncFunctionDef) and not inspect.iscoroutinefunction(target):
        mismatches.append(f"{label} is async in fence but not in code")

    if STRICT_SIGNATURES:
        if isinstance(fence_node, ast.FunctionDef) and inspect.iscoroutinefunction(target):
            mismatches.append(f"{label} is sync in fence but async in code")
        fence_descriptor = next(
            (d for d in _DESCRIPTOR_DECORATORS if d in fence_decorators), None
        )
        if fence_descriptor != runtime_descriptor:
            mismatches.append(
                f"{label} descriptor mismatch: fence declares "
                f"{fence_descriptor or 'plain method'}, code declares "
                f"{runtime_descriptor or 'plain method'}"
            )

    fence_params = _fence_params(fence_node)
    if "staticmethod" not in fence_decorators:
        fence_params = _strip_receiver(fence_params)

    try:
        actual_params = _runtime_params(target)
    except (ValueError, TypeError):
        return  # non-inspectable callable — preserve revision-1 behaviour

    if strip_runtime:
        actual_params = _strip_receiver(actual_params)

    _compare_params(label, fence_params, actual_params, mismatches)


def check_enum(enum_cls: type, ast_node: ast.ClassDef, mismatches: list[str]):
    ast_members = get_class_members(ast_node)
    actual_members = {m.name: m.value for m in enum_cls}

    for name, ast_stmt in ast_members.items():
        if name.startswith("_"):
            continue
        if name not in actual_members:
            mismatches.append(f"Enum {enum_cls.__name__} missing member {name}")
            continue

        if isinstance(ast_stmt, ast.Assign) and isinstance(ast_stmt.value, ast.Constant):
            if actual_members[name] != ast_stmt.value.value:
                mismatches.append(f"Enum {enum_cls.__name__}.{name} value mismatch: expected {ast_stmt.value.value!r}, got {actual_members[name]!r}")

    for name in actual_members:
        if name not in ast_members and not name.startswith("_"):
            mismatches.append(f"Enum {enum_cls.__name__} has extra member {name}")


def check_dataclass(dc_cls: type, ast_node: ast.ClassDef, mismatches: list[str]):
    if not is_dataclass(dc_cls):
        mismatches.append(f"{dc_cls.__name__} is a dataclass in stub but not in code")
        return

    ast_fields = get_class_members(ast_node)

    # FIX 1: Exclude inherited dataclass fields from the "exact set" check
    # for this specific class so subclasses aren't flagged for base fields.
    inherited_fields = set()
    for base in dc_cls.__mro__[1:]:
        if is_dataclass(base):
            inherited_fields.update(f.name for f in fields(base))

    actual_fields = {f.name for f in fields(dc_cls) if f.name not in inherited_fields}

    for name in ast_fields:
        if name.startswith("_"):
            continue
        if isinstance(ast_fields[name], (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if name not in actual_fields:
            if not has_member(dc_cls, name):
                mismatches.append(f"Dataclass {dc_cls.__name__} missing field/method {name}")

    for name in actual_fields:
        if name not in ast_fields:
            mismatches.append(f"Dataclass {dc_cls.__name__} has extra field {name}")


def has_member(cls: type, member_name: str) -> bool:
    """Check whether a class exposes a member, covering both runtime
    attributes AND annotation-only declarations (Protocols, TypedDicts,
    slotted dataclass fields without defaults, ABCs with bare annotations).

    Standard hasattr() misses annotation-only members because Python stores
    them in __annotations__ without creating a class-level attribute.
    """
    # 1. Standard runtime attributes, methods, descriptors, slots (including inherited).
    if hasattr(cls, member_name):
        return True

    # 2. Annotation-only declarations across the full MRO.
    for base in cls.__mro__:
        if member_name in getattr(base, "__annotations__", {}):
            return True

    return False


def check_class(cls: type, ast_node: ast.ClassDef, mismatches: list[str],
                source_node: ast.ClassDef | None = None):
    ast_members = get_class_members(ast_node)

    for name, ast_stmt in ast_members.items():
        if name.startswith("_"):
            continue
        if not has_member(cls, name):
            mismatches.append(f"Class {cls.__name__} missing member {name}")
            continue

        if isinstance(ast_stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_method(cls, name, ast_stmt, mismatches)

    # Reverse direction (code ⊆ sheet): every public member defined in the
    # class body must be declared in the fence. The source AST excludes
    # inherited members and dataclass-synthesized dunders by construction.
    if source_node is not None:
        source_members = get_class_members(source_node)
        dc_field_names = {f.name for f in fields(cls)} if is_dataclass(cls) else set()
        for name in source_members:
            if name.startswith("_") or name in ast_members:
                continue
            if name in dc_field_names:
                continue  # already reported by check_dataclass if undeclared
            mismatches.append(
                f"Class {cls.__name__} defines public member '{name}' absent from contract fence"
            )


def check_function(func: Any, ast_node: ast.FunctionDef | ast.AsyncFunctionDef,
                   mismatches: list[str]):
    label = f"Function {func.__name__}"

    if isinstance(ast_node, ast.AsyncFunctionDef) and not inspect.iscoroutinefunction(func):
        mismatches.append(f"{label} is async in fence but not in code")
    if STRICT_SIGNATURES and isinstance(ast_node, ast.FunctionDef) and inspect.iscoroutinefunction(func):
        mismatches.append(f"{label} is sync in fence but async in code")

    try:
        actual_params = _runtime_params(func)
    except (ValueError, TypeError):
        return

    _compare_params(label, _fence_params(ast_node), actual_params, mismatches)


@pytest.mark.parametrize("sheet_path", discover_sheets(), ids=lambda p: str(p.relative_to(CONTRACTS_DIR)))
def test_contract_sheet(sheet_path: Path):
    status, version = parse_sheet_status(sheet_path)
    if status != "FROZEN":
        pytest.skip(f"Sheet is {status} (v{version})")

    code = extract_python_fence(sheet_path)
    if not code.strip():
        pytest.fail("No python fence found in section 1")

    tree = ast.parse(code)
    ast_names = get_ast_names(tree)

    module = load_module(sheet_path)
    source_tree = parse_module_source(module)
    source_names = get_ast_names(source_tree) if source_tree is not None else {}
    mismatches = []

    for name, ast_node in ast_names.items():
        if not hasattr(module, name):
            mismatches.append(f"Module missing symbol {name}")
            continue

        actual = getattr(module, name)

        if isinstance(ast_node, ast.ClassDef):
            src_node = source_names.get(name)
            src_node = src_node if isinstance(src_node, ast.ClassDef) else None
            bases = [b.id for b in ast_node.bases if isinstance(b, ast.Name)]
            if "StrEnum" in bases or "Enum" in bases:
                if not issubclass(actual, Enum):
                    mismatches.append(f"{name} is an Enum in stub but not in code")
                else:
                    check_enum(actual, ast_node, mismatches)
            elif is_dataclass(actual):
                check_dataclass(actual, ast_node, mismatches)
                check_class(actual, ast_node, mismatches, source_node=src_node)
            else:
                check_class(actual, ast_node, mismatches, source_node=src_node)

        elif isinstance(ast_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            check_function(actual, ast_node, mismatches)

    # Reverse direction (code ⊆ sheet): every public symbol defined by the
    # module must be declared in the fence. get_ast_names captures only
    # Assign/AnnAssign/ClassDef/FunctionDef nodes, so imports are excluded
    # by construction.
    for name in source_names:
        if name.startswith("_") or name in ast_names:
            continue
        mismatches.append(
            f"Module defines public symbol '{name}' absent from contract fence (undeclared surface — requires amendment)"
        )

    if mismatches:
        pytest.fail("Contract mismatches:\n" + "\n".join(mismatches))