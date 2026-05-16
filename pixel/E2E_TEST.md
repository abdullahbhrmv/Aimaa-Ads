# AimaaPixel — Lokal E2E Test Akışı

Bu döküman SDK'nın uçtan uca lokal akışını test etmek içindir: SDK build →
backend ingest → DB'de `ConversionEvent` satırı. VPS deploy / CDN / nginx
ayrı bir görev (production deploy faz'ı).

---

## 1. Test pixel kaydı oluştur

```bash
cd backend
source venv/bin/activate
python manage.py create_test_pixel
```

Çıktıdan **`pixel_id`** (UUID) değerini kopyalayın. Örnek:

```
Pixel created.

  pixel_id        : 4f8d3a1e-...-9c2b
  advertiser      : admin (admin@aimaa.uz)
  allowed_domains : ['localhost', '127.0.0.1']
  debug_mode      : True
  enabled         : True

Paste this into pixel/test-page/index.html:

  <script src="../dist/pixel.js" data-pixel-id="4f8d3a1e-...-9c2b"></script>
```

Komut idempotent — tekrar çalıştırılırsa aynı pixel_id'yi getirir.

---

## 2. Pixel SDK'yı build et

```bash
cd pixel
npm install          # ilk seferde
npm run build
```

Çıktı:

```
dist/pixel.js       4.2kb
dist/pixel.js.map  16.5kb
⚡ Done in 13ms
```

Hash parity test'i de doğrulayın (29 vector + 2 sanity check):

```bash
npm test
```

---

## 3. Test sayfasına pixel_id yapıştır

`pixel/test-page/index.html` içinde:

```html
<script src="../dist/pixel.js"
        data-pixel-id="REPLACE_WITH_REAL_UUID"
        data-aimaa-debug></script>
```

`REPLACE_WITH_REAL_UUID` yerine 1. adımdan aldığınız UUID'i yazın.

---

## 4. Servisleri başlat (3 terminal)

**Terminal 1 — Backend:**

```bash
cd backend
source venv/bin/activate
python manage.py runserver 8000
```

**Terminal 2 — Pixel build watcher (opsiyonel; kaynak değiştirirken):**

```bash
cd pixel
npm run build:watch
```

**Terminal 3 — Test sayfası serve et:**

```bash
cd pixel/test-page
python -m http.server 8080
```

> ⚠ Sayfa `file://` ile değil `http://localhost:8080` ile açılmalı —
> aksi halde browser fetch CORS preflight'ı reddeder.

---

## 5. Browser test akışı

1. **Browser**: `http://localhost:8080` aç.
2. Sayfa üstünde yeşil ✓ kutusu görmelisin: "AimaaPixel yüklendi".
3. **DevTools → Network**, "event" filtresi.
4. Sayfa yüklenir yüklenmez **otomatik 1 POST** gitmeli:

   ```
   POST http://localhost:8000/api/pixel/event/
   Body:  {
            "pixel_id": "<UUID>",
            "event_name": "PageView",
            "event_id": "<auto-uuid>",
            "client_ts": 1747...,
            "url": "http://localhost:8080/",
            "referrer": ""
          }
   Response: 200 {"status": "created", "event_id": "..."}
   ```
5. Butonlara sırayla bas:
   - **Purchase**  → `event_name: "Purchase"`, `value: 250000`, `currency: "UZS"`
   - **Lead**       → `event_name: "Lead"`
   - **Custom**     → `event_name: "CustomDemoEvent"`, `custom_params: {action, category}`
   - **Advanced**   → `event_name: "Lead"`, `advanced_matching: {em_hash, ph_hash, fn_hash, ln_hash, external_id_hash}`
                       — PII **client-side hashed**, raw değerler payload'da
                       **YOK** olmalı (DevTools → Request payload doğrula).

---

## 6. Backend'de doğrula

```bash
cd backend
source venv/bin/activate
python manage.py shell
```

```python
>>> from pixel.models import ConversionEvent
>>> [e.event_name for e in ConversionEvent.objects.order_by('-id')[:5]]
['Lead', 'CustomDemoEvent', 'Lead', 'Purchase', 'PageView']

>>> last = ConversionEvent.objects.order_by('-id').first()
>>> last.event_name, last.value, last.currency
('Lead', None, '')

>>> # Advanced matching event'i için hash alanları:
>>> e = ConversionEvent.objects.filter(em_hash__gt='').order_by('-id').first()
>>> len(e.em_hash), len(e.ph_hash)
(64, 64)  # SHA-256 hex
```

---

## 7. Olası hatalar ve çözümleri

| Belirti | Sebep | Çözüm |
|---|---|---|
| Sayfada kırmızı "AimaaPixel YÜKLENMEDİ" | `dist/pixel.js` yok | `cd pixel && npm run build` |
| Network 403 `domain_not_allowed` | localhost whitelist'te yok | `create_test_pixel` komutunu tekrar çalıştır; debug_mode=True ve allowed_domains'e localhost ekler |
| Network 404 `pixel_not_found` | `data-pixel-id` UUID değil veya yanlış | 1. adımdan UUID'i doğru kopyalayın |
| Network 400 `invalid_payload event_id required` | SDK eski sürüm cache'lenmiş | DevTools → Network → "Disable cache" + hard refresh; ya da dev server DEBUG mode'da olmalı (`Cache-Control: no-cache`) |
| Network CORS preflight fail | Sayfa `file://` üzerinden açıldı | `python -m http.server 8080` ile serve edin |
| `/api/pixel/p.js` 501 | dist build edilmemiş | `npm run build`; backend view otomatik 200'e döner |

---

## 8. Snippet endpoint testi (opsiyonel)

Bu, **advertiser panel** akışını test eder — snippet HTML'i nasıl
gösterilir.

```bash
# Flag False (default) — 503 ile pending mesajı:
curl -i http://localhost:8000/api/pixel/install-snippet/ \
     -H "Authorization: Bearer <ADV_JWT>"
# → HTTP/1.1 503 SERVICE UNAVAILABLE
# → {"status": "sdk_deployment_pending", ...}

# Flag True — snippet HTML döner:
AIMAA_SDK_DEPLOYED=True python manage.py runserver 8000

curl -s http://localhost:8000/api/pixel/install-snippet/ \
     -H "Authorization: Bearer <ADV_JWT>" | python -m json.tool
# → {"pixel_id": "...", "snippet": "<script>...</script>", "snippet_version": 1, ...}
```

Snippet HTML'ini bir test sitesine yapıştırırsanız Meta Pixel pattern'i
ile aynı queue+flush davranışını alırsınız:
`window.aimaa('init', PIXEL_ID)` → `window.aimaa('track', 'PageView')`
→ SDK yüklenir → kuyruk flush edilir.

---

## 9. Bir sonraki adım

E2E test başarılı geçtikten sonra ileride yapılacaklar (bu görev kapsamı dışı):

- **VPS deploy** — `pixel/dist/pixel.js`'i CDN'e push, `nginx` config,
  TLS sertifikası
- **`AIMAA_SDK_DEPLOYED=True`** flag'i production env'inde aktive et
- **FAZ 5 Adımlar 4-8** — attribution windows, funnel/cohort endpoints,
  advanced matching cross-device lookup
