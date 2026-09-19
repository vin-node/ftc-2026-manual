"""Build and check the searchable BIOBUZZ Markdown edition.

Requires pypdf and pypdfium2. Run from the repository root:
    python3 compatition-manual/build_markdown.py
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

import pypdfium2
from pypdf import PdfReader


HERE = Path(__file__).resolve().parent
PDF = HERE / "BIOBUZZ_Competition_Manual_TU01.pdf"
MARKDOWN = HERE / "BIOBUZZ_Competition_Manual_TU01.md"
IMAGES = HERE / "BIOBUZZ_Competition_Manual_TU01_pages"

CHAPTERS = [
    ("Introduction", 5, 19, "Meet FIRST, learn the team's shared values, and find out how to read this manual and ask official questions."),
    ("FIRST Season Overview", 21, 21, "See the season's theme and how this year's challenge fits into it."),
    ("Competition Eligibility and Inspection (I)", 22, 25, "Check whether your team and robot can compete and what inspection involves."),
    ("Advancement", 27, 31, "Learn how results at one event can lead to another event."),
    ("Event Rules (E)", 33, 41, "Know how to stay safe and respectful at the venue, pits, and field."),
    ("Awards (A)", 43, 59, "Find out what judges look for, how interviews and portfolios work, and what awards recognize."),
    ("Game Sponsor Recognition", 61, 61, "Meet the organization presenting the game."),
    ("Game Overview", 62, 62, "Get a short picture of what the robots try to do in BIOBUZZ."),
    ("ARENA", 63, 79, "Explore the field, hive, flowers, scoring pieces, markings, and field staff."),
    ("Game Details", 81, 97, "Follow match setup, timing, scoring, ranking points, and penalties."),
    ("Game Rules (G)", 99, 116, "Read the rules for people and robots before and during a match."),
    ("ROBOT Construction Rules (R)", 117, 143, "Check robot size, materials, signs, motors, wiring, controls, and other build limits."),
    ("Tournament (T)", 145, 164, "See how practice, qualification, and playoff matches are run."),
    ("League Play Tournaments (L)", 165, 165, "Find the extra details for regions that use league play."),
    ("FIRST Championship (C)", 167, 168, "See how the championship divisions and playoffs work."),
    ("Glossary", 169, 173, "Look up the special meanings of words written in ALL CAPS."),
]


def page_text(page) -> str:
    try:
        value = page.extract_text() or ""
    except KeyError:  # Divider pages without a content stream.
        value = ""
    # Keep extracted wording and line order. Remove only the repeated running footer.
    value = re.sub(
        r"(?m)^Section .+?Version: TU01\s+\d+ of 173\s*\n?",
        "",
        value,
    )
    # This font run drops three glyphs in both text extractors; the page image
    # clearly reads "ROBOT is DISABLED."
    if "the offending team’s  OBOT is DI ABLED." in value:
        value = value.replace(
            "the offending team’s  OBOT is DI ABLED.",
            "the offending team’s ROBOT is DISABLED.",
        )
    return value.strip()


def main() -> None:
    reader = PdfReader(PDF)
    renderer = pypdfium2.PdfDocument(str(PDF))
    assert len(reader.pages) == len(renderer) == 173
    IMAGES.mkdir(exist_ok=True)

    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    lines = [
        "# BIOBUZZ: 2026-2027 FIRST Tech Challenge Competition Manual",
        "",
        "**Source edition:** TU01 · **PDF pages:** 173 · "
        f"**Source SHA-256:** `{digest}`",
        "",
        "[Open the original PDF](BIOBUZZ_Competition_Manual_TU01.pdf)",
        "",
        "This edition gives you a quick reading map, then the manual's page-by-page wording. "
        "Open **See the original PDF page** under any page to view its exact tables, figures, "
        "colors, symbols, and layout. The page images are part of this Markdown edition.",
        "",
        "## A quick reading map",
        "",
        "Start with **Game Overview** for the big idea. Use **Game Details** to learn how points "
        "are earned. Read **Game Rules** before planning a match strategy and **ROBOT "
        "Construction Rules** before finalizing a design. The **Glossary** explains words "
        "written in ALL CAPS. Other chapters cover team eligibility, events, judging, and tournaments.",
        "",
    ]
    for title, first, last, explanation in CHAPTERS:
        span = f"{first}" if first == last else f"{first}-{last}"
        lines.append(f"- **{title}** (PDF pages {span}): {explanation}")
    lines.extend(
        [
            "",
            "## Quick word help",
            "",
            "- **ALLIANCE:** two teams working together in a match.",
            "- **AUTO:** the first 30 seconds, when robots follow their programs without driver input.",
            "- **TELEOP:** the two-minute part of the match when drivers control robots.",
            "- **POLLEN:** the yellow game balls. **NECTAR:** the red and blue game balls.",
            "- **HIVE:** the tilting structure in the middle of the field. Its **CELLS** can hold POLLEN and NECTAR.",
            "- **MATCH points:** the points for what an alliance does in a match. **RANKING POINTS:** "
            "points used to rank teams during qualification.",
            "",
            "## How to use this edition",
            "",
            "- Use your editor's search to find a rule ID such as `G301` or a term such as `HIVE`.",
            "- Every PDF page has a matching page heading below, including the cover, contents, and dividers.",
            "- For a table or diagram, open the page image; its visual arrangement can carry meaning.",
            "- The reading map is a short explanation. The page-by-page content contains the manual's detailed wording.",
            "- The searchable text comes from the PDF text layer. A few diagram labels and special font glyphs "
            "may extract imperfectly; the page images preserve the exact visual content.",
            "",
            "## Full manual, page by page",
            "",
        ]
    )

    for index, page in enumerate(reader.pages, 1):
        raw = page_text(page)
        image_name = f"page-{index:03d}.jpg"
        image_path = IMAGES / image_name
        image = renderer[index - 1].render(scale=1.6).to_pil().convert("RGB")
        image.save(image_path, "JPEG", quality=82, optimize=True)

        chapter = next((title for title, first, last, _ in CHAPTERS if first == index), None)
        if chapter:
            lines.extend([f"## {chapter}", ""])
        lines.extend([f"### PDF page {index}", ""])
        if raw:
            # Explicit line breaks preserve page reading order, lists, and table cell text.
            # HTML escape prevents source characters from being mistaken for Markdown syntax.
            lines.extend(f"{html.escape(line, quote=False)}  " if line else "" for line in raw.splitlines())
        else:
            lines.append("*(This page has no extractable text; see its image.)*")
        lines.extend(
            [
                "",
                "<details>",
                f"<summary>See the original PDF page {index}</summary>",
                "",
                f'<img src="BIOBUZZ_Competition_Manual_TU01_pages/{image_name}" '
                f'alt="Original PDF page {index}" width="980">',
                "",
                "</details>",
                "",
            ]
        )

    MARKDOWN.write_text("\n".join(lines), encoding="utf-8")

    # Check every source page, text block, and image link after writing.
    output = MARKDOWN.read_text(encoding="utf-8")
    for index, page in enumerate(reader.pages, 1):
        start = f"### PDF page {index}\n\n"
        end = "\n\n<details>"
        block = output.split(start, 1)[1].split(end, 1)[0]
        raw = page_text(page)
        if raw:
            recovered = "\n".join(
                html.unescape(line.removesuffix("  ")) for line in block.splitlines()
            )
            assert recovered == raw, f"Text mismatch on page {index}"
        assert (IMAGES / f"page-{index:03d}.jpg").is_file(), index
        assert f'alt="Original PDF page {index}"' in output, index
    print(f"Verified {len(reader.pages)} PDF pages, text blocks, and page images.")
    print(f"Markdown: {MARKDOWN} ({MARKDOWN.stat().st_size:,} bytes)")
    print(f"Page images: {sum(p.stat().st_size for p in IMAGES.glob('*.jpg')):,} bytes")


if __name__ == "__main__":
    main()
