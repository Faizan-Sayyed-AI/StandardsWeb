"""
PDF report for the weekly digest.

One document per recipient, listing every standard (no cap) grouped by event
type. Each reference and each "View" cell is a clickable link to
{FRONTEND_URL}/standards/{id}. Built in memory with reportlab (pure Python).
"""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.email_digest_template import DigestSection

TEAL = colors.HexColor("#0f766e")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")


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
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=11, textColor=SLATE)
    head = ParagraphStyle(
        "head", parent=body, fontName="Helvetica-Bold", textColor=colors.white
    )
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, textColor=TEAL, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#0f172a"),
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

    story = [
        Paragraph("StandardSphere weekly digest", h1),
        Paragraph(
            f"{escape(period_label)} &nbsp;|&nbsp; Prepared for {escape(recipient_name)} "
            f"&nbsp;|&nbsp; {total} standard{'s' if total != 1 else ''} with updates",
            sub,
        ),
        Spacer(1, 4),
        Paragraph(f'<link href="{escape(base)}" color="#0f766e">Open the StandardSphere dashboard</link>', body),
        Spacer(1, 8),
    ]

    # Summary table: counts per event type
    summary = [[_p("Event", head), _p("Standards", head)]]
    for sec in sections:
        summary.append([_p(sec.label, body), _p(str(len(sec.items)), body)])
    t = Table(summary, colWidths=[70 * mm, 30 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
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
            link = f'<link href="{escape(url)}" color="#0f766e">{escape(it.iso_reference)}</link>'
            view = f'<link href="{escape(url)}" color="#0f766e"><u>View</u></link>'
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
            ("BACKGROUND", (0, 0), (-1, 0), TEAL),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
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
