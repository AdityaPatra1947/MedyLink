import secrets

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from .authentication import CookieJWTAuthentication
from .models import (
    AccountToken,
    AuthSession,
    EmailVerificationChallenge,
    User,
)
from .registration import register_account
from .serializers import (
    EmailSerializer,
    EmailVerificationSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    check_password_strength,
    user_payload,
)
from .services import (
    EMAIL_CODE_ATTEMPT_LIMIT,
    EMAIL_CODE_RESEND_SECONDS,
    audit,
    clear_auth_cookies,
    digest,
    email_code_digest,
    issue_tokens,
    new_session,
    revoke_sessions,
    send_account_email,
)
from .throttles import AuthIdentityThrottle, AuthIPThrottle

GENERIC_EMAIL = (
    "If the address is eligible, an email with the next steps has been sent."
)


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PublicAuthView(APIView):
    # The project middleware enforces CSRF even when no authenticated session exists.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AuthIPThrottle, AuthIdentityThrottle]

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'


class AccountView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthIPThrottle]


class CSRFView(PublicAuthView):
    throttle_classes = []

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(PublicAuthView):
    def post(self, request):
        data = validated(RegisterSerializer, request)
        register_account(data, request)
        return Response({"detail": GENERIC_EMAIL}, status=status.HTTP_202_ACCEPTED)


class LoginView(PublicAuthView):
    def post(self, request):
        data = validated(LoginSerializer, request)
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(email__iexact=data["email"].strip())
                .first()
            )
            password_valid = user.check_password(data["password"]) if user else False
            if not user:
                make_password(data["password"])
            if (
                not user
                or not password_valid
                or not user.is_active
                or not user.email_verified
            ):
                audit(user, "login", request, outcome="denied")
                return Response(
                    {
                        "code": "invalid_credentials",
                        "detail": "Unable to sign in. Check your details and verify your email.",
                    },
                    status=401,
                )
            return new_session(user, request, Response({"user": user_payload(user)}))


class MeView(AccountView):
    def get(self, request):
        return Response({"user": user_payload(request.user)})


class EmailActionView(PublicAuthView):
    purpose = AccountToken.Purpose.VERIFY_EMAIL

    def post(self, request):
        data = validated(EmailSerializer, request)
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(email__iexact=data["email"].strip(), is_active=True)
                .first()
            )
            if user and (
                self.purpose == AccountToken.Purpose.RESET_PASSWORD
                or not user.email_verified
            ):
                if send_account_email(user, self.purpose):
                    audit(user, f"{self.purpose}_requested", request)
        result = {"detail": GENERIC_EMAIL}
        if self.purpose == AccountToken.Purpose.VERIFY_EMAIL:
            result["resend_after"] = EMAIL_CODE_RESEND_SECONDS
        return Response(result)


class ForgotPasswordView(EmailActionView):
    purpose = AccountToken.Purpose.RESET_PASSWORD


def locked_account_token(raw, purpose):
    candidate = AccountToken.objects.filter(digest=digest(raw), purpose=purpose).first()
    if not candidate:
        raise serializers.ValidationError("This link is invalid or has expired.")
    user = User.objects.select_for_update().get(id=candidate.user_id)
    token = AccountToken.objects.select_for_update().get(id=candidate.id)
    if token.used_at or token.expires_at <= timezone.now() or not user.is_active:
        raise serializers.ValidationError("This link is invalid or has expired.")
    return user, token


class VerifyEmailView(PublicAuthView):
    def post(self, request):
        data = validated(EmailVerificationSerializer, request)
        failure = {
            "code": "invalid_verification_code",
            "detail": "That code is invalid or has expired. Check the email address or request a new code.",
            "request_id": str(getattr(request, "request_id", "")),
        }
        with transaction.atomic():
            user = (
                User.objects.select_for_update()
                .filter(email__iexact=data["email"].strip())
                .first()
            )
            if not user or not user.is_active or user.email_verified:
                audit(user, "email_verification", request, outcome="denied")
                return Response(failure, status=400)
            challenge = (
                EmailVerificationChallenge.objects.select_for_update()
                .filter(user=user)
                .order_by("-created_at", "-id")
                .first()
            )
            now = timezone.now()
            if (
                not challenge
                or challenge.used_at
                or challenge.expires_at <= now
                or challenge.attempts >= EMAIL_CODE_ATTEMPT_LIMIT
            ):
                audit(user, "email_verification", request, outcome="denied")
                return Response(failure, status=400)
            expected = email_code_digest(user.id, challenge.nonce, data["code"])
            if not secrets.compare_digest(expected, challenge.digest):
                challenge.attempts += 1
                challenge.save(update_fields=["attempts"])
                audit(user, "email_verification", request, outcome="denied")
                # Return rather than raise: failed attempts must commit.
                return Response(failure, status=400)
            EmailVerificationChallenge.objects.filter(
                user=user, used_at__isnull=True
            ).update(used_at=now)
            AccountToken.objects.filter(
                user=user,
                purpose=AccountToken.Purpose.VERIFY_EMAIL,
                used_at__isnull=True,
            ).update(used_at=now)
            user.email_verified_at = now
            user.save(update_fields=["email_verified_at"])
            audit(user, "email_verified", request)
        return Response({"detail": "Email verified. You can now sign in."})


class ResetPasswordView(PublicAuthView):
    def post(self, request):
        data = validated(ResetPasswordSerializer, request)
        with transaction.atomic():
            user, token = locked_account_token(
                data["token"], AccountToken.Purpose.RESET_PASSWORD
            )
            check_password_strength(data["password"], user)
            user.set_password(data["password"])
            user.save(update_fields=["password"])
            AccountToken.objects.filter(
                user=user, purpose=token.purpose, used_at__isnull=True
            ).update(used_at=timezone.now())
            revoke_sessions(user)
            audit(user, "password_reset", request)
        return clear_auth_cookies(
            Response({"detail": "Password updated. Please sign in again."})
        )


class RefreshView(PublicAuthView):
    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        try:
            # Validate signature and expiry before a DB lookup, but defer blacklist checking
            # until the session is locked so replay can revoke the entire session family.
            token = UntypedToken(raw or "")
            if token.get("token_type") != "refresh" or not token.get("sid"):
                raise TokenError("Invalid refresh token")
            with transaction.atomic():
                user = User.objects.select_for_update().get(id=token.get("user_id"))
                session = AuthSession.objects.select_for_update().get(
                    id=token["sid"], user=user
                )
                if (
                    session.revoked_at
                    or session.expires_at <= timezone.now()
                    or not user.is_active
                    or not user.email_verified
                ):
                    return clear_auth_cookies(
                        Response({"detail": "Please sign in again."}, status=401)
                    )
                if session.refresh_jti != token.get("jti"):
                    session.revoked_at = timezone.now()
                    session.save(update_fields=["revoked_at"])
                    audit(user, "refresh_replay", request, outcome="denied")
                    return clear_auth_cookies(
                        Response(
                            {"detail": "Your session has ended. Please sign in again."},
                            status=401,
                        )
                    )
                try:
                    old_refresh = RefreshToken(raw)
                    old_refresh.blacklist()
                except TokenError:
                    session.revoked_at = timezone.now()
                    session.save(update_fields=["revoked_at"])
                    return clear_auth_cookies(
                        Response({"detail": "Please sign in again."}, status=401)
                    )
                return issue_tokens(
                    user, session, Response({"user": user_payload(user)})
                )
        except (
            TokenError,
            User.DoesNotExist,
            AuthSession.DoesNotExist,
            DjangoValidationError,
            ValueError,
            TypeError,
        ):
            return clear_auth_cookies(
                Response({"detail": "Please sign in again."}, status=401)
            )


class LogoutView(PublicAuthView):
    def post(self, request):
        # Accept refresh credentials when the access cookie has already expired.
        raw = request.COOKIES.get(
            settings.AUTH_REFRESH_COOKIE_NAME
        ) or request.COOKIES.get(
            settings.AUTH_ACCESS_COOKIE_NAME
        )
        if raw:
            try:
                token = UntypedToken(raw)
                with transaction.atomic():
                    user = User.objects.select_for_update().get(id=token.get("user_id"))
                    session = (
                        AuthSession.objects.select_for_update()
                        .filter(id=token.get("sid"), user=user, revoked_at__isnull=True)
                        .first()
                    )
                    if session:
                        session.revoked_at = timezone.now()
                        session.save(update_fields=["revoked_at"])
                        audit(user, "logout", request)
            except (
                TokenError,
                User.DoesNotExist,
                DjangoValidationError,
                ValueError,
                TypeError,
            ):
                pass
        return clear_auth_cookies(Response({"detail": "Signed out."}))


class LogoutAllView(AccountView):
    def post(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(id=request.user.id)
            revoke_sessions(user)
            audit(user, "all_sessions_revoked", request)
        return clear_auth_cookies(Response({"detail": "Signed out on all devices."}))


class SessionsView(AccountView):
    def get(self, request):
        sessions = AuthSession.objects.filter(
            user=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("-last_used_at")[:50]
        return Response(
            {
                "results": [
                    {
                        "id": str(session.id),
                        "created_at": session.created_at,
                        "last_used_at": session.last_used_at,
                        "expires_at": session.expires_at,
                        "user_agent": session.user_agent,
                        "current": session.id == request.auth_session.id,
                    }
                    for session in sessions
                ]
            }
        )


class SessionDetailView(AccountView):
    def delete(self, request, session_id):
        with transaction.atomic():
            user = User.objects.select_for_update().get(id=request.user.id)
            session = (
                AuthSession.objects.select_for_update()
                .filter(id=session_id, user=user)
                .first()
            )
            if not session:
                raise NotFound()
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at"])
            audit(user, "session_revoked", request)
        response = Response(status=204)
        return (
            clear_auth_cookies(response)
            if session.id == request.auth_session.id
            else response
        )
