"""
Pytest konfigürasyonu — FAZ 1 test altyapısı.

Tasarım notları:
- Celery task'ları `CELERY_TASK_ALWAYS_EAGER=True` ile senkron çalışır —
  test sırasında broker bağımlılığı yoktur.
- `TelegramAdSender` otomatik mocklanır: hiçbir test Telegram'a gerçek
  HTTP atmaz. Her test kendi davranışını `telegram_sender_mock` fixture'ı
  üzerinden konfigüre edebilir.
- Test DB Postgres olmalıdır — `select_for_update(skip_locked=True)`
  SQLite üzerinde desteklenmez.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _celery_eager(settings):
    """Tüm testlerde Celery'yi senkron moda al.

    Django `settings` üzerinden set yetmez — Celery app başlangıçta konfigi
    cache'liyor. Hem settings hem `app.conf`'a direkt yaz.
    """
    from core.celery import app
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True


@pytest.fixture(autouse=True)
def telegram_sender_mock(monkeypatch):
    """`TelegramAdSender` sınıfını otomatik mockla.

    Default davranış:
      - send_ad → sabit bir message_id döndürür
      - delete_message → True
      - get_chat_info → boş dict
    Testler sender.send_ad.side_effect gibi alanları özelleştirebilir.
    """
    from ads import telegram_client

    sender = MagicMock(spec=telegram_client.TelegramAdSender)
    sender.send_ad.return_value = 12345
    sender.delete_message.return_value = True
    sender.get_chat_info.return_value = {"member_count": 0}

    def _factory(*args, **kwargs):
        return sender

    monkeypatch.setattr(telegram_client, "TelegramAdSender", _factory)
    # ads.tasks modülü import sırasında from ads.telegram_client import ... yapmadığı
    # için factory üzerinden patch yeterli.
    return sender


@pytest.fixture
def money():
    """Test'lerde tekrarlayan Decimal literal'leri kısaltan yardımcı."""

    def _m(value):
        return Decimal(str(value))

    return _m


# --- Factory re-export'ları -------------------------------------------------
# Testlerde `from tests.factories import ...` yerine fixture kullanmak
# isteyenler için kısa yollar.

@pytest.fixture
def advertiser_factory(db):
    from tests.factories import AdvertiserFactory
    return AdvertiserFactory


@pytest.fixture
def publisher_factory(db):
    from tests.factories import PublisherFactory
    return PublisherFactory


@pytest.fixture
def channel_factory(db):
    from tests.factories import TelegramChannelFactory
    return TelegramChannelFactory


@pytest.fixture
def campaign_factory(db):
    from tests.factories import CampaignFactory
    return CampaignFactory


@pytest.fixture
def ad_factory(db):
    from tests.factories import AdFactory
    return AdFactory


@pytest.fixture
def placement_factory(db):
    from tests.factories import AdPlacementFactory
    return AdPlacementFactory


@pytest.fixture
def balance_factory(db):
    from tests.factories import UserBalanceFactory
    return UserBalanceFactory


@pytest.fixture
def transaction_factory(db):
    from tests.factories import TransactionFactory
    return TransactionFactory


@pytest.fixture
def payout_factory(db):
    from tests.factories import PayoutRequestFactory
    return PayoutRequestFactory


@pytest.fixture
def pixel_factory(db):
    from tests.factories import PixelInstallationFactory
    return PixelInstallationFactory


@pytest.fixture
def conversion_event_factory(db):
    from tests.factories import ConversionEventFactory
    return ConversionEventFactory


@pytest.fixture
def pixel_throttle_override():
    """Pixel throttle rate'ini geçici olarak override eder (FAZ 5 Adım 3 — I2).

    DRF `SimpleRateThrottle.THROTTLE_RATES` module import zamanında dict
    reference yakalar; reassign eski referansı kırar. Bu fixture dict'i
    in-place mutate eder ve finally'de restore eder.

    Kullanım:
        def test_something(pixel_throttle_override):
            pixel_throttle_override("2/min")
            # ... testing
            # Restore otomatik (fixture teardown).
    """
    from django.core.cache import cache
    from rest_framework.throttling import SimpleRateThrottle

    rates = SimpleRateThrottle.THROTTLE_RATES
    sentinel = object()
    original = rates.get("pixel", sentinel)

    def _apply(rate: str):
        rates["pixel"] = rate
        cache.clear()

    yield _apply

    # Restore — sentinel kullanarak "key yoktu" durumunu da doğru ele al.
    if original is sentinel:
        rates.pop("pixel", None)
    else:
        rates["pixel"] = original
    cache.clear()
