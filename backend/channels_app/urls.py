from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChannelViewSet, CategoryViewSet, BalanceView

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("", ChannelViewSet, basename="channel")

urlpatterns = [
    path("balance/", BalanceView.as_view(), name="channel_balance"),
    path("", include(router.urls)),
]
