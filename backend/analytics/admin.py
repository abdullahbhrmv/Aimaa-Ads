from django.contrib import admin
from .models import AdEvent, ClickEvent, DailyFunnelStats, DailyStats


@admin.register(AdEvent)
class AdEventAdmin(admin.ModelAdmin):
    list_display = ["id", "placement", "event_type", "telegram_user_id", "created_at"]
    list_filter = ["event_type", "created_at"]
    raw_id_fields = ["placement"]


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ["date", "campaign", "channel", "impressions", "clicks", "spent", "revenue"]
    list_filter = ["date"]
    raw_id_fields = ["campaign", "channel"]


@admin.register(ClickEvent)
class ClickEventAdmin(admin.ModelAdmin):
    list_display = [
        "id", "placement", "is_suspicious", "telegram_user_id",
        "created_at",
    ]
    list_filter = ["is_suspicious", "created_at"]
    search_fields = ["ip_hash", "em_hash"]
    raw_id_fields = ["placement"]
    readonly_fields = [
        "placement", "ip_hash", "ip_subnet_hash", "user_agent_hash",
        "is_suspicious", "suspicion_reasons",
        "telegram_user_id", "em_hash", "created_at",
    ]


@admin.register(DailyFunnelStats)
class DailyFunnelStatsAdmin(admin.ModelAdmin):
    list_display = [
        "date", "campaign", "ad", "channel",
        "impressions", "clicks", "valid_clicks",
        "conversion_count", "conversion_value", "spent",
    ]
    list_filter = ["date"]
    raw_id_fields = ["campaign", "ad", "channel"]
