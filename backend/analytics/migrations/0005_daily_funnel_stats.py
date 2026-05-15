# Generated manually for FAZ 5 — DailyFunnelStats model.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0004_clickevent_em_hash'),
        ('ads', '0015_utm_and_ab_experiment'),
        ('channels_app', '0004_daily_channel_snapshot'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyFunnelStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('date', models.DateField(db_index=True)),
                ('impressions', models.IntegerField(default=0)),
                ('clicks', models.IntegerField(default=0)),
                ('valid_clicks', models.IntegerField(default=0)),
                ('conversion_count', models.IntegerField(default=0)),
                ('conversion_value', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('spent', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='daily_funnel_stats',
                    to='ads.campaign',
                )),
                ('ad', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='daily_funnel_stats',
                    to='ads.ad',
                )),
                ('channel', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='daily_funnel_stats',
                    to='channels_app.telegramchannel',
                )),
            ],
            options={
                'db_table': 'daily_funnel_stats',
                'ordering': ['-date'],
            },
        ),
        migrations.AddConstraint(
            model_name='dailyfunnelstats',
            constraint=models.UniqueConstraint(
                fields=('date', 'campaign', 'ad', 'channel'),
                name='unique_daily_funnel_tuple',
            ),
        ),
        migrations.AddIndex(
            model_name='dailyfunnelstats',
            index=models.Index(fields=['campaign', '-date'], name='funnel_camp_date_idx'),
        ),
        migrations.AddIndex(
            model_name='dailyfunnelstats',
            index=models.Index(fields=['ad', '-date'], name='funnel_ad_date_idx'),
        ),
    ]
