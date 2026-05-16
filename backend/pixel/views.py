"""
Pixel HTTP endpoint'leri (FAZ 5 Adım 3).

Endpoint'ler:
- `POST /api/pixel/event/`              — browser SDK + Conversions API
- `OPTIONS /api/pixel/event/`           — CORS preflight
- `GET /api/pixel/install-snippet/`     — advertiser için kopyala-yapıştır HTML
- `GET /api/pixel/p.js`                 — SDK dosyası (Adım 1'e kadar 501)

CORS:
- `allowed_domains` pixel'e özgü (whitelist dinamik)
- Wildcard `*.example.com` permissive (`matches_allowed_domain`)
- Credentials kullanılmıyor (pixel public, cookie session yok)

Throttle: `PixelEventThrottle` (300/min IP).

Güvenlik:
- Origin header ZORUNLU; yoksa 403.
- pixel_id payload'dan veya query string'den gelir; enabled=False → 403.
- Event payload validasyonu `record_event` servisinde.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from pixel.models import PixelInstallation
from pixel.services import (
    DomainNotAllowedError,
    EventValidationError,
    PixelDisabledError,
    matches_allowed_domain,
    record_event,
)
from pixel.throttle import PixelEventThrottle

logger = logging.getLogger(__name__)


def _extract_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _extract_origin(request) -> str:
    """`Origin` header öncelikli, yoksa `Referer`'dan domain türet."""
    origin = request.META.get("HTTP_ORIGIN", "").strip()
    if origin:
        return origin
    return request.META.get("HTTP_REFERER", "").strip()


def _cors_headers(response, origin: str) -> HttpResponse:
    """Dinamik origin echo — sadece doğrulanmış origin'ler için."""
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type, Accept"
    response["Vary"] = "Origin"
    response["Access-Control-Max-Age"] = "86400"
    return response


class PixelEventIngestView(APIView):
    """Browser SDK + Conversions API ortak ingest endpoint'i.

    Auth YOK — pixel public kanal. Koruma: origin whitelist + throttle +
    payload validasyon. Dedup DB unique constraint (pixel, event_id).
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PixelEventThrottle]

    def options(self, request, *args, **kwargs):
        """CORS preflight — origin whitelist'te varsa dinamik echo."""
        origin = _extract_origin(request)
        pixel = self._resolve_pixel(request)
        response = HttpResponse(status=200)
        if pixel and matches_allowed_domain(
            origin, pixel.allowed_domains, pixel.debug_mode
        ):
            _cors_headers(response, origin)
        return response

    def post(self, request, *args, **kwargs):
        origin = _extract_origin(request)
        pixel = self._resolve_pixel(request)
        if pixel is None:
            return Response(
                {"error": "pixel_not_found"}, status=status.HTTP_404_NOT_FOUND,
            )

        # event_source — SDK'dan gelen trafik "browser", server-side
        # Conversions API kullanımı için header veya payload override.
        event_source = request.data.get("event_source") or "browser"

        try:
            event, ingest_status = record_event(
                pixel=pixel,
                payload=request.data,
                origin=origin,
                client_ip=_extract_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                event_source=event_source,
            )
        except PixelDisabledError:
            return Response(
                {"error": "pixel_disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )
        except DomainNotAllowedError:
            return Response(
                {"error": "domain_not_allowed"},
                status=status.HTTP_403_FORBIDDEN,
            )
        except EventValidationError as exc:
            return Response(
                {"error": "invalid_payload", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("Pixel ingest failed: %s", exc)
            return Response(
                {"error": "internal"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = Response(
            {"status": ingest_status, "event_id": str(event.event_id)},
            status=status.HTTP_200_OK,
        )
        return _cors_headers(response, origin)

    @staticmethod
    def _resolve_pixel(request) -> PixelInstallation | None:
        """pixel_id query string veya body'den çekilir."""
        pixel_id = (
            request.GET.get("pixel_id")
            or (isinstance(request.data, dict) and request.data.get("pixel_id"))
            or ""
        )
        if not pixel_id:
            return None
        try:
            return PixelInstallation.objects.get(pixel_id=pixel_id)
        except (PixelInstallation.DoesNotExist, ValueError):
            return None


class InstallSnippetView(APIView):
    """Advertiser için kopyala-yapıştır HTML snippet (E1).

    Auth'lı — yalnız advertiser kendi pixel'ini alabilir. `GET` döner,
    body'de `snippet` alanı SDK yükleme kodunu içerir. Frontend `<textarea>`
    ile gösterip "Copy" butonu koyar.

    **K1 gate**: `settings.AIMAA_SDK_DEPLOYED=False` ise endpoint `503`
    döner — reklamveren snippet'i siteye yapıştırıp `/api/pixel/p.js`
    (henüz 501 placeholder) yüzünden her page load'da console error
    almasın. Adım 1 tamamlanıp SDK deploy olunca env var True yapılır.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if not settings.AIMAA_SDK_DEPLOYED:
            return Response(
                {
                    "status": "sdk_deployment_pending",
                    "eta": "pending admin confirmation",
                    "detail": (
                        "AimaaPixel SDK henüz deploy edilmedi. "
                        "Endpoint SDK hazır olunca aktifleşecek."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        pixel, _ = PixelInstallation.objects.get_or_create(advertiser=request.user)

        # Base URL — production'da ortam değişkeninden. Dev'de host header.
        base_url = request.build_absolute_uri("/").rstrip("/")

        snippet = _render_install_snippet(
            pixel_id=str(pixel.pixel_id),
            base_url=base_url,
        )

        return Response({
            "pixel_id": str(pixel.pixel_id),
            "snippet": snippet,
            "snippet_version": 1,
            "endpoint": f"{base_url}/api/pixel/event/",
            "debug_mode": pixel.debug_mode,
            "enabled": pixel.enabled,
        })


# Snippet versiyonu — SDK bu değeri script tag'inin `data-aimaa-version`
# attribute'undan okur. Debug mode'da console.log'lar, mismatch durumunda
# "eski snippet kullanıyorsunuz" uyarısı verir. Destek ekibi teşhisi için
# reklamveren snippet'ini kopyaladığı tarih dolaylı olarak tespit edilir.
INSTALL_SNIPPET_VERSION = 1


def _render_install_snippet(pixel_id: str, base_url: str) -> str:
    """Meta Pixel benzeri inline snippet.

    `_aq` kuyruğu SDK yüklenmeden önceki çağrıları (örn. sayfa başında
    `aimaa('track', 'PageView')`) biriktirir; SDK init olunca flush eder.
    Dinamik oluşturulan `<script>` tag'ine `data-aimaa-version` eklenir;
    SDK bunu okuyup versiyonu doğrular (I3).
    """
    version = str(INSTALL_SNIPPET_VERSION)
    return (
        "<!-- Aimaa Pixel -->\n"
        "<script>\n"
        "(function(w,d,s,u,v){\n"
        "  if(w.aimaa)return;\n"
        "  var q=w._aq=w._aq||[];\n"
        "  w.aimaa=function(){q.push(arguments)};\n"
        "  w.aimaa('init','" + pixel_id + "');\n"
        "  w.aimaa('track','PageView');\n"
        "  var el=d.createElement(s);el.async=1;el.src=u;\n"
        "  el.setAttribute('data-aimaa-version',v);\n"
        "  var f=d.getElementsByTagName(s)[0];f.parentNode.insertBefore(el,f);\n"
        "})(window,document,'script','" + base_url + "/api/pixel/p.js','" + version + "');\n"
        "</script>\n"
        "<!-- End Aimaa Pixel -->\n"
    )


_PIXEL_DIST_PATH = settings.BASE_DIR.parent / "pixel" / "dist" / "pixel.js"


@csrf_exempt
def pixel_script_view(request):
    """SDK JS dosyasını serve et.

    Build edilmiş `pixel/dist/pixel.js` varsa `application/javascript` + 200
    döner. Yoksa 501 + placeholder (geliştirici daha `npm run build`
    çalıştırmamış demektir).

    Cache: DEBUG=True iken no-cache (build sonrası anında yeni versiyon),
    DEBUG=False iken 5 dakika public cache. Production'da nginx / CDN bu
    URL'i daha agresif cache'leyebilir.
    """
    try:
        body = _PIXEL_DIST_PATH.read_bytes()
    except (FileNotFoundError, OSError):
        placeholder = (
            "/* Aimaa Pixel SDK — bundle not built. "
            "Run `npm run build` in pixel/ to produce dist/pixel.js. */\n"
            "console.warn('aimaa-pixel: SDK bundle not yet built');\n"
        )
        response = HttpResponse(
            placeholder,
            content_type="application/javascript; charset=utf-8",
            status=501,
        )
        response["Cache-Control"] = "no-store"
        return response

    response = HttpResponse(
        body,
        content_type="application/javascript; charset=utf-8",
        status=200,
    )
    if settings.DEBUG:
        response["Cache-Control"] = "no-cache"
    else:
        response["Cache-Control"] = "public, max-age=300"
    return response
