from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role", "language",
                  "phone", "company_name"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "language", "telegram_id",
                  "telegram_username", "phone", "company_name", "company_description",
                  "website", "balance", "created_at"]
        read_only_fields = ["id", "balance", "created_at", "telegram_id"]


class UserPublicSerializer(serializers.ModelSerializer):
    """Herkese açık kullanıcı bilgisi."""
    class Meta:
        model = User
        fields = ["id", "username", "company_name"]
