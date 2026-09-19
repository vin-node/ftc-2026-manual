# BIOBUZZ manual site

The source PDF is `BIOBUZZ_Competition_Manual_TU01.pdf`. The Zensical site
configuration is at the repository root in `zensical.toml`. Site pages live in
`site-docs/`, and the generated HTML goes to `manual-site/`.

## Preview locally

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r compatition-manual/requirements-site.txt
.venv/bin/python compatition-manual/build_markdown.py
.venv/bin/python compatition-manual/build_site.py
.venv/bin/zensical serve
```

Open <http://localhost:8000/>. The `serve` command rebuilds the site when its
pages change. Use `.venv/Scripts/python` and `.venv/Scripts/zensical` on Windows.

## Regenerate after a PDF update

```sh
.venv/bin/python compatition-manual/build_markdown.py
.venv/bin/python compatition-manual/build_site.py
.venv/bin/zensical build --strict
```

The site generator reads each PDF page's text and links the corresponding page
image into the site input folder. It places the PDF's body illustrations inline
beside the extracted text, reconstructs PDF tables as accessible HTML, and uses
the PDF's line positions for semantic paragraph reconstruction, indentation,
and paragraph spacing. PDF
lines within the same paragraph are reflowed for the reader's screen, while
rules and nested lists retain hanging indents. The expandable page image still preserves
the complete visual layout, including details text extraction cannot express. The
generator also detects orange note backgrounds and styles the matching text as
callouts. The short chapter introductions are reading aids; the detailed
manual wording appears below them. Chapters with rule IDs also receive a
right-sidebar tag index that links directly to each rule.

Tables, including the glossary, are reconstructed from the PDF's cell geometry.
Their merged cells, headings, original wording, and visual column layout are
retained without using table screenshots.

The source PDF contains 10 completely blank print-separator pages. The site
omits those empty entries while retaining all 163 content-bearing pages and the
complete original PDF download.

## Publish with GitHub Pages

The workflow in `.github/workflows/pages.yml` regenerates the Markdown, page
images, semantic site pages, and final HTML on every push to `main`. It then
publishes `manual-site/` through GitHub Pages.

In the GitHub repository, open **Settings → Pages** and select **GitHub Actions**
as the deployment source. The generated site and temporary Python files are
excluded from Git because the workflow rebuilds them from the checked-in PDF.
