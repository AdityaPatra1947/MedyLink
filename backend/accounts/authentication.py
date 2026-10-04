from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import AuthSession


class CookieJWTAuthentication(JWTAuthentication):
    """Authenticate verified accounts through protected browser cookies and active sessions."""

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_ACCESS_COOKIE_NAME)
        if not raw_token:
            return None
        token = self.get_validated_token(raw_token)
        user = self.get_user(token)
        if not user.is_active or not user.email_verified:
            raise AuthenticationFailed("Please sign in again.")
        try:
            session = AuthSession.objects.get(
                id=token.get("sid"),
                user=user,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        except (AuthSession.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            raise AuthenticationFailed(
                "Your session has ended. Please sign in again."
            ) from None
        request.auth_session = session
        return user, token
