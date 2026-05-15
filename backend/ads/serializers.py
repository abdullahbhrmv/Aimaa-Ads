from rest_framework import serializers
from .models import Campaign, Ad, AdPlacement


class AdSerializer(serializers.ModelSerializer):
    ctr = serializers.ReadOnlyField()

    class Meta:
        model = Ad
        fields = [
            "id", "campaign", "ad_type", "text_uz", "text_ru",
            "image", "button_text", "button_url",
            "impressions", "clicks", "ctr", "is_active", "created_at",
        ]
        read_only_fields = ["id", "impressions", "clicks", "created_at"]


class CampaignSerializer(serializers.ModelSerializer):
    ads = AdSerializer(many=True, read_only=True)
    remaining_budget = serializers.ReadOnlyField()

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "status", "rejection_reason", "target_categories", "target_languages",
            "min_subscribers", "billing_type", "budget", "daily_budget",
            "bid_amount", "spent", "remaining_budget", "start_date",
            "end_date", "ads", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "spent", "status", "rejection_reason", "created_at", "updated_at"]


class CampaignListSerializer(serializers.ModelSerializer):
    ad_count = serializers.IntegerField(source="ads.count", read_only=True)
    total_impressions = serializers.SerializerMethodField()
    total_clicks = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "status", "billing_type", "budget", "spent",
            "start_date", "end_date", "ad_count",
            "total_impressions", "total_clicks", "created_at",
        ]

    def get_total_impressions(self, obj):
        return sum(ad.impressions for ad in obj.ads.all())

    def get_total_clicks(self, obj):
        return sum(ad.clicks for ad in obj.ads.all())


class AdPlacementSerializer(serializers.ModelSerializer):
    channel_title = serializers.CharField(source="channel.title", read_only=True)

    class Meta:
        model = AdPlacement
        fields = [
            "id", "ad", "channel", "channel_title", "status",
            "impressions", "clicks", "cost", "scheduled_at", "sent_at",
        ]
        read_only_fields = ["id", "status", "impressions", "clicks", "cost", "sent_at"]
