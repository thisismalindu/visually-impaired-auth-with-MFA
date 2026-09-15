from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "submissions" / "member1" / "member1-design-contribution.md"
OUTPUT = REPO / "output" / "pdf" / "member1-design-contribution.pdf"
PREVIEWS = REPO / "tmp" / "pdfs" / "diagram-previews"


def register_fonts() -> tuple[str, str, str]:
    font_dir = Path("C:/Windows/Fonts")
    regular = font_dir / "arial.ttf"
    bold = font_dir / "arialbd.ttf"
    mono = font_dir / "consola.ttf"
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("DocSans", str(regular)))
        pdfmetrics.registerFont(TTFont("DocSans-Bold", str(bold)))
        body_font, bold_font = "DocSans", "DocSans-Bold"
    else:
        body_font, bold_font = "Helvetica", "Helvetica-Bold"
    if mono.exists():
        pdfmetrics.registerFont(TTFont("DocMono", str(mono)))
        mono_font = "DocMono"
    else:
        mono_font = "Courier"
    return body_font, bold_font, mono_font


BODY_FONT, BOLD_FONT, MONO_FONT = register_fonts()


def ascii_punctuation(value: str) -> str:
    return (
        value.replace("—", "-")
        .replace("–", "-")
        .replace("‑", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
    )


def inline_markup(value: str) -> str:
    value = ascii_punctuation(value.strip())
    escaped = html.escape(value)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"_(Source:.*?)_", r"<i>\1</i>", escaped)
    escaped = re.sub(
        r"`([^`]+)`",
        rf'<font name="{MONO_FONT}" size="8.2">\1</font>',
        escaped,
    )
    return escaped


def styles():
    sample = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=sample["BodyText"],
        fontName=BODY_FONT,
        fontSize=9.5,
        leading=13.2,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=5,
        alignment=TA_LEFT,
    )
    return {
        "title": ParagraphStyle(
            "Title",
            parent=body,
            fontName=BOLD_FONT,
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#153b66"),
            spaceAfter=15,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=body,
            fontName=BOLD_FONT,
            fontSize=14,
            leading=17,
            textColor=colors.HexColor("#153b66"),
            spaceBefore=11,
            spaceAfter=6,
            keepWithNext=False,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=body,
            fontName=BOLD_FONT,
            fontSize=11.5,
            leading=14,
            textColor=colors.HexColor("#24598c"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=False,
        ),
        "body": body,
        "meta": ParagraphStyle(
            "Meta",
            parent=body,
            fontSize=9.7,
            leading=14,
            spaceAfter=2,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=body,
            fontSize=8.2,
            leading=11,
            textColor=colors.HexColor("#475569"),
            alignment=TA_CENTER,
            spaceBefore=5,
            spaceAfter=10,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=body,
            fontSize=9,
            leading=12,
            leftIndent=8,
            rightIndent=8,
            borderColor=colors.HexColor("#d59b16"),
            borderWidth=0.7,
            borderPadding=7,
            backColor=colors.HexColor("#fff8dc"),
            spaceBefore=7,
            spaceAfter=9,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=body,
            fontName=MONO_FONT,
            fontSize=7.8,
            leading=10.5,
            leftIndent=8,
            rightIndent=8,
            borderColor=colors.HexColor("#cbd5e1"),
            borderWidth=0.5,
            borderPadding=7,
            backColor=colors.HexColor("#f8fafc"),
            spaceBefore=4,
            spaceAfter=8,
        ),
        "table": ParagraphStyle(
            "TableCell",
            parent=body,
            fontSize=7.7,
            leading=10.2,
            spaceAfter=0,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            parent=body,
            fontName=BOLD_FONT,
            fontSize=8,
            leading=10.5,
            textColor=colors.white,
            spaceAfter=0,
        ),
    }


STYLES = styles()


def is_special(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith("#")
        or stripped.startswith("```")
        or stripped.startswith("> ")
        or bool(re.match(r"!\[.*\]\(.*\)", stripped))
        or stripped.startswith("|")
        or bool(re.match(r"[-*] ", stripped))
        or bool(re.match(r"\d+\. ", stripped))
    )


def table_widths(rows: list[list[str]], available: float) -> list[float]:
    count = len(rows[0])
    if count == 2:
        return [available * 0.34, available * 0.66]
    if count == 3:
        return [available * 0.25, available * 0.48, available * 0.27]
    return [available / count] * count


def make_table(raw_rows: list[str], available: float) -> Table:
    parsed = []
    for raw in raw_rows:
        cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        parsed.append(cells)
    column_count = max(len(row) for row in parsed)
    parsed = [row + [""] * (column_count - len(row)) for row in parsed]
    data = []
    for row_index, row in enumerate(parsed):
        style = STYLES["table_head"] if row_index == 0 else STYLES["table"]
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    table = Table(
        data,
        colWidths=table_widths(parsed, available),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24598c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#aebdca")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def image_flowable(relative_svg: str, available: float) -> Image:
    png_name = Path(relative_svg).with_suffix(".png").name
    png_path = PREVIEWS / png_name
    with PILImage.open(png_path) as source:
        width_px, height_px = source.size
    width = min(available, 178 * mm)
    height = width * height_px / width_px
    return Image(str(png_path), width=width, height=height, hAlign="CENTER")


def parse_markdown() -> list:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    story = []
    available = A4[0] - 36 * mm
    i = 0
    first_title = True
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(ascii_punctuation(lines[i]))
                i += 1
            i += 1
            code_block = Preformatted("\n".join(code_lines), STYLES["code"])
            story.append(CondPageBreak(min(len(code_lines), 24) * 10.5 + 24))
            story.append(KeepTogether([code_block]))
            continue

        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image_match:
            figure = image_flowable(image_match.group(2), available)
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            caption = None
            if i < len(lines) and lines[i].strip().startswith("**Figure"):
                caption = Paragraph(inline_markup(lines[i]), STYLES["caption"])
                i += 1
            required = figure.drawHeight + 18 * mm
            story.append(CondPageBreak(required))
            story.append(KeepTogether([figure, caption] if caption else [figure]))
            continue

        if stripped.startswith("# "):
            style = STYLES["title"] if first_title else STYLES["h2"]
            story.append(Paragraph(inline_markup(stripped[2:]), style))
            first_title = False
            i += 1
            continue

        if stripped.startswith("**") and i < 15:
            story.append(Paragraph(inline_markup(stripped), STYLES["meta"]))
            i += 1
            continue

        if stripped.startswith("## "):
            heading = stripped[3:]
            story.append(Paragraph(inline_markup(heading), STYLES["h2"]))
            story.append(Spacer(1, 2))
            i += 1
            continue

        if stripped.startswith("### "):
            story.append(Paragraph(inline_markup(stripped[4:]), STYLES["h3"]))
            story.append(Spacer(1, 8))
            i += 1
            continue

        if stripped.startswith("> "):
            story.append(Paragraph(inline_markup(stripped[2:]), STYLES["quote"]))
            i += 1
            continue

        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            story.append(Spacer(1, 3))
            story.append(make_table(rows, available))
            story.append(Spacer(1, 7))
            continue

        bullet_match = re.match(r"[-*] (.+)", stripped)
        if bullet_match:
            items = []
            while i < len(lines):
                match = re.match(r"[-*] (.+)", lines[i].strip())
                if not match:
                    break
                items.append([
                    Paragraph("&#8226;", STYLES["body"]),
                    Paragraph(inline_markup(match.group(1)), STYLES["body"]),
                ])
                i += 1
            list_table = Table(items, colWidths=[12, available - 12], hAlign="LEFT")
            list_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            story.append(list_table)
            story.append(Spacer(1, 3))
            continue

        number_match = re.match(r"\d+\. (.+)", stripped)
        if number_match:
            items = []
            while i < len(lines):
                match = re.match(r"\d+\. (.+)", lines[i].strip())
                if not match:
                    break
                number = lines[i].strip().split(".", 1)[0]
                items.append([
                    Paragraph(number + ".", STYLES["body"]),
                    Paragraph(inline_markup(match.group(1)), STYLES["body"]),
                ])
                i += 1
            list_table = Table(items, colWidths=[18, available - 18], hAlign="LEFT")
            list_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(list_table)
            story.append(Spacer(1, 3))
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines) and not is_special(lines[i]):
            paragraph_lines.append(lines[i].strip())
            i += 1
        text = " ".join(paragraph_lines)
        style = STYLES["meta"] if text.startswith("**") and i < 16 else STYLES["body"]
        story.append(Paragraph(inline_markup(text), style))

    return story


def add_page_number(canvas, doc):
    canvas.saveState()
    page = canvas.getPageNumber()
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.setFont(BODY_FONT, 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(18 * mm, 9.5 * mm, "Individual Design Contribution - Member 1")
    canvas.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"Page {page}")
    canvas.restoreState()


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title="Individual Design Contribution - Member 1",
        author="Member 1",
        subject="Accessible MFA group project",
    )
    document.build(parse_markdown(), onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(OUTPUT)


if __name__ == "__main__":
    main()
