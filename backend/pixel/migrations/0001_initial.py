# Generated manually for FAZ 5 — AimaaPixel initial schema.

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import pixel.models  # validate_allowed_domains referansı — alt field'da kullanılıyor


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ads', '0015_utm_and_ab_experiment'),
        ('analytics', '0004_clickevent_em_hash'),
    ]

    operations = [
        # --- PixelInstallation ----------------------------------------------
        migrations.CreateModel(
            name='PixelInstallation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('pixel_id', models.UUIDField(
                    db_index=True, default=uuid.uuid4, editable=False, unique=True,
                )),
                ('allowed_domains', models.JSONField(
                    blank=True, default=list,
                    help_text=(
                        "Kabul edilen origin'ler. Wildcard: *.example.com. "
                        "Max 20 entry, her biri max 253 karakter."
                    ),
                    validators=[pixel.models.validate_allowed_domains],
                )),
                ('enabled', models.BooleanField(db_index=True, default=True)),
                ('debug_mode', models.BooleanField(
                    default=False,
                    help_text='SDK console.log açık + localhost origin kabul edilir',
                )),
                ('attribution_events', models.JSONField(
                    blank=True, default=list,
                    help_text='Örn: ["Purchase", "Lead", "CompleteRegistration"]',
                )),
                ('click_window_days', models.PositiveSmallIntegerField(default=7)),
                ('view_window_days', models.PositiveSmallIntegerField(default=1)),
                ('advanced_matching_enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('advertiser', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pixel_installation',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'pixel_installations',
            },
        ),

        # --- ConversionEvent ------------------------------------------------
        migrations.CreateModel(
            name='ConversionEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('event_name', models.CharField(db_index=True, max_length=64)),
                ('event_id', models.UUIDField(db_index=True)),
                ('event_source', models.CharField(
                    choices=[
                        ('browser', 'Tarayıcı (JS SDK)'),
                        ('server', 'Server-side Conversions API'),
                    ],
                    default='browser', max_length=10,
                )),
                ('url', models.TextField(blank=True, default='')),
                ('referrer', models.TextField(blank=True, default='')),
                ('user_agent_hash', models.CharField(blank=True, default='', max_length=64)),
                ('ip_hash', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('ip_subnet_hash', models.CharField(blank=True, default='', max_length=64)),
                ('click_id', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('utm_source', models.CharField(blank=True, default='', max_length=100)),
                ('utm_medium', models.CharField(blank=True, default='', max_length=100)),
                ('utm_campaign', models.CharField(blank=True, db_index=True, default='', max_length=100)),
                ('utm_content', models.CharField(blank=True, default='', max_length=100)),
                ('utm_term', models.CharField(blank=True, default='', max_length=100)),
                ('value', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('currency', models.CharField(blank=True, default='', max_length=3)),
                ('em_hash', models.CharField(blank=True, default='', max_length=64)),
                ('ph_hash', models.CharField(blank=True, default='', max_length=64)),
                ('external_id_hash', models.CharField(blank=True, default='', max_length=64)),
                ('raw_params', models.JSONField(blank=True, default=dict)),
                ('attribution_attempted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('pixel', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='events',
                    to='pixel.pixelinstallation',
                )),
            ],
            options={
                'db_table': 'conversion_events',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='conversionevent',
            constraint=models.UniqueConstraint(
                fields=('pixel', 'event_id'),
                name='unique_pixel_event_id',
            ),
        ),
        migrations.AddIndex(
            model_name='conversionevent',
            index=models.Index(
                fields=['pixel', 'event_name', '-created_at'],
                name='conv_ev_pix_name_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='conversionevent',
            index=models.Index(
                fields=['attribution_attempted_at'],
                name='conv_ev_attr_attempt_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='conversionevent',
            index=models.Index(
                fields=['em_hash', '-created_at'],
                condition=~models.Q(em_hash=''),
                name='conv_ev_em_hash_partial',
            ),
        ),

        # --- Conversion -----------------------------------------------------
        migrations.CreateModel(
            name='Conversion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('attribution_type', models.CharField(
                    choices=[('click', 'Tıklama'), ('view', 'Görüntüleme')],
                    default='click', max_length=10,
                )),
                ('touch_method', models.CharField(
                    choices=[
                        ('click_id', 'Click ID Cookie/QueryParam'),
                        ('utm', 'UTM Parametreleri'),
                        ('advanced_matching', 'Advanced Matching'),
                    ],
                    default='click_id', max_length=32,
                )),
                ('attributed_at', models.DateTimeField(auto_now_add=True)),
                ('attribution_delay_seconds', models.BigIntegerField(blank=True, null=True)),
                ('attributed_value', models.DecimalField(
                    decimal_places=2, default=Decimal('0'), max_digits=14,
                )),
                ('currency', models.CharField(blank=True, default='UZS', max_length=3)),
                ('attribution_path', models.JSONField(blank=True, null=True)),
                ('event', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='conversion',
                    to='pixel.conversionevent',
                )),
                ('campaign', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='conversions',
                    to='ads.campaign',
                )),
                ('placement', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='conversions',
                    to='ads.adplacement',
                )),
                ('click_event', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='conversions',
                    to='analytics.clickevent',
                )),
            ],
            options={
                'db_table': 'conversions',
                'ordering': ['-attributed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='conversion',
            index=models.Index(
                fields=['campaign', '-attributed_at'],
                name='conv_camp_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='conversion',
            index=models.Index(
                fields=['placement', '-attributed_at'],
                name='conv_place_date_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='conversion',
            index=models.Index(
                fields=['click_event'],
                name='conv_click_idx',
            ),
        ),
    ]
