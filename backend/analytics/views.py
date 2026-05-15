from datetime import timedelta
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.db.models import Sum
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import AdEvent, DailyStats
from ads.models import AdPlacement
from core.permissions import IsBotAuthenticated


class TrackEventView(APIView):
    """Reklam olaylarını kaydet (bot tarafından çağrılır)."""
    permission_classes = [IsBotAuthenticated]

    def post(self, request):
        placement_id = request.data.get("placement_id")
        event_type = request.data.get("event_type")
        telegram_user_id = request.data.get("telegram_user_id")

        try:
            placement = AdPlacement.objects.get(id=placement_id)
        except AdPlacement.DoesNotExist:
            return Response(
                {"error": "Geçersiz placement"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Event kaydet
        AdEvent.objects.create(
            placement=placement,
            event_type=event_type,
            telegram_user_id=telegram_user_id,
            metadata=request.data.get("metadata", {}),
        )

        # Denormalized sayaçları güncelle
        if event_type == "impression":
            placement.impressions += 1
            placement.ad.impressions += 1
        elif event_type in ("click", "button_click"):
            placement.clicks += 1
            placement.ad.clicks += 1

        placement.save(update_fields=["impressions", "clicks"])
        placement.ad.save(update_fields=["impressions", "clicks"])

        return Response({"status": "ok"})


class CampaignAnalyticsView(APIView):
    """Kampanya bazlı analitik verileri."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, campaign_id):
        days = int(request.query_params.get("days", 7))
        since = timezone.now().date() - timedelta(days=days)

        stats = (
            DailyStats.objects
            .filter(campaign_id=campaign_id, date__gte=since)
            .values("date")
            .annotate(
                total_impressions=Sum("impressions"),
                total_clicks=Sum("clicks"),
                total_spent=Sum("spent"),
            )
            .order_by("date")
        )

        return Response(list(stats))


class TrackClickRedirectView(APIView):
    """Reklam button'u → backend → advertiser URL redirect akışı (FAZ 3).

    Her placement için `telegram_client.send_ad` bu endpoint'in URL'ini
    button_url yerine kullanır. İstek geldiğinde:
      1. HMAC token doğrulanır — URL parametresi kurcalanmış mı kontrol
         edilir.
      2. IP + User-Agent çıkarılır, `validate_click` çalıştırılır
         (ClickEvent oluşturulur, fraud flag'leri set edilir).
      3. 302 ile advertiser'ın orijinal URL'ine yönlendirilir.

    `is_suspicious=True` bile olsa redirect VERİLİR — kullanıcı deneyimini
    bozmayız. Sadece `valid_clicks` sayacına eklenmez; CPC billing bu
    sayede fraud'lara ödeme yapmaz.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # public endpoint

    def get(self, request, placement_id, token):
        from analytics.fraud import ClickContext, validate_click, verify_tracking_token

        # Target URL query string'den alınır — token bu URL + placement_id
        # üzerinde imzalı olduğu için değiştirilemez.
        target_url = request.query_params.get("u", "").strip()
        if not target_url:
            return Response({"error": "missing target"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            placement = AdPlacement.objects.select_related("ad").get(id=placement_id)
        except AdPlacement.DoesNotExist:
            return Response({"error": "placement not found"}, status=status.HTTP_404_NOT_FOUND)

        if not verify_tracking_token(placement_id, target_url, token):
            return Response({"error": "invalid token"}, status=status.HTTP_403_FORBIDDEN)

        ip = _extract_client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")
        tg_user_id = request.query_params.get("tg_id")
        try:
            tg_user_id_int = int(tg_user_id) if tg_user_id else None
        except ValueError:
            tg_user_id_int = None

        validate_click(
            placement,
            ClickContext(ip=ip, user_agent=ua, telegram_user_id=tg_user_id_int),
        )

        return HttpResponseRedirect(target_url)


def _extract_client_ip(request) -> str:
    """X-Forwarded-For header'ının ilk IP'sini kullan (reverse proxy arkasında)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class ChannelAnalyticsView(APIView):
    """Kanal bazlı analitik verileri (kanal sahipleri için)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, channel_id):
        days = int(request.query_params.get("days", 7))
        since = timezone.now().date() - timedelta(days=days)

        stats = (
            DailyStats.objects
            .filter(channel_id=channel_id, date__gte=since)
            .values("date")
            .annotate(
                total_impressions=Sum("impressions"),
                total_clicks=Sum("clicks"),
                total_revenue=Sum("revenue"),
            )
            .order_by("date")
        )

        return Response(list(stats))
