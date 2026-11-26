"""Pure tests for the weekly digest: slot scheduling and rendering."""

from datetime import datetime, timezone

from app.core.email_digest_template import (
    MAX_PER_SECTION,
    DigestItem,
    DigestSection,
    render_digest,
)
from app.services.email_digest_service import due_slot_key

KW = dict(days="mon,thu", hour=11, tz_name="Asia/Kolkata")


def utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_monday_1100_ist_is_a_slot():
    # 2026-11-23 is a Monday; 11:00 IST == 05:30 UTC
    assert due_slot_key(utc(2026, 11, 23, 5, 30), **KW) == "2026-11-23"


def test_before_1100_ist_is_not_a_slot():
    assert due_slot_key(utc(2026, 11, 23, 5, 29), **KW) is None


def test_catches_up_later_the_same_day():
    assert due_slot_key(utc(2026, 11, 23, 12, 0), **KW) == "2026-11-23"


def test_thursday_is_a_slot_and_tuesday_is_not():
    assert due_slot_key(utc(2026, 11, 26, 6, 0), **KW) == "2026-11-26"  # Thursday
    assert due_slot_key(utc(2026, 11, 24, 6, 0), **KW) is None  # Tuesday


def test_day_is_decided_in_local_time_not_utc():
    # Sunday 22:00 UTC is already Monday 03:30 IST — before the hour, so no slot.
    assert due_slot_key(utc(2026, 11, 22, 22, 0), **KW) is None
    # Monday 20:00 UTC is Tuesday 01:30 IST — wrong day.
    assert due_slot_key(utc(2026, 11, 23, 20, 0), **KW) is None


def _item(i, count=1):
    return DigestItem(f"id-{i}", f"ISO {i}", f"Title <{i}>", "PUBLISHED", count)


def test_render_groups_escapes_and_counts():
    html, text, total = render_digest(
        recipient_name="Ann & Bob",
        sections=[DigestSection("new", "New standards", [_item(1), _item(2, count=3)])],
        frontend_url="https://example.test/",
        period_label="26 Nov 2026",
    )
    assert total == 2
    assert "Ann &amp; Bob" in html
    assert "Title &lt;1&gt;" in html  # HTML-escaped
    assert "3 changes" in html
    assert "https://example.test/standards/id-1" in html
    assert "https://example.test//" not in html  # no double slash
    assert "ISO 2" in text


def test_render_caps_long_sections():
    items = [_item(i) for i in range(MAX_PER_SECTION + 7)]
    html, text, total = render_digest(
        recipient_name="x",
        sections=[DigestSection("updated", "Updated", items)],
        frontend_url="https://example.test",
        period_label="p",
    )
    assert total == MAX_PER_SECTION + 7
    assert "and 7 more in the attached PDF" in html
    assert "and 7 more in the attached PDF" in text


def test_pdf_has_clickable_links_and_lists_everything():
    from app.core.email_digest_pdf import build_digest_pdf

    items = [_item(i) for i in range(MAX_PER_SECTION + 7)]
    pdf = build_digest_pdf(
        recipient_name="Ann",
        sections=[DigestSection("updated", "Updated", items)],
        frontend_url="https://example.test/",
        period_label="26 Nov 2026",
    )
    assert pdf.startswith(b"%PDF")
    # link annotations point at the app (uncompressed URIs appear in the annots)
    assert b"https://example.test/standards/id-0" in pdf
    assert f"https://example.test/standards/id-{MAX_PER_SECTION + 6}".encode() in pdf  # no cap
    assert b"example.test//" not in pdf
