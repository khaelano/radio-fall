"""Protect the dependency direction between domain code and the applications."""

import ast
from importlib.util import resolve_name
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "fall_detection"


def test_domain_modules_do_not_import_apps():
    """Shared libraries, including ``session``, never import application code."""
    violations = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        if relative.parts[0] == "apps":
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
                for prefix in ("fall_detection.apps",)
            ):
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, f"Domain code imports apps: {violations}"


ALLOWED_DEPENDENCIES = {
    "protocol": set(),
    "radio": set(),
    "session": {"protocol"},
    "collection": {"protocol", "radio", "session"},
    "analysis": {"protocol", "radio", "session"},
    "apps": {"analysis", "collection", "protocol", "radio", "session"},
}
"""Project packages each top-level package may import, besides itself."""

SHARED_MODULES = {"_radio_native"}
"""Top-level project modules every package may import (the Rust extension)."""

_DYNAMIC_IMPORTS = {"import_module", "__import__"}


def _project_packages_imported(path: Path, package: str) -> dict[str, int]:
    """Return the top-level project names ``path`` imports, with a line number.

    Covers ``import`` statements anywhere in the module (including function
    bodies and ``TYPE_CHECKING`` blocks) and ``importlib.import_module`` or
    ``__import__`` calls whose first argument is a string literal.
    """
    found: dict[str, int] = {}
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            name = "." * node.level + (node.module or "")
            base = resolve_name(name, package) if node.level else name
            names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            called = getattr(function, "attr", getattr(function, "id", None))
            argument = node.args[0]
            if (
                called in _DYNAMIC_IMPORTS
                and isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ):
                names = [argument.value]
        for name in names:
            parts = name.split(".")
            if len(parts) > 1 and parts[0] == "fall_detection":
                found.setdefault(parts[1], node.lineno)
    return found


def test_top_level_packages_follow_the_layering():
    """Imports flow one way: protocol and radio are leaves, apps sit on top."""
    top_level = {
        path.name if path.is_dir() else path.stem
        for path in PACKAGE.iterdir()
        if (path.is_dir() and path.name != "__pycache__")
        or (path.suffix == ".py" and path.name != "__init__.py")
    }
    assert top_level == set(ALLOWED_DEPENDENCIES), (
        "Every top-level package or module needs an entry in ALLOWED_DEPENDENCIES"
    )
    violations = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        owner = relative.parts[0]
        if owner not in ALLOWED_DEPENDENCIES:
            continue
        package = ".".join(("fall_detection", *relative.with_suffix("").parts[:-1]))
        for imported, line in _project_packages_imported(path, package).items():
            if imported in SHARED_MODULES or imported == owner:
                continue
            if imported not in ALLOWED_DEPENDENCIES[owner]:
                violations.append(f"{relative}:{line} imports {imported}")
    assert not violations, f"Layering violations: {violations}"


def test_live_acquisition_is_owned_by_rust():
    """Live apps reach radios only through the native session, never Python serial I/O."""
    live_paths = [
        PACKAGE / "radio" / "live.py",
        *(PACKAGE / "apps").rglob("*.py"),
        *(PACKAGE / "collection").rglob("*.py"),
    ]
    retired = {
        f"fall_detection.radio.{name}"
        for name in (
            "gateway_reader",
            "transmitter_reference",
            "clock_sync",
            "gateway_journal",
            "gateway_protocol",
            "packet_reader",
            "usb_buffer",
            "recovery",
        )
    }
    assert not (PACKAGE / "radio" / "acquisition").exists()
    for name in retired:
        module = PACKAGE / Path(*name.split(".")[1:])
        assert not module.with_suffix(".py").exists(), module
        assert not module.exists(), module
    violations = []
    for path in live_paths:
        relative = path.relative_to(PACKAGE)
        package = ".".join(("fall_detection", *relative.with_suffix("").parts[:-1]))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                name = "." * node.level + (node.module or "")
                base = resolve_name(name, package) if node.level else name
                names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            if any(
                n == "serial" or n.startswith("serial.") or n in retired for n in names
            ):
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, f"Python live code opens radios directly: {violations}"


def test_package_inits_define_no_names():
    """Package ``__init__.py`` files hold only a docstring; import from modules.

    Re-exporting names from a package hides which module defines them and lets
    two import paths reach one object. The root package may set ``__version__``.
    """
    violations = []
    for path in sorted(PACKAGE.rglob("__init__.py")):
        relative = path.relative_to(PACKAGE)
        body = ast.parse(path.read_text(encoding="utf-8")).body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
        ):
            body = body[1:]  # the module docstring
        for node in body:
            is_version = (
                relative == Path("__init__.py")
                and isinstance(node, ast.Assign)
                and [getattr(t, "id", None) for t in node.targets] == ["__version__"]
            )
            if not is_version:
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, f"Package __init__.py defines names: {violations}"
