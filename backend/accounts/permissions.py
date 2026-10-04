from rest_framework.permissions import BasePermission


class IsVerifiedAccount(BasePermission):
    message = "Verify your email before continuing."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.email_verified
        )


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
            and request.user.is_active
            and request.user.email_verified
        )
