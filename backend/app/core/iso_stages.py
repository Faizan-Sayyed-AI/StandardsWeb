"""
ISO lifecycle stage helpers.

ISO stage codes are "major.minor" strings (e.g. "30.00", "60.60"). The major
number tracks the lifecycle: 10-50 are pre-publication drafts, 60 is
publication, 90 is periodic review, 95 is withdrawal.

Kept dependency-free and in core/ rather than importing from
app/tasks/feeds.py, which holds the full stage tables but is a Celery task
module that services must not import.
"""

# First published stage. Anything below this has no purchasable document.
_FIRST_PUBLISHED_MAJOR = 60


def is_draft_stage(stage_code: str | None) -> bool:
    """
    True when the stage code is pre-publication (major < 60).

    An absent or unparseable stage code returns False — manually created
    standards carry no stage code and must not be silently locked out of
    upload and purchase.
    """
    if not stage_code:
        return False
    try:
        major = int(str(stage_code).split(".")[0])
    except (ValueError, IndexError):
        return False
    return major < _FIRST_PUBLISHED_MAJOR
