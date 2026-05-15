from django.contrib import admin
from .models import Category, TelegramChannel


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name_uz", "name_ru", "slug", "icon", "is_active"]
    list_filter = ["is_active"]
    prepopulated_fields = {"slug": ("name_uz",)}


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    list_display = ["title", "username", "owner", "status", "subscriber_count", "total_earnings", "created_at"]
    list_filter = ["status", "is_active", "bot_added", "language", "category"]
    search_fields = ["title", "username", "owner__username"]
    raw_id_fields = ["owner", "category"]
    actions = ["approve_channels", "reject_channels", "suspend_channels"]

    @admin.action(description="Tanlangan kanallarni tasdiqlash")
    def approve_channels(self, request, queryset):
        updated = queryset.update(status="approved")
        self.message_user(request, f"{updated} ta kanal tasdiqlandi.")

    @admin.action(description="Tanlangan kanallarni rad etish")
    def reject_channels(self, request, queryset):
        updated = queryset.update(status="rejected")
        self.message_user(request, f"{updated} ta kanal rad etildi.")

    @admin.action(description="Tanlangan kanallarni to'xtatib qo'yish")
    def suspend_channels(self, request, queryset):
        updated = queryset.update(status="suspended", is_active=False)
        self.message_user(request, f"{updated} ta kanal to'xtatildi.")
