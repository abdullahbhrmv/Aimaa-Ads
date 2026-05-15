# Generated manually for FAZ 5 Adım 2 — ConversionEvent name hash alanları.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pixel', '0002_rename_conv_camp_date_idx_conversions_campaig_eb6678_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversionevent',
            name='fn_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='conversionevent',
            name='ln_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
