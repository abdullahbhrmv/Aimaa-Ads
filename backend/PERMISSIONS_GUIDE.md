# 🔐 Permission & Role Sistemi Kılavuzu

## 📌 Kullanıcı Tipleri

### 1. Root Admin (Superuser)
- **Özellikler:**
  - `is_superuser = True`
  - Her şeye tam erişim
  - Sistem ayarlarını değiştirebilir
  - Diğer adminleri silebilir
  - Asla silinmez

- **Kontrol:**
  ```python
  user.is_superuser  # True
  user.is_root_admin  # True (property)
  ```

- **Mevcut Root Admin:**
  - Username: `admin`
  - Password: `admin123`
  - Email: `admin@aimaa.uz`

---

### 2. Staff Admin (Kısıtlı Yetkili Admin)
- **Özellikler:**
  - `is_staff = True`, `is_superuser = False`
  - `role = 'admin'`
  - Gruplar ile yetkilendirilir
  - Root admin tarafından silinebilir
  - Sadece atanan yetkileri kullanabilir

- **Kontrol:**
  ```python
  user.is_staff_admin  # True (property)
  user.is_any_admin    # True (root veya staff)
  ```

- **Örnek Staff Admin:**
  - Username: `moderator`
  - Password: `moderator123`
  - Grup: Kanal Moderatörleri

---

### 3. Advertiser (Reklamveren)
- `role = 'advertiser'`
- Kampanya oluşturur, bakiye yükler

### 4. Publisher (Kanal Sahibi)
- `role = 'publisher'`
- Telegram kanalı ekler, reklam yayınlar

---

## 🎯 Admin Grupları

### Kanal Moderatörleri
**Yetkiler:**
- Kanalları onaylama/reddetme
- Kanal detaylarını görüntüleme
- Kanal bilgilerini düzenleme

**Kullanım:**
```python
from django.contrib.auth.models import Group
from core.models import User

user = User.objects.get(username='moderator')
group = Group.objects.get(name='Kanal Moderatörleri')
user.groups.add(group)
```

---

### Kampanya İnceleyicileri
**Yetkiler:**
- Kampanyaları inceleme
- Kampanya onaylama/reddetme
- Reklam içeriklerini görüntüleme

---

### Kullanıcı Yöneticileri
**Yetkiler:**
- Kullanıcı listesini görüntüleme
- Kullanıcı bilgilerini düzenleme
- Kullanıcı durumlarını değiştirme

---

### Finans Yöneticileri
**Yetkiler:**
- Gelir raporlarını görüntüleme
- Ödeme taleplerini onaylama/reddetme
- Bakiye işlemlerini görüntüleme

---

### Tam Yetkili Admin
**Yetkiler:**
- Yukarıdaki tüm yetkilerin toplamı
- Root admin hariç her şeye erişim

---

## 🛠️ API Permission Classes

### `IsSuperAdmin`
Sadece root admin erişebilir.

```python
from core.permissions import IsSuperAdmin

class CriticalView(APIView):
    permission_classes = [IsSuperAdmin]
```

**Kullanım Alanları:**
- Sistem ayarları
- Staff admin silme
- Kritik yapılandırma değişiklikleri

---

### `IsStaffAdmin`
Staff admin veya root admin erişebilir.

```python
from core.permissions import IsStaffAdmin

class ModerationView(APIView):
    permission_classes = [IsStaffAdmin]
```

**Kullanım Alanları:**
- Kanal moderasyonu
- Kampanya inceleme
- Kullanıcı yönetimi

---

### `IsAdmin`
Herhangi bir admin (root veya staff) erişebilir.

```python
from core.permissions import IsAdmin

class AdminDashboardView(APIView):
    permission_classes = [IsAdmin]
```

**Kullanım Alanları:**
- Admin dashboard
- Genel raporlar
- Backward compatibility

---

## 📝 Yeni Staff Admin Nasıl Oluşturulur?

### 1. Django Shell ile
```bash
python manage.py shell
```

```python
from django.contrib.auth.models import Group
from core.models import User

# Staff admin oluştur
staff = User.objects.create_user(
    username='ahmet',
    email='ahmet@aimaa.uz',
    password='guclu_sifre',
    role=User.Role.ADMIN,
    is_staff=True,
    is_superuser=False,  # ÖNEMLI!
)

# Grup ata
group = Group.objects.get(name='Kanal Moderatörleri')
staff.groups.add(group)

print(f"✅ {staff.username} oluşturuldu!")
print(f"   is_staff_admin: {staff.is_staff_admin}")
print(f"   Gruplar: {[g.name for g in staff.groups.all()]}")
```

---

### 2. Admin Panel Üzerinden (Django Admin)

1. http://localhost:8000/admin/ → Users bölümü
2. "Add user" tıkla
3. Formu doldur:
   - Username: `ahmet`
   - Password: `***`
   - Role: `Admin`
   - ✅ Staff status: **İşaretle**
   - ❌ Superuser status: **İşaretleme!**
4. Groups: İstediğin grubu seç
5. Save

---

### 3. API ile (Sonra yapılacak)

```python
# AdminUserCreateView (sadece superuser erişebilir)
POST /api/admin-panel/users/create/
{
  "username": "ahmet",
  "email": "ahmet@aimaa.uz",
  "password": "guclu_sifre",
  "role": "admin",
  "groups": ["Kanal Moderatörleri"]
}
```

---

## 🔍 Permission Kontrolü Örnekleri

### View İçinde
```python
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsSuperAdmin, IsStaffAdmin

class DeleteUserView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def delete(self, request, pk):
        # Sadece superuser silebilir
        user = User.objects.get(pk=pk)
        if user.is_superuser:
            return Response({"error": "Root admin silinemez!"}, status=400)
        user.delete()
        return Response({"success": True})
```

### Model Seviyesinde
```python
# Belirli bir yetkiyi kontrol et
if request.user.has_perm('core.can_moderate_channels'):
    # Kanal moderasyonu yapabilir
    pass
```

### Template/Frontend'de
```python
# Kullanıcı bilgisini serializer ile gönder
{
  "username": "admin",
  "role": "admin",
  "is_root_admin": true,
  "is_staff_admin": false,
  "permissions": ["can_moderate_channels", "can_review_campaigns"]
}
```

Frontend'de:
```javascript
if (user.is_root_admin) {
  // Sistem ayarları butonunu göster
}

if (user.permissions.includes('can_moderate_channels')) {
  // Kanal moderasyon panelini göster
}
```

---

## 🚀 İlk Kurulum

```bash
# 1. Permission gruplarını oluştur
python manage.py setup_permissions

# 2. Root admin oluştur (eğer yoksa)
python manage.py createsuperuser

# 3. Test için staff admin oluştur (opsiyonel)
python manage.py shell -c "
from core.models import User
from django.contrib.auth.models import Group

staff = User.objects.create_user(
    username='moderator',
    password='moderator123',
    email='moderator@aimaa.uz',
    role='admin',
    is_staff=True,
)
staff.groups.add(Group.objects.get(name='Kanal Moderatörleri'))
print('✅ Test moderator oluşturuldu!')
"
```

---

## ⚠️ Önemli Notlar

1. **Root admin asla silinmemeli!**
   - Sistem tam kontrolü kaybeder
   - En az 1 root admin her zaman olmalı

2. **Staff admin oluştururken `is_superuser=False` olmalı!**
   - Yoksa root admin olur

3. **Permission kontrollerini backend'de yap!**
   - Frontend sadece UI gösterir
   - Asıl güvenlik backend'de

4. **Tenant yapısı geldiğinde:**
   - Tenant başına ayrı staff adminler
   - `tenant_id` foreign key eklenebilir
   - Root admin tüm tenant'lara erişir

---

## 📚 Custom Permission Listesi

| Permission Codename | Açıklama |
|---------------------|----------|
| `can_moderate_channels` | Kanalları moderasyon yapabilir |
| `can_review_campaigns` | Kampanya inceleyebilir |
| `can_manage_users` | Kullanıcı yönetebilir |
| `can_view_revenue` | Gelir raporlarını görebilir |
| `can_manage_categories` | Kategorileri yönetebilir |
| `can_approve_payouts` | Ödeme taleplerini onaylayabilir |

---

## 🧪 Test Kullanıcıları

| Username | Password | Role | Tip | Yetkiler |
|----------|----------|------|-----|----------|
| `admin` | `admin123` | admin | Root Admin | Her şey |
| `moderator` | `moderator123` | admin | Staff Admin | Kanal Moderasyonu |

---

## 🔄 Multi-Tenant İçin Hazırlık

Mevcut yapı multi-tenant için hazır:

```python
# İleride eklenebilir
class User(AbstractUser):
    tenant = models.ForeignKey('Tenant', null=True, blank=True)  # Opsiyonel

    class Meta:
        permissions = [
            ("can_manage_tenant", "Tenant yönetebilir"),  # Yeni
            ...
        ]
```

Root admin tüm tenant'lara erişir, staff adminler sadece kendi tenant'larına.
