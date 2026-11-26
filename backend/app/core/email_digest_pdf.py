"""
PDF report for the weekly digest.

One document per recipient, listing every standard (no cap) grouped by event
type. Each reference and each "View" cell is a clickable link to
{FRONTEND_URL}/standards/{id}. Built in memory with reportlab (pure Python).
"""

import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.email_digest_template import DigestSection

# App palette (frontend/src/index.css): gold table headers with dark text,
# brand blue for links, near-black foreground, soft grey borders.
GOLD = colors.HexColor("#efcb48")      # --gold
INK = colors.HexColor("#131825")       # --foreground
MUTED = colors.HexColor("#5a6272")     # --muted-foreground
BRAND = colors.HexColor("#2557a7")     # --brand (links)
LINE = colors.HexColor("#d9dce3")      # --border
ZEBRA = colors.HexColor("#f0f1f5")     # --muted
LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "biorad-medisys.png"
LINK = "#2557a7"


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or "—"), style)


def build_digest_pdf(
    *,
    recipient_name: str,
    sections: list[DigestSection],
    frontend_url: str,
    period_label: str,
) -> bytes:
    base = frontend_url.rstrip("/")
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=11, textColor=INK)
    head = ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", textColor=INK)
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, textColor=INK, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=13, textColor=INK,
        spaceBefore=14, spaceAfter=6,
    )
    sub = ParagraphStyle("sub", parent=body, textColor=MUTED, fontSize=10)

    total = sum(len(s.items) for s in sections)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"StandardSphere weekly digest - {period_label}",
        author="StandardSphere",
    )

    story = []
    if LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH), width=48 * mm, height=48 * mm * 62 / 282)
        logo.hAlign = "LEFT"
        story += [logo, Spacer(1, 6)]
    rule = Table([[""]], colWidths=[258 * mm], rowHeights=[1.6 * mm])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)]))
    story += [
        rule,
        Spacer(1, 6),
        Paragraph("StandardSphere weekly digest", h1),
        Paragraph(
            f"{escape(period_label)} &nbsp;|&nbsp; Prepared for {escape(recipient_name)} "
            f"&nbsp;|&nbsp; {total} standard{'s' if total != 1 else ''} with updates",
            sub,
        ),
        Spacer(1, 4),
        Paragraph(f'<link href="{escape(base)}" color="{LINK}">Open the StandardSphere dashboard</link>', body),
        Spacer(1, 8),
    ]

    # Summary table: counts per event type
    summary = [[_p("Event", head), _p("Standards", head)]]
    for sec in sections:
        summary.append([_p(sec.label, body), _p(str(len(sec.items)), body)])
    t = Table(summary, colWidths=[70 * mm, 30 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GOLD),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)

    cols = [40 * mm, 92 * mm, 34 * mm, 20 * mm, 34 * mm, 20 * mm, 18 * mm]
    for sec in sections:
        story.append(Paragraph(f"{escape(sec.label)} ({len(sec.items)})", h2))
        rows = [[_p(h, head) for h in ("Reference", "Title", "Status", "Edition", "Committee", "Changes", "Link")]]
        for it in sec.items:
            url = f"{base}/standards/{it.standard_id}"
            link = f'<link href="{escape(url)}" color="{LINK}">{escape(it.iso_reference)}</link>'
            view = f'<link href="{escape(url)}" color="{LINK}"><u>View</u></link>'
            rows.append([
                Paragraph(link, body),
                _p(it.title, body),
                _p(it.status.replace("_", " "), body),
                _p(it.edition, body),
                _p(it.committee, body),
                _p(str(it.count), body),
                Paragraph(view, body),
            ])
        tbl = Table(rows, colWidths=cols, repeatRows=1, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GOLD),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)

    def footer(canvas, d):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(14 * mm, 8 * mm, "Automated digest from StandardSphere")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
