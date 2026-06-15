"""
Email delivery helper.

In M1 this is a stub that logs emails instead of sending them.
In M5 this will be replaced with a real aiosmtplib implementation.
"""

import structlog

log = structlog.get_logger(__name__)


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str = "",
) -> None:
    """
    Send a transactional email.

    M1 stub: logs the email details; does NOT connect to SMTP.
    Replace the body of this function in M5 with the aiosmtplib send call.
    """
    log.info(
        "email_mock_send",
        to=to,
        subject=subject,
        html_preview=html_body[:120].replace("\n", " "),
    )


async def send_password_reset_email(to: str, reset_token: str) -> None:
    """
    Send a password reset link email.

    M1 stub: logs the token instead of emailing it.
    """
    reset_url = f"http://localhost:5173/reset-password?token={reset_token}"
    log.info(
        "password_reset_email_mock",
        to=to,
        reset_url=reset_url,
        note="Copy the reset_url from this log to complete the password reset in dev.",
    )
