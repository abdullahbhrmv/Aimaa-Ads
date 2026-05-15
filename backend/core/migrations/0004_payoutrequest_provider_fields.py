# Generated manually for FAZ 4a — PayoutRequest provider alanları.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_user_company_description_user_website'),
    ]

    operations = [
        migrations.AddField(
            model_name='payoutrequest',
            name='provider',
            field=models.CharField(
                choices=[
                    ('click', 'Click.uz'),
                    ('payme', 'Payme'),
                    ('manual', 'Manuel'),
                ],
                default='manual',
                help_text="Ödeme provider'ı — FAZ 4b'de otomatik havale bu alana bakar",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='payoutrequest',
            name='provider_account',
            field=models.CharField(
                blank=True, default='', max_length=100,
                help_text='Provider hedef hesabı (kart numarası veya telefon)',
            ),
        ),
        migrations.AddField(
            model_name='payoutrequest',
            name='provider_status',
            field=models.CharField(
                blank=True, default='', max_length=50,
                help_text="Provider'ın kendi status string'i (raw response)",
            ),
        ),
        migrations.AddField(
            model_name='payoutrequest',
            name='provider_ref',
            field=models.CharField(
                blank=True, default='', max_length=255,
                help_text="Provider transaction ref'i — audit ve mutabakat için",
            ),
        ),
    ]
