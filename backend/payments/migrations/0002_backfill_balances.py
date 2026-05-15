# Generated manually for FAZ 4a — User.balance → UserBalance backfill.
#
# UYARI: Bu migration mevcut `User.balance` değerlerini `UserBalance.balance`'a
# kopyalar. Apply öncesi mutlaka staging'de preview + DB yedeği.
#
# Sınıflandırma:
#   - user.balance > 0 ve UserBalance yoksa → UserBalance(balance=user.balance) oluştur
#   - UserBalance zaten varsa dokunma (idempotent apply)
#
# Reverse: noop. User.balance field'ı hâlâ yerinde olduğu için geri alınabilir
# bir veri kaybı yok; UserBalance satırlarını silmek istemezsiniz.

from decimal import Decimal

from django.db import migrations


def backfill_user_balances(apps, schema_editor):
    User = apps.get_model('core', 'User')
    UserBalance = apps.get_model('payments', 'UserBalance')

    for user in User.objects.iterator(chunk_size=500):
        if UserBalance.objects.filter(user=user).exists():
            continue
        UserBalance.objects.create(
            user=user,
            balance=user.balance or Decimal('0'),
        )


def reverse_noop(apps, schema_editor):
    # UserBalance satırları silinmez — veri kaybı riskine karşı.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill_user_balances, reverse_noop),
    ]
