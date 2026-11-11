import os
import sys
import inspect
from pathlib import Path
import importlib
import enum

def generate_module_summary(file_path_str: str) -> None:
    path = Path(file_path_str).resolve()
    
    # Ensure we are working inside src/
    try:
        rel_path = path.relative_to(Path("src").resolve())
    except ValueError:
        print(f"Skipped: {path} is not under src/")
        return

    # Calculate target output path in docs/api-ref mirroring src/ structure (.md extension)
    out_path = Path("docs") / "api-ref" / rel_path.with_suffix(".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the full module name including 'src'
    module_parts = ["src"] + list(rel_path.with_suffix("").parts)
    mod_str = ".".join(module_parts)

    # Ensure project root is in sys.path so 'src' can be imported as a package
    project_root = str(Path(__file__).resolve().parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        mod = importlib.import_module(mod_str)
    except Exception as e:
        print(f"Error importing {mod_str}: {e}")
        return

    # Build clean Markdown content
    lines = [f"# API Reference: `{mod_str}`\n"]
    
    # 1. Capture module-level constants, lookup dictionaries, and rule collections
    annotations = getattr(mod, "__annotations__", {})
    constants = []
    for name, obj in inspect.getmembers(mod):
        if name.startswith("_") or name == "annotations":
            continue
        if inspect.ismodule(obj) or inspect.isclass(obj) or inspect.isfunction(obj) or inspect.isbuiltin(obj):
            continue
        annot = annotations.get(name, type(obj).__name__)
        constants.append(f"- `{name}`: `{annot}`")
        
    if constants:
        lines.append("## Constants & Collections\n")
        lines.extend(constants)
        lines.append("")

    # 2. Capture classes and Enums
    for name, obj in inspect.getmembers(mod):
        if inspect.isclass(obj) and getattr(obj, "__module__", "") == mod.__name__:
            lines.append(f"## `class {name}`")
            if obj.__doc__:
                doc_line = obj.__doc__.strip().splitlines()[0]
                lines.append(f"> _{doc_line}_\n")
                
            # Capture Enums (StrEnum, IntEnum, Enum) with their values
            if issubclass(obj, enum.Enum):
                lines.append("**Values:**")
                for member in obj:
                    lines.append(f"- `{member.name}`: `{member.value!r}`")
                lines.append("")
            elif hasattr(obj, "__annotations__") and obj.__annotations__:
                lines.append("**Fields:**")
                for field, ftype in obj.__annotations__.items():
                    ftype_name = getattr(ftype, "__name__", str(ftype))
                    lines.append(f"- `{field}`: `{ftype_name}`")
                lines.append("")
                
            methods = []
            for m_name, m_obj in inspect.getmembers(obj, predicate=inspect.isfunction):
                if m_obj.__qualname__.startswith(f"{name}."):
                    try:
                        sig = inspect.signature(m_obj)
                        methods.append(f"- `def {m_name}{sig}`")
                    except (ValueError, TypeError):
                        pass
            if methods:
                lines.append("**Methods:**")
                lines.extend(methods)
                lines.append("")
                
    # 3. Capture module-level functions
    for name, obj in inspect.getmembers(mod):
        if inspect.isfunction(obj) and getattr(obj, "__module__", "") == mod.__name__:
            try:
                sig = inspect.signature(obj)
                lines.append(f"## `def {name}{sig}`")
                if obj.__doc__:
                    doc_line = obj.__doc__.strip().splitlines()[0]
                    lines.append(f"> _{doc_line}_\n")
            except (ValueError, TypeError):
                pass

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Successfully generated Markdown API ref: {out_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_module_summary(sys.argv[1])
    else:
        print("No file path provided.")