# Generated manually for FAZ 5 — Campaign UTM + AdVariantExperiment + Ad.experiment.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ads', '0014_adplacement_valid_clicks'),
    ]

    operations = [
        # --- Campaign UTM fields --------------------------------------------
        migrations.AddField(
            model_name='campaign',
            name='utm_auto_generate',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='campaign',
            name='utm_source',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='campaign',
            name='utm_medium',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='campaign',
            name='utm_campaign',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='campaign',
            name='utm_content_template',
            field=models.CharField(
                blank=True, default='', max_length=100,
                help_text='Boş ise ad_id kullanılır — her ad için otomatik content üretimi',
            ),
        ),

        # --- AdVariantExperiment create -------------------------------------
        migrations.CreateModel(
            name='AdVariantExperiment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[
                        ('running', 'Çalışıyor'),
                        ('completed', 'Tamamlandı'),
                        ('inconclusive', 'Sonuçsuz'),
                        ('paused', 'Durduruldu'),
                    ],
                    db_index=True, default='running', max_length=20,
                )),
                ('winner_criteria', models.CharField(
                    choices=[
                        ('ctr', 'CTR (Tıklama Oranı)'),
                        ('conversion_rate', 'Conversion Oranı'),
                        ('cpa', 'CPA (Conversion Başına Maliyet)'),
                    ],
                    default='ctr', max_length=20,
                )),
                ('traffic_split', models.JSONField(blank=True, default=dict)),
                ('min_impressions_per_variant', models.IntegerField(default=2000)),
                ('min_clicks_per_variant', models.IntegerField(default=40)),
                ('min_conversions_per_variant', models.IntegerField(default=30)),
                ('peeking_wait_hours', models.PositiveSmallIntegerField(default=24)),
                ('max_experiment_days', models.PositiveSmallIntegerField(default=30)),
                ('min_sample_reached_at', models.DateTimeField(blank=True, null=True)),
                ('p_value', models.DecimalField(blank=True, decimal_places=8, max_digits=10, null=True)),
                ('decision_notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='experiments',
                    to='ads.campaign',
                )),
                ('winner_ad', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='winner_of_experiments',
                    to='ads.ad',
                )),
            ],
            options={
                'db_table': 'ad_variant_experiments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='advariantexperiment',
            constraint=models.UniqueConstraint(
                fields=('campaign',),
                condition=models.Q(('status', 'running')),
                name='unique_running_experiment_per_campaign',
            ),
        ),

        # --- Ad.experiment FK -----------------------------------------------
        migrations.AddField(
            model_name='ad',
            name='experiment',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='variants',
                to='ads.advariantexperiment',
            ),
        ),
    ]
