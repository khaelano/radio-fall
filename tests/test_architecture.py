"""Protect the dependency direction between domain code and presentation."""

import ast
from importlib.util import resolve_name
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "fall_detection"


def test_domain_modules_do_not_import_presentation():
    """Shared libraries must remain usable without importing application views."""
    violations = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        if relative.parts[0] in {"apps", "presentation"}:
            continue
        parts = ("fall_detection", *relative.with_suffix("").parts)
        package = ".".join(parts[:-1])
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = "." * node.level + (node.module or "")
                base = resolve_name(name, package) if node.level else name
                names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            if any(
                name == prefix or name.startswith(prefix + ".")
                for name in names
                for prefix in (
                    "fall_detection.apps",
                    "fall_detection.presentation",
                )
            ):
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, f"Domain code imports presentation: {violations}"
