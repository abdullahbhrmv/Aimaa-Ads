from django.urls import path

from .views import InstallSnippetView, PixelEventIngestView, pixel_script_view

urlpatterns = [
    # Public ingest — browser SDK + Conversions API
    path("event/", PixelEventIngestView.as_view(), name="pixel_event_ingest"),

    # SDK JS bundle — Adım 1'de gerçek dist'e dönecek; şimdilik 501 placeholder.
    path("p.js", pixel_script_view, name="pixel_script"),

    # Authenticated advertiser endpoint — install snippet HTML
    path("install-snippet/", InstallSnippetView.as_view(), name="pixel_install_snippet"),
]
