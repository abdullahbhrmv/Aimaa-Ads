"""
Moderasyon testleri (FAZ 2).

Kapsam:
- `normalize_text` — casefold, diakritik, leetspeak, tekrar sıkıştırma
- `scan_text` — UZ/RU/TR/EN yasaklı kelime tespiti, fuzzy match (aralıklı harfler)
- Severity kademesi — critical → auto-reject, high → flagged
- `scan_campaign_creatives` — kampanya moderasyon pipeline'ı
"""

from __future__ import annotations

import pytest

from ads.models import Ad, Campaign
from ads.moderation import (
    ModerationResult,
    combined_result,
    normalize_text,
    scan_image,
    scan_text,
)
from ads.tasks import scan_campaign_creatives


# --- normalize_text -----------------------------------------------------------


def test_normalize_casefolds_and_strips_diacritics():
    assert normalize_text("CASÍNO") == "casino"
    assert normalize_text("ÇÖÇEK") == "cocek"


def test_normalize_collapses_repeated_characters():
    assert normalize_text("cassssino") == "cassino"
    assert normalize_text("aaaaaaa") == "aa"


def test_normalize_applies_leetspeak():
    assert normalize_text("c@s1n0") == "casino"
    assert normalize_text("p0k3r") == "poker"


def test_normalize_preserves_normal_text():
    # Normal metinler bozulmamalı
    assert normalize_text("Salom dunyo") == "salom dunyo"


# --- scan_text ---------------------------------------------------------------


pytestmark = []  # no DB required for most of these


def test_scan_clean_text_is_approved():
    result = scan_text("Yangi mahsulot — sifatli va arzon!", language="uz")
    assert result.approved is True
    assert result.severity == "clean"
    assert result.flags == []
    assert result.requires_human_review is False


def test_scan_detects_gambling_in_uzbek():
    result = scan_text("Qimor o'ynash va pul ishlash!", language="uz")
    assert result.approved is False
    assert "gambling" in result.flags
    assert result.severity == "critical"


def test_scan_detects_gambling_in_russian():
    result = scan_text("Лучшее казино онлайн — играйте сейчас", language="ru")
    assert result.approved is False
    assert "gambling" in result.flags
    assert result.severity == "critical"


def test_scan_detects_leetspeak_casino():
    result = scan_text("Best c@s1n0 ever", language="en")
    assert result.approved is False
    assert "gambling" in result.flags


def test_scan_detects_spaced_letters_fuzzy():
    """`k u m a r` whitespace'siz geçişle yakalanır, severity düşer."""
    result = scan_text("Tez yerda k u m a r bor", language="tr")
    assert result.approved is False
    assert "gambling" in result.flags
    # Fuzzy match → severity bir kademe düşük (critical → high)
    assert result.severity == "high"
    assert any(m.fuzzy for m in result.matched_terms)


def test_scan_alcohol_is_flagged_not_auto_rejected():
    result = scan_text("Eng yaxshi aroq — arzon narx", language="uz")
    assert "alcohol" in result.flags
    # Alcohol severity=high → approved=False, ancak auto-reject değil
    assert result.severity == "high"
    assert result.requires_human_review is True


def test_scan_tobacco_is_critical():
    result = scan_text("Elektron sigaret sotamiz", language="uz")
    assert "tobacco" in result.flags
    assert result.severity == "critical"


def test_scan_multiple_categories_produces_multiple_flags():
    result = scan_text("Kazino va aroq aksiyasi", language="uz")
    assert "gambling" in result.flags
    assert "alcohol" in result.flags
    # En kötü severity kumar (critical)
    assert result.severity == "critical"


def test_scan_crypto_medium_severity_requires_review():
    result = scan_text("Forex trading signals — 100% profit", language="en")
    assert "crypto" in result.flags
    # Medium → insan review
    assert result.requires_human_review is True
    assert result.severity == "medium"


def test_scan_adult_content_critical():
    result = scan_text("porno videos here", language="en")
    assert "adult" in result.flags
    assert result.severity == "critical"


def test_empty_text_is_approved():
    result = scan_text("", language="uz")
    assert result.approved is True
    assert result.flags == []


def test_scan_image_stub_returns_not_scanned_flag():
    result = scan_image("http://example.test/banner.png")
    assert result.approved is True
    assert "not_scanned" in result.flags


# --- combined_result ---------------------------------------------------------


def test_combined_result_aggregates_flags():
    r1 = scan_text("Yangi pivo tushdi", language="uz")  # alcohol
    r2 = scan_text("forex trading", language="en")  # crypto
    combined = combined_result([r1, r2])

    assert "alcohol" in combined.flags
    assert "crypto" in combined.flags
    # En kötü severity: alcohol = high
    assert combined.severity == "high"


def test_combined_result_with_no_matches_is_approved():
    r1 = scan_text("Salom", language="uz")
    r2 = scan_text("Hello", language="en")
    combined = combined_result([r1, r2])
    assert combined.approved is True
    assert combined.flags == []


def test_combined_result_empty_input_is_approved():
    combined = combined_result([])
    assert combined.approved is True
    assert combined.severity == "clean"


# --- scan_campaign_creatives -------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_scan_campaign_with_clean_ad_auto_approves(campaign_factory, ad_factory):
    campaign = campaign_factory()
    ad_factory(campaign=campaign, text_uz="Yangi mahsulot taqdimot")

    scan_campaign_creatives(campaign.id)

    campaign.refresh_from_db()
    assert campaign.moderation_status == Campaign.ModerationStatus.AUTO_APPROVED
    assert campaign.moderation_flags == []


@pytest.mark.django_db(transaction=True)
def test_scan_campaign_with_critical_content_is_auto_rejected(
    campaign_factory, ad_factory
):
    campaign = campaign_factory(status=Campaign.Status.PENDING)
    ad_factory(campaign=campaign, text_uz="Kazino — eng yaxshi qimor uyasi")

    scan_campaign_creatives(campaign.id)

    campaign.refresh_from_db()
    assert campaign.moderation_status == Campaign.ModerationStatus.REJECTED
    assert campaign.status == Campaign.Status.REJECTED
    assert "gambling" in campaign.moderation_flags
    assert "yasaklı içerik" in campaign.rejection_reason.lower() or "gambling" in campaign.rejection_reason.lower()


@pytest.mark.django_db(transaction=True)
def test_scan_campaign_with_high_severity_is_flagged_not_rejected(
    campaign_factory, ad_factory
):
    campaign = campaign_factory(status=Campaign.Status.PENDING)
    ad_factory(campaign=campaign, text_uz="Aroq va vino aksiyasi")

    scan_campaign_creatives(campaign.id)

    campaign.refresh_from_db()
    assert campaign.moderation_status == Campaign.ModerationStatus.FLAGGED
    # Business status dokunulmamış olmalı — admin karar versin
    assert campaign.status == Campaign.Status.PENDING
    assert "alcohol" in campaign.moderation_flags


@pytest.mark.django_db(transaction=True)
def test_scan_campaign_with_no_ads_is_noop(campaign_factory):
    campaign = campaign_factory()
    result = scan_campaign_creatives(campaign.id)
    assert result == {"status": "no_ads"}
    campaign.refresh_from_db()
    # moderation_status değişmemeli — hâlâ pending
    assert campaign.moderation_status == Campaign.ModerationStatus.PENDING


@pytest.mark.django_db(transaction=True)
def test_scan_campaign_includes_russian_text(campaign_factory, ad_factory):
    campaign = campaign_factory()
    ad_factory(
        campaign=campaign,
        text_uz="Salom dunyo",
        text_ru="Казино и ставки онлайн",
    )

    scan_campaign_creatives(campaign.id)

    campaign.refresh_from_db()
    assert campaign.moderation_status == Campaign.ModerationStatus.REJECTED
    assert "gambling" in campaign.moderation_flags
