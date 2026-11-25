"""Reusable email service using Brevo HTTPS API in production and optional Gmail SMTP in development."""

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import smtplib
from fastapi import HTTPException, status
import httpx

from app.core.config import get_settings

logger = logging.getLogger("academyflow.email")

BREVO_SMTP_API_URL = "https://api.brevo.com/v3/smtp/email"


def _build_otp_html(otp: str, purpose: str = "register") -> str:
    heading = (
        "Verify Your Email"
        if purpose == "register"
        else "Verify Password Reset"
    )
    return f"""
    <!DOCTYPE html>
    <html>
      <body style="margin:0;padding:0;background-color:#f8fafc;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 16px;">
          <tr>
            <td align="center">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;">
                <tr>
                  <td style="background:#4f46e5;padding:24px 28px;color:#ffffff;">
                    <h1 style="margin:0;font-size:20px;font-weight:700;">
                      AcademyFlow
                    </h1>
                    <p style="margin:6px 0 0;font-size:13px;color:#e0e7ff;">
                      {heading}
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:28px;">
                    <p style="margin:0 0 12px;font-size:15px;font-weight:600;color:#334155;">
                      Your verification OTP is:
                    </p>
                    <div style="margin:12px 0 20px;padding:16px;background:#f1f5f9;border:1px dashed #6366f1;border-radius:10px;text-align:center;">
                      <span style="font-size:32px;font-weight:800;letter-spacing:8px;color:#312e81;">
                        {otp}
                      </span>
                    </div>
                    <p style="margin:0 0 8px;font-size:14px;color:#334155;">
                      This OTP will expire in 5 minutes.
                    </p>
                    <p style="margin:0 0 8px;font-size:13px;color:#475569;">
                      Do not share this OTP with anyone.
                    </p>
                    <p style="margin:0 0 20px;font-size:13px;color:#64748b;">
                      If you did not request this verification, ignore this email.
                    </p>
                    <p style="margin:0;font-size:13px;color:#334155;">
                      Regards,<br />
                      <strong>AcademyFlow Team</strong>
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


async def _send_via_brevo(
    recipient_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    settings = get_settings()
    sender_email = settings.SMTP_FROM_EMAIL.strip()
    sender_name = settings.SMTP_FROM_NAME.strip() or "AcademyFlow"

    if not sender_email:
        logger.error("BREVO_API_KEY is set, but SMTP_FROM_EMAIL is missing.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email sender address is not configured.",
        )

    logger.info("Sending OTP through Brevo")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                BREVO_SMTP_API_URL,
                headers={
                    "api-key": settings.BREVO_API_KEY.strip(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "sender": {"name": sender_name, "email": sender_email},
                    "to": [{"email": recipient_email}],
                    "subject": subject,
                    "htmlContent": html_body,
                    "textContent": text_body,
                },
            )
    except httpx.RequestError as exc:
        logger.error("Brevo HTTPS request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send OTP right now. Please try again.",
        ) from exc

    if resp.status_code >= 400:
        logger.error(
            "Brevo API returned HTTP %s: %s",
            resp.status_code,
            resp.text[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send OTP right now. Please try again.",
        )

    logger.info("Brevo email request successful")


def _send_smtp_sync(
    recipient_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    settings = get_settings()
    from_email = settings.SMTP_FROM_EMAIL.strip() or settings.SMTP_USERNAME.strip()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = recipient_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, 465, timeout=20) as server:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(from_email, [recipient_email], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(from_email, [recipient_email], msg.as_string())
    except Exception as exc:
        logger.error("Development SMTP send failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send OTP right now. Please try again.",
        ) from exc


async def send_otp_email(
    recipient_email: str,
    otp: str,
    purpose: str = "register",
) -> None:
    """Send a 6-digit OTP email via Brevo HTTPS API (primary) or local dev SMTP fallback."""
    settings = get_settings()
    subject = (
        "AcademyFlow - Email Verification OTP"
        if purpose == "register"
        else "AcademyFlow - Password Reset OTP"
    )
    text_body = (
        "AcademyFlow\n"
        "Verify Your Email\n\n"
        f"Your verification OTP is:\n{otp}\n\n"
        "This OTP will expire in 5 minutes.\n"
        "Do not share this OTP with anyone.\n"
        "If you did not request this verification, ignore this email.\n\n"
        "Regards,\n"
        "AcademyFlow Team"
    )
    html_body = _build_otp_html(otp, purpose=purpose)

    if settings.BREVO_API_KEY.strip():
        await _send_via_brevo(recipient_email, subject, html_body, text_body)
        logger.info("OTP email sent successfully")
        return

    if settings.SMTP_USERNAME.strip() and settings.SMTP_PASSWORD.strip():
        logger.info("Sending OTP through development Gmail SMTP")
        await asyncio.to_thread(_send_smtp_sync, recipient_email, subject, html_body, text_body)
        logger.info("OTP email sent successfully")
        return

    logger.error("Email provider is not configured (BREVO_API_KEY missing).")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Email service is not configured. Please configure BREVO_API_KEY.",
    )
