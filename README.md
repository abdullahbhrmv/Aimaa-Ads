# AimaaAds — Telegram Reklam Platformu

> O'zbekiston uchun qurilgan Telegram reklama va monetizatsiya platformasi.
> Mahalliy to'lov tizimlari (Click, Payme), UZS narxlash va o'zbek/rus tilida to'liq qo'llab-quvvatlash.
>
> Telegram advertising and monetization platform built for Uzbekistan.
> Native UZS pricing, Click.uz + Payme integration, full Uzbek and Russian support,
> local team in Qo'qon.

## 📋 Proje Hakkında

**AimaaAds**, Aimaa Software (Qo'qon) tarafından Özbekistan pazarı için inşa edilen, reklamverenleri (advertisers) Telegram kanal sahipleri (publishers) ile buluşturan bir platformdur. Yerel ekip, yerel ödeme altyapısı ve yerel dil desteğiyle bu coğrafyaya özel kurgulanmıştır.

### Özgün Değer Önerisi

- 🇺🇿 **Yerel ekip**: Qo'qon merkezli Aimaa Software ekibi tarafından geliştiriliyor — Özbek pazarının ihtiyaçlarına birinci elden hakim
- 💳 **Yerel ödeme entegrasyonu**: Click.uz + Payme (Uzcard, Humo) webhook ile native; UZS-native bakiye, fatura ve raporlama
- 🌐 **Tam çift dil**: Özbekçe (Latin + Kiril) ve Rusça — UI, bot mesajları, e-postalar
- 🎯 **AimaaPixel SDK**: Sahibi olduğu sitelerde conversion tracking (Purchase, Lead, PageView) — Meta Pixel paterni, server-side Conversions API
- 🛡️ **Yerleşik fraud detection**: IP cluster analizi, bot speed checks, click validation, kalitesiz tıklamaların otomatik iadesi
- 📊 **AI-destekli kanal kalite skorlama**: Subscriber anomaly detection, dinamik CPM ayarlaması, probation sistemi
- ⚙️ **Tam otomasyon**: Celery ile zamanlanmış reklam gönderimi, otomatik billing/refund, moderasyon kuyrukları
- 🛡️ **Role-Based Permissions**: Root admin, staff admin, advertiser, publisher hiyerarşisi

### Gelir Modeli

- **Platform komisyonu**: %30
- **Publisher kazancı**: %70
- **Ödeme modelleri**: CPM (1000 gösterim) / CPC (tıklama başı)

---

## 🏗️ Proje Yapısı

```
aimaa-ads/
├── backend/          # Django REST API (Port 8000)
│   ├── core/         # User, Auth, Admin API
│   ├── ads/          # Campaign, Ad, AdPlacement
│   ├── channels_app/ # TelegramChannel, Category
│   ├── analytics/    # AdEvent, DailyStats
│   ├── payments/     # Balance, Click.uz + Payme webhooks
│   ├── pixel/        # AimaaPixel ingestion + attribution
│   └── bot_webhook/  # Telegram webhook endpoint
├── frontend/         # Advertiser Panel - React (Port 5173)
├── admin/            # Admin Panel - React (Port 5174)
├── bot/              # Telegram Bot - aiogram
├── pixel/            # AimaaPixel JS SDK (vanilla)
└── README.md         # Bu dosya
```

---

## 🚀 Kurulum

### Ön Gereksinimler

Sisteminizde şunlar yüklü olmalı:

- **Python 3.14+**
- **Node.js 18+**
- **PostgreSQL 14+**
- **Redis 7+**
- **Git**

**macOS için:**
```bash
brew install python@3.14 node postgresql@16 redis git
brew services start postgresql@16
brew services start redis
```

---

## 📦 1. Backend Kurulumu

### 1.1. Veritabanı Oluştur

```bash
# PostgreSQL'e bağlan
psql postgres

# Kullanıcı ve database oluştur
CREATE USER postgres WITH SUPERUSER PASSWORD 'postgres';
CREATE DATABASE aimaa_ads OWNER postgres;
\q
```

> **Eski kurulumdan (legacy DB adı) geçiş yapıyorsanız**: lokal DB rename adımları
> için [CHANGELOG.md](CHANGELOG.md) Rebrand entry'sine bakın.

### 1.2. Backend Paketlerini Kur

```bash
cd backend

# Virtual environment oluştur
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
# veya: venv\Scripts\activate  # Windows

# Paketleri yükle
pip install -r requirements.txt
```

### 1.3. Environment Variables (.env)

`backend/.env` dosyası oluştur (örnek: `backend/.env.example`):

```env
# Django Settings
SECRET_KEY=your_secret_key_here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=aimaa_ads
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_BOT_USERNAME=YourBotUsername
PLATFORM_BOT_USERNAME=aimaa_ads_bot

# Bot API Secret (backend ↔ bot shared)
BOT_API_SECRET=your_bot_api_secret_here

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
```

### 1.4. Migration ve Superuser

```bash
# Migration'ları oluştur ve uygula
python manage.py makemigrations
python manage.py migrate

# Admin kullanıcısı oluştur
python manage.py createsuperuser
# Username: admin
# Email: admin@aimaa.uz
# Password: <strong-password-of-your-choice>

# Permission gruplarını oluştur
python manage.py setup_permissions
```

### 1.5. Backend'i Başlat

```bash
python manage.py runserver 8000
```

✅ **API:** http://localhost:8000/api/

---

## 🎨 2. Frontend Kurulumu (Advertiser Panel)

```bash
cd frontend

# Paketleri yükle
npm install

# Development server
npm run dev
```

✅ **Frontend:** http://localhost:5173

---

## 🛡️ 3. Admin Panel Kurulumu

```bash
cd admin

# Paketleri yükle
npm install

# Development server
npm run dev
```

✅ **Admin:** http://localhost:5174

**Login:**
- Username: `admin`
- Password: createsuperuser sırasında belirlediğiniz şifre

---

## 🤖 4. Telegram Bot Kurulumu

### 4.1. Bot Token Al

1. Telegram'da **@BotFather**'ı aç
2. `/newbot` komutunu gönder
3. Bot ismini gir: `AimaaAds Bot`
4. Bot username gir: `aimaaads_bot` (benzersiz olmalı)
5. **Token**'ı kopyala

### 4.2. Bot Paketlerini Kur

```bash
cd bot

# Virtual environment oluştur
python3 -m venv venv
source venv/bin/activate

# Paketleri yükle
pip install -r requirements.txt
```

### 4.3. Bot .env Dosyası

`bot/.env` dosyası oluştur:

```env
# Telegram Bot Token (BotFather'dan aldın)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Backend API URL
BACKEND_API=http://localhost:8000/api

# Bot Secret (Backend .env'deki BOT_API_SECRET ile AYNI olmalı!)
BOT_SECRET=your_bot_api_secret_here
```

⚠️ **Önemli**: `BOT_SECRET` backend'deki `BOT_API_SECRET` ile **aynı** olmalı!

### 4.4. Bot'u Başlat

```bash
python main.py
```

✅ **Bot çalışıyor!** Telegram'da `/start` ile test et.

---

## ⚙️ 5. Celery Kurulumu (Reklam Gönderimi)

Celery, reklamların zamanlanmış olarak gönderilmesi için gereklidir.

### 5.1. Redis'in Çalıştığından Emin Ol

```bash
# Redis çalışıyor mu kontrol et
redis-cli ping
# PONG döndüyse çalışıyor

# Çalışmıyorsa başlat
brew services start redis  # macOS
sudo systemctl start redis  # Linux
```

### 5.2. Celery Worker Başlat

**Yeni terminal aç (Terminal 5):**

```bash
cd backend
source venv/bin/activate

celery -A core worker -l info
```

✅ **Worker çalışıyor!** Celery task'ları işlemeye başlayacak.

**Ne yapıyor?**
- Reklamları Telegram kanallarına gönderir
- API isteklerini işler
- Background görevleri çalıştırır

### 5.3. Celery Beat Başlat (Zamanlanmış Görevler)

**Başka bir terminal aç (Terminal 6):**

```bash
cd backend
source venv/bin/activate

celery -A core beat -l info
```

✅ **Beat çalışıyor!** Her dakika zamanlanmış görevleri kontrol eder.

**Ne yapıyor?**
- 60 saniyede bir: Zamanı gelen reklamları gönderir
- 5 dakikada bir: Süresi dolan kampanyaları durdurur
- 5 dakikada bir: Bütçesi biten kampanyaları durdurur
- Günlük: İstatistikleri günceller

---

## 🔥 Tüm Servisleri Başlatma

Toplam **6 terminal** açman gerekiyor:

| Terminal | Komutlar | Port/Durum |
|----------|----------|------------|
| **1️⃣ Backend** | `cd backend && source venv/bin/activate`<br>`python manage.py runserver 8000` | http://localhost:8000 |
| **2️⃣ Frontend** | `cd frontend`<br>`npm run dev` | http://localhost:5173 |
| **3️⃣ Admin** | `cd admin`<br>`npm run dev` | http://localhost:5174 |
| **4️⃣ Bot** | `cd bot && source venv/bin/activate`<br>`python main.py` | Telegram polling |
| **5️⃣ Celery Worker** | `cd backend && source venv/bin/activate`<br>`celery -A core worker -l info` | Background tasks |
| **6️⃣ Celery Beat** | `cd backend && source venv/bin/activate`<br>`celery -A core beat -l info` | Scheduler |

---

## 🧪 Test Senaryosu

### 1️⃣ Admin: Kategori Oluştur

1. http://localhost:5174 → Login (`admin` / createsuperuser şifresi)
2. **Kategoriler** → Yeni Kategori
   - Isim: `Texnologiya`
   - Icon: `💻`
   - Aktiv: ✅

### 2️⃣ Publisher: Kanal Ekle (Telegram Bot)

1. Telegram'da bot'a `/start`
2. **Kanal qo'shish** → Kanal linkini gönder
3. Admin panelde **Kanallar** → Kanalı onayla (Approve)

### 3️⃣ Advertiser: Kampanya Oluştur

1. http://localhost:5173 → Register ile yeni kullanıcı oluştur
2. **Kampanyalar** → Yangi kampaniya
3. Formu doldur:
   - Kampanya nomi: `Test Reklam`
   - Byudjet: `100000` UZS
   - Narx: `5000` UZS (CPM)
   - Kanal seç, reklam metni yaz
4. **Yuborish**

### 4️⃣ Admin: Kampanyayı Onayla

1. Admin panelde **Kampanyalar**
2. Test kampanyasını bul → **Tasdiqlash**

### 5️⃣ Reklam Gönderimini İzle

- **Celery Beat** (Terminal 6) her dakika kontrol eder
- **Celery Worker** (Terminal 5) reklamı gönderir
- Telegram kanalında reklam görünür! 🎉

---

## 📊 Celery Task'ları

Backend'de zamanlanmış görevler:

| Task | Sıklık | Açıklama |
|------|--------|----------|
| `send_scheduled_ads` | 60 saniye | Zamanı gelen reklamları gönderir |
| `check_expired_ads` | 5 dakika | Süresi dolan reklamları durdurur |
| `check_budget_depleted` | 5 dakika | Bütçesi biten kampanyaları durdurur |
| `update_daily_stats` | Günlük (00:05) | Günlük istatistikleri günceller |
| `update_channel_stats` | Saatlik | Kanal istatistiklerini günceller |

**Celery task'larını manuel çalıştır:**
```bash
python manage.py shell
>>> from ads.tasks import send_scheduled_ads
>>> send_scheduled_ads.delay()  # Hemen çalıştır
```

---

## 🔐 Permission Sistemi

### Kullanıcı Rolleri

1. **Root Admin** (`is_superuser=True`)
   - Her şeye tam yetki
   - Sistem ayarlarını değiştirebilir
   - Asla silinmez

2. **Staff Admin** (`is_staff=True, role='admin'`)
   - Gruplar ile yetkilendirilir
   - Moderasyon, kullanıcı yönetimi
   - Silinebilir

3. **Advertiser** (`role='advertiser'`)
   - Kampanya oluşturur
   - Bakiye yükler

4. **Publisher** (`role='publisher'`)
   - Telegram kanalı ekler
   - Reklam yayınlar

### Permission Grupları

- **Kanal Moderatörleri**: Kanalları onaylar/reddeder
- **Kampanya İnceleyicileri**: Kampanyaları inceler
- **Kullanıcı Yöneticileri**: Kullanıcıları yönetir
- **Finans Yöneticileri**: Gelir raporları, ödeme onayı
- **Tam Yetkili Admin**: Tüm yetkiler (superuser hariç)

**Detaylı bilgi:** [PERMISSIONS_GUIDE.md](backend/PERMISSIONS_GUIDE.md)

---

## 🚨 Sorun Giderme

### Backend çalışmıyor

**Hata:** `psycopg.OperationalError: connection failed`

**Çözüm:**
```bash
# PostgreSQL çalışıyor mu?
brew services list | grep postgres
brew services start postgresql@16

# Database var mı?
psql postgres -c "\l" | grep aimaa_ads
```

### Redis bağlanamıyor

**Hata:** `redis.exceptions.ConnectionError`

**Çözüm:**
```bash
# Redis çalışıyor mu?
redis-cli ping  # PONG dönmeli

# Çalışmıyorsa
brew services start redis
```

### Celery task çalışmıyor

**Sorun:** Reklam gönderilmiyor

**Kontrol Listesi:**
1. ✅ Celery Worker çalışıyor mu? (Terminal 5)
2. ✅ Celery Beat çalışıyor mu? (Terminal 6)
3. ✅ Redis çalışıyor mu? (`redis-cli ping`)
4. ✅ Kampanya onaylı mı? (Admin panelde kontrol et)
5. ✅ Başlangıç tarihi geçmiş mi?

**Manuel test:**
```bash
python manage.py shell
>>> from ads.tasks import send_scheduled_ads
>>> send_scheduled_ads.delay()
```

### Bot yanıt vermiyor

**Sorun:** Telegram bot mesaja yanıt vermiyor

**Kontrol:**
1. Bot terminali (Terminal 4) çalışıyor mu?
2. `BOT_SECRET` backend ile aynı mı?
3. Backend `/api/bot/register/` endpoint'i çalışıyor mu?

**Log'lara bak:**
- Bot log'u: Terminal 4
- Backend log'u: Terminal 1

---

## 📁 Önemli Dosyalar

### Backend
- [core/models.py](backend/core/models.py) - User, PayoutRequest
- [ads/models.py](backend/ads/models.py) - Campaign, Ad, AdPlacement
- [ads/tasks.py](backend/ads/tasks.py) - Celery task'ları
- [core/admin_api.py](backend/core/admin_api.py) - Admin panel API
- [core/permissions.py](backend/core/permissions.py) - Permission class'ları

### Bot
- [bot/main.py](bot/main.py) - Bot başlangıç noktası
- [bot/handlers/publisher.py](bot/handlers/publisher.py) - Publisher komutları
- [bot/services/api_client.py](bot/services/api_client.py) - Backend API iletişimi

### Frontend & Admin
- [frontend/src/pages/CampaignCreate.jsx](frontend/src/pages/CampaignCreate.jsx) - Kampanya oluşturma
- [admin/src/pages/AdminDashboard.jsx](admin/src/pages/AdminDashboard.jsx) - Admin dashboard

---

## 🛠️ Geliştirme Notları

### Django Admin

Django'nun yerleşik admin paneli:

```
http://localhost:8000/admin/

Login: admin / createsuperuser şifresi
```

### API Dokümantasyonu

DRF Spectacular otomatik dokümantasyon:

```
http://localhost:8000/api/schema/swagger-ui/
```

---

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit edin (`git commit -m 'feat: Add amazing feature'`)
4. Push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

---

## 📝 Lisans

Bu proje eğitim amaçlıdır.

---

**Aimaa Software · Qo'qon, O'zbekiston · Built locally, for Uzbekistan ❤️**

Web: https://ads.aimaa.uz · Destek: support@aimaa.uz
