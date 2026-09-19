"""Generate Zensical chapter pages from the checked PDF transcription.

Run from the repository root after installing pypdf and pypdfium2:
    python3 compatition-manual/build_site.py
    zensical build
"""

from __future__ import annotations

import html
import os
import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber
from PIL import Image
from pypdf import PdfReader

from build_markdown import CHAPTERS, HERE, PDF, page_text

DOCS = HERE / "site-docs"

CHAPTER_FILES = [
    "01-introduction.md", "02-season-overview.md", "03-eligibility-inspection.md",
    "04-advancement.md", "05-event-rules.md", "06-awards.md", "07-sponsor.md",
    "08-game-overview.md", "09-arena.md", "10-game-details.md", "11-game-rules.md",
    "12-robot-construction.md", "13-tournament.md", "14-league-play.md",
    "15-championship.md", "16-glossary.md",
]


def orange_spans(page: pdfplumber.page.Page, raw: str) -> list[tuple[int, int]]:
    """Find text lines inside the PDF's pale-orange note backgrounds."""
    rects = sorted(
        (
            rect for rect in page.rects
            if rect["width"] > 300
            and isinstance((color := rect.get("non_stroking_color")), tuple)
            and len(color) == 3
            and color[0] > .9 and .6 < color[1] < .8 and .4 < color[2] < .6
        ),
        key=lambda rect: rect["top"],
    )
    groups: list[list[float]] = []
    for rect in rects:
        if groups and rect["top"] <= groups[-1][1] + 3:
            groups[-1][1] = max(groups[-1][1], rect["bottom"])
        else:
            groups.append([rect["top"], rect["bottom"]])

    def normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).lower()

    source = raw.splitlines()
    spans: list[tuple[int, int]] = []
    cursor = 0
    for top, bottom in groups:
        box_lines = [
            normalized(line)
            for line in (page.crop((103, top, 510, bottom)).extract_text() or "").splitlines()
            if normalized(line)
        ]
        if not box_lines:
            raise ValueError(f"Empty orange box on PDF page {page.page_number}")
        try:
            start = next(i for i in range(cursor, len(source)) if normalized(source[i]) == box_lines[0])
            end = next(i for i in range(start, len(source)) if normalized(source[i]) == box_lines[-1])
        except StopIteration as error:
            raise ValueError(f"Cannot align orange box on PDF page {page.page_number}") from error
        spans.append((start, end))
        cursor = end + 1
    return spans


def line_positions(page: pdfplumber.page.Page, raw: str) -> dict[int, tuple[float, float]]:
    """Align the checked text transcription with the PDF's line coordinates."""
    visual = page.extract_text_lines()
    positions: dict[int, tuple[float, float]] = {}
    cursor = 0

    def normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    for index, original in enumerate(raw.splitlines()):
        target = normalized(original)
        if not target:
            continue
        candidates = range(cursor, min(len(visual), cursor + 14))
        scored = [
            (SequenceMatcher(None, target, normalized(visual[j]["text"])).ratio(), j)
            for j in candidates
        ]
        if not scored:
            continue
        score, match = max(scored)
        if score >= .58:
            positions[index] = (visual[match]["x0"], visual[match]["top"])
            cursor = match + 1
    return positions


def page_figures(page: pdfplumber.page.Page, image_dir: Path) -> list[tuple[float, str, str]]:
    """Crop body illustrations from the rendered source page."""
    images = [
        item for item in page.images
        if not (item["top"] < 5 and item["height"] <= 105 and item["width"] > 580)
        and item["width"] >= 40 and item["height"] >= 25
    ]
    regions = [
        (item["top"], (item["x0"], item["top"], item["x1"], item["bottom"]),
         "Illustration")
        for item in images
    ]
    figures: list[tuple[float, str, str]] = []
    with Image.open(HERE / "BIOBUZZ_Competition_Manual_TU01_pages" /
                    f"page-{page.page_number:03d}.jpg") as rendered:
        if page.page_number == 27:
            # Figure 4-2 is assembled from vector boxes and connector lines,
            # so it does not appear in pdfplumber's embedded-image inventory.
            regions.append((430, (100, 430, 520, 716),
                            "Illustration of Figure 4-2 tournament advancement structure"))

        regions.sort(key=lambda region: (region[0], region[1][0]))
        scale_x, scale_y = rendered.width / page.width, rendered.height / page.height
        for number, (top, (x0, y0, x1, y1), label) in enumerate(regions, 1):
            box = (
                max(0, round((x0 - 2) * scale_x)),
                max(0, round((y0 - 2) * scale_y)),
                min(rendered.width, round((x1 + 2) * scale_x)),
                min(rendered.height, round((y1 + 2) * scale_y)),
            )
            filename = f"page-{page.page_number:03d}-figure-{number:02d}.jpg"
            rendered.crop(box).save(image_dir / filename, quality=90, optimize=True)
            figures.append((top, filename, label))
    return figures


def _orange_rectangles(page: pdfplumber.page.Page) -> list[dict]:
    """Return pale-orange note rectangles, which are not tables."""
    return [
        rect for rect in page.rects
        if rect["width"] > 300
        and isinstance((color := rect.get("non_stroking_color")), tuple)
        and len(color) == 3
        and color[0] > .9 and .6 < color[1] < .8 and .4 < color[2] < .6
    ]


def _cluster_edges(values: list[float], tolerance: float = 11) -> list[float]:
    """Collapse thin decorative columns around PDF table borders."""
    groups: list[list[float]] = []
    for value in sorted(set(values)):
        if groups and value - sum(groups[-1]) / len(groups[-1]) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _nearest_edge(value: float, edges: list[float]) -> int:
    return min(range(len(edges)), key=lambda index: abs(edges[index] - value))


def _dark_cell(rendered: Image.Image, page: pdfplumber.page.Page,
               box: tuple[float, float, float, float]) -> bool:
    """Detect the manual's dark teal table-header fill from source pixels."""
    x0, top, x1, bottom = box
    scale_x, scale_y = rendered.width / page.width, rendered.height / page.height
    left = max(0, round((x0 + 2) * scale_x))
    right = min(rendered.width - 1, round((x1 - 2) * scale_x))
    upper = max(0, round((top + 2) * scale_y))
    lower = min(rendered.height - 1, round((bottom - 2) * scale_y))
    if right <= left or lower <= upper:
        return False
    samples = []
    step_x = max(2, (right - left) // 12)
    step_y = max(2, (lower - upper) // 5)
    for y in range(upper, lower + 1, step_y):
        for x in range(left, right + 1, step_x):
            red, green, blue = rendered.getpixel((x, y))[:3]
            samples.append(red < 80 and green < 130 and blue < 150)
    return bool(samples) and sum(samples) / len(samples) >= .38


def _cell_text(value: str | None) -> str:
    """Reflow wrapped PDF cell lines without changing their wording."""
    if not value:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    text = ""
    for line in filter(None, lines):
        separator = "" if text.endswith("-") else " "
        text = f"{text}{separator}{line}" if text else line
    return html.escape(text, quote=False)


def _generic_table_html(page: pdfplumber.page.Page, table, rendered: Image.Image) -> list[str]:
    """Reconstruct a ruled PDF table with its row and column spans."""
    cells = []
    for row, values in zip(table.rows, table.extract()):
        for box, value in zip(row.cells, values):
            if box is None:
                continue
            # Thin blank strips draw inset rules and are not actual cells.
            if not value and box[2] - box[0] <= 8:
                continue
            cells.append((box, value or ""))

    x_edges = _cluster_edges([x for box, _ in cells for x in (box[0], box[2])])
    y_edges = _cluster_edges(
        [y for box, _ in cells for y in (box[1], box[3])], tolerance=2
    )
    placed: dict[int, list[tuple[int, int, int, str, bool]]] = {}
    for box, value in cells:
        column = _nearest_edge(box[0], x_edges)
        column_end = _nearest_edge(box[2], x_edges)
        row = _nearest_edge(box[1], y_edges)
        row_end = _nearest_edge(box[3], y_edges)
        placed.setdefault(row, []).append((
            column,
            max(1, column_end - column),
            max(1, row_end - row),
            value,
            _dark_cell(rendered, page, box),
        ))

    lines = [
        '<div class="pdf-table-wrap">',
        '<table class="pdf-table">',
        f'<caption class="manual-visually-hidden">Table from PDF page {page.page_number}</caption>',
        '<tbody>',
    ]
    first_content_row = min(placed, default=0)
    for row in sorted(placed):
        lines.append("<tr>")
        for column, colspan, rowspan, value, dark in sorted(placed[row]):
            attributes = []
            if colspan > 1:
                attributes.append(f'colspan="{colspan}"')
            if rowspan > 1:
                attributes.append(f'rowspan="{rowspan}"')
            classes = []
            if dark:
                classes.append("pdf-table-header")
            row_heading = column == 0 and row > first_content_row
            if row_heading:
                classes.append("pdf-table-row-heading")
            if classes:
                attributes.append(f'class="{" ".join(classes)}"')
            tag = "th" if dark or row_heading else "td"
            if tag == "th":
                attributes.append(f'scope="{"row" if row_heading else "col"}"')
            joined = f" {' '.join(attributes)}" if attributes else ""
            lines.append(f"<{tag}{joined}>{_cell_text(value)}</{tag}>")
        lines.append("</tr>")
    lines.extend(["</tbody>", "</table>", "</div>"])
    return lines


def purpose_table_html(page: pdfplumber.page.Page) -> list[str]:
    words = [word for word in page.extract_words() if 375 < word["top"] < 455]
    columns = [
        " ".join(word["text"] for word in words if left <= word["x0"] < right)
        for left, right in ((0, 212), (212, 392), (392, 612))
    ]
    lines = [
        '<div class="pdf-table-wrap"><table class="pdf-table purpose-table">',
        '<caption class="manual-visually-hidden">FIRST purpose, vision, and mission</caption>',
        '<thead><tr><th>Purpose</th><th>Vision</th><th>Mission</th></tr></thead>',
        '<tbody><tr>',
    ]
    lines.extend(f"<td>{html.escape(value, quote=False)}</td>" for value in columns)
    lines.extend(["</tr></tbody>", "</table></div>"])
    return lines


def page_tables(page: pdfplumber.page.Page) -> list[tuple[float, float, list[str]]]:
    """Find true data tables and rebuild them as semantic HTML."""
    if 169 <= page.page_number <= 173:
        return []
    orange = _orange_rectangles(page)
    tables = []
    image_path = (HERE / "BIOBUZZ_Competition_Manual_TU01_pages" /
                  f"page-{page.page_number:03d}.jpg")
    with Image.open(image_path) as rendered:
        for table in page.find_tables():
            x0, top, x1, bottom = table.bbox
            columns = max((len(row.cells) for row in table.rows), default=0)
            orange_overlap = any(
                rect["top"] < bottom and rect["bottom"] > top
                for rect in orange
            )
            if columns < 2 or x1 - x0 < 180 or orange_overlap:
                continue
            tables.append((top, bottom, _generic_table_html(page, table, rendered)))
    if page.page_number == 5:
        tables.append((350, 464, purpose_table_html(page)))
    return tables


def glossary_rows(page: pdfplumber.page.Page) -> list[tuple[str, str]]:
    """Return the two semantic columns from the glossary's ruled PDF table."""
    if not 169 <= page.page_number <= 173:
        return []
    tables = page.find_tables()
    if len(tables) != 1:
        raise ValueError(f"Expected one glossary table on PDF page {page.page_number}")
    rows: list[tuple[str, str]] = []
    for row in tables[0].extract():
        if len(row) == 6:
            term = next((value for value in row[:3] if value), "")
            definition = next((value for value in row[3:] if value), "")
        else:
            term, definition = row[:2]
        if term == "Term" and definition == "Definition":
            continue
        rows.append((term or "", definition or ""))
    return rows


def glossary_table(rows: list[tuple[str, str]], show_header: bool) -> list[str]:
    """Render glossary rows as accessible HTML while retaining the PDF wording."""
    lines = [
        '<div class="glossary-table-wrap">',
        '<table class="glossary-table">',
        '<caption class="manual-visually-hidden">BIOBUZZ glossary terms and definitions</caption>',
        '<colgroup><col class="glossary-term-column"><col></colgroup>',
    ]
    if show_header:
        lines.extend([
            "<thead><tr>",
            '<th scope="col">Term</th>',
            '<th scope="col">Definition</th>',
            "</tr></thead>",
        ])
    lines.append("<tbody>")
    for term, definition in rows:
        parts = re.split(r"\n(?=[A-Z]\.\s)", definition)
        definition_html = html.escape(re.sub(r"\s+", " ", parts[0]).strip(), quote=False)
        if len(parts) > 1:
            definition_html += '<ol class="glossary-cell-list" type="A">'
            for item in parts[1:]:
                item = re.sub(r"^[A-Z]\.\s*", "", item)
                item = html.escape(re.sub(r"\s+", " ", item).strip(), quote=False)
                definition_html += f"<li>{item}</li>"
            definition_html += "</ol>"
        lines.extend([
            "<tr>",
            f'<th scope="row">{html.escape(term, quote=False)}</th>',
            f"<td>{definition_html}</td>",
            "</tr>",
        ])
    lines.extend(["</tbody>", "</table>", "</div>"])
    return lines


def source_lines(
    raw: str, callouts: list[tuple[int, int]], chapter_heading: tuple[int, str] | None,
    positions: dict[int, tuple[float, float]], figures: list[tuple[float, str, str]],
    tables: list[tuple[float, float, list[str]]], image_prefix: str,
    page_number: int, parse_headings: bool,
) -> list[str]:
    result = []
    starts = {start for start, _ in callouts}
    ends = {end for _, end in callouts}
    figure_after: dict[int, list[tuple[str, str]]] = {}
    for top, filename, label in figures:
        before = [index for index, (_, y) in positions.items() if y < top]
        index = max(before, default=-1)
        figure_after.setdefault(index, []).append((filename, label))
    table_after: dict[int, list[list[str]]] = {}
    for top, _, table_html in tables:
        before = [index for index, (_, y) in positions.items() if y < top]
        index = max(before, default=-1)
        table_after.setdefault(index, []).append(table_html)

    paragraph: list[tuple[str, float]] = []
    paragraph_kind = "prose"
    paragraph_anchor: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_kind, paragraph_anchor
        if not paragraph:
            return
        first_x = paragraph[0][1]
        base = 108 if paragraph_kind == "callout" else 36
        first_indent = max(0, min(140, round(first_x - base)))
        continuation_x = max((x for _, x in paragraph[1:]), default=first_x)
        hanging = max(0, min(72, round(continuation_x - first_x)))
        if paragraph_kind == "rule":
            hanging = max(36, hanging)
        elif paragraph_kind != "list":
            hanging = 0
        indent = min(140, first_indent + hanging)
        classes = ["source-paragraph"]
        if paragraph_kind in {"rule", "list"}:
            classes.append(f"source-{paragraph_kind}")

        text = ""
        for fragment, _ in paragraph:
            fragment = fragment.strip()
            if not fragment:
                continue
            # A terminal hyphen belongs directly beside the next PDF line.
            separator = "" if text.endswith("-") else " "
            text = f"{text}{separator}{fragment}" if text else fragment
        anchor = f' id="{paragraph_anchor}"' if paragraph_anchor else ""
        result.append(
            f'<p{anchor} class="{" ".join(classes)}" '
            f'style="--source-indent:{indent}px;--source-hang:{hanging}px">'
            f'{text}</p>'
        )
        paragraph = []
        paragraph_kind = "prose"
        paragraph_anchor = None

    def add_embedded_content(index: int) -> None:
        if figure_after.get(index) or table_after.get(index):
            flush_paragraph()
        for filename, label in figure_after.get(index, []):
            result.extend([
                "", '<figure class="manual-figure">',
                f'<img src="{image_prefix}images/{filename}" '
                f'alt="{label} from PDF page {page_number}" loading="lazy">',
                "</figure>", "",
            ])
        for table_html in table_after.get(index, []):
            result.extend(["", *table_html, ""])

    add_embedded_content(-1)
    previous_position: float | None = None
    previous_x0 = 36.0
    for index, original in enumerate(raw.splitlines()):
        if index in starts:
            flush_paragraph()
            result.extend(["", '<aside class="pdf-callout" markdown="1">', ""])
        stripped = original.strip()
        line = html.escape(stripped, quote=False)
        current_position = positions.get(index, (0, None))[1]
        paragraph_gap = (
            current_position is not None
            and previous_position is not None
            and current_position - previous_position >= 17
        )
        x0 = positions.get(index, (previous_x0, 0))[0]
        rule = re.match(r"^([IEAGRTLC]\d{3})(\s+.+)$", stripped)
        list_item = re.match(
            r"^(?:[−•▪]\s+|[A-Z]\.(?:\s+|$)|[ivxlcdm]+\.(?:\s+|$))", stripped
        )
        standalone_line = (
            bool(re.search(r"\.{5,}\s*\d+\s*$", stripped))
            or bool(re.match(r"^(?:Figure|Table)\s+\d", stripped))
        )

        # Chapter labels are corrected from the PDF's typography when its text
        # layer inserts extra spaces (for example, "Tourn ament").
        if (chapter_heading and index < 10 and re.match(
            rf"^{chapter_heading[0]}\s+[A-Z]", line.strip()
        )):
            flush_paragraph()
            number, title = chapter_heading
            result.extend(["", f"## {number} {title} {{ .manual-chapter-heading }}", ""])
        elif stripped == "Engineer a Thriving Planet with FIRST":
            flush_paragraph()
            result.extend([
                "", "### Engineer a Thriving Planet with *FIRST* "
                "{ .manual-feature-heading }", "",
            ])
        else:
            section = re.match(r"^(\d{1,2}(?:\.\d+)+)\s+\S", line.strip())
            if parse_headings and section and not line.startswith(
                "1.5 Competition Integrity Contract (CIC) below."
            ):
                flush_paragraph()
                depth = section.group(1).count(".")
                if depth == 1:
                    result.extend(["", f"### {line.strip()} {{ .manual-section-heading }}", ""])
                else:
                    result.extend(["", f"#### {line.strip()} {{ .manual-subsection-heading }}", ""])
            elif not stripped:
                flush_paragraph()
            elif standalone_line:
                flush_paragraph()
                paragraph.append((line, x0))
                flush_paragraph()
            else:
                if rule:
                    flush_paragraph()
                    identifier, rest = rule.groups()
                    line = (
                        f'<strong>{identifier}</strong>{html.escape(rest, quote=False)}'
                    )
                    paragraph_kind = "rule"
                    paragraph_anchor = identifier.lower()
                    x0 = positions.get(index, (36, 0))[0]
                elif list_item:
                    flush_paragraph()
                    paragraph_kind = "list"
                elif paragraph_gap or (paragraph and x0 < paragraph[0][1] - 8):
                    flush_paragraph()
                    paragraph_kind = (
                        "callout" if any(start <= index <= end for start, end in callouts)
                        else "prose"
                    )
                elif not paragraph:
                    paragraph_kind = (
                        "callout" if any(start <= index <= end for start, end in callouts)
                        else "prose"
                    )
                paragraph.append((line, x0))
        if index in ends:
            flush_paragraph()
            result.extend(["", "</aside>", ""])
        add_embedded_content(index)
        if current_position is not None:
            previous_position = current_position
            previous_x0 = positions[index][0]
    flush_paragraph()
    return result


def page_section(
    number: int, raw: str, image_prefix: str, callouts: list[tuple[int, int]],
    positions: dict[int, tuple[float, float]], figures: list[tuple[float, str, str]],
    tables: list[tuple[float, float, list[str]]],
    chapter_heading: tuple[int, str] | None = None, parse_headings: bool = True,
    source_range: tuple[int, int] | None = None,
    glossary: list[tuple[str, str]] | None = None,
) -> list[str]:
    first, last = source_range or (number, number)
    page_span = str(first) if first == last else f"{first}-{last}"
    page_label = "page" if first == last else "pages"
    lines = [
        f'<section class="manual-page" id="pdf-page-{number}" markdown="1">',
        '<details class="source-page">',
        '<summary><span class="source-summary-content">',
        f'<span>PDF Page {number}</span>',
        f'<span>Source: TU01, PDF {page_label} {page_span}.</span>',
        f'<a href="{image_prefix}BIOBUZZ_Competition_Manual_TU01.pdf" '
        'onclick="event.stopPropagation()">Open the original PDF</a>',
        '</span></summary>', "",
        f'<img src="{image_prefix}BIOBUZZ_Competition_Manual_TU01_pages/page-{number:03d}.jpg" '
        f'alt="Original PDF page {number}" loading="lazy">',
        "", "</details>", "",
    ]
    if raw:
        lines.extend(source_lines(
            raw, callouts, chapter_heading, positions, figures, tables, image_prefix, number,
            parse_headings,
        ))
    elif not glossary:
        lines.extend([
            f'<img class="source-page-full" src="{image_prefix}'
            f'BIOBUZZ_Competition_Manual_TU01_pages/page-{number:03d}.jpg" '
            f'alt="Original PDF page {number}" loading="lazy">',
        ])
    if glossary:
        lines.extend(["", *glossary_table(glossary, number == 169), ""])
    lines.extend(["", "</section>", ""])
    return lines


def write_home() -> None:
    content = """# BIOBUZZ manual

<p class="manual-eyebrow">2026-2027 FIRST Tech Challenge · TU01</p>

## Find a rule. Understand the game. Check the source.

This site makes the 173-page competition manual easier to explore. Each chapter starts with a short description, followed by the manual's wording and illustrations. Expand a PDF page label to check its complete original layout.

<div class="manual-cards">
  <a href="chapters/08-game-overview/"><strong>New to BIOBUZZ?</strong><span>See what happens in a match.</span></a>
  <a href="chapters/10-game-details/"><strong>How do points work?</strong><span>Read match timing and scoring.</span></a>
  <a href="chapters/11-game-rules/"><strong>Planning a strategy?</strong><span>Find the gameplay rules.</span></a>
  <a href="chapters/12-robot-construction/"><strong>Building a robot?</strong><span>Check sizes, parts, and wiring.</span></a>
</div>

## Quick word help

- **ALLIANCE:** two teams working together in a match.
- **AUTO:** the first 30 seconds, when robots follow their programs without driver input.
- **TELEOP:** the two-minute part of the match when drivers control robots.
- **POLLEN:** the yellow game balls. **NECTAR:** the red and blue game balls.
- **HIVE:** the tilting structure in the middle of the field. Its **CELLS** can hold POLLEN and NECTAR.

## Read with confidence

Use the search box for a rule ID such as `G301`, or for a game word such as `HIVE`. The short descriptions help you find a topic. The detailed text and the page image let you verify the manual itself.

[Open the complete source PDF](BIOBUZZ_Competition_Manual_TU01.pdf)

The searchable text comes from the PDF text layer. Diagram labels and special font glyphs can extract imperfectly; the page images preserve the source layout and visual content.
"""
    (DOCS / "index.md").write_text(content, encoding="utf-8")


def main() -> None:
    reader = PdfReader(PDF)
    assert len(reader.pages) == 173
    DOCS.mkdir(exist_ok=True)
    image_dir = DOCS / "images"
    image_dir.mkdir(exist_ok=True)
    for stale in image_dir.glob("page-*-figure-*.jpg"):
        stale.unlink()
    # Zensical 0.0.62 does not scan a docs directory containing symlinked
    # assets. Hard links share the source files' data without duplicating it.
    asset_dir = DOCS / "BIOBUZZ_Competition_Manual_TU01_pages"
    asset_dir.mkdir(exist_ok=True)
    for source in [PDF, *sorted((HERE / "BIOBUZZ_Competition_Manual_TU01_pages").glob("*.jpg"))]:
        destination = (DOCS / source.name) if source == PDF else (asset_dir / source.name)
        if destination.exists() and os.path.samefile(source, destination):
            continue
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
    chapter_dir = DOCS / "chapters"
    chapter_dir.mkdir(exist_ok=True)
    write_home()

    callout_count = 0
    figure_count = 0
    table_count = 0
    with pdfplumber.open(PDF) as layout:
        def render_page(
            number: int, image_prefix: str,
            chapter_heading: tuple[int, str] | None = None,
            parse_headings: bool = True,
            source_range: tuple[int, int] | None = None,
        ) -> list[str]:
            nonlocal callout_count, figure_count, table_count
            raw = page_text(reader.pages[number - 1])
            page = layout.pages[number - 1]
            glossary = glossary_rows(page)
            tables = page_tables(page)
            original_positions = line_positions(page, raw)
            if glossary:
                table_top = page.find_tables()[0].bbox[1]
                raw = "\n".join(
                    line for index, line in enumerate(raw.splitlines())
                    if original_positions.get(index, (0, float("inf")))[1] < table_top
                )
            elif tables:
                table_spans = []
                source_rows = raw.splitlines()
                for top, _, table_html in tables:
                    before = [
                        index for index, (_, y) in original_positions.items()
                        if y < top - 2
                    ]
                    start = max(before, default=-1) + 1
                    table_text = html.unescape(re.sub(
                        r"<[^>]+>", " ", " ".join(table_html)
                    )).casefold()
                    table_words = set(re.findall(r"[\w*]+", table_text))
                    end = start - 1
                    misses = 0
                    for index in range(start, len(source_rows)):
                        words = re.findall(r"[\w*]+", source_rows[index].casefold())
                        match = words and sum(word in table_words for word in words) / len(words) >= .8
                        if match:
                            end = index
                            misses = 0
                        elif end >= start:
                            misses += 1
                            if misses >= 2:
                                break
                    if end >= start:
                        table_spans.append((start, end))
                raw = "\n".join(
                    line for index, line in enumerate(raw.splitlines())
                    if not any(start <= index <= end for start, end in table_spans)
                )
            callouts = orange_spans(page, raw)
            callout_count += len(callouts)
            positions = line_positions(page, raw)
            figures = page_figures(page, image_dir)
            figure_count += len(figures)
            table_count += len(tables) + bool(glossary)
            return page_section(
                number, raw, image_prefix, callouts, positions, figures, tables, chapter_heading,
                parse_headings, source_range, glossary,
            )

        for chapter_number, ((title, first, last, explanation), filename) in enumerate(
            zip(CHAPTERS, CHAPTER_FILES), 1
        ):
            lines = [
                f"# {title}", "",
                f'<p class="manual-intro">{explanation}</p>', "",
            ]
            for number in range(first, last + 1):
                heading = (chapter_number, title) if number == first else None
                lines.extend(render_page(number, "../", heading, source_range=(first, last)))
            (chapter_dir / filename).write_text("\n".join(lines), encoding="utf-8")

        assigned = {number for _, first, last, _ in CHAPTERS for number in range(first, last + 1)}
        unassigned = sorted(set(range(1, 174)) - assigned)
        blank_pages = [
            number for number in unassigned
            if not page_text(reader.pages[number - 1]).strip()
            and not any((
                layout.pages[number - 1].images,
                layout.pages[number - 1].rects,
                layout.pages[number - 1].curves,
                layout.pages[number - 1].lines,
                layout.pages[number - 1].chars,
            ))
        ]
        remaining = [number for number in unassigned if number not in blank_pages]
        lines = ["# Cover and contents", "",
                 "These pages contain the cover and contents from the TU01 PDF.", ""]
        for number in remaining:
            lines.extend(render_page(number, "", parse_headings=False))
        (DOCS / "source-pages.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {len(CHAPTERS)} chapters and {173 - len(blank_pages)} content-bearing "
          f"PDF pages; omitted {len(blank_pages)} blank print-separator pages; "
          f"{figure_count} inline illustrations, {table_count} table views, "
          f"and {callout_count} orange callouts.")


if __name__ == "__main__":
    main()
