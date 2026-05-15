from django.urls import path
from .views import (
    TrackEventView, CampaignAnalyticsView, ChannelAnalyticsView,
    TrackClickRedirectView,
)

urlpatterns = [
    path("track/", TrackEventView.as_view(), name="track_event"),
    # FAZ 3 — public click redirect (auth yok; HMAC token koruması).
    path(
        "track/c/<int:placement_id>/<str:token>/",
        TrackClickRedirectView.as_view(),
        name="track_click_redirect",
    ),
    path("campaign/<int:campaign_id>/", CampaignAnalyticsView.as_view(), name="campaign_analytics"),
    path("channel/<int:channel_id>/", ChannelAnalyticsView.as_view(), name="channel_analytics"),
]
