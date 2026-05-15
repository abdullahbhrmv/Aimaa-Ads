# Generated manually for FAZ 3 — AdPlacement.valid_clicks (CPC fraud filtresi).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0013_backfill_moderation_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='adplacement',
            name='valid_clicks',
            field=models.IntegerField(default=0),
        ),
    ]
