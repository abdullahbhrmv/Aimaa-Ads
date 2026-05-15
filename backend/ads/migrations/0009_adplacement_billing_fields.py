# Generated manually for FAZ 1 — billing idempotency.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0008_alter_campaign_start_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='adplacement',
            name='billed_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='adplacement',
            name='billing_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Beklemede'),
                    ('billed', 'Faturalandı'),
                    ('failed', 'Başarısız'),
                    ('skipped', 'Atlandı'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
    ]
