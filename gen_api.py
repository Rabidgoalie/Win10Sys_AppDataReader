import os
import sys
import inspect
from pathlib import Path
import importlib

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

    # Build clean Markdown content (no inherited cruft)
    lines = [f"# API Reference: `{mod_str}`\n"]
    
    for name, obj in inspect.getmembers(mod):
        if inspect.isclass(obj) and getattr(obj, "__module__", "") == mod.__name__:
            lines.append(f"## `class {name}`")
            if obj.__doc__:
                doc_line = obj.__doc__.strip().splitlines()[0]
                lines.append(f"> _{doc_line}_\n")
                
            if hasattr(obj, "__annotations__") and obj.__annotations__:
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
                
        elif inspect.isfunction(obj) and getattr(obj, "__module__", "") == mod.__name__:
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