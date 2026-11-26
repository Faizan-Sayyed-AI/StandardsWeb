"""
Pure rendering for the weekly digest email (no I/O, easy to test).

Input is a list of sections — one per event type, in display order — each with
the standards that had that event this period. A standard that changed several
times is shown once with a change count.
"""

from dataclasses import dataclass
from html import escape

# Display order and labels. document_uploaded is deliberately absent: it never
# enters the digest (see EMAIL_DIGEST_EXCLUDED_EVENT_TYPES).
SECTION_ORDER: list[tuple[str, str]] = [
    ("withdrawn", "Withdrawn"),
    ("replaced", "Replaced"),
    ("new", "New standards"),
    ("updated", "Updated"),
    ("amended", "Amended"),
    ("status_change", "Status changes"),
    ("purchased", "Purchased"),
]

# The email body is a short preview; the attached PDF lists everything.
MAX_PER_SECTION = 5


@dataclass
class DigestItem:
    standard_id: str
    iso_reference: str
    title: str
    status: str
    count: int  # how many times this event hit this standard in the period
    edition: str = ""
    committee: str = ""


@dataclass
class DigestSection:
    event_type: str
    label: str
    items: list[DigestItem]  # already deduplicated; may exceed MAX_PER_SECTION


def _status(value: object) -> str:
    return str(getattr(value, "value", value) or "").upper()


def render_digest(
    *,
    recipient_name: str,
    sections: list[DigestSection],
    frontend_url: str,
    period_label: str,
) -> tuple[str, str, int]:
    """Return (html, text, total_standard_count)."""
    total = sum(len(s.items) for s in sections)
    base = frontend_url.rstrip("/")

    html_sections = []
    text_sections = []
    for sec in sections:
        shown = sec.items[:MAX_PER_SECTION]
        hidden = len(sec.items) - len(shown)

        rows = ""
        lines = []
        for it in shown:
            url = f"{base}/standards/{it.standard_id}"
            times = f" &middot; {it.count} changes" if it.count > 1 else ""
            rows += (
                '<tr><td style="padding:10px 12px;border-bottom:1px solid #d9dce3;">'
                f'<a href="{escape(url)}" style="color:#2557a7;font-weight:600;text-decoration:none;">'
                f"{escape(it.iso_reference)}</a>"
                f'<span style="color:#5a6272;font-size:12px;"> &middot; {escape(it.status)}{times}</span>'
                f'<div style="color:#131825;font-size:14px;margin-top:2px;">{escape(it.title)}</div>'
                "</td></tr>"
            )
            lines.append(
                f"  - {it.iso_reference} [{it.status}"
                f"{f', {it.count} changes' if it.count > 1 else ''}] {it.title}\n    {url}"
            )
        if hidden:
            rows += (
                '<tr><td style="padding:10px 12px;color:#5a6272;font-size:13px;">'
                f"...and {hidden} more in the attached PDF. "
                f'<a href="{escape(base)}/standards" style="color:#2557a7;">Open the dashboard</a>'
                "</td></tr>"
            )
            lines.append(f"  ...and {hidden} more in the attached PDF: {base}/standards")

        html_sections.append(
            '<table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top:24px;">'
            '<tr><td style="background-color:#efcb48;padding:9px 12px;font-size:14px;font-weight:700;color:#131825;">'
            f'{escape(sec.label)} <span style="font-weight:500;">({len(sec.items)})</span></td></tr>'
            f'{rows}</table>'
        )
        text_sections.append(f"{sec.label} ({len(sec.items)})\n" + "\n".join(lines))

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>StandardSphere weekly digest</title></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background-color:#fcfcfc;color:#131825;">
<table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#fcfcfc;padding:40px 20px;"><tr><td align="center">
<table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff;border:1px solid #d9dce3;border-top:6px solid #efcb48;">
<tr><td style="padding:28px 32px 0 32px;">
<h1 style="color:#131825;font-size:22px;margin:0;">StandardSphere</h1>
<p style="color:#5a6272;font-size:14px;margin:6px 0 0 0;">Weekly standards digest &middot; {escape(period_label)}</p></td></tr>
<tr><td style="padding:32px;">
<p style="font-size:16px;margin-top:0;">Hello {escape(recipient_name)},</p>
<p style="font-size:15px;color:#131825;">{total} standard{'s' if total != 1 else ''} had updates since the last digest. The full report with a link to every standard is attached as a PDF.</p>
{''.join(html_sections)}
<p style="margin-top:32px;text-align:center;"><a href="{escape(base)}" style="background-color:#efcb48;color:#131825;text-decoration:none;padding:12px 28px;border-radius:6px;font-weight:600;display:inline-block;">Open dashboard</a></p>
</td></tr>
<tr><td style="background-color:#f0f1f5;padding:20px;text-align:center;border-top:1px solid #d9dce3;">
<p style="font-size:12px;color:#5a6272;margin:0;">Automated digest from StandardSphere. You receive it because your email is mapped to these lifecycle events.</p>
</td></tr></table></td></tr></table></body></html>"""

    text = (
        f"Hello {recipient_name},\n\n"
        f"StandardSphere weekly digest ({period_label}) - {total} standard"
        f"{'s' if total != 1 else ''} had updates. The full report is attached as a PDF.\n\n"
        + "\n\n".join(text_sections)
        + f"\n\nDashboard: {base}\n\n--\nAutomated digest from StandardSphere.\n"
    )
    return html, text, total
