from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Campaign, Ad, AdPlacement
from .serializers import (
    CampaignSerializer, CampaignListSerializer,
    AdSerializer, AdPlacementSerializer,
)
from .services import AdDeliveryService


class CampaignViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_queryset(self):
        return Campaign.objects.filter(
            advertiser=self.request.user
        ).prefetch_related("ads", "target_categories")

    def get_serializer_class(self):
        if self.action == "list":
            return CampaignListSerializer
        return CampaignSerializer

    def perform_create(self, serializer):
        campaign = serializer.save(advertiser=self.request.user)
        # Kampanya kreatifleri eklendiğinde ad ViewSet'i ayrıca scan tetikler.
        # Yine de bu noktada da tetikleyelim — boş kreatifli kampanya no-op.
        from ads.tasks import scan_campaign_creatives
        scan_campaign_creatives.delay(campaign.id)

    def perform_update(self, serializer):
        campaign = serializer.save()
        # Kampanya metadata güncellendiğinde yeniden tarama — hedefleme veya
        # kreatif listesi değişmiş olabilir.
        from ads.tasks import scan_campaign_creatives
        scan_campaign_creatives.delay(campaign.id)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Kampanyayı aktive et ve reklam dağıtımını başlat."""
        campaign = self.get_object()

        # Sadece onaylanmış veya duraklatılmış kampanyalar aktive edilebilir
        if campaign.status == Campaign.Status.PENDING:
            return Response(
                {"error": "Kampanya henüz admin tarafından onaylanmadı."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if campaign.status == Campaign.Status.REJECTED:
            return Response(
                {"error": "Reddedilen kampanya aktive edilemez."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if campaign.status not in [Campaign.Status.APPROVED, Campaign.Status.PAUSED]:
            return Response(
                {"error": "Bu kampanya aktive edilemez."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not campaign.ads.filter(is_active=True).exists():
            return Response(
                {"error": "Kampanyada aktif reklam bulunmuyor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # FAZ 4a: Balance + frozen kontrolü. Kampanya `approved`'a geçerken
        # admin akışında `freeze_for_campaign` çağrılıyor — burada sadece
        # sanity check: frozen yeterli değilse (ör. admin freeze'siz approve
        # etmiş), activate reddedilir.
        from payments.models import UserBalance
        wallet, _ = UserBalance.objects.get_or_create(user=request.user)
        if wallet.frozen_amount < (campaign.budget - campaign.spent):
            return Response(
                {"error": "Yetersiz dondurulmuş bütçe. Lütfen admin ile iletişime geçin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        campaign.status = Campaign.Status.ACTIVE
        campaign.save()

        # Reklam dağıtımını planla
        AdDeliveryService.schedule_campaign(campaign)

        return Response({"status": "Kampanya aktive edildi."})

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Aktif kampanyayı duraklat."""
        campaign = self.get_object()
        if campaign.status != Campaign.Status.ACTIVE:
            return Response(
                {"error": "Sadece aktif kampanyalar duraklatılabilir."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        campaign.status = Campaign.Status.PAUSED
        campaign.save()
        return Response({"status": "Kampanya duraklatıldı."})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Duraklatılmış kampanyayı devam ettir."""
        campaign = self.get_object()
        if campaign.status != Campaign.Status.PAUSED:
            return Response(
                {"error": "Sadece duraklatılmış kampanyalar devam ettirilebilir."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        campaign.status = Campaign.Status.ACTIVE
        campaign.save()
        return Response({"status": "Kampanya devam ettirildi."})


class AdViewSet(viewsets.ModelViewSet):
    serializer_class = AdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Ad.objects.filter(campaign__advertiser=self.request.user)

    def perform_create(self, serializer):
        ad = serializer.save()
        from ads.tasks import scan_campaign_creatives
        scan_campaign_creatives.delay(ad.campaign_id)

    def perform_update(self, serializer):
        ad = serializer.save()
        from ads.tasks import scan_campaign_creatives
        scan_campaign_creatives.delay(ad.campaign_id)


class AdPlacementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AdPlacementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == "publisher":
            return AdPlacement.objects.filter(channel__owner=user)
        return AdPlacement.objects.filter(ad__campaign__advertiser=user)

    @action(detail=False, methods=["get"], url_path="upcoming")
    def upcoming(self, request):
        """Yayıncı için kanala gelmek üzere olan, henüz karar verilmemiş placement'lar."""
        user = request.user
        if user.role != "publisher":
            raise PermissionDenied("Bu endpoint sadece yayıncılar içindir.")

        qs = (
            AdPlacement.objects.filter(
                channel__owner=user,
                status=AdPlacement.Status.SCHEDULED,
                publisher_action=AdPlacement.PublisherAction.AUTO,
                scheduled_at__gte=timezone.now(),
            )
            .select_related("ad", "ad__campaign", "channel")
            .order_by("scheduled_at")
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Yayıncı bu placement'ı kanalında yayınlamayı reddeder.

        Side effect: `reassign_rejected_placement` task fırlatılır — ad
        başka uygun bir kanala yeniden atanır (max 3 deneme).
        """
        placement = self.get_object()

        # Yetki — placement kendisine ait kanalda olmalı.
        if placement.channel.owner_id != request.user.id:
            raise PermissionDenied("Bu placement'ı reddedemezsiniz.")

        # Sadece henüz karar verilmemiş placement'lar reddedilebilir.
        if placement.publisher_action != AdPlacement.PublisherAction.AUTO:
            raise ValidationError(
                {"publisher_action": "Bu placement hakkında zaten karar verilmiş."}
            )

        # Yayınlanmışsa red anlamsız.
        if placement.status != AdPlacement.Status.SCHEDULED:
            raise ValidationError(
                {"status": "Sadece planlanmış placement'lar reddedilebilir."}
            )

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            raise ValidationError({"reason": "Red sebebi zorunludur."})

        placement.publisher_action = AdPlacement.PublisherAction.REJECTED
        placement.publisher_rejection_reason = reason
        placement.save(
            update_fields=["publisher_action", "publisher_rejection_reason"]
        )

        from ads.tasks import reassign_rejected_placement
        reassign_rejected_placement.delay(placement.id)

        return Response(
            {
                "status": "rejected",
                "placement_id": placement.id,
                "reason": reason,
            }
        )

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        """Yayıncı placement'ı açıkça kabul eder (opsiyonel — default auto)."""
        placement = self.get_object()
        if placement.channel.owner_id != request.user.id:
            raise PermissionDenied("Bu placement'ı kabul edemezsiniz.")
        if placement.publisher_action != AdPlacement.PublisherAction.AUTO:
            raise ValidationError(
                {"publisher_action": "Bu placement hakkında zaten karar verilmiş."}
            )
        placement.publisher_action = AdPlacement.PublisherAction.ACCEPTED
        placement.save(update_fields=["publisher_action"])
        return Response({"status": "accepted", "placement_id": placement.id})
