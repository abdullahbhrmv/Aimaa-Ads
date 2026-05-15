from django.urls import path
from .views import telegram_webhook

urlpatterns = [
    path("<str:token>/", telegram_webhook, name="telegram_webhook"),
]
