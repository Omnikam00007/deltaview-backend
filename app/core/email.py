"""
Email utility for sending transactional emails (e.g. password reset).
Uses aiosmtplib for async SMTP delivery.
Falls back to logging the email content when SMTP is not configured.
"""
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an HTML email. Returns True on success."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            "SMTP not configured — printing email to logs.\n"
            "To: %s\nSubject: %s\n%s",
            to, subject, html_body,
        )
        return True  # treat as success in dev

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("Email sent to %s", to)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def build_password_reset_email(reset_link: str) -> str:
    """Return a styled HTML email body for password reset."""
    return f"""\
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f0f23; color: #e2e8f0; margin: 0; padding: 0; }}
    .container {{ max-width: 520px; margin: 40px auto; background: #1a1a2e; border-radius: 12px; padding: 40px; border: 1px solid #2d2d44; }}
    h1 {{ color: #818cf8; font-size: 24px; margin-bottom: 8px; }}
    p {{ color: #94a3b8; line-height: 1.6; font-size: 15px; }}
    .btn {{ display: inline-block; background: linear-gradient(135deg, #6366f1, #818cf8); color: #fff !important;
             text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 15px;
             margin: 24px 0; }}
    .footer {{ font-size: 12px; color: #475569; margin-top: 32px; border-top: 1px solid #2d2d44; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Reset Your Password</h1>
    <p>We received a request to reset your DeltaView account password. Click the button below to set a new password.</p>
    <a class="btn" href="{reset_link}">Reset Password</a>
    <p>This link will expire in <strong>{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes</strong>.</p>
    <p>If you didn't request this, you can safely ignore this email.</p>
    <div class="footer">
      &copy; {settings.APP_NAME} &mdash; Portfolio Intelligence for Indian Investors
    </div>
  </div>
</body>
</html>"""
