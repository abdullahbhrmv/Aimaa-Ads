from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "role", "language", "telegram_id", "balance", "created_at"]
    list_filter = ["role", "language", "is_active"]
    search_fields = ["username", "email", "telegram_username", "company_name"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("AimaaAds", {"fields": ("role", "language", "telegram_id", "telegram_username", "phone", "company_name", "company_description", "website", "balance")}),
    )
