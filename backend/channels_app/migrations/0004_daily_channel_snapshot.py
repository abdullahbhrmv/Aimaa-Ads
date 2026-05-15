# Generated manually for FAZ 3 — DailyChannelSnapshot modeli.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels_app', '0003_channel_quality_probation'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyChannelSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('date', models.DateField(db_index=True)),
                ('subscriber_count', models.IntegerField()),
                ('avg_views', models.IntegerField(default=0)),
                ('sent_count', models.IntegerField(default=0)),
                ('failed_count', models.IntegerField(default=0)),
                ('impressions', models.IntegerField(default=0)),
                ('clicks', models.IntegerField(default=0)),
                ('valid_clicks', models.IntegerField(default=0)),
                ('quality_score', models.PositiveSmallIntegerField(default=50)),
                ('components', models.JSONField(
                    blank=True, default=dict,
                    help_text='Skorun alt bileşenleri — debug/audit için',
                )),
                ('suspicious_growth_flag', models.BooleanField(default=False)),
                ('growth_pct', models.DecimalField(
                    decimal_places=2, default=0, max_digits=7,
                    help_text='Önceki güne göre subscriber artış yüzdesi',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('channel', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='daily_snapshots',
                    to='channels_app.telegramchannel',
                )),
            ],
            options={
                'db_table': 'daily_channel_snapshots',
                'ordering': ['-date'],
                'unique_together': {('channel', 'date')},
            },
        ),
        migrations.AddIndex(
            model_name='dailychannelsnapshot',
            index=models.Index(
                fields=['channel', '-date'],
                name='daily_chan_channel_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='dailychannelsnapshot',
            index=models.Index(
                fields=['suspicious_growth_flag', '-date'],
                name='daily_chan_susp_growth_idx',
            ),
        ),
    ]
