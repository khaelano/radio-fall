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


def test_live_acquisition_is_owned_by_rust():
    """Live apps reach radios only through the native session, never Python serial I/O."""
    live_paths = [
        PACKAGE / "radio" / "live.py",
        *(PACKAGE / "apps").rglob("*.py"),
        *(PACKAGE / "collection").rglob("*.py"),
        *(PACKAGE / "presentation").rglob("*.py"),
    ]
    retired = {
        f"fall_detection.radio.acquisition.{name}"
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
        assert not (PACKAGE / Path(*name.split(".")[1:])).with_suffix(".py").exists()
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
                names = [resolve_name(name, package) if node.level else name]
            if any(
                n == "serial" or n.startswith("serial.") or n in retired for n in names
            ):
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, f"Python live code opens radios directly: {violations}"
