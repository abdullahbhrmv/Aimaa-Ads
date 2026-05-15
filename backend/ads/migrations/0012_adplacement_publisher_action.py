# Generated manually for FAZ 2 — Yayıncı red/onay alanları.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0011_campaign_moderation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='adplacement',
            name='publisher_action',
            field=models.CharField(
                choices=[
                    ('auto', 'Otomatik'),
                    ('accepted', 'Yayıncı Onayladı'),
                    ('rejected', 'Yayıncı Reddetti'),
                ],
                db_index=True,
                default='auto',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='adplacement',
            name='publisher_rejection_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='adplacement',
            name='reassignment_count',
            field=models.IntegerField(default=0),
        ),
    ]
