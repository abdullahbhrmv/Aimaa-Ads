from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CampaignViewSet, AdViewSet, AdPlacementViewSet

router = DefaultRouter()
router.register("campaigns", CampaignViewSet, basename="campaign")
router.register("creatives", AdViewSet, basename="ad")
router.register("placements", AdPlacementViewSet, basename="placement")

urlpatterns = [
    path("", include(router.urls)),
]
