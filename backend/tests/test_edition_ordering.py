"""
Pins the edition-ordering SQL in standard_service.

This is the logic that decides which edition of a standard the library shows —
if it regresses, every list, every dashboard KPI and the version hierarchy all
show the wrong row, silently and plausibly. The expressions are pure functions
of `edition`, `iso_reference` and `published_date`, so they can be evaluated
directly against an inline VALUES clause: no rows are inserted and no table is
touched.

Each expression is fed the reference shapes that actually occur in the data —
a year in `edition`, a year only in the reference, an amendment suffix, a
designation with no year at all (ASTM/IEC/ANSI), an edition *number* rather
than a year, and blank/whitespace editions.
"""

from datetime import date

import pytest
from sqlalchemy import Date, Integer, String, column, select, values

from app.services.standard_service import (
    _edition_year_sql,
    _has_edition_sql,
    _is_amendment_sql,
    _version_order_sql,
)


class _Probe:
    """
    Duck-types the two or four Standard attributes the ordering helpers read.

    The helpers take an `entity` and only touch attributes, never the mapper, so
    pointing those attributes at the columns of a VALUES clause evaluates the
    real expression tree against literal rows.
    """

    def __init__(self, source):
        self.id = source.c.id
        self.edition = source.c.edition
        self.iso_reference = source.c.iso_reference
        self.published_date = source.c.published_date


def _probe(rows):
    """(probe, source) for rows of (id, edition, iso_reference, published_date)."""
    source = values(
        column("id", Integer),
        column("edition", String),
        column("iso_reference", String),
        column("published_date", Date),
        name="probe",
    ).data(rows)
    return _Probe(source), source


async def _eval(db, expr, rows):
    """Evaluate `expr(probe)` once per row, in row order."""
    probe, source = _probe(rows)
    result = await db.execute(select(expr(probe)).select_from(source).order_by(probe.id))
    return [r[0] for r in result.all()]


@pytest.mark.parametrize(
    ("edition", "iso_reference", "expected"),
    [
        # The edition column carries the year — the common case.
        ("2015", "ISO 9001:2015", 2015),
        # No edition column; the year comes from the reference.
        (None, "ISO 10993-1:2025", 2025),
        ("", "ISO 10993-1:2025", 2025),
        # An amendment takes the BASE edition's year (the first one), which is
        # what groups it with the edition it amends rather than with 2024.
        (None, "ISO 9001:2015/AMD 1:2024", 2015),
        # Designations with no year anywhere — many ASTM/IEC/ANSI references.
        # NULL, so _version_order_sql sorts them last rather than first.
        (None, "ASTM A313", None),
        ("", "ASTM A313", None),
        # `edition` holding an edition NUMBER, not a year. Four digits are
        # required, so "3" is not mistaken for one and the reference year wins.
        ("3", "ISO 13485:2016", 2016),
        # Neither source usable.
        ("3", "ASTM A313", None),
        # A four-digit year embedded in a longer edition string still reads.
        ("Edition 4, 2018", "ASTM A313", 2018),
    ],
)
async def test_edition_year(db, edition, iso_reference, expected):
    assert await _eval(db, _edition_year_sql, [(1, edition, iso_reference, None)]) == [expected]


@pytest.mark.parametrize(
    ("iso_reference", "expected"),
    [
        # Amendments and corrigenda: anchored on ":<year>/".
        ("ISO 4287:1997/AMD 1:2009", 1),
        ("ISO 9001:2015/COR 1:2016", 1),
        ("ISO 5817:2014/DAMD 1:2020", 1),
        # A bare "/" that is a designation prefix, not an amendment. This is
        # what the ":<year>/" anchor exists to exclude.
        ("ISO/TS 6892-5", 0),
        ("ISO/CD 12111", 0),
        ("ISO/IEC 27001:2022", 0),
        ("ISO 9001:2015", 0),
    ],
)
async def test_is_amendment(db, iso_reference, expected):
    assert await _eval(db, _is_amendment_sql, [(1, None, iso_reference, None)]) == [expected]


@pytest.mark.parametrize(
    ("edition", "expected"),
    [
        ("2015", True),
        # NULL, empty and whitespace-only all count as missing, so a blank
        # imported edition is not treated as a present one.
        (None, False),
        ("", False),
        ("   ", False),
        ("\t", False),
    ],
)
async def test_has_edition(db, edition, expected):
    assert await _eval(db, _has_edition_sql, [(1, edition, "ISO 9001", None)]) == [expected]


async def test_version_order_puts_newest_edition_first(db):
    """
    The whole point of the ordering: newest edition first, amendments under the
    edition they amend, and year-less rows last rather than first.

    published_date is deliberately *inverted* against edition here — the 2018
    edition carries a later stage-change date than the 2025 one, which is
    exactly the production shape that used to decide the ordering and put the
    superseded edition at the top of the list.
    """
    rows = [
        (1, None, "ISO 10993-1:2018", date(2025, 6, 1)),
        (2, None, "ISO 10993-1:2025", date(2025, 1, 1)),
        (3, None, "ISO 10993-1:2018/AMD 1:2020", date(2020, 3, 1)),
        (4, None, "ISO 10993-1", None),
        (5, "2025", "ISO 10993-1/CD", date(2019, 1, 1)),
    ]
    probe, source = _probe(rows)
    result = await db.execute(
        select(probe.id).select_from(source).order_by(*_version_order_sql(probe))
    )
    assert [r[0] for r in result.all()] == [
        2,  # 2025, year from the reference — later stage-change date wins the tie
        5,  # 2025, year from the edition column
        1,  # 2018 base edition…
        3,  # …then the amendment to it, never above it
        4,  # no year anywhere: last, not first
    ]


async def test_version_order_ties_break_on_id(db):
    """
    Two rows identical on every ordering key must still come back in a fixed
    order, or paginated pages overlap and a standard can appear twice or never.
    """
    rows = [
        (2, "2015", "ISO 9001:2015", date(2015, 9, 1)),
        (1, "2015", "ISO 9001:2015", date(2015, 9, 1)),
    ]
    probe, source = _probe(rows)
    result = await db.execute(
        select(probe.id).select_from(source).order_by(*_version_order_sql(probe))
    )
    assert [r[0] for r in result.all()] == [1, 2]
