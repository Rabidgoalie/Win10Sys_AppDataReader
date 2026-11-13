"""
Mechanical enforcement of governance Freeze Rule 4:
Implemented modules must match the §1 fence of their FROZEN contract sheets.
"""
import ast
import importlib
import importlib.util
import inspect
import sys
from dataclasses import is_dataclass, fields
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
            if not hasattr(dc_cls, name):
                mismatches.append(f"Dataclass {dc_cls.__name__} missing field/method {name}")
                
    for name in actual_fields:
        if name not in ast_fields:
            mismatches.append(f"Dataclass {dc_cls.__name__} has extra field {name}")


def check_class(cls: type, ast_node: ast.ClassDef, mismatches: list[str],
                source_node: ast.ClassDef | None = None):
    ast_members = get_class_members(ast_node)

    for name, ast_stmt in ast_members.items():
        if name.startswith("_"):
            continue
        if not hasattr(cls, name):
            mismatches.append(f"Class {cls.__name__} missing member {name}")
            continue

        if isinstance(ast_stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            actual_method = getattr(cls, name)
            if isinstance(ast_stmt, ast.AsyncFunctionDef) and not inspect.iscoroutinefunction(actual_method):
                mismatches.append(f"Class {cls.__name__}.{name} is async in fence but not in code")
            ast_args = [arg.arg for arg in ast_stmt.args.args]
            if ast_args and ast_args[0] in ("self", "cls"):
                ast_args = ast_args[1:]

            try:
                sig = inspect.signature(actual_method)
                actual_args = [p.name for p in sig.parameters.values() if p.name not in ("self", "cls")]
                if ast_args != actual_args:
                    mismatches.append(f"Class {cls.__name__}.{name} parameter mismatch: expected {ast_args}, got {actual_args}")
            except (ValueError, TypeError):
                pass

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


def check_function(func: Any, ast_node: ast.FunctionDef, mismatches: list[str]):
    try:
        sig = inspect.signature(func)
        actual_args = [p.name for p in sig.parameters.values()]
        
        # FIX 2: Include keyword-only arguments (and positional-only for completeness)
        posonlyargs = [arg.arg for arg in getattr(ast_node.args, 'posonlyargs', [])]
        args = [arg.arg for arg in ast_node.args.args]
        kwonlyargs = [arg.arg for arg in ast_node.args.kwonlyargs]
        ast_args = posonlyargs + args + kwonlyargs
        
        if ast_args != actual_args:
            mismatches.append(f"Function {func.__name__} parameter mismatch: expected {ast_args}, got {actual_args}")

        if isinstance(ast_node, ast.AsyncFunctionDef) and not inspect.iscoroutinefunction(func):
            mismatches.append(f"Function {func.__name__} is async in fence but not in code")
        
    except (ValueError, TypeError):
        pass


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