# Generated manually for FAZ 2 — Campaign moderation pipeline alanları.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0010_backfill_billing_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='moderation_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Taranmadı'),
                    ('auto_approved', 'Otomatik Onaylandı'),
                    ('flagged', 'İşaretlendi'),
                    ('human_review', 'İnsan İncelemesi'),
                    ('rejected', 'Reddedildi'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='moderation_flags',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Moderasyon taramasından gelen kategori bayrakları (kumar, alkol, ...)',
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='moderation_notes',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Moderatör notları — queue\'dan yapılan onay/red sebepleri',
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='moderated_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='moderated_campaigns',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='moderated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
