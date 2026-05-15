from rest_framework import serializers
from .models import TelegramChannel, Category


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name_uz", "name_ru", "slug", "icon"]


class ChannelSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name_uz", read_only=True)
    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = TelegramChannel
        fields = [
            "id", "telegram_chat_id", "username", "title", "description",
            "category", "category_name", "language", "subscriber_count",
            "avg_views", "status", "is_active", "bot_added",
            "max_ads_per_day", "min_cpm", "ad_hours_start", "ad_hours_end",
            "total_earnings", "pending_earnings", "owner_username",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "subscriber_count", "avg_views",
            "status", "bot_added", "total_earnings", "pending_earnings",
            "created_at", "updated_at",
        ]


class ChannelListSerializer(serializers.ModelSerializer):
    """Reklamverenler için kanal listesi (basitleştirilmiş)."""
    category_name = serializers.CharField(source="category.name_uz", read_only=True)

    class Meta:
        model = TelegramChannel
        fields = [
            "id", "title", "username", "category_name", "language",
            "subscriber_count", "avg_views", "min_cpm",
        ]
