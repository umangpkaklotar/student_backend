"""Reusable Gmail SMTP email service for sending verification OTPs."""

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from fastapi import HTTPException, status

from app.core.config import get_settings


def _build_otp_html(otp: str, purpose: str = "register") -> str:
    heading = (
        "Email Verification OTP"
        if purpose == "register"
        else "Password Reset Verification OTP"
    )
    subtitle = (
        "Thank you for registering with the Student Attendance & Fee Management System."
        if purpose == "register"
        else "We received a request to reset your account password."
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
                      Student Attendance &amp; Fee Management System
                    </h1>
                    <p style="margin:6px 0 0;font-size:13px;color:#e0e7ff;">
                      {heading}
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:28px;">
                    <p style="margin:0 0 16px;font-size:15px;line-height:1.5;color:#334155;">
                      {subtitle}
                    </p>
                    <p style="margin:0 0 10px;font-size:14px;font-weight:600;color:#475569;">
                      Your verification OTP is:
                    </p>
                    <div style="margin:12px 0 20px;padding:16px;background:#f1f5f9;border:1px dashed #6366f1;border-radius:10px;text-align:center;">
                      <span style="font-size:32px;font-weight:800;letter-spacing:8px;color:#312e81;">
                        {otp}
                      </span>
                    </div>
                    <p style="margin:0 0 8px;font-size:14px;color:#334155;">
                      <strong>OTP expires in 5 minutes.</strong>
                    </p>
                    <p style="margin:0;font-size:13px;color:#64748b;">
                      Do not share this OTP with anyone. If you did not request this, you can safely ignore this email.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8;">
                    Karate &amp; Skating Student Portal
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def _send_smtp_sync(recipient_email: str, otp: str, purpose: str) -> None:
    settings = get_settings()
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured. Set SMTP_USERNAME and SMTP_PASSWORD (Gmail App Password) in backend/.env.",
        )

    from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        "Verify Your Email - Student Attendance & Fee Management System"
        if purpose == "register"
        else "Password Reset OTP - Student Attendance & Fee Management System"
    )
    msg["From"] = from_email
    msg["To"] = recipient_email

    text_body = (
        "Student Attendance & Fee Management System\n\n"
        f"Your verification OTP is:\n{otp}\n\n"
        "OTP expires in 5 minutes.\n"
        "Do not share this OTP with anyone."
    )
    html_body = _build_otp_html(otp, purpose=purpose)
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(from_email, [recipient_email], msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SMTP authentication failed. Ensure you are using a valid Gmail App Password.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to send verification email right now. Please try again shortly.",
        ) from exc


async def send_otp_email(email: str, otp: str, purpose: str = "register") -> None:
    """Send a 6-digit OTP email asynchronously using Gmail SMTP."""
    await asyncio.to_thread(_send_smtp_sync, email, otp, purpose)
