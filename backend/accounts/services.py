import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    AccountToken,
    AuthSession,
    EmailVerificationChallenge,
    SecurityEvent,
)

AUTH_PATH = "/api/v1/auth/"


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def audit(user, event, request=None, outcome="success"):
    SecurityEvent.objects.create(
        user=user,
        event=event,
        outcome=outcome,
        request_id=str(getattr(request, "request_id", ""))[:64],
    )


def set_cookie(response, name, value, max_age, path):
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def clear_auth_cookies(response):
    response.delete_cookie(
        settings.AUTH_ACCESS_COOKIE_NAME, path="/api/v1/", samesite="Lax"
    )
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME, path=AUTH_PATH, samesite="Lax"
    )
    return response


def issue_tokens(user, session, response):
    refresh = RefreshToken.for_user(user)
    refresh["sid"] = str(session.id)
    # Rotation is bounded by the original login, never by the latest refresh.
    refresh["exp"] = int(session.expires_at.timestamp())
    session.refresh_jti = refresh["jti"]
    session.last_used_at = timezone.now()
    session.save(update_fields=["refresh_jti", "last_used_at"])
    access = refresh.access_token
    access["exp"] = min(access["exp"], refresh["exp"])
    now = int(timezone.now().timestamp())
    set_cookie(
        response,
        settings.AUTH_ACCESS_COOKIE_NAME,
        str(access),
        max(0, access["exp"] - now),
        "/api/v1/",
    )
    set_cookie(
        response,
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(refresh),
        max(0, refresh["exp"] - now),
        AUTH_PATH,
    )
    return response


def new_session(user, request, response):
    session = AuthSession.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(days=7),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
    )
    audit(user, "login", request)
    return issue_tokens(user, session, response)


def revoke_sessions(user):
    now = timezone.now()
    AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=now
    )


EMAIL_CODE_LIFETIME = timedelta(minutes=10)
EMAIL_CODE_RESEND_SECONDS = 60
EMAIL_CODE_ATTEMPT_LIMIT = 5


def email_code_digest(user_id, nonce, code):
    """Short codes need a server secret as well as per-challenge randomness."""
    return salted_hmac(
        "accounts.email-verification-code.v1",
        f"{user_id}:{nonce}:{code}",
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def send_verification_code(user):
    """Caller holds the user row lock inside an atomic transaction."""
    if not user.is_active or user.email_verified:
        return False
    now = timezone.now()
    previous = (
        EmailVerificationChallenge.objects.filter(user=user)
        .order_by("-created_at", "-id")
        .first()
    )
    if (
        previous
        and previous.created_at + timedelta(seconds=EMAIL_CODE_RESEND_SECONDS) > now
    ):
        return False
    EmailVerificationChallenge.objects.filter(user=user, used_at__isnull=True).update(
        used_at=now
    )
    # Retire any pending challenges from the former email-link flow.
    AccountToken.objects.filter(
        user=user, purpose=AccountToken.Purpose.VERIFY_EMAIL, used_at__isnull=True
    ).update(used_at=now)
    code = f"{secrets.randbelow(1_000_000):06d}"
    if previous and secrets.compare_digest(
        previous.digest, email_code_digest(user.id, previous.nonce, code)
    ):
        # A resend must invalidate the previous digits even if randomness repeats.
        code = f"{(int(code) + 1 + secrets.randbelow(999_999)) % 1_000_000:06d}"
    challenge = EmailVerificationChallenge(
        user=user,
        expires_at=now + EMAIL_CODE_LIFETIME,
        created_at=now,
    )
    challenge.digest = email_code_digest(user.id, challenge.nonce, code)
    challenge.save()
    send_mail(
        "Your MedyLink email verification code",
        f"Your verification code: {code}\n\n"
        "Enter this six-digit code on the MedyLink email verification screen. "
        "No link needs to be opened.\n\n"
        "The code expires in 10 minutes and can be used only once. "
        "You can request another code after 60 seconds. "
        "If you did not request this, ignore this email.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
    return True


def send_account_email(user, purpose):
    """Use six-digit verification codes; password recovery keeps its URL token."""
    if purpose == AccountToken.Purpose.VERIFY_EMAIL:
        return send_verification_code(user)
    if purpose != AccountToken.Purpose.RESET_PASSWORD:
        raise ValueError("Unsupported account email purpose.")
    now = timezone.now()
    AccountToken.objects.filter(
        user=user, purpose=purpose, used_at__isnull=True
    ).update(used_at=now)
    raw = secrets.token_urlsafe(32)
    AccountToken.objects.create(
        user=user,
        purpose=purpose,
        digest=digest(raw),
        expires_at=now + timedelta(minutes=30),
    )
    link = f"{settings.FRONTEND_ORIGIN.rstrip('/')}/reset-password?token={raw}"
    send_mail(
        "Reset your MedyLink password",
        f"Reset your MedyLink password:\n\n{link}\n\n"
        "This single-use link expires in 30 minutes. "
        "If you did not request this, you can ignore this email.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
    return True
