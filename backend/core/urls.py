from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import (
    RegisterView, MeView, DashboardStatsView,
    TelegramRegisterView, DashboardChartView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/me/", MeView.as_view(), name="me"),
    path("api/auth/telegram-register/", TelegramRegisterView.as_view(), name="telegram_register"),

    # Dashboard
    path("api/dashboard/stats/", DashboardStatsView.as_view(), name="dashboard_stats"),
    path("api/dashboard/chart/", DashboardChartView.as_view(), name="dashboard_chart"),

    # Apps
    path("api/ads/", include("ads.urls")),
    path("api/channels/", include("channels_app.urls")),
    path("api/analytics/", include("analytics.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/pixel/", include("pixel.urls")),

    # Admin API
    path("api/admin-panel/", include("core.admin_urls")),

    # Webhook for Telegram bot
    path("api/bot/webhook/", include("bot_webhook.urls")),

    # API docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
