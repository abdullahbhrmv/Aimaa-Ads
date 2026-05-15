# Generated manually for FAZ 3 — ClickEvent modeli.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0002_initial'),
        ('ads', '0014_adplacement_valid_clicks'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClickEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('ip_hash', models.CharField(db_index=True, max_length=64)),
                ('ip_subnet_hash', models.CharField(db_index=True, max_length=64)),
                ('user_agent_hash', models.CharField(max_length=64)),
                ('is_suspicious', models.BooleanField(db_index=True, default=False)),
                ('suspicion_reasons', models.JSONField(blank=True, default=list)),
                ('telegram_user_id', models.BigIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('placement', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='click_events',
                    to='ads.adplacement',
                )),
            ],
            options={
                'db_table': 'click_events',
            },
        ),
        migrations.AddIndex(
            model_name='clickevent',
            index=models.Index(
                fields=['placement', 'is_suspicious'],
                name='click_event_place_sus_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='clickevent',
            index=models.Index(
                fields=['created_at'],
                name='click_event_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='clickevent',
            index=models.Index(
                fields=['ip_subnet_hash', 'created_at'],
                name='click_event_subnet_ts_idx',
            ),
        ),
    ]
