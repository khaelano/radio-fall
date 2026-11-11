#!/usr/bin/env python3
"""Convert Pandoc Markdown to ODT with live Zotero citation fields.

Usage:
    python3 tools/thesis/build_draft_odt.py draft/pendahuluan.md -o draft/pendahuluan.odt

Requires Pandoc >= 2.16.2 and running Zotero with Better BibTeX. Install the
Zotero LibreOffice integration to edit the resulting fields. On first opening,
choose Zotero > Document Preferences > OK, then Refresh. Bibliography and
citation formatting are completed by Zotero in LibreOffice.

Input must contain real Pandoc citations, e.g. [@citationKey]. Paper hyperlinks
alone are not citations. Narrative citations should use an explicit author name
followed by [@citationKey] (or [-@citationKey] to suppress the author).

The official, self-contained MIT-licensed filter is downloaded at conversion
time and checksum-verified; no Python packages beyond the standard library are
needed. Use --filter for a locally maintained copy instead.
Source: https://retorque.re/zotero-better-bibtex/exporting/pandoc/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Iterator

FILTER_URL = "https://retorque.re/zotero-better-bibtex/exporting/zotero.lua"
FILTER_SHA256 = "a9ccec3de37954ad3b66c67c2d05e41a4c7ad3a99a4cfd99e184cebb822faf02"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def download_filter() -> bytes:
    """Download the official standalone Better BibTeX filter."""
    # The download host rejects urllib's default Python user agent with HTTP 403.
    request = urllib.request.Request(
        FILTER_URL, headers={"User-Agent": "radio-fall-detection-odt/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.URLError as error:
        raise ValueError(
            f"Unduhan filter Better BibTeX gagal ({FILTER_URL}): {error}. "
            "Gunakan --filter /lokasi/zotero.lua jika memiliki salinan lokal."
        ) from error


def citations(node: Any) -> Iterator[list[dict[str, Any]]]:
    """Yield citation clusters from the parsed Pandoc document, excluding code."""
    if isinstance(node, dict):
        if node.get("t") == "Cite":
            yield node["c"][0]
        else:
            for value in node.values():
                yield from citations(value)
    elif isinstance(node, list):
        for value in node:
            yield from citations(value)


def ensure_bibliography(document: dict[str, Any]) -> None:
    """Provide the explicit refs Div supported by the Better BibTeX filter."""

    def has_refs(node: Any) -> bool:
        if isinstance(node, dict):
            if node.get("t") == "Div" and node["c"][0][0] == "refs":
                return True
            return any(has_refs(value) for value in node.values())
        if isinstance(node, list):
            return any(has_refs(value) for value in node)
        return False

    # This filter version's automatic insertion uses a Doc hook, which Pandoc
    # 3.7 does not invoke. Its explicit Div handler works across these versions.
    if not has_refs(document["blocks"]):
        document["blocks"].append({"t": "Div", "c": [["refs", [], []], []]})


def verify_fields(path: Path, expected_sizes: list[int]) -> None:
    """Reject partial conversion, unlinked citation fields, or no bibliography."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    sizes = []
    for mark in root.iter(f"{{{TEXT_NS}}}reference-mark-start"):
        name = mark.get(f"{{{TEXT_NS}}}name", "")
        prefix = "ZOTERO_ITEM CSL_CITATION "
        if not name.startswith(prefix):
            continue
        payload, _ = json.JSONDecoder().raw_decode(name[len(prefix) :])
        items = payload.get("citationItems", [])
        if not items or any(not item.get("uris") for item in items):
            raise ValueError("Field sitasi tidak terhubung ke item Zotero.")
        sizes.append(len(items))
    if sizes != expected_sizes:
        raise ValueError(
            "Sebagian sitasi gagal menjadi field Zotero. Periksa citation key "
            "yang hilang/duplikat dan pesan filter di atas. Output tidak disimpan."
        )
    if "ZOTERO_BIBL" not in ET.tostring(root, encoding="unicode"):
        raise ValueError("Field daftar pustaka Zotero tidak ditemukan.")


def build(args: argparse.Namespace) -> None:
    """Build in a temporary directory and publish only after field validation."""
    if shutil.which("pandoc") is None:
        raise ValueError("Pandoc tidak ditemukan di PATH.")
    version = subprocess.check_output(["pandoc", "--version"], text=True)
    match = re.search(r"pandoc (\d+)\.(\d+)(?:\.(\d+))?", version)
    if not match or tuple(int(n or 0) for n in match.groups()) < (2, 16, 2):
        raise ValueError("Gunakan Pandoc versi 2.16.2 atau lebih baru.")
    inputs = [path.expanduser().resolve(strict=True) for path in args.inputs]
    output = args.output.expanduser().resolve()
    if output.suffix.lower() != ".odt":
        raise ValueError("Nama output harus berakhiran .odt.")
    if output.exists() and not args.force:
        raise ValueError("Output sudah ada; gunakan --force untuk menimpanya.")
    ast = json.loads(
        subprocess.check_output(
            ["pandoc", "--from=markdown+citations", "--to=json", *map(str, inputs)],
            text=True,
        )
    )
    clusters = list(citations(ast))
    if not clusters:
        raise ValueError(
            "Tidak ada sitasi Pandoc. Gunakan [@citationKey], bukan tautan paper."
        )
    if any(
        item["citationMode"]["t"] == "AuthorInText"
        for cluster in clusters
        for item in cluster
    ):
        raise ValueError(
            "Sitasi naratif @key tidak didukung sebagai field aktif oleh filter. "
            "Tulis nama penulis secara eksplisit, diikuti [@key] atau [-@key]."
        )
    # Override source metadata so it cannot silently select plain/scannable cites.
    config = {
        "client": "zotero",
        "scannable-cite": False,
        "transferable": False,
        "csl-style": args.style,
        "author-in-text": False,
    }
    if args.library:
        config["library"] = args.library
    ast["meta"]["zotero"] = {
        "t": "MetaMap",
        "c": {
            key: {
                "t": "MetaBool" if isinstance(value, bool) else "MetaString",
                "c": value,
            }
            for key, value in config.items()
        },
    }
    for key in list(ast["meta"]):
        if key.startswith("zotero_"):
            del ast["meta"][key]
    ensure_bibliography(ast)
    with urllib.request.urlopen(
        "http://127.0.0.1:23119/better-bibtex/cayw?probe=true", timeout=10
    ) as response:
        if response.read().decode().strip() != "ready":
            raise ValueError("Buka Zotero dan pastikan Better BibTeX aktif.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".odt-build-", dir=output.parent) as temp:
        work = Path(temp)
        if args.filter:
            lua_filter = args.filter.expanduser().resolve(strict=True)
        else:
            data = download_filter()
            if hashlib.sha256(data).hexdigest() != FILTER_SHA256:
                raise ValueError(
                    "Versi filter resmi berubah. Tinjau versi baru, lalu gunakan "
                    "--filter /lokasi/zotero.lua atau perbarui checksum skrip."
                )
            lua_filter = work / "zotero.lua"
            lua_filter.write_bytes(data)
        staged = work / "document.odt"
        command = [
            "pandoc",
            "--from=json",
            "--to=odt",
            "--standalone",
            f"--lua-filter={lua_filter}",
            f"--output={staged}",
        ]
        directories = dict.fromkeys(path.parent for path in inputs)
        command.append("--resource-path=" + os.pathsep.join(map(str, directories)))
        if args.reference_odt:
            command.append(f"--reference-doc={args.reference_odt.resolve(strict=True)}")
        # Do not add --citeproc: Zotero must retain ownership of live fields.
        subprocess.run(command, input=json.dumps(ast), text=True, check=True)
        verify_fields(staged, [len(cluster) for cluster in clusters])
        if output.exists() and not args.force:
            raise ValueError("Output dibuat proses lain; tidak ditimpa.")
        staged.replace(output)
    print(f"ODT dibuat: {output} ({len(clusters)} kelompok sitasi aktif).")
    print("Di LibreOffice: Zotero > Document Preferences > OK, lalu Refresh.")


def main() -> int:
    """Parse command-line options and report actionable build errors."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "inputs", nargs="+", type=Path, help="Markdown dengan [@citationKey]."
    )
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument(
        "--style", default="harvard-cite-them-right", help="ID style Zotero."
    )
    parser.add_argument(
        "--library", help="Nama group library; default library pribadi."
    )
    parser.add_argument(
        "--filter", type=Path, help="Filter zotero.lua mandiri dari Better BibTeX."
    )
    parser.add_argument(
        "--reference-odt", type=Path, help="Template format ODT opsional."
    )
    parser.add_argument("--force", action="store_true", help="Izinkan menimpa output.")
    args = parser.parse_args()
    try:
        build(args)
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
        ET.ParseError,
    ) as error:
        print(f"Gagal: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
