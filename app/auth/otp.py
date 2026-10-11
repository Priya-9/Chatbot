"""End-user authentication.

A WhatsApp number alone doesn't prove who owns a customer account, so protected journey steps
(e.g. "My account") ask for the registered email, send a one-time code to that email, and link the
WhatsApp user to the CRM customer for `SESSION_TTL_HOURS` once the code is confirmed.
"""

import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from enum import Enum
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.crm.providers import CRMProvider, CustomerRecord
from app.models import OtpCode, User, as_utc, utcnow

log = logging.getLogger(__name__)


class VerifyResult(Enum):
    OK = "ok"
    INVALID = "invalid"
    EXPIRED = "expired"
    TOO_MANY = "too_many"


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:2] + "•" * max(len(local) - 2, 1)) + "@" + domain


def smtp_delivery(settings: Settings) -> Callable[[str, str], None]:
    def deliver(email: str, code: str) -> None:
        if not settings.smtp_host:
            if settings.is_production:
                raise RuntimeError("SMTP_HOST must be configured to send OTP codes in production")
            log.warning("[DEV] OTP for %s: %s  (configure SMTP_HOST to send real emails)", email, code)
            return
        msg = EmailMessage()
        msg["Subject"] = f"Your {settings.business_name} verification code"
        msg["From"] = settings.smtp_from
        msg["To"] = email
        msg.set_content(
            f"Your verification code is {code}. It expires in {settings.otp_ttl_minutes} minutes.\n"
            "If you didn't request this, you can ignore this email."
        )
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)

    return deliver


class AuthService:
    def __init__(self, settings: Settings, crm: CRMProvider,
                 deliver: Callable[[str, str], None] | None = None):
        self.settings = settings
        self.crm = crm
        self.deliver = deliver or smtp_delivery(settings)

    def _hash(self, code: str) -> str:
        return hmac.new(self.settings.jwt_secret.encode(), code.encode(), hashlib.sha256).hexdigest()

    def is_verified(self, user: User) -> bool:
        until = as_utc(user.verified_until)
        return bool(user.customer_ref and until and until > utcnow())

    def start(self, db: Session, user: User, email: str) -> CustomerRecord | None:
        """Look the email up in the CRM and send a code. Returns None if no such customer exists."""
        customer = self.crm.find_customer_by_email(db, email)
        if customer is None:
            return None
        db.execute(update(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False)).values(used=True))
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(OtpCode(
            user_id=user.id,
            customer_ref=customer.ref,
            code_hash=self._hash(code),
            expires_at=utcnow() + timedelta(minutes=self.settings.otp_ttl_minutes),
        ))
        db.flush()
        self.deliver(customer.email, code)
        return customer

    def verify(self, db: Session, user: User, code: str) -> tuple[VerifyResult, int]:
        """Returns (result, attempts_left)."""
        otp = db.scalar(
            select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False))
            .order_by(OtpCode.id.desc())
        )
        if otp is None or as_utc(otp.expires_at) < utcnow():
            if otp:
                otp.used = True
            return VerifyResult.EXPIRED, 0
        otp.attempts += 1
        if hmac.compare_digest(otp.code_hash, self._hash(code.strip())):
            otp.used = True
            user.customer_ref = otp.customer_ref
            user.verified_until = utcnow() + timedelta(hours=self.settings.session_ttl_hours)
            return VerifyResult.OK, 0
        left = self.settings.otp_max_attempts - otp.attempts
        if left <= 0:
            otp.used = True
            return VerifyResult.TOO_MANY, 0
        return VerifyResult.INVALID, left

    def logout(self, user: User) -> None:
        user.customer_ref = None
        user.verified_until = None
