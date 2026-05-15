# Generated manually for FAZ 3 — TelegramChannel kalite + probation alanları.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels_app', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramchannel',
            name='quality_score',
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text='0-100 arası ağırlıklı kalite skoru (default=50 yeni kanal)',
            ),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='engagement_rate',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=6,
                help_text='avg_views / subscriber_count × 100',
            ),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='ad_completion_rate',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=5,
                help_text='sent / (sent+failed) × 100',
            ),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='avg_ctr',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=5,
                help_text='CPC reklamlarda valid_clicks / impressions × 100',
            ),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='suspicious_growth_flag',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='ip_cluster_fraud_flag',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='quality_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='probation_ends_at',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True,
                help_text='Probation süresi bitişi; NULL → probation dışı',
            ),
        ),
        migrations.AddField(
            model_name='telegramchannel',
            name='is_trusted_override',
            field=models.BooleanField(
                default=False,
                help_text='Admin tarafından elle güvenilir işaretlendi — probation + fraud bypass',
            ),
        ),
    ]
