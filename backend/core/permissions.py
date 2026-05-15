"""
Özel izin sınıfları — Bot ve Admin erişim kontrolü.
"""

from django.conf import settings
from rest_framework import permissions


class IsBotAuthenticated(permissions.BasePermission):
    """Bot'tan gelen istekleri X-Bot-Secret header ile doğrula."""

    def has_permission(self, request, view):
        bot_secret = request.headers.get("X-Bot-Secret", "")
        expected = getattr(settings, "BOT_API_SECRET", "")
        return bool(bot_secret and bot_secret == expected)


class IsSuperAdmin(permissions.BasePermission):
    """
    Sadece root admin (superuser) erişebilir.

    Kullanım: Kritik işlemler (sistem ayarları, staff admin silme, vb.)
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser


class IsStaffAdmin(permissions.BasePermission):
    """
    Staff admin veya superuser erişebilir.

    Kullanım: Moderasyon, kullanıcı yönetimi gibi işlemler
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and (request.user.is_superuser or request.user.is_staff_admin)
        )


class IsAdmin(permissions.BasePermission):
    """
    Herhangi bir admin (root veya staff) erişebilir.

    Backward compatibility için korundu.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_any_admin
