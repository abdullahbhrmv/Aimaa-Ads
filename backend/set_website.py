#!/usr/bin/env python
"""
Aimaa kullanıcısına website ve company description ekle
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from core.models import User

# Aimaa kullanıcısını bul
try:
    aimaa = User.objects.get(username='aimaa')

    # Website ve description ekle
    aimaa.website = 'https://aimaa.uz'
    aimaa.company_description = 'Aimaa - O\'zbekiston uchun ishonchli xizmatlar. Biz sizning biznesingizni rivojlantirishda yordam beramiz.'
    aimaa.save()

    print(f"✅ Website eklendi: {aimaa.website}")
    print(f"✅ Description: {aimaa.company_description[:50]}...")
    print(f"\n🎉 Aimaa profili güncellendi!")

except User.DoesNotExist:
    print("❌ 'aimaa' kullanıcısı bulunamadı!")
    print("Önce Aimaa hesabı ile giriş yapın.")
