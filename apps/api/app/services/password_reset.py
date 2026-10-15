import logging
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AuthRateLimit, LoginSession, PasswordReset, User, utcnow
from app.security import hasher, token_hash

logger = logging.getLogger(__name__)
INVALID_LINK = "This reset link is invalid or has expired. Request a new one."


def mail_configured(config: Settings) -> bool:
    return bool(
        config.smtp_host
        and config.smtp_username
        and config.smtp_sender
        and config.smtp_password
        and config.smtp_password.get_secret_value()
    )


def send_email(config: Settings, recipient: str, subject: str, body: str) -> None:
    if not mail_configured(config):
        raise RuntimeError("Mail delivery is not configured")
    assert config.smtp_host and config.smtp_username and config.smtp_sender and config.smtp_password
    message = EmailMessage()
    message["From"] = str(config.smtp_sender)
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    if config.smtp_security == "ssl":
        with smtplib.SMTP_SSL(
            config.smtp_host, config.smtp_port, timeout=10, context=context
        ) as smtp:
            smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
            smtp.send_message(message)
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
            smtp.send_message(message)


def issue_and_email(bind: Engine | Connection, config: Settings, email: str) -> None:
    # Lookup and delivery happen after the HTTP response for both known and unknown
    # emails. SMTP latency must not disclose whether the account exists.
    try:
        with Session(bind, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
            now = utcnow()
            key = token_hash(f"reset-email:{email}")
            statement = insert(AuthRateLimit).values(
                key=key,
                attempts=1,
                reset_at=now + timedelta(seconds=config.reset_email_window_seconds),
            )
            attempts = db.execute(
                statement.on_conflict_do_update(
                    index_elements=[AuthRateLimit.key],
                    set_={
                        "attempts": case(
                            (AuthRateLimit.reset_at <= now, 1), else_=AuthRateLimit.attempts + 1
                        ),
                        "reset_at": case(
                            (
                                AuthRateLimit.reset_at <= now,
                                now + timedelta(seconds=config.reset_email_window_seconds),
                            ),
                            else_=AuthRateLimit.reset_at,
                        ),
                    },
                ).returning(AuthRateLimit.attempts)
            ).scalar_one()
            if attempts > config.reset_email_rate_limit:
                db.commit()
                return
            user = db.scalar(select(User).where(User.email == email).with_for_update())
            if user is None:
                db.commit()
                return
            db.execute(
                delete(PasswordReset).where(
                    PasswordReset.user_id == user.id, PasswordReset.expires_at <= now
                )
            )
            raw = SecretStr(secrets.token_urlsafe(32))
            db.add(
                PasswordReset(
                    token_hash=token_hash(raw.get_secret_value()),
                    user_id=user.id,
                    created_at=now,
                    expires_at=now + timedelta(seconds=config.reset_token_ttl_seconds),
                )
            )
            db.commit()
            link = f"{config.reset_frontend_url}/reset-password#token={raw.get_secret_value()}"
        send_email(
            config,
            email,
            "Reset your rapo password",
            f"Use this link to reset your rapo password:\n\n{link}\n\n"
            f"It expires in {config.reset_token_ttl_seconds // 60} minutes and can be used once. "
            "If you did not request this, ignore this email.",
        )
    except Exception:
        # Never log SMTP exception text, addresses, passwords, or reset links.
        logger.warning(
            "Password reset request delivery failed; check mail and database configuration."
        )


def redeem(db: Session, raw: str, password: str) -> str:
    digest = token_hash(raw)
    user_id = db.scalar(select(PasswordReset.user_id).where(PasswordReset.token_hash == digest))
    if user_id is None:
        raise HTTPException(400, INVALID_LINK)
    # All reset issuance/redemption and password logins serialize on this user.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    token = db.get(PasswordReset, digest, populate_existing=True)
    if user is None or token is None or token.expires_at <= utcnow():
        raise HTTPException(400, INVALID_LINK)
    user.password_hash = hasher.hash(password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))
    db.flush()
    return user.email


def notify_reset(config: Settings, recipient: str) -> None:
    try:
        send_email(
            config,
            recipient,
            "Your rapo password was reset",
            "Your rapo password was reset and all existing sessions were signed out. "
            "If you did not do this, request a new reset link from rapo immediately. "
            "Your password is never included in email.",
        )
    except Exception:
        logger.warning("Password reset confirmation delivery failed; check mail configuration.")
