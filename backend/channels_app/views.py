from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import TelegramChannel, Category
from .serializers import ChannelSerializer, ChannelListSerializer, CategorySerializer
from core.permissions import IsBotAuthenticated

User = get_user_model()


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class ChannelViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelSerializer
    permission_classes = [permissions.IsAuthenticated | IsBotAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["category", "language", "status", "is_active"]
    search_fields = ["title", "username"]

    def get_queryset(self):
        qs = TelegramChannel.objects.all()

        # Bot istekleri owner_telegram_id ile gelir
        owner_telegram_id = self.request.query_params.get("owner_telegram_id")
        if owner_telegram_id:
            return qs.filter(owner__telegram_id=owner_telegram_id)

        user = self.request.user
        if hasattr(user, "role"):
            if user.role == "publisher":
                return qs.filter(owner=user)
            # Reklamverenler sadece onaylanmış kanalları görür
            return qs.filter(status="approved", is_active=True)

        return qs.filter(status="approved", is_active=True)

    def get_serializer_class(self):
        user = self.request.user
        if hasattr(user, "role") and user.role == "advertiser":
            return ChannelListSerializer
        return ChannelSerializer

    def perform_create(self, serializer):
        # Bot'tan gelen isteklerde owner_telegram_id ile kullanıcı bulunur
        owner_telegram_id = self.request.data.get("owner_telegram_id")
        if owner_telegram_id:
            try:
                owner = User.objects.get(telegram_id=owner_telegram_id)
                serializer.save(owner=owner)
                return
            except User.DoesNotExist:
                pass
        serializer.save(owner=self.request.user)


class BalanceView(APIView):
    """Yayıncı bakiye bilgisi (bot tarafından çağrılır)."""
    permission_classes = [IsBotAuthenticated]

    def get(self, request):
        telegram_id = request.query_params.get("telegram_id")
        if not telegram_id:
            return Response({"available": 0, "pending": 0})

        try:
            user = User.objects.get(telegram_id=telegram_id)
        except User.DoesNotExist:
            return Response({"available": 0, "pending": 0})

        channels = TelegramChannel.objects.filter(owner=user)
        pending = sum(float(c.pending_earnings) for c in channels)

        return Response({
            "available": float(user.balance),
            "pending": pending,
        })
