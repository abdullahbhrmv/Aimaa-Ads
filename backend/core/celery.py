import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("aimaa_ads")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Periyodik görevler
app.conf.beat_schedule = {
    "deliver-ads-every-minute": {
        "task": "ads.tasks.deliver_scheduled_ads",
        "schedule": 60.0,
    },
    "delete-expired-ads-every-5min": {
        "task": "ads.tasks.delete_expired_ads",
        "schedule": 300.0,
    },
    "check-budgets-every-5min": {
        "task": "ads.tasks.check_campaign_budgets",
        "schedule": 300.0,
    },
    "aggregate-stats-daily": {
        "task": "ads.tasks.aggregate_daily_stats",
        "schedule": 86400.0,
    },
    "update-channel-stats-hourly": {
        "task": "ads.tasks.update_channel_stats",
        "schedule": 3600.0,
    },
    # FAZ 3 — kalite ve fraud nightly task'ları. 24 saatlik döngü; küçük
    # kaymalar tolere edilebilir. Production'da crontab ifadeleri ile
    # belirli saatlere sabitlenmeli (django-celery-beat üzerinden).
    "recalculate-channel-quality-daily": {
        "task": "ads.tasks.recalculate_channel_quality_scores",
        "schedule": 86400.0,
    },
    "detect-subscriber-anomalies-hourly": {
        "task": "ads.tasks.detect_subscriber_anomalies",
        "schedule": 3600.0,
    },
    "detect-ip-cluster-fraud-daily": {
        "task": "ads.tasks.detect_ip_cluster_fraud_task",
        "schedule": 86400.0,
    },
    # FAZ 5 Adım 2 — pending ConversionEvent'leri attribute et. 5 dakikada
    # bir çalışır; 30+ gün eski unattributed event'ler burada "expired"
    # işaretlenir, sonsuz retry önlenir.
    "attribute-pending-conversions-every-5min": {
        "task": "pixel.tasks.attribute_pending_conversions",
        "schedule": 300.0,
    },
}
