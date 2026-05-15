# Generated manually for FAZ 5 — ClickEvent.em_hash + partial index
# (FAZ 5.5 cross-device attribution için şimdiden sakla).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0003_click_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='clickevent',
            name='em_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        # Partial index — yalnızca boş olmayan em_hash'leri indexler.
        # Postgres required (SQLite partial index desteklemez ama projede
        # test DB Postgres olacak şekilde kurulmuş).
        migrations.AddIndex(
            model_name='clickevent',
            index=models.Index(
                fields=['em_hash'],
                condition=~models.Q(em_hash=''),
                name='click_event_em_hash_partial',
            ),
        ),
    ]
