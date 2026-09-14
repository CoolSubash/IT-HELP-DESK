"""
Renders docs/rag-manual/chapters/*.md (in filename order) into a single
paginated PDF: docs/rag-manual/RAG-Knowledge-Base-Manual.pdf.

A small hand-written Markdown -> reportlab Platypus converter, not a
general-purpose Markdown renderer -- it supports exactly the subset this
manual's chapters use: headings (# ## ### ####), paragraphs with **bold**
/*italic*/`code` inline spans, bullet and numbered lists (one level of
nesting via 2-space indents), fenced ``` code blocks, pipe tables, and
horizontal rules. No external Markdown or HTML-to-PDF library, and no
system libraries (WeasyPrint needs pango/gobject via Homebrew, which this
environment doesn't have) -- reportlab is pure Python plus its own
bundled font/graphics code, so `pip install reportlab` is the only
dependency.

Usage (from repo root, with backend/.venv active -- reportlab is already
a dependency there, added for tests/test_rag_ingestion.py's PDF fixture):
    python docs/rag-manual/build_pdf.py
"""
import pathlib
import re
import textwrap

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = pathlib.Path(__file__).parent
CHAPTERS_DIR = HERE / "chapters"
OUTPUT_PATH = HERE / "RAG-Knowledge-Base-Manual.pdf"
TITLE = "RAG Knowledge Base &amp; Retrieval -- Implementation Manual"
SUBTITLE = "AI IT Helpdesk Agent -- Phase 7 (claudeprompt/phase7.md)"

PAGE_WIDTH, PAGE_HEIGHT = LETTER
MARGIN = 0.9 * inch

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()

styles.add(ParagraphStyle("ManualTitle", parent=styles["Title"], fontSize=28, leading=34, spaceAfter=14))
styles.add(ParagraphStyle("ManualSubtitle", parent=styles["Normal"], fontSize=13, alignment=TA_CENTER, textColor=colors.HexColor("#555555"), spaceAfter=6))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=20, spaceBefore=6, spaceAfter=14, textColor=colors.HexColor("#1a1a2e")))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=15, spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#16213e")))
styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontSize=12.5, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#0f3460")))
styles.add(ParagraphStyle("H4", parent=styles["Heading4"], fontSize=11, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#333333")))
styles.add(ParagraphStyle("ManualBody", parent=styles["Normal"], fontSize=10.2, leading=14.5, spaceAfter=8, alignment=4))  # 4 = justify
styles.add(ParagraphStyle("ManualBullet", parent=styles["ManualBody"], leftIndent=16, bulletIndent=4, spaceAfter=3))
styles.add(ParagraphStyle("ManualBulletL2", parent=styles["ManualBody"], leftIndent=32, bulletIndent=20, spaceAfter=3))
styles.add(ParagraphStyle("ManualQuote", parent=styles["ManualBody"], leftIndent=18, textColor=colors.HexColor("#444444"), fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle("ManualCode", parent=styles["Code"], fontSize=7.6, leading=9.6, backColor=colors.HexColor("#f4f4f4"), borderPadding=6, spaceBefore=4, spaceAfter=10))

# Preformatted (used for fenced code blocks) never wraps on its own --
# a long line just runs off the page edge and gets silently clipped.
# CODE_WRAP_WIDTH is sized to what ManualCode's font/page width can
# actually hold; _wrap_code_line() (below) hard-wraps anything longer,
# with a hanging indent so wrapped continuations are visually distinct
# from a new line of code.
CODE_WRAP_WIDTH = 96
styles.add(ParagraphStyle("ManualTableCell", parent=styles["ManualBody"], fontSize=8.8, leading=11, spaceAfter=0, alignment=0))
styles.add(ParagraphStyle("TOC1", parent=styles["Normal"], fontSize=12, leftIndent=0, spaceAfter=6, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("TOC2", parent=styles["Normal"], fontSize=10, leftIndent=16, spaceAfter=3, textColor=colors.HexColor("#333333")))

# ---------------------------------------------------------------------------
# Inline markdown -> reportlab mini-markup
# ---------------------------------------------------------------------------
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _wrap_code_line(line: str, width: int = CODE_WRAP_WIDTH) -> list[str]:
    if len(line) <= width:
        return [line]
    leading_ws = len(line) - len(line.lstrip(" "))
    hanging_indent = " " * min(leading_ws + 4, width // 2)
    wrapped = textwrap.wrap(
        line,
        width=width,
        initial_indent="",
        subsequent_indent=hanging_indent,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    )
    return wrapped or [line]


def inline_markup(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _LINK_RE.sub(r"\1 (\2)", text)
    text = _INLINE_CODE_RE.sub(r'<font face="Courier" size="9" color="#a1260d">\1</font>', text)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    return text


# ---------------------------------------------------------------------------
# Block-level Markdown -> Platypus flowables
# ---------------------------------------------------------------------------
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
_ORDERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def parse_markdown_to_flowables(markdown_text: str, toc_entries: list) -> list:
    lines = markdown_text.split("\n")
    flowables: list = []
    i = 0
    paragraph_buffer: list[str] = []

    def flush_paragraph():
        if paragraph_buffer:
            text = " ".join(paragraph_buffer).strip()
            if text:
                flowables.append(Paragraph(inline_markup(text), styles["ManualBody"]))
            paragraph_buffer.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "":
            flush_paragraph()
            i += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            wrapped_lines: list[str] = []
            for code_line in code_lines:
                wrapped_lines.extend(_wrap_code_line(code_line))
            flowables.append(Preformatted("\n".join(wrapped_lines), styles["ManualCode"]))
            continue

        if stripped == "---":
            flush_paragraph()
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cccccc")))
            flowables.append(Spacer(1, 8))
            i += 1
            continue

        if _TABLE_ROW_RE.match(stripped) and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1].strip()):
            flush_paragraph()
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = [header_cells]
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i].strip()):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            table_data = [
                [Paragraph(inline_markup(cell), styles["ManualTableCell"]) for cell in row] for row in rows
            ]
            table = Table(table_data, hAlign="LEFT", repeatRows=1)
            table.setStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8f0")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
            flowables.append(table)
            flowables.append(Spacer(1, 10))
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            if level == 1:
                flowables.append(PageBreak())
                flowables.append(Paragraph(inline_markup(text), styles["H1"]))
                toc_entries.append((0, text, flowables[-1]))
            elif level == 2:
                flowables.append(Paragraph(inline_markup(text), styles["H2"]))
                toc_entries.append((1, text, flowables[-1]))
            elif level == 3:
                flowables.append(Paragraph(inline_markup(text), styles["H3"]))
            else:
                flowables.append(Paragraph(inline_markup(text), styles["H4"]))
            i += 1
            continue

        bullet_match = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if bullet_match:
            flush_paragraph()
            indent = len(bullet_match.group(1))
            text = bullet_match.group(2)
            style = styles["ManualBulletL2"] if indent >= 2 else styles["ManualBullet"]
            flowables.append(Paragraph(inline_markup(text), style, bulletText="\u2022"))
            i += 1
            continue

        ordered_match = _ORDERED_RE.match(stripped)
        if ordered_match:
            flush_paragraph()
            number, text = ordered_match.groups()
            flowables.append(Paragraph(inline_markup(text), styles["ManualBullet"], bulletText=f"{number}."))
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            text = stripped.lstrip(">").strip()
            flowables.append(Paragraph(inline_markup(text), styles["ManualQuote"]))
            i += 1
            continue

        paragraph_buffer.append(stripped)
        i += 1

    flush_paragraph()
    return flowables


# ---------------------------------------------------------------------------
# Page template: header/footer + page numbers
# ---------------------------------------------------------------------------
class NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if total_pages > 1 and self._pageNumber > 1:
                self._draw_footer(total_pages)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_footer(self, total_pages: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#888888"))
        self.drawString(MARGIN, 0.55 * inch, "RAG Knowledge Base & Retrieval -- Implementation Manual")
        self.drawRightString(PAGE_WIDTH - MARGIN, 0.55 * inch, f"Page {self._pageNumber - 1} of {total_pages - 1}")
        self.restoreState()


def build() -> None:
    doc = BaseDocTemplate(
        str(OUTPUT_PATH),
        pagesize=LETTER,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="RAG Knowledge Base and Retrieval -- Implementation Manual",
        author="AI IT Helpdesk Agent -- Phase 7",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    toc_entries: list = []
    story: list = []

    story.append(Spacer(1, 2.4 * inch))
    story.append(Paragraph(TITLE, styles["ManualTitle"]))
    story.append(Paragraph(SUBTITLE, styles["ManualSubtitle"]))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Design, implementation, testing, and evaluation of the RAG knowledge base built for this project.", styles["ManualSubtitle"]))

    story.append(PageBreak())
    story.append(Paragraph("Table of Contents", styles["H1"]))
    toc = TableOfContents()
    toc.levelStyles = [styles["TOC1"], styles["TOC2"]]
    story.append(toc)

    chapter_files = sorted(CHAPTERS_DIR.glob("*.md"))
    if not chapter_files:
        raise SystemExit(f"No chapter files found in {CHAPTERS_DIR}")

    for chapter_file in chapter_files:
        text = chapter_file.read_text(encoding="utf-8")
        story.extend(parse_markdown_to_flowables(text, toc_entries))

    # afterFlowable() below reads heading text off each Paragraph's own
    # style name (H1/H2) rather than off toc_entries, so TOC entries are
    # collected as a side effect of parsing but the real registration
    # happens per-flowable during doc.multiBuild()'s rendering passes.

    def after_flowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style_name = flowable.style.name
            text = flowable.getPlainText()
            if style_name == "H1":
                self.notify("TOCEntry", (0, text, self.page))
                self.canv.bookmarkPage(text)
                self.canv.addOutlineEntry(text, text, level=0)
            elif style_name == "H2":
                self.notify("TOCEntry", (1, text, self.page))

    BaseDocTemplate.afterFlowable = after_flowable

    doc.multiBuild(story, canvasmaker=NumberedCanvas)
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
