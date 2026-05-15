"""
Admin Panel API — Platform yönetim endpoint'leri.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import generics, serializers, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .permissions import IsAdmin
from .serializers import UserPublicSerializer
from ads.models import Campaign, Ad, AdPlacement
from ads.serializers import AdSerializer
from channels_app.models import TelegramChannel, Category
from channels_app.serializers import CategorySerializer
from analytics.models import DailyStats
from .models import PayoutRequest

User = get_user_model()


# ─── Serializers ────────────────────────────────────────────


class AdminUserSerializer(serializers.ModelSerializer):
    channels_count = serializers.IntegerField(read_only=True)
    campaigns_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "role", "language",
            "telegram_id", "telegram_username", "phone",
            "company_name", "balance", "is_active",
            "channels_count", "campaigns_count",
            "created_at",
        ]


class AdminChannelSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    owner_telegram_id = serializers.IntegerField(source="owner.telegram_id", read_only=True)
    category_name = serializers.CharField(source="category.name_uz", read_only=True)

    class Meta:
        model = TelegramChannel
        fields = [
            "id", "telegram_chat_id", "username", "title", "description",
            "category", "category_name", "language",
            "subscriber_count", "avg_views",
            "status", "is_active", "bot_added",
            "max_ads_per_day", "min_cpm",
            "ad_hours_start", "ad_hours_end",
            "total_earnings", "pending_earnings",
            "owner_username", "owner_telegram_id",
            "created_at", "updated_at",
        ]


class AdminCampaignSerializer(serializers.ModelSerializer):
    advertiser_username = serializers.CharField(source="advertiser.username", read_only=True)
    advertiser_company = serializers.CharField(source="advertiser.company_name", read_only=True)
    owner = serializers.IntegerField(source="advertiser.id", read_only=True)
    owner_username = serializers.CharField(source="advertiser.username", read_only=True)
    moderated_by_username = serializers.CharField(
        source="moderated_by.username", read_only=True, default=None
    )
    ads = AdSerializer(many=True, read_only=True)
    remaining_budget = serializers.ReadOnlyField()

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "status", "rejection_reason", "billing_type",
            "target_categories", "target_languages", "min_subscribers",
            "budget", "daily_budget", "bid_amount", "spent", "remaining_budget",
            "start_date", "end_date",
            "advertiser_username", "advertiser_company", "owner", "owner_username",
            "moderation_status", "moderation_flags", "moderation_notes",
            "moderated_by", "moderated_by_username", "moderated_at",
            "ads", "created_at", "updated_at",
        ]


class CategoryManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name_uz", "name_ru", "slug", "icon", "is_active"]


# ─── Platform Stats ────────────────────────────────────────


class AdminPlatformStatsView(APIView):
    """Platform geneli istatistikler."""
    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        total_revenue = AdPlacement.objects.filter(
            status="deleted"
        ).aggregate(total=Sum("cost"))["total"] or Decimal("0")

        commission = total_revenue * Decimal(str(0.30))

        stats = {
            "total_users": User.objects.count(),
            "total_advertisers": User.objects.filter(role="advertiser").count(),
            "total_publishers": User.objects.filter(role="publisher").count(),
            "total_channels": TelegramChannel.objects.count(),
            "approved_channels": TelegramChannel.objects.filter(status="approved").count(),
            "pending_channels": TelegramChannel.objects.filter(status="pending").count(),
            "total_campaigns": Campaign.objects.count(),
            "active_campaigns": Campaign.objects.filter(status="active").count(),
            "pending_campaigns": Campaign.objects.filter(status="pending").count(),
            "total_revenue": float(total_revenue),
            "total_commission": float(commission),
            "total_publisher_payouts": float(total_revenue - commission),
            "monthly_revenue": float(
                AdPlacement.objects.filter(
                    status="deleted", sent_at__gte=thirty_days_ago
                ).aggregate(total=Sum("cost"))["total"] or 0
            ),
        }
        return Response(stats)


# ─── Channel Management ────────────────────────────────────


class AdminChannelListView(generics.ListAPIView):
    """Tüm kanalları listele (admin)."""
    serializer_class = AdminChannelSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "category", "language", "is_active"]
    search_fields = ["title", "username", "owner__username"]

    def get_queryset(self):
        return TelegramChannel.objects.select_related("owner", "category").order_by("-created_at")


class AdminChannelApproveView(APIView):
    """Kanalı onayla — yeni onaylarda 30 günlük probation başlatılır (FAZ 3)."""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            channel = TelegramChannel.objects.get(pk=pk)
        except TelegramChannel.DoesNotExist:
            return Response({"error": "Kanal topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        channel.status = "approved"
        channel.is_active = True
        update_fields = ["status", "is_active"]

        # Probation — sadece daha önce set edilmemişse (geriye dönük uyumluluk).
        # Mevcut onaylı kanallar ilk deploy'da probation'a alınmaz; yeni onaylar
        # 30 gün gözetim altına girer.
        if channel.probation_ends_at is None and not channel.is_trusted_override:
            channel.probation_ends_at = timezone.now() + timedelta(days=30)
            update_fields.append("probation_ends_at")

        channel.save(update_fields=update_fields)
        return Response({
            "status": "approved",
            "channel_id": pk,
            "probation_ends_at": channel.probation_ends_at,
        })


class AdminChannelRejectView(APIView):
    """Kanalı reddet."""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            channel = TelegramChannel.objects.get(pk=pk)
        except TelegramChannel.DoesNotExist:
            return Response({"error": "Kanal topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        channel.status = "rejected"
        channel.is_active = False
        channel.save(update_fields=["status", "is_active"])
        return Response({"status": "rejected", "channel_id": pk})


# ─── Campaign Management ───────────────────────────────────


class AdminCampaignListView(generics.ListAPIView):
    """Tüm kampanyaları listele (admin)."""
    serializer_class = AdminCampaignSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "billing_type"]
    search_fields = ["name", "advertiser__username"]

    def get_queryset(self):
        from django.db.models import F, OrderBy
        # Sıralama: 1) start_date (NULL olanlar en öne), 2) created_at
        # NULL start_date = hemen başlayacak = en acil = en önde
        return Campaign.objects.select_related("advertiser").prefetch_related("ads").order_by(
            OrderBy(F('start_date'), nulls_first=True),
            'created_at'
        )


class AdminCampaignApproveView(APIView):
    """Kampanyayı onayla — FAZ 4a: budget otomatik frozen'a taşınır."""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        from payments.services import (
            InsufficientBalanceError, freeze_for_campaign,
        )

        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Kampaniya topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if campaign.status != "pending":
            return Response(
                {"error": "Sadece bekleyen kampanyalar onaylanabilir"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Budget'ı freeze et — yetersiz bakiyede approve reddedilir.
        try:
            freeze_for_campaign(campaign)
        except InsufficientBalanceError as exc:
            return Response(
                {"error": "Yetersiz bakiye", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        campaign.status = "approved"
        campaign.save(update_fields=["status"])
        return Response({"status": "approved", "campaign_id": pk})


class AdminCampaignRejectView(APIView):
    """Kampanyayı reddet."""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Kampaniya topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response(
                {"error": "Red sebebi belirtilmesi zorunludur"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # FAZ 4a: Önceden freeze edilmiş bütçe varsa iade et.
        from payments.services import refund_unspent_campaign

        previous_status = campaign.status
        campaign.status = "rejected"
        campaign.rejection_reason = reason
        campaign.save(update_fields=["status", "rejection_reason"])

        if previous_status in {"approved", "active", "paused"}:
            refund_unspent_campaign(campaign)

        return Response({"status": "rejected", "campaign_id": pk, "reason": reason})


# ─── User Management ───────────────────────────────────────


class AdminUserListView(generics.ListAPIView):
    """Tüm kullanıcıları listele (admin)."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["username", "email", "company_name", "telegram_username"]

    def get_queryset(self):
        return User.objects.annotate(
            channels_count=Count("channels", distinct=True),
            campaigns_count=Count("campaigns", distinct=True),
        ).order_by("-created_at")


# ─── Revenue Reports ───────────────────────────────────────


class AdminRevenueReportView(APIView):
    """Gelir/komisyon raporu."""
    permission_classes = [IsAdmin]

    def get(self, request):
        days = int(request.query_params.get("days", 30))
        since = timezone.now().date() - timedelta(days=days)

        daily = (
            DailyStats.objects
            .filter(date__gte=since)
            .values("date")
            .annotate(
                impressions=Sum("impressions"),
                clicks=Sum("clicks"),
                gross_revenue=Sum("spent"),
                publisher_payouts=Sum("revenue"),
            )
            .order_by("date")
        )

        # Her gün için komisyon hesapla
        data = []
        for row in daily:
            gross = float(row["gross_revenue"] or 0)
            payouts = float(row["publisher_payouts"] or 0)
            data.append({
                "date": row["date"],
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "gross_revenue": gross,
                "commission": gross - payouts,
                "publisher_payouts": payouts,
            })

        # Toplam özet
        totals = {
            "total_gross": sum(r["gross_revenue"] for r in data),
            "total_commission": sum(r["commission"] for r in data),
            "total_payouts": sum(r["publisher_payouts"] for r in data),
        }

        return Response({"daily": data, "totals": totals})


# ─── Category Management ───────────────────────────────────


class AdminCategoryListCreateView(generics.ListCreateAPIView):
    """Kategorileri listele ve oluştur."""
    queryset = Category.objects.all()
    serializer_class = CategoryManageSerializer
    permission_classes = [IsAdmin]


class AdminCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Kategori detay, güncelle, sil."""
    queryset = Category.objects.all()
    serializer_class = CategoryManageSerializer
    permission_classes = [IsAdmin]


# ─── Payout Management ───────────────────────────────────


class AdminPayoutSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    telegram_id = serializers.IntegerField(source="user.telegram_id", read_only=True)

    class Meta:
        model = PayoutRequest
        fields = [
            "id", "username", "telegram_id", "amount",
            "status", "payment_method", "payment_details",
            "admin_note",
            # FAZ 4a: provider akışı alanları
            "provider", "provider_account", "provider_status", "provider_ref",
            "created_at", "updated_at",
        ]


class AdminPayoutListView(generics.ListAPIView):
    """Barcha to'lov so'rovlari."""
    serializer_class = AdminPayoutSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_queryset(self):
        return PayoutRequest.objects.select_related("user").order_by("-created_at")


class AdminPayoutApproveView(APIView):
    """To'lov so'rovini tasdiqlash."""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        from payments.services import (
            InsufficientBalanceError, withdraw_for_payout,
        )

        try:
            payout = PayoutRequest.objects.select_related("user").get(pk=pk)
        except PayoutRequest.DoesNotExist:
            return Response({"error": "So'rov topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if payout.status != "pending":
            return Response(
                {"error": "Faqat kutilayotgan so'rovlarni tasdiqlash mumkin"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # FAZ 4a: Bakiyeyi UserBalance'tan atomik düş + Transaction kaydı.
        # Status PENDING ile başlar — FAZ 4b'de provider ödemeyi tamamlayınca
        # `COMPLETED`'a geçecek; şu an admin elle tamamladığı için hemen ilerletiriz.
        try:
            withdraw_for_payout(payout)
        except InsufficientBalanceError as exc:
            return Response(
                {"error": "Yetersiz bakiye", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Payout status: FAZ 4a'da provider entegrasyonu yok → processing.
        # Admin provider'a ödemeyi yapıp sonra `complete` endpoint'i ile
        # kapatır (FAZ 4b). Şimdilik "processing" — audit trail doğru kalır.
        payout.status = PayoutRequest.Status.PROCESSING
        payout.admin_note = request.data.get("note", "")
        payout.save(update_fields=["status", "admin_note", "updated_at"])

        return Response({
            "status": payout.status,
            "payout_id": pk,
            "note": "Bakiye düşüldü, provider ödemesi bekleniyor (FAZ 4b).",
        })


class AdminPayoutRejectView(APIView):
    """To'lov so'rovini rad etish."""
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            payout = PayoutRequest.objects.get(pk=pk)
        except PayoutRequest.DoesNotExist:
            return Response({"error": "So'rov topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        payout.status = "rejected"
        payout.admin_note = request.data.get("note", "")
        payout.save(update_fields=["status", "admin_note", "updated_at"])
        return Response({"status": "rejected", "payout_id": pk})


# ─── Moderation Queue (FAZ 2) ─────────────────────────────


class AdminModerationQueueView(generics.ListAPIView):
    """Otomatik tarayıcı tarafından işaretlenmiş kampanyalar.

    Sadece `moderation_status IN (flagged, human_review)` — yani insan
    moderatör kararını bekleyen kuyruğu listeler. `rejected` ve
    `auto_approved` durumları buraya gelmez (rejected'ı zaten
    `AdminCampaignListView` kapsıyor).
    """

    serializer_class = AdminCampaignSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return (
            Campaign.objects.filter(
                moderation_status__in=[
                    Campaign.ModerationStatus.FLAGGED,
                    Campaign.ModerationStatus.HUMAN_REVIEW,
                ]
            )
            .select_related("advertiser")
            .prefetch_related("ads", "target_categories")
            .order_by("-created_at")
        )


class AdminModerationApproveView(APIView):
    """Flagged bir kampanyayı moderatör onayı ile auto_approved'a taşı.

    Yan etki: business `status='approved'`, böylece advertiser activate
    edebilir (mevcut flow'a uygun).
    """

    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Kampaniya topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if campaign.moderation_status not in {
            Campaign.ModerationStatus.FLAGGED,
            Campaign.ModerationStatus.HUMAN_REVIEW,
            Campaign.ModerationStatus.PENDING,
        }:
            return Response(
                {"error": "Sadece işaretlenmiş kampanyalar moderatör onayı alabilir."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = (request.data.get("notes") or "").strip()

        # FAZ 4a: Moderation approve ile business onay birleşiyorsa budget
        # freeze'i burada da çalıştırmalıyız. Yetersiz bakiye → reject.
        from payments.services import (
            InsufficientBalanceError, freeze_for_campaign,
        )

        campaign.moderation_status = Campaign.ModerationStatus.AUTO_APPROVED
        campaign.moderated_by = request.user
        campaign.moderated_at = timezone.now()
        if notes:
            campaign.moderation_notes = (
                (campaign.moderation_notes + "\n\n" if campaign.moderation_notes else "")
                + f"[Onaylayan: {request.user.username}] {notes}"
            )

        update_fields = [
            "moderation_status", "moderated_by", "moderated_at", "moderation_notes",
        ]
        business_was_pending = campaign.status == Campaign.Status.PENDING
        if business_was_pending:
            # Freeze budget önce dene — yetersiz bakiyede approve başarısız.
            try:
                freeze_for_campaign(campaign)
            except InsufficientBalanceError as exc:
                return Response(
                    {"error": "Yetersiz bakiye", "detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            campaign.status = Campaign.Status.APPROVED
            update_fields.append("status")

        campaign.save(update_fields=update_fields)

        return Response(
            {
                "status": "approved",
                "campaign_id": pk,
                "moderation_status": campaign.moderation_status,
                "business_status": campaign.status,
            }
        )


class AdminModerationRejectView(APIView):
    """Flagged kampanyayı moderatör kararıyla reddet."""

    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Kampaniya topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"error": "Red sebebi zorunludur."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = (request.data.get("notes") or "").strip()

        from payments.services import refund_unspent_campaign

        previous_status = campaign.status
        campaign.moderation_status = Campaign.ModerationStatus.REJECTED
        campaign.status = Campaign.Status.REJECTED
        campaign.rejection_reason = reason
        campaign.moderated_by = request.user
        campaign.moderated_at = timezone.now()
        if notes:
            campaign.moderation_notes = (
                (campaign.moderation_notes + "\n\n" if campaign.moderation_notes else "")
                + f"[Reddeden: {request.user.username}] {notes}"
            )

        campaign.save(
            update_fields=[
                "moderation_status", "status", "rejection_reason",
                "moderated_by", "moderated_at", "moderation_notes",
            ]
        )

        # FAZ 4a: Budget daha önce frozen'a taşındıysa iade et.
        if previous_status in {"approved", "active", "paused"}:
            refund_unspent_campaign(campaign)

        return Response(
            {
                "status": "rejected",
                "campaign_id": pk,
                "reason": reason,
            }
        )


# ─── Fraud dashboard (FAZ 3) ──────────────────────────────


class AdminFraudDashboardView(APIView):
    """Son 7 günün fraud özeti — admin fraud sekmesinin landing endpoint'i."""

    permission_classes = [IsAdmin]

    def get(self, request):
        from analytics.models import ClickEvent

        window_days = int(request.query_params.get("days", 7))
        since = timezone.now() - timedelta(days=window_days)

        click_agg = ClickEvent.objects.filter(created_at__gte=since).aggregate(
            total=Count("id"),
            suspicious=Count("id", filter=Q(is_suspicious=True)),
        )

        suspicious_growth_count = TelegramChannel.objects.filter(
            suspicious_growth_flag=True
        ).count()
        ip_cluster_count = TelegramChannel.objects.filter(
            ip_cluster_fraud_flag=True
        ).count()
        probation_count = TelegramChannel.objects.filter(
            probation_ends_at__gt=timezone.now(),
            is_trusted_override=False,
        ).count()
        low_quality_count = TelegramChannel.objects.filter(
            quality_score__lt=30,
            status="approved",
        ).count()

        return Response({
            "window_days": window_days,
            "clicks": {
                "total": click_agg["total"] or 0,
                "suspicious": click_agg["suspicious"] or 0,
                "suspicious_pct": (
                    round((click_agg["suspicious"] or 0) * 100 / click_agg["total"], 2)
                    if click_agg["total"] else 0
                ),
            },
            "channels": {
                "suspicious_growth": suspicious_growth_count,
                "ip_cluster_fraud": ip_cluster_count,
                "on_probation": probation_count,
                "low_quality": low_quality_count,
            },
        })


class AdminSuspiciousChannelsView(generics.ListAPIView):
    """Fraud flag'lerinden en az biri set olmuş kanalları listele."""

    serializer_class = AdminChannelSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return (
            TelegramChannel.objects.filter(
                Q(suspicious_growth_flag=True)
                | Q(ip_cluster_fraud_flag=True)
                | Q(quality_score__lt=30)
            )
            .select_related("owner", "category")
            .order_by("quality_score", "-updated_at")
        )


class AdminSuspiciousClicksView(APIView):
    """Son N gün içindeki şüpheli click'leri kanal başına özetler."""

    permission_classes = [IsAdmin]

    def get(self, request):
        from analytics.models import ClickEvent

        days = int(request.query_params.get("days", 7))
        since = timezone.now() - timedelta(days=days)

        rows = (
            ClickEvent.objects.filter(
                created_at__gte=since, is_suspicious=True,
            )
            .values("placement__channel_id", "placement__channel__title")
            .annotate(
                suspicious_count=Count("id"),
            )
            .order_by("-suspicious_count")[:50]
        )

        return Response(list(rows))


class AdminChannelTrustToggleView(APIView):
    """Bir kanalı trusted ↔ untrusted arasında taşı.

    Trusted olunca:
      - is_trusted_override=True
      - probation_ends_at=None
      - suspicious_growth_flag=False
      - ip_cluster_fraud_flag=False
    Untrust olunca sadece is_trusted_override=False (diğer flag'ler otomatik
    doğrulamayla geri gelir; manuel temizlik gerekirse admin çalıştırır).
    """

    permission_classes = [IsAdmin]

    def post(self, request, pk):
        try:
            channel = TelegramChannel.objects.get(pk=pk)
        except TelegramChannel.DoesNotExist:
            return Response({"error": "Kanal topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        action = (request.data.get("action") or "").strip()
        if action not in {"trust", "untrust"}:
            return Response(
                {"error": "action must be 'trust' or 'untrust'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == "trust":
            channel.is_trusted_override = True
            channel.probation_ends_at = None
            channel.suspicious_growth_flag = False
            channel.ip_cluster_fraud_flag = False
            update_fields = [
                "is_trusted_override", "probation_ends_at",
                "suspicious_growth_flag", "ip_cluster_fraud_flag",
            ]
        else:
            channel.is_trusted_override = False
            update_fields = ["is_trusted_override"]

        channel.save(update_fields=update_fields)
        return Response({
            "status": action,
            "channel_id": pk,
            "is_trusted_override": channel.is_trusted_override,
        })
