from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.db.models import Sum
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model

from .serializers import RegisterSerializer, UserSerializer
from .permissions import IsBotAuthenticated

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class TelegramRegisterView(APIView):
    """Telegram bot üzerinden kullanıcı kayıt/güncelleme."""
    permission_classes = [IsBotAuthenticated]

    def post(self, request):
        telegram_id = request.data.get("telegram_id")
        username = request.data.get("username", "")
        language = request.data.get("language", "uz")

        if not telegram_id:
            return Response(
                {"error": "telegram_id zorunlu"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = User.objects.update_or_create(
            telegram_id=telegram_id,
            defaults={
                "username": username or f"tg_{telegram_id}",
                "telegram_username": username,
                "language": language,
                "role": User.Role.PUBLISHER,
            },
        )

        return Response({
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "language": user.language,
            "created": created,
        })


class DashboardStatsView(APIView):
    """Kullanıcıya özel dashboard istatistikleri."""
    permission_classes = [permissions.IsAuthenticated | IsBotAuthenticated]

    def get(self, request):
        # Bot istekleri telegram_id ile gelir
        telegram_id = request.query_params.get("telegram_id")
        if telegram_id:
            try:
                user = User.objects.get(telegram_id=telegram_id)
            except User.DoesNotExist:
                return Response({})
        else:
            user = request.user

        if user.role == User.Role.ADVERTISER:
            from ads.models import Campaign, Ad
            campaigns = Campaign.objects.filter(advertiser=user)
            stats = {
                "total_campaigns": campaigns.count(),
                "active_campaigns": campaigns.filter(status="active").count(),
                "total_spent": float(
                    campaigns.aggregate(total=models.Sum("spent"))["total"] or 0
                ),
                "total_impressions": Ad.objects.filter(
                    campaign__advertiser=user
                ).aggregate(
                    total=models.Sum("impressions")
                )["total"] or 0,
                "balance": float(user.balance),
            }
        elif user.role == User.Role.PUBLISHER:
            from channels_app.models import TelegramChannel
            channels = TelegramChannel.objects.filter(owner=user)
            agg = channels.aggregate(
                total_earnings=models.Sum("total_earnings"),
                total_subscribers=models.Sum("subscriber_count"),
            )
            stats = {
                "total_channels": channels.count(),
                "active_channels": channels.filter(is_active=True).count(),
                "total_earnings": float(agg["total_earnings"] or 0),
                "total_subscribers": agg["total_subscribers"] or 0,
                "balance": float(user.balance),
            }
        else:
            stats = {}

        return Response(stats)


class DashboardChartView(APIView):
    """Dashboard grafik verileri — tarih bazlı aggregated istatistikler."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from analytics.models import DailyStats

        days = int(request.query_params.get("days", 7))
        since = timezone.now().date() - timedelta(days=days)
        user = request.user

        if user.role == User.Role.ADVERTISER:
            stats = (
                DailyStats.objects
                .filter(campaign__advertiser=user, date__gte=since)
                .values("date")
                .annotate(
                    impressions=Sum("impressions"),
                    clicks=Sum("clicks"),
                    spent=Sum("spent"),
                )
                .order_by("date")
            )
        elif user.role == User.Role.PUBLISHER:
            stats = (
                DailyStats.objects
                .filter(channel__owner=user, date__gte=since)
                .values("date")
                .annotate(
                    impressions=Sum("impressions"),
                    clicks=Sum("clicks"),
                    revenue=Sum("revenue"),
                )
                .order_by("date")
            )
        else:
            stats = []

        return Response(list(stats))
