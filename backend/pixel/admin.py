from django.contrib import admin

from .models import Conversion, ConversionEvent, PixelInstallation


@admin.register(PixelInstallation)
class PixelInstallationAdmin(admin.ModelAdmin):
    list_display = [
        "pixel_id", "advertiser", "enabled", "debug_mode",
        "click_window_days", "created_at",
    ]
    list_filter = ["enabled", "debug_mode", "advanced_matching_enabled"]
    search_fields = ["pixel_id", "advertiser__username"]
    raw_id_fields = ["advertiser"]
    readonly_fields = ["pixel_id", "created_at", "updated_at"]


@admin.register(ConversionEvent)
class ConversionEventAdmin(admin.ModelAdmin):
    list_display = [
        "id", "event_name", "pixel", "event_source",
        "value", "currency", "click_id", "created_at",
    ]
    list_filter = ["event_source", "event_name", "created_at"]
    search_fields = ["event_id", "utm_campaign", "url"]
    raw_id_fields = ["pixel"]
    readonly_fields = [
        "event_id", "event_name", "event_source",
        "url", "referrer",
        "user_agent_hash", "ip_hash", "ip_subnet_hash",
        "click_id",
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "value", "currency",
        "em_hash", "ph_hash", "external_id_hash",
        "raw_params", "attribution_attempted_at", "created_at",
    ]


@admin.register(Conversion)
class ConversionAdmin(admin.ModelAdmin):
    list_display = [
        "id", "campaign", "placement", "attribution_type",
        "touch_method", "attributed_value", "currency",
        "attribution_delay_seconds", "attributed_at",
    ]
    list_filter = ["attribution_type", "touch_method", "attributed_at"]
    raw_id_fields = ["event", "campaign", "placement", "click_event"]
    readonly_fields = [
        "event", "attribution_type", "touch_method",
        "attributed_at", "attribution_delay_seconds",
        "attributed_value", "currency", "attribution_path",
    ]
