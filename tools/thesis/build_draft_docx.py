#!/usr/bin/env python3
"""Build a polished DOCX from the research chapter drafts with rendered citations."""

from __future__ import annotations

import json
import argparse
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Twips


ROOT = Path(__file__).resolve().parents[2]
DRAFT_DIR = ROOT / "draft"
DEFAULT_INPUTS = (
    DRAFT_DIR / "pendahuluan.md",
    DRAFT_DIR / "landasan-kepustakaan.md",
    DRAFT_DIR / "metodologi-penelitian.md",
)
DEFAULT_OUTPUT = DRAFT_DIR / "naskah-bab-1-3.docx"
DEFAULT_ZOTERO_DIR = Path.home() / "Zotero"
DEFAULT_ZOTERO_DB = DEFAULT_ZOTERO_DIR / "zotero.sqlite"
DEFAULT_CSL_FILE = DEFAULT_ZOTERO_DIR / "styles" / "harvard-cite-them-right.csl"
RENDERER = Path(
    "/home/khaelano/.codex/plugins/cache/openai-primary-runtime/documents/"
    "26.826.12353/skills/documents/render_docx.py"
)
PYTHON = Path(
    "/home/khaelano/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)

CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120
CELL_MARGINS_DXA = {"top": 80, "bottom": 80, "start": 120, "end": 120}

NAVY = "203748"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
MUTED = "666666"
TABLE_FILL = "E8EEF5"
TABLE_BORDER = "B7C5D3"


def set_run_font(
    run,
    *,
    name: str = "Calibri",
    size: float | None = None,
    color: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    run.font.name = name
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:ascii"), name)
    r_fonts.set(qn("w:hAnsi"), name)
    r_fonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_style_font(style, *, name: str = "Calibri", size: float = 11, color: str = "000000") -> None:
    style.font.name = name
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor.from_string(color)
    r_pr = style._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:ascii"), name)
    r_fonts.set(qn("w:hAnsi"), name)
    r_fonts.set(qn("w:eastAsia"), name)


def set_paragraph_spacing(style, *, before: float = 0, after: float = 8, line: float = 1.333) -> None:
    fmt = style.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line


def set_keep_with_next(style, value: bool = True) -> None:
    p_pr = style._element.get_or_add_pPr()
    keep = p_pr.find(qn("w:keepNext"))
    if value and keep is None:
        p_pr.append(OxmlElement("w:keepNext"))
    elif not value and keep is not None:
        p_pr.remove(keep)


def remove_paragraph_borders(style) -> None:
    p_pr = style._element.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is not None:
        p_pr.remove(borders)


def set_page_geometry(section) -> None:
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)
    shd.set(qn("w:val"), "clear")


def set_cell_margins(cell, margins: dict[str, int]) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side in ("top", "bottom", "start", "end"):
        node = tc_mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(margins[side]))
        node.set(qn("w:type"), "dxa")


def apply_table_geometry(table, widths: list[int]) -> None:
    if sum(widths) != CONTENT_WIDTH_DXA:
        raise ValueError(f"Table widths must sum to {CONTENT_WIDTH_DXA}: {widths}")
    table.autofit = False
    table.alignment = 0
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:type"), "dxa")
    tbl_w.set(qn("w:w"), str(CONTENT_WIDTH_DXA))
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:type"), "dxa")
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    grid = tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for col_idx, width in enumerate(widths):
        table.columns[col_idx].width = Twips(width)
    for row in table.rows:
        row.height = None
        for col_idx, cell in enumerate(row.cells):
            cell.width = Twips(widths[col_idx])
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:type"), "dxa")
            tc_w.set(qn("w:w"), str(widths[col_idx]))
            set_cell_margins(cell, CELL_MARGINS_DXA)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def mark_header_row(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tr_pr.append(tbl_header)
    tbl_header.set(qn("w:val"), "true")


def set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), TABLE_BORDER)


def configure_template() -> Document:
    doc = Document()
    section = doc.sections[0]
    set_page_geometry(section)

    styles = doc.styles
    normal = styles["Normal"]
    set_style_font(normal, size=11)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(normal, after=8, line=1.333)

    for style_name in ("Body Text", "First Paragraph"):
        if style_name in styles:
            style = styles[style_name]
            set_style_font(style, size=11)
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            set_paragraph_spacing(style, after=8, line=1.333)

    title = styles["Title"]
    set_style_font(title, size=30, color=NAVY)
    title.font.bold = True
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(72)
    title.paragraph_format.space_after = Pt(8)
    title.paragraph_format.keep_with_next = True
    remove_paragraph_borders(title)

    subtitle = styles["Subtitle"]
    set_style_font(subtitle, size=15, color="2B5163")
    subtitle.font.italic = False
    subtitle.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(24)
    subtitle.paragraph_format.keep_with_next = True

    heading_tokens = {
        "Heading 1": (16, BLUE, 18, 10),
        "Heading 2": (13, BLUE, 12, 6),
        "Heading 3": (12, DARK_BLUE, 8, 4),
    }
    for name, (size, color, before, after) in heading_tokens.items():
        style = styles[name]
        set_style_font(style, size=size, color=color)
        style.font.bold = True
        set_paragraph_spacing(style, before=before, after=after, line=1.15)
        set_keep_with_next(style)

    for name in ("List Paragraph", "List Bullet", "List Number"):
        if name in styles:
            style = styles[name]
            set_style_font(style, size=11)
            style.paragraph_format.left_indent = Inches(0.375)
            style.paragraph_format.first_line_indent = Inches(-0.194)
            style.paragraph_format.space_after = Pt(4)
            style.paragraph_format.line_spacing = 1.208

    # Pandoc uses this paragraph style inside table cells. Defining it in the
    # reference document prevents LibreOffice from falling back to a broken
    # inherited layout when a wide table spans pages.
    if "Compact" not in styles:
        compact = styles.add_style("Compact", WD_STYLE_TYPE.PARAGRAPH)
    else:
        compact = styles["Compact"]
    set_style_font(compact, size=9.2)
    compact.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    compact.paragraph_format.space_before = Pt(0)
    compact.paragraph_format.space_after = Pt(2)
    compact.paragraph_format.line_spacing = 1.05

    if "Caption" in styles:
        caption = styles["Caption"]
        set_style_font(caption, size=10.5, color=MUTED)
        caption.font.italic = True
        caption.paragraph_format.space_before = Pt(4)
        caption.paragraph_format.space_after = Pt(6)

    if "Bibliography" not in styles:
        bibliography = styles.add_style("Bibliography", WD_STYLE_TYPE.PARAGRAPH)
    else:
        bibliography = styles["Bibliography"]
    set_style_font(bibliography, size=9.5)
    bibliography.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    bibliography.paragraph_format.left_indent = Inches(0.25)
    bibliography.paragraph_format.first_line_indent = Inches(-0.25)
    bibliography.paragraph_format.space_after = Pt(4)
    bibliography.paragraph_format.line_spacing = 1.05

    # Quiet running furniture for a multi-page research document.
    header = section.header
    header_p = header.paragraphs[0]
    header_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_p.paragraph_format.space_after = Pt(0)
    header_p.paragraph_format.line_spacing = 1
    header_run = header_p.add_run("Draf Bab 1–3  |  Deteksi Jatuh Berbasis Radar Doppler")
    set_run_font(header_run, size=8.5, color=MUTED)

    footer = section.footer
    footer_p = footer.paragraphs[0]
    footer_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer_p.paragraph_format.space_before = Pt(0)
    footer_p.paragraph_format.space_after = Pt(0)
    footer_p.paragraph_format.line_spacing = 1
    footer_run = footer_p.add_run("Halaman ")
    set_run_font(footer_run, size=8.5, color=MUTED)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    footer_run._r.extend([begin, instr, separate, text, end])
    return doc


def field_map(con: sqlite3.Connection, item_id: int) -> dict[str, str]:
    return dict(
        con.execute(
            """
            SELECT f.fieldName, v.value
            FROM itemData AS d
            JOIN fieldsCombined AS f ON f.fieldID = d.fieldID
            JOIN itemDataValues AS v ON v.valueID = d.valueID
            WHERE d.itemID = ?
            """,
            (item_id,),
        ).fetchall()
    )


def cited_keys(markdown: str) -> list[str]:
    """Return citation keys used by Pandoc citation syntax in Markdown.

    The negative lookbehind prevents email addresses and ordinary @mentions
    from being interpreted as citations. It still supports Pandoc's narrative
    form (``@key``) and bracketed form (``[@key; @other]``).
    """
    keys = sorted(set(re.findall(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_:-]*)", markdown)))
    return keys


def export_csl_json(keys: list[str], destination: Path, zotero_db: Path) -> None:
    """Export only cited Zotero items as CSL-JSON and fail on missing keys."""
    if not zotero_db.exists():
        raise FileNotFoundError(
            f"Database Zotero tidak ditemukan: {zotero_db}. "
            "Gunakan --zotero-db untuk menentukan lokasi lain."
        )
    db_uri = f"file:{zotero_db}?mode=ro&immutable=1"
    con = sqlite3.connect(db_uri, uri=True)
    citation_key_field = con.execute(
        "SELECT fieldID FROM fieldsCombined WHERE fieldName = 'citationKey'"
    ).fetchone()
    if citation_key_field is None:
        raise RuntimeError(
            "Field citationKey tidak tersedia di database Zotero. "
            "Pastikan Better BibTeX terpasang dan citation key telah dibuat."
        )
    citation_key_field_id = citation_key_field[0]
    key_rows = dict(
        con.execute(
            """
            SELECT v.value, d.itemID
            FROM itemData AS d
            JOIN itemDataValues AS v ON v.valueID = d.valueID
            WHERE d.fieldID = ?
            """,
            (citation_key_field_id,),
        ).fetchall()
    )
    type_rows = dict(con.execute("SELECT itemTypeID, typeName FROM itemTypesCombined"))
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for key in keys:
        item_id = key_rows.get(key)
        if item_id is None:
            missing.append(key)
            continue
        values = field_map(con, item_id)
        item_type = type_rows.get(
            con.execute("SELECT itemTypeID FROM items WHERE itemID = ?", (item_id,)).fetchone()[0],
            "journalArticle",
        )
        creator_rows = con.execute(
            """
            SELECT c.firstName, c.lastName, c.fieldMode
            FROM itemCreators AS ic
            JOIN creators AS c ON c.creatorID = ic.creatorID
            JOIN creatorTypes AS ct ON ct.creatorTypeID = ic.creatorTypeID
            WHERE ic.itemID = ? AND ct.creatorType = 'author'
            ORDER BY ic.orderIndex
            """,
            (item_id,),
        ).fetchall()
        authors = []
        for first_name, last_name, field_mode in creator_rows:
            if field_mode or not last_name:
                authors.append({"literal": first_name or last_name})
            else:
                authors.append({"family": last_name, "given": first_name})
        entry: dict[str, Any] = {
            "id": key,
            "type": {
                "journalArticle": "article-journal",
                "conferencePaper": "paper-conference",
                "webpage": "webpage",
                "report": "report",
                "book": "book",
                "thesis": "thesis",
            }.get(item_type, "article-journal"),
            "title": values.get("title", key),
        }
        if authors:
            entry["author"] = authors
        date_value = values.get("date", "")
        year_match = re.search(r"(\d{4})", date_value)
        if year_match:
            entry["issued"] = {"date-parts": [[int(year_match.group(1))]]}
        venue = values.get("publicationTitle") or values.get("proceedingsTitle") or values.get("conferenceName")
        if venue:
            entry["container-title"] = venue
        for source_field, csl_field in (
            ("volume", "volume"),
            ("issue", "issue"),
            ("pages", "page"),
            ("DOI", "DOI"),
            ("url", "URL"),
            ("publisher", "publisher"),
        ):
            value = values.get(source_field)
            if value:
                entry[csl_field] = value
        entries.append(entry)
    con.close()
    if missing:
        raise RuntimeError(f"Citation key tidak ditemukan di Zotero: {', '.join(missing)}")
    destination.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def make_combined_markdown(
    destination: Path,
    chapter_files: list[Path],
    *,
    title: str,
    subtitle: str,
    chapter_breaks: bool,
) -> str:
    chunks = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"subtitle: {json.dumps(subtitle, ensure_ascii=False)}",
        "lang: id-ID",
        "reference-section-title: \"Daftar Pustaka\"",
        "---",
        "",
    ]
    for index, path in enumerate(chapter_files):
        if index and chapter_breaks:
            chunks.extend(["\\newpage", ""])
        chunks.append(path.read_text(encoding="utf-8").strip())
        chunks.append("")
    combined = "\n".join(chunks)
    destination.write_text(combined, encoding="utf-8")
    return combined


def postprocess_tables(path: Path) -> None:
    doc = Document(path)
    for table in doc.tables:
        # Content-specific widths: compact study label, wider findings, readable limits.
        widths = [1500, 1800, 1950, 2350, 1760]
        if len(table.columns) != len(widths):
            widths = [CONTENT_WIDTH_DXA // len(table.columns)] * len(table.columns)
            widths[-1] += CONTENT_WIDTH_DXA - sum(widths)
        apply_table_geometry(table, widths)
        set_table_borders(table)
        if table.rows:
            mark_header_row(table.rows[0])
            for cell in table.rows[0].cells:
                set_cell_shading(cell, TABLE_FILL)
        for row_idx, row in enumerate(table.rows):
            tr_pr = row._tr.get_or_add_trPr()
            if tr_pr.find(qn("w:cantSplit")) is None:
                tr_pr.append(OxmlElement("w:cantSplit"))
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    paragraph.paragraph_format.space_before = Pt(0)
                    paragraph.paragraph_format.space_after = Pt(2)
                    paragraph.paragraph_format.line_spacing = 1.05
                    for run in paragraph.runs:
                        set_run_font(run, size=9.2, color="000000", bold=(row_idx == 0))
    doc.save(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Konversi Markdown berisi sitasi Pandoc/Zotero menjadi DOCX."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="File Markdown input; jika kosong, gunakan tiga draf utama di draft/.",
    )
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--title", default="Deteksi Jatuh Berbasis Radar Doppler")
    parser.add_argument("--subtitle", default="Draf Gabungan Bab 1–3")
    parser.add_argument("--zotero-db", type=Path, default=DEFAULT_ZOTERO_DB)
    parser.add_argument("--csl", type=Path, default=DEFAULT_CSL_FILE)
    parser.add_argument(
        "--no-chapter-breaks",
        action="store_true",
        help="Jangan memulai setiap file input pada halaman baru.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validasi file input dan citation key tanpa membuat DOCX.",
    )
    return parser.parse_args()


def build(args: argparse.Namespace) -> None:
    chapter_files = args.inputs or list(DEFAULT_INPUTS)
    missing_inputs = [path for path in chapter_files if not path.exists()]
    if missing_inputs:
        joined = ", ".join(str(path) for path in missing_inputs)
        raise FileNotFoundError(f"File Markdown tidak ditemukan: {joined}")
    if not args.csl.exists():
        raise FileNotFoundError(
            f"CSL style tidak ditemukan: {args.csl}. "
            "Gunakan --csl untuk menentukan style lain."
        )
    if shutil.which("pandoc") is None:
        raise RuntimeError("Pandoc tidak ditemukan di PATH.")

    with tempfile.TemporaryDirectory(prefix="radio-fall-docx-") as tmp_dir:
        tmp = Path(tmp_dir)
        combined_path = tmp / "combined.md"
        refs_path = tmp / "references.json"
        combined = make_combined_markdown(
            combined_path,
            chapter_files,
            title=args.title,
            subtitle=args.subtitle,
            chapter_breaks=not args.no_chapter_breaks,
        )
        keys = cited_keys(combined)
        export_csl_json(keys, refs_path, args.zotero_db)
        print(f"Validated {len(keys)} citation key(s) against Zotero.")

        if args.check:
            return

        reference_docx = tmp / "reference.docx"
        configure_template().save(reference_docx)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "pandoc",
            str(combined_path),
            "--from=markdown+tex_math_dollars+citations",
            "--to=docx",
            "--citeproc",
            f"--bibliography={refs_path}",
            f"--csl={args.csl}",
            f"--reference-doc={reference_docx}",
            f"--output={args.output}",
        ]
        subprocess.run(command, cwd=ROOT, check=True)
    postprocess_tables(args.output)
    print(f"Created {args.output}")


if __name__ == "__main__":
    build(parse_args())
