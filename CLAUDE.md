# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AimaaAds** is a Telegram advertising platform built for the Uzbekistan market by Aimaa Software (Qo'qon). It connects advertisers with Telegram channel publishers, with native UZS billing, Click.uz + Payme payment integration, and Uzbek/Russian UI. It has four cooperating services plus a standalone JS SDK: Django REST backend, React advertiser panel, React admin panel, aiogram-based Telegram bot, and **AimaaPixel** (vanilla JS conversion tracking SDK — Meta Pixel pattern).

Revenue model: 30% platform commission, 70% publisher. Billing is CPM or CPC. Primary UI languages are Uzbek (`uz`, Latin + Cyrillic) and Russian (`ru`). Operating domain: `ads.aimaa.uz`. Local team in Qo'qon.

## Architecture

Five deliverables; first four are runtime services:

- **backend/** — Django 5.2 + DRF + PostgreSQL 16. Single source of truth. Ad delivery, billing, moderation, fraud, payments webhooks, pixel ingestion. JWT auth (`rest_framework_simplejwt`), `AUTH_USER_MODEL = core.User`. Timezone `Asia/Tashkent`. Swagger at `/api/docs/`. **Python 3.14** in dev venv.
- **frontend/** — React 18 + Vite + Tailwind. Advertiser panel (port 5173). State via zustand, API via axios.
- **admin/** — React 18 + Vite + Tailwind. Admin/moderation panel (port 5174). Consumes `/api/admin-panel/*`.
- **bot/** — Python 3.14 + aiogram 3. Publisher onboarding via Telegram. Talks to backend via `services/api_client.py` using `X-Bot-Secret` header — no JWT.
- **pixel/** — Vanilla JS SDK (repo root, backend dışında). Advertiser sites embed it for conversion tracking (Purchase, Lead, PageView). Backend ingestion endpoint + server-side Conversions API. Adım 1 build pending — dist yet to be deployed.

### Backend apps (Django)

- `core/` — Custom `User`, `PayoutRequest`, JWT, dashboard. **Admin-panel API lives here in `admin_api.py` + `admin_urls.py`** (not a separate app). 200+ admin endpoints span campaigns, channels, users, payouts, moderation queue, fraud dashboard, channel trust override.
- `ads/` — `Campaign`, `Ad`, `AdPlacement`, `AdVariantExperiment`. `tasks.py` — all Celery jobs (settlement, scan, reassignment, quality, fraud, anomaly). `services.py` — cost/revenue splits (Decimal), campaign scheduling. `telegram_client.py` — Telegram Bot API wrapper + tracking URL generation.
- `channels_app/` — `Category`, `TelegramChannel`, `DailyChannelSnapshot`. Per-channel CPM is dynamic: base subscriber tier × quality multiplier × probation multiplier (see `TelegramChannel.cpm_rate`).
- `analytics/` — `AdEvent`, `DailyStats`, `DailyFunnelStats`, `ClickEvent`. Click fraud detection in `fraud.py` (IP hashing, rate limit, bot speed, cluster analysis). Click redirect endpoint for tracking URL attribution.
- `payments/` — `UserBalance`, `Transaction`, `Invoice`, `PaymentAuditLog`, `PaymentSettings`. Click.uz + Payme webhook handlers in `providers/`. Balance freeze/spend/refund flow atomic with `select_for_update`. **Provider env vars empty until FAZ 4b — webhooks return 503.**
- `pixel/` — `PixelInstallation`, `ConversionEvent`, `Conversion`. Conversion ingest + attribution. `attribution.py` — click_id + UTM strategies (advanced matching FAZ 5.5). `tasks.py` — nightly `attribute_pending_conversions` with 30-day expiry cutoff.
- `bot_webhook/` — Inbound Telegram webhook (though bot runs in polling mode by default).

### Ad delivery lifecycle (critical flow)

Don't invent a new path — this is the pipeline the Celery schedule in `backend/core/celery.py` drives. **`AdPlacement` has orthogonal `status` (delivery state) and `billing_status` (financial state) fields** — idempotency guarantees rely on this separation.

1. Advertiser creates `Campaign` (status `pending`, `moderation_status=pending`) → `scan_campaign_creatives.delay()` fires. Scanner sets `moderation_status` to `auto_approved` / `flagged` / `rejected` based on `banned_words.py` taxonomy (severity: critical → hard reject, high/medium → queue).
2. Admin approves → `freeze_for_campaign()` moves budget from `UserBalance.balance` to `frozen_amount`. Insufficient balance → approve fails with 400.
3. Approval creates `AdPlacement(status=scheduled, billing_status=pending, publisher_action=auto, scheduled_at=...)`. Scheduler uses weighted random variant selection if `Campaign.experiment` exists (A/B test).
4. `deliver_scheduled_ads` (every 60s) picks due placements with `select_for_update(skip_locked=True)`, sends via `TelegramAdSender` (button URL wrapped through `/api/analytics/track/c/<id>/<token>/?u=...`), marks `sent`. Excludes `publisher_action=rejected`.
5. `delete_expired_ads` (every 5 min) finds sent placements past `sent_at + delete_after_hours` with `billed_at IS NULL`. Dispatches `_settle_placement.delay(id)` per placement.
6. `_settle_placement` — **bills FIRST inside transaction, then Telegram delete**. Computes cost/revenue (Decimal), sets `billed_at`, `billing_status=billed|skipped`. Calls `payments.services.spend_from_frozen()` + `credit_publisher()` (balance system). Updates denormalized `Campaign.spent` + `TelegramChannel.total_earnings` via F() atomic update. Telegram delete happens outside transaction — failure leaves `status=sent` but `billed_at` set, next run skips.
7. `check_campaign_budgets` (every 5 min) completes campaigns whose `spent >= budget` or `end_date` passed. On complete, `refund_unspent_campaign()` returns unused frozen budget.
8. `aggregate_daily_stats` (daily) + `aggregate_funnel_stats` (FAZ 5.5 pending) roll into analytics tables.
9. `update_channel_stats` (hourly) refreshes subscriber counts.
10. `recalculate_channel_quality_scores` (daily), `detect_subscriber_anomalies` (hourly), `detect_ip_cluster_fraud_task` (daily) — quality + fraud pipeline.
11. `attribute_pending_conversions` (every 5 min) — pixel events → Conversion via `click_id` cookie or `utm_campaign` slug match. 30-day cutoff marks stale events as attempted.

### Auth & permissions

- JWT for web clients (`/api/auth/login/`, `/api/auth/refresh/`). Access 12h, refresh 30d.
- Bot: shared-secret header `X-Bot-Secret` (backend `BOT_API_SECRET` == bot `BOT_SECRET`). Enforced by `core.permissions.IsBotAuthenticated`.
- Admin hierarchy: `is_superuser` (root, undeletable) > `is_staff + role='admin'` > `advertiser`/`publisher`. Helper props: `user.is_root_admin`, `user.is_staff_admin`, `user.is_any_admin`. Permission classes: `IsSuperAdmin`, `IsStaffAdmin`, `IsAdmin` in `core/permissions.py`.
- Payment webhooks (`/api/payments/{click,payme}/webhook/`) — provider-native auth: Click MD5 signature, Payme Basic Auth. Env var yoksa endpoint 503.
- Pixel ingest (`/api/pixel/event/`) — **public**, no auth. Protected by `PixelInstallation.allowed_domains` origin whitelist + dedup via unique `(pixel, event_id)` + IP-based throttle (300/min).

## Commands

Backend/bot Python commands assume corresponding venv is activated.

### Backend

```bash
cd backend && source venv/bin/activate
python manage.py makemigrations
python manage.py migrate
python manage.py setup_permissions       # seeds admin permission groups
python manage.py createsuperuser
python manage.py runserver 8000
python manage.py shell                    # for manual task triggering
```

Celery (two separate terminals):

```bash
celery -A core worker -l info
celery -A core beat -l info
```

### Test suite (exists — 220 tests as of FAZ 5 Adım 3)

```bash
cd backend && source venv/bin/activate
pytest                                    # full suite
pytest tests/test_billing.py -v           # single module
pytest -k idempotent -v                   # filter by test name
```

Test DB **must be Postgres** — `select_for_update(skip_locked=True)` + partial unique indexes + JSON aggregation are Postgres-specific. SQLite won't work. pytest-django auto-creates `test_aimaa_ads`; needs `CREATEDB` permission.

`pytest.ini` disables `pytest-celery` plugin (`-p no:celery`) — it imports `pkg_resources` which was removed in Python 3.14. The plugin isn't used (tests run Celery eager mode).

### Pixel SDK (Adım 0 done, Adım 1 pending)

```bash
cd pixel
npm test                                  # hash contract parity (29 vectors)
# npm run build                           # esbuild — Adım 1 will add
```

Hash fixture at `pixel/fixtures/hash_fixtures.json` is ground truth for JS ↔ Python parity (see `backend/tests/test_hash_fixtures_parity.py`).

### Frontend / Admin

```bash
cd frontend && npm install && npm run dev    # advertiser panel → :5173
cd admin && npm install && npm run dev       # admin panel → :5174
```

Neither defines `lint` or `test` scripts.

### Bot

```bash
cd bot && source venv/bin/activate && python main.py   # aiogram long-polling
```

### Docker alternative

`docker-compose.yml` at repo root brings up db, redis, backend, celery, celery-beat, bot, frontend. DB name `aimaa_ads` across compose and local dev.

## Configuration

- `backend/.env` + `bot/.env` required. `BOT_API_SECRET` (backend) == `BOT_SECRET` (bot) veya 401.
- **Monetary fields are `DecimalField`** — preserve Decimal arithmetic, never convert to float. `payments.services` uses `ROUND_HALF_UP` and quantizes to 2 decimal places. `platform_fee + publisher_revenue == total_cost` invariant is enforced.
- `PLATFORM_COMMISSION_RATE` and `MIN_PAYOUT_AMOUNT` still in `settings.py` for backward compat; source of truth is `payments.PaymentSettings.get_solo()` singleton.
- Env vars:
  - `FRAUD_IP_SALT`, `CLICK_TRACKING_SECRET` — hash / token signing
  - `TRACKING_BASE_URL` — pixel redirect target (boşsa redirect devre dışı)
  - `CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID`, `CLICK_SECRET_KEY` — Click.uz (FAZ 4b)
  - `PAYME_MERCHANT_ID`, `PAYME_MERCHANT_KEY` — Payme (FAZ 4b)
  - `AIMAA_SDK_DEPLOYED` — `True` olunca `/api/pixel/install-snippet/` snippet döner; default `False` → 503 (Adım 1 gate)
- CORS default = dev Vite ports. `CORS_URLS_REGEX = r"^/api/(?!pixel/).*$"` — **pixel endpoint'leri corsheaders'tan muaf**, view'lar kendi dinamik per-installation CORS logic'ini uygular. Yeni "pixel" kelimeli app eklerken bu regex'i gözden geçir.

## Gotchas

- **Historical note (resolved)**: Proje önceden bir Türk platformunun "UZ versiyonu" olarak konumlanmıştı; bu konumlandırma rebrand ile tamamen kaldırıldı (bkz. CHANGELOG.md `[Rebrand]` entry'si). Yeni metinlerde, yorumlarda ya da örneklerde **rakip marka adına atıf yapma** — AimaaAds bağımsız bir üründür ve yerel kimliği üzerinden konumlanır.
- **Mixed language**: Yorumlar, `help_text`, docstring'ler Türkçe / Özbekçe / Rusça karışık. Dosyanın mevcut dilini takip et.
- **`AdPlacement.unique_together = ["ad", "channel", "scheduled_at"]`** — bulk generation'da identical `scheduled_at` çakışır. `schedule_campaign` 30dk ofset + placement_id mod 60 saniye ile unique timestamp garantiler.
- **Billing on deletion, not send**: `_settle_placement` `delete_expired_ads` dispatcher'ı tarafından tetiklenir. `deliver_scheduled_ads`'e `campaign.spent +=` eklersen double-charge olur.
- **frontend/ ve admin/ paralel**: Neredeyse özdeş `package.json` + dizin layout. Shared-looking değişiklik ikisini de etkiliyor olabilir, her iki kopyayı da kontrol et.
- **Celery eager bug precedent**: `conftest.py::_celery_eager` fixture'ı `app.conf.task_always_eager = True` ile DOĞRUDAN Celery app'e yazmalı — sadece `settings.CELERY_TASK_ALWAYS_EAGER = True` yetmez (startup cache). FAZ 5 Adım 2'ye kadar 4 test silent broker'a gidiyordu (test_ad_lifecycle, test_publisher_rejection). `.delay()` eklerken test'ler fail ettiğinde ilk bakılacak yer buradaki fixture.
- **QueryDict flatten**: Click.uz form-encoded POST yollar. DRF `request.data` `QueryDict` olarak parse eder. `dict(QueryDict)` multi-value liste üretir (`click_trans_id=['value']`), signature doğrulama bozulur. `payments/providers/base.py::flatten_request_data(request)` helper kullan.
- **DRF throttle class-level cache**: `SimpleRateThrottle.THROTTLE_RATES` module import zamanında dict reference yakalar. Test'te `api_settings.DEFAULT_THROTTLE_RATES = {...}` reassign ESKİ referansı bağlı bırakır; in-place `rates["pixel"] = "2/min"` mutate gerek. Bunun için `pixel_throttle_override` fixture'ı var (`backend/conftest.py`).
- **Partial indexes Postgres-only**: `ClickEvent.em_hash`, `ConversionEvent.em_hash` üzerinde `condition=~Q(em_hash="")` partial index var. `AdVariantExperiment` üzerinde `condition=Q(status="running")` partial unique (kampanya başına tek running). SQLite bunları desteklemez.
- **Hash contract parity**: JS (`pixel/src/hash.js`) ve Python (`backend/pixel/services.py::normalize_for_hash`) IDENTIK çıktı üretmeli. Ground truth `pixel/fixtures/hash_fixtures.json`. Parity bozulursa cross-device attribution (FAZ 5.5) sessizce bozulur. İki ayrı test dosyası (`pixel/test/hash.test.js` + `backend/tests/test_hash_fixtures_parity.py`) bu invariant'ı doğruluyor.
- **Python 3.14 + pytest-celery**: pytest-celery plugin `pkg_resources` (setuptools 82 öncesi kaldırıldı) import eder. `pytest.ini` `-p no:celery` ile plugin disabled. Staging deploy öncesi Python 3.13 LTS'e düşürme değerlendiriliyor.

## Phase status

FAZ 1 (billing safety + test foundation) → ✅
FAZ 2 (moderation + publisher reject) → ✅
FAZ 3 (fraud + quality scoring + probation) → ✅
FAZ 4a (balance system + webhook infrastructure) → ✅ (4b: real provider keys pending)
FAZ 5 Adım 0 (hash contract) → ✅
FAZ 5 Adım 2 (backend services + attribution) → ✅
FAZ 5 Adım 3 (ingest + snippet + placeholder) → ✅ (snippet 503-gated until Adım 1)
FAZ 5 Adım 1 (SDK build) → pending
FAZ 5 Adımlar 4-8 → pending
FAZ 7, FAZ 6, FAZ 8 → pending (order revised 5 → 7 → 6 → 8)

See `CHANGELOG.md` for scope-creep additions and retroactive silent bug discoveries.
