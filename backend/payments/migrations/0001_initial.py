# Generated manually for FAZ 4a — payments app initial schema.

from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ads', '0014_adplacement_valid_clicks'),
        ('core', '0004_payoutrequest_provider_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserBalance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('balance', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('frozen_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('currency', models.CharField(default='UZS', max_length=3)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='wallet',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'user_balances',
            },
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('type', models.CharField(
                    choices=[
                        ('deposit', 'Bakiye Yükleme'),
                        ('withdraw', 'Çekim'),
                        ('ad_spend', 'Reklam Harcaması'),
                        ('ad_earning', 'Reklam Geliri'),
                        ('freeze', 'Bütçe Dondurma'),
                        ('refund', 'Bütçe İadesi'),
                        ('adjustment', 'Manuel Düzeltme'),
                    ],
                    db_index=True,
                    max_length=20,
                )),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Beklemede'),
                        ('completed', 'Tamamlandı'),
                        ('failed', 'Başarısız'),
                        ('cancelled', 'İptal'),
                    ],
                    db_index=True,
                    default='completed',
                    max_length=20,
                )),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('balance_after', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('frozen_after', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('provider', models.CharField(
                    choices=[
                        ('click', 'Click.uz'),
                        ('payme', 'Payme'),
                        ('manual', 'Manuel'),
                        ('internal', 'Dahili'),
                    ],
                    default='internal',
                    max_length=20,
                )),
                ('provider_ref', models.CharField(blank=True, default='', max_length=255)),
                ('description', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='transactions',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('related_campaign', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='transactions',
                    to='ads.campaign',
                )),
                ('related_placement', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='transactions',
                    to='ads.adplacement',
                )),
                ('related_payout', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='transactions',
                    to='core.payoutrequest',
                )),
            ],
            options={
                'db_table': 'payment_transactions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='transaction',
            constraint=models.UniqueConstraint(
                condition=models.Q(('provider_ref', ''), _negated=True),
                fields=('provider', 'provider_ref'),
                name='unique_provider_ref_when_set',
            ),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['user', '-created_at'], name='tx_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['type', 'status'], name='tx_type_status_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['provider', 'provider_ref'], name='tx_provider_ref_idx'),
        ),
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('invoice_number', models.CharField(max_length=50, unique=True)),
                ('net_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('kdv_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('gross_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('currency', models.CharField(default='UZS', max_length=3)),
                ('status', models.CharField(
                    choices=[
                        ('draft', 'Taslak'),
                        ('issued', 'Düzenlendi'),
                        ('cancelled', 'İptal'),
                    ],
                    default='draft',
                    max_length=20,
                )),
                ('provider', models.CharField(
                    default='manual', max_length=20,
                    help_text="didox, faktura, manual — FAZ 4b'de aktifleşir",
                )),
                ('provider_ref', models.CharField(blank=True, default='', max_length=255)),
                ('issued_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('transaction', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invoice',
                    to='payments.transaction',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='invoices',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'payment_invoices',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PaymentAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('event_type', models.CharField(db_index=True, max_length=50)),
                ('provider', models.CharField(blank=True, default='', max_length=20)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('signature_valid', models.BooleanField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('result', models.CharField(default='success', max_length=30)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payment_audit_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'payment_audit_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='paymentauditlog',
            index=models.Index(fields=['provider', '-created_at'], name='audit_prov_created_idx'),
        ),
        migrations.AddIndex(
            model_name='paymentauditlog',
            index=models.Index(fields=['event_type', '-created_at'], name='audit_event_created_idx'),
        ),
        migrations.CreateModel(
            name='PaymentSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('min_payout_amount', models.DecimalField(
                    decimal_places=2, default=Decimal('50000'), max_digits=14,
                    help_text='Yayıncı çekim minimumu (UZS)',
                )),
                ('platform_commission_rate', models.DecimalField(
                    decimal_places=4, default=Decimal('0.3000'), max_digits=5,
                    help_text='Platform komisyon oranı (0-1 arası)',
                )),
                ('kdv_rate', models.DecimalField(
                    decimal_places=4, default=Decimal('0.1200'), max_digits=5,
                    help_text='QQS / KDV oranı (UZ %12)',
                )),
                ('currency', models.CharField(default='UZS', max_length=3)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'payment_settings',
                'verbose_name_plural': 'payment settings',
            },
        ),
    ]
