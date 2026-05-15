"""
Django management command: Admin grupları ve yetkilerini otomatik oluşturur.

Kullanım: python manage.py setup_permissions
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from core.models import User
from channels_app.models import TelegramChannel
from ads.models import Campaign


class Command(BaseCommand):
    help = "Admin grupları ve yetkilerini oluşturur"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🔧 Admin grupları ve yetkileri oluşturuluyor...\n"))

        # 1. Kanal Moderatörleri
        channel_moderators, created = Group.objects.get_or_create(name="Kanal Moderatörleri")
        if created:
            self.stdout.write("✓ 'Kanal Moderatörleri' grubu oluşturuldu")

        channel_perms = Permission.objects.filter(
            codename__in=['can_moderate_channels', 'view_telegramchannel', 'change_telegramchannel']
        )
        channel_moderators.permissions.set(channel_perms)
        self.stdout.write(f"  → {channel_perms.count()} yetki eklendi")

        # 2. Kampanya İnceleyicileri
        campaign_reviewers, created = Group.objects.get_or_create(name="Kampanya İnceleyicileri")
        if created:
            self.stdout.write("✓ 'Kampanya İnceleyicileri' grubu oluşturuldu")

        campaign_perms = Permission.objects.filter(
            codename__in=['can_review_campaigns', 'view_campaign', 'change_campaign', 'view_ad']
        )
        campaign_reviewers.permissions.set(campaign_perms)
        self.stdout.write(f"  → {campaign_perms.count()} yetki eklendi")

        # 3. Kullanıcı Yöneticileri
        user_managers, created = Group.objects.get_or_create(name="Kullanıcı Yöneticileri")
        if created:
            self.stdout.write("✓ 'Kullanıcı Yöneticileri' grubu oluşturuldu")

        user_perms = Permission.objects.filter(
            codename__in=['can_manage_users', 'view_user', 'change_user']
        )
        user_managers.permissions.set(user_perms)
        self.stdout.write(f"  → {user_perms.count()} yetki eklendi")

        # 4. Finans Yöneticileri
        finance_managers, created = Group.objects.get_or_create(name="Finans Yöneticileri")
        if created:
            self.stdout.write("✓ 'Finans Yöneticileri' grubu oluşturuldu")

        finance_perms = Permission.objects.filter(
            codename__in=['can_view_revenue', 'can_approve_payouts', 'view_payoutrequest', 'change_payoutrequest']
        )
        finance_managers.permissions.set(finance_perms)
        self.stdout.write(f"  → {finance_perms.count()} yetki eklendi")

        # 5. Tam Yetkili Staff Admin
        full_staff, created = Group.objects.get_or_create(name="Tam Yetkili Admin")
        if created:
            self.stdout.write("✓ 'Tam Yetkili Admin' grubu oluşturuldu")

        all_custom_perms = Permission.objects.filter(
            codename__in=[
                'can_moderate_channels',
                'can_review_campaigns',
                'can_manage_users',
                'can_view_revenue',
                'can_manage_categories',
                'can_approve_payouts',
            ]
        )
        full_staff.permissions.set(all_custom_perms)
        self.stdout.write(f"  → {all_custom_perms.count()} custom yetki eklendi")

        self.stdout.write(self.style.SUCCESS("\n✅ Tüm gruplar ve yetkiler başarıyla oluşturuldu!"))
        self.stdout.write(self.style.WARNING("\n📌 Kullanım örnekleri:"))
        self.stdout.write("  • Kanal moderatörü ekle: user.groups.add(Group.objects.get(name='Kanal Moderatörleri'))")
        self.stdout.write("  • Staff admin oluştur: User.objects.create_user(..., is_staff=True, role='admin')")
        self.stdout.write("  • Root admin kontrol: user.is_superuser")
