import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    # Local apps
    "core",
    "ads",
    "channels_app",
    "analytics",
    "payments",
    "pixel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "aimaa_ads"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Auth
AUTH_USER_MODEL = "core.User"

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Webhook rate limiting (FAZ 4a) — provider bazında abuse izolasyonu.
    # Pixel event ingest (FAZ 5 Adım 3) — browser SDK yüksek frekanslı.
    "DEFAULT_THROTTLE_RATES": {
        "webhook": "120/min",
        "webhook_click": "120/min",
        "webhook_payme": "120/min",
        "pixel": "300/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

# CORS
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174"
).split(",")

# DİKKAT: Bu regex /api/pixel/* path'ini corsheaders'tan muaf tutar.
# Pixel view'ları kendi dinamik per-installation CORS logic'ini uygular
# (PixelInstallation.allowed_domains + wildcard matching).
#
# Yeni bir "pixel" kelimeli app eklenirse (örn. /api/pixel-analytics/)
# regex yanlışlıkla onu da muaf tutar. Bu gibi eklemelerde regex'i
# daha spesifik yap: `r"^/api/(?!pixel/[^-/]).*$"` gibi negatif lookahead
# ile sadece tek path segment'ini hedefle, ya da explicit pattern listesi kullan.
CORS_URLS_REGEX = r"^/api/(?!pixel/).*$"

# --- Pixel SDK deployment flag (FAZ 5 Adım 1 öncesi K1) ---------------------
# SDK bundle (`pixel/dist/aimaa-pixel.min.js`) henüz deploy edilmediyse,
# `InstallSnippetView` `503` döner. Reklamveren snippet'i siteye
# yapıştırırsa `/api/pixel/p.js` 501 dönerdi → page'de console error.
# Advertiser-safe davranış: snippet endpoint'i SDK deploy olmadan
# açılmaz. Adım 1 tamamlanınca env var True yapılır.
AIMAA_SDK_DEPLOYED = os.getenv("AIMAA_SDK_DEPLOYED", "False").lower() in ("true", "1", "yes")

# Celery
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Media
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")
ADS_CHANNEL_ID = int(os.getenv("ADS_CHANNEL_ID", "0"))  # Bot'un reklam hazırlama kanalı

# Bot API
BOT_API_SECRET = os.getenv("BOT_API_SECRET", "")

# Platform settings
# NOT (FAZ 4a): Bu iki değer `payments.PaymentSettings` singleton'ından
# okunacak şekilde genişletildi. Bu sabitler geriye dönük uyumluluk için
# fallback olarak korunur; yeni kod `PaymentSettings.get_solo()` kullanmalı.
PLATFORM_COMMISSION_RATE = 0.30  # 30% komisyon
MIN_PAYOUT_AMOUNT = 50000  # 50,000 UZS minimum ödeme

# --- Ödeme provider env var'ları (FAZ 4a) ---------------------------------
# API keyler FAZ 4b'de edinildiğinde env'e eklenir. Boş olduklarında
# webhook endpoint'leri `503 Service Unavailable` döner.
CLICK_SERVICE_ID = os.getenv("CLICK_SERVICE_ID", "")
CLICK_MERCHANT_ID = os.getenv("CLICK_MERCHANT_ID", "")
CLICK_SECRET_KEY = os.getenv("CLICK_SECRET_KEY", "")
PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID", "")
PAYME_MERCHANT_KEY = os.getenv("PAYME_MERCHANT_KEY", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# i18n
LANGUAGE_CODE = "uz"
LANGUAGES = [
    ("uz", "O'zbekcha"),
    ("ru", "Русский"),
]
USE_I18N = True
TIME_ZONE = "Asia/Tashkent"
USE_TZ = True

# Spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "AimaaAds API",
    "DESCRIPTION": "Telegram Reklam Platformu API",
    "VERSION": "1.0.0",
}
