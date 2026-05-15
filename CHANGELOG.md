# Changelog

Bu dosya planlı faz kapsamı dışında yapılan eklemeleri ve bulunan silent
bug'ları takip eder. Faz özetleri için her faz sonundaki summary mesajlarına
bakılmalı; bu dosya yalnızca **scope creep** ve **retroactive discovery**
için tutulur.

## [Rebrand] — 2026-05-15

### Changed

- Repositioned from "Magfi's Uzbekistan version" to standalone "Built for
  Uzbekistan" identity. AimaaAds artık Aimaa Software (Qo'qon) tarafından
  Özbek pazarı için bağımsız bir ürün olarak konumlanıyor.
- Mass-renamed legacy `magfi_uz` / `magfi.uz` / `MagfiUZBot` / `MagfiUZSupport`
  strings to `aimaa_ads` / `aimaa.uz` / `aimaa_ads_bot` / `aimaa_ads_support`
  across docker-compose, `.env.example` (root + bot), seed data, comments,
  and documentation.
- Updated README, CLAUDE.md, PERMISSIONS_GUIDE, frontend (Deposit,
  CampaignCreate), admin (SystemSettings), and bot footer to AimaaAds branding.
- Bot footer (`bot/services/telegram_sender.py`) artık dinamik:
  `PLATFORM_BOT_USERNAME` env var'ından okur, default `aimaa_ads_bot`.
- README + .env.example dosyalarındaki gerçek görünen secret'lar placeholder'a
  çevrildi (`your_secret_key_here`, `your_bot_token_here`,
  `your_bot_api_secret_here`). **Bunlar rotate edilmedi** — ayrı bir security
  görevi olarak operator tarafından yapılacak.

### Rationale

- **Legal exposure**: Magfi (magfiads.com) Özbekistan pazarına 2026 başında
  resmi olarak girdi. Kendi dokümantasyonumuzda kendimizi "onların klonu"
  olarak tanımlamamız trademark / haksız rekabet riski oluşturuyordu.
- **Strategic**: AimaaAds'in gerçek değer önerisi yerel olmaktan geliyor —
  UZS-native fiyatlandırma, Click.uz + Payme entegrasyonu, Özbekçe/Rusça
  arayüz, Qo'qon merkezli Aimaa Software ekibi. Magfi'ye atıf bu değer
  önerisini gizliyordu.

### Migration (mevcut lokal kurulumlar için)

Eski `magfi_uz` adıyla çalışan lokal DB'ler için iki opsiyon:

```bash
# Opsiyon A — Docker volume'u sıfırla (veri kaybı kabul edilebiliyorsa)
docker-compose down -v && docker-compose up -d db
docker-compose run backend python manage.py migrate

# Opsiyon B — Veriyi koru, yalnız adı değiştir
psql postgres -c "ALTER DATABASE magfi_uz RENAME TO aimaa_ads;"
```

Bot username de değiştirilmek isteniyorsa: `backend/.env` ve `bot/.env`
içinde `TELEGRAM_BOT_USERNAME` / `BOT_USERNAME` değerlerini güncelleyin;
`PLATFORM_BOT_USERNAME` env var'ı reklam footer'ında kullanılır.

## FAZ 5 Adım 2 (2026-04-20)

### Plan-dışı ek

- **`pixel.ConversionEvent.fn_hash` + `ln_hash`** — plana göre yalnız
  `em_hash`, `ph_hash`, `external_id_hash` vardı. `hash_fixtures.json`
  `name` kategorisi için test vektörleri içerdiğinden, ingestion consistency
  için bu iki alan da eklendi. Migration `pixel/0003_conversionevent_name_hashes`.
  Ek maliyet: 2 CharField(64) kolonu — ihmal edilebilir.

### Silent bug'lar (retroactive discovery)

Full test suite ilk defa Adım 2 sonunda çalıştırıldı; iki bug yakalandı:

1. **Celery eager scope bug** (FAZ 1'den beri silent, 4 test etkilendi).
   `conftest.py::_celery_eager` fixture'ı Django `settings` üzerinden
   `CELERY_TASK_ALWAYS_EAGER=True` yazıyordu, ancak Celery app config'i
   startup'ta cache'liyor — runtime değişiklikler propagate etmiyor.
   Etkilenen test'ler broker'a gerçekten bağlanıyordu (AMQP connection
   refused → silent `.delay()` dispatch miss).
   **Fix**: `app.conf.task_always_eager = True` direkt Celery app instance'a
   yazılıyor.

   Etkilenen ve artık gerçek eager mode'da koşan test'ler:
   - `test_ad_lifecycle.py::test_full_scheduled_to_billed_flow`
   - `test_ad_lifecycle.py::test_expired_ads_dispatcher_only_picks_due_placements`
   - `test_ad_lifecycle.py::test_concurrent_dispatch_only_bills_once`
   - `test_publisher_rejection.py::test_publisher_can_reject_own_placement`

2. **QueryDict flatten bug** (FAZ 4a'dan, 9 Click webhook test'i etkiliyordu).
   Click.uz form-encoded POST yapıyor; DRF `request.data` `QueryDict` olarak
   parse ediyor. `dict(QueryDict)` multi-value liste formatına çevirir
   (`click_trans_id=['aud-1']`), imza doğrulama ve dispatch bozuluyordu.
   **Fix**: `payments/providers/base.py::flatten_request_data(request)` helper;
   `ClickProvider.verify_request/handle_webhook` + webhook view'ları kullanıyor.

### TODO'lar (ileriki fazlar)

- **FAZ 5.5**: `test_attribution.py::test_second_attribute_call_returns_existing_conversion`
  mock-level (sequential double-call). Real concurrency test threading +
  ayrı DB connection ile yazılmalı.
- **FAZ 5.5**: Advanced matching (em_hash cross-device) attribution'a entegre.
  Şu an sadece hash saklama; lookup yok.
- **Python version pin**: pytest-celery Python 3.14'te `pkg_resources`
  kullandığından çalışmıyor, `-p no:celery` workaround'u var. Staging
  deploy öncesi `.python-version` 3.13 LTS'e düşürme değerlendirilmeli.
- **Retroaktif smoke test review**: FAZ 5 bitiminde FAZ 1 ve FAZ 4a test'lerinin
  Celery eager bug benzerlerinin olmadığı tekrar doğrulanmalı.
- **Unmatched event counter exposure**: `attribute_pending_conversions`'un
  `unmatched` counter'ı şu an yalnız task return payload'ında. FAZ 5 Adım 6
  Funnel/Cohort endpoint'lerinde advertiser-görünür metriğe dönüştürülmeli
  ("attribute edilemeyen Purchase event sayısı").
