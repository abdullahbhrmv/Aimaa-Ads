from django.contrib import admin
from .models import Ad, AdPlacement, AdVariantExperiment, Campaign


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = [
        "name", "advertiser", "status", "moderation_status",
        "billing_type", "budget", "spent", "created_at",
    ]
    list_filter = ["status", "moderation_status", "billing_type"]
    search_fields = ["name", "advertiser__username"]
    raw_id_fields = ["advertiser", "moderated_by"]


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = [
        "id", "campaign", "experiment", "ad_type",
        "impressions", "clicks", "ctr", "is_active",
    ]
    list_filter = ["ad_type", "is_active"]
    raw_id_fields = ["campaign", "experiment"]


@admin.register(AdPlacement)
class AdPlacementAdmin(admin.ModelAdmin):
    list_display = [
        "id", "ad", "channel", "status", "billing_status",
        "publisher_action", "impressions", "clicks", "valid_clicks",
        "cost", "scheduled_at", "sent_at",
    ]
    list_filter = ["status", "billing_status", "publisher_action"]
    raw_id_fields = ["ad", "channel"]


@admin.register(AdVariantExperiment)
class AdVariantExperimentAdmin(admin.ModelAdmin):
    list_display = [
        "id", "campaign", "status", "winner_criteria",
        "winner_ad", "p_value", "created_at", "decided_at",
    ]
    list_filter = ["status", "winner_criteria"]
    raw_id_fields = ["campaign", "winner_ad"]
    readonly_fields = ["min_sample_reached_at", "decided_at", "p_value"]
