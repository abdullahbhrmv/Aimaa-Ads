"""
Reklam içerik moderasyonu (FAZ 2).

`scan_text` fonksiyonu verilen metni normalize eder ve `banned_words.py`
içindeki kategorilere karşı iki geçiş halinde tarar:

1. **Word-boundary geçiş** — whitespace korunur, `\\b(kelime)\\b`
   ile aranır. Yüksek güvenilirlikli match. Severity olduğu gibi raporlanır.
2. **Fuzzy geçiş** — whitespace silinmiş metin üzerinde aynı pattern aranır
   (`k u m a r` gibi kaçırma denemelerini yakalamak için). Bu geçiş
   severity'yi bir kademe aşağı indirir — yanlış pozitif riskine karşı
   daha temkinli raporlanır.

`scan_image` şu an yer tutucudur; FAZ 8'de AI vision ile doldurulacak.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from core.constants.banned_words import (
    AUTO_REJECT_SEVERITIES,
    BANNED_CATEGORIES,
    HUMAN_REVIEW_SEVERITIES,
)

logger = logging.getLogger(__name__)


# Leetspeak ve benzeri karakter ikameleri — scan öncesi normalize edilir.
# Not: agresif normalize etmiyoruz; normal metindeki rakamları harflere
# çevirmek yanlış pozitif üretebilir. Yine de en sık kullanılan ikameler
# için eşleme yapıyoruz.
_LEET_MAP = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
        "$": "s",
        "!": "i",
        "€": "e",
    }
)

# Aynı karakterin 3+ tekrarını 2'ye indir: "cassssino" → "cassino"
# Not: "oo" gibi legitimate tekrarları korur.
_REPEAT_COMPRESS = re.compile(r"(.)\1{2,}")


# Severity kademesi — fuzzy (whitespace-stripped) geçişte bir basamak
# aşağıya düşmek için kullanılır.
_SEVERITY_LADDER = ["critical", "high", "medium", "low"]


def _downgrade_severity(severity: str) -> str:
    """Fuzzy geçişte severity'yi bir basamak aşağı düşür."""
    try:
        idx = _SEVERITY_LADDER.index(severity)
    except ValueError:
        return severity
    return _SEVERITY_LADDER[min(idx + 1, len(_SEVERITY_LADDER) - 1)]


def normalize_text(text: str) -> str:
    """Tarama öncesi metin normalizasyonu.

    Adımlar:
      1. Unicode NFKD + combining karakterleri at (diakritik temizliği).
      2. `casefold()` — Unicode-uyumlu lowercase.
      3. Leetspeak ikameleri.
      4. Aynı karakterin 3+ tekrarını 2'ye indir.
      5. Whitespace birden çok boşlukla geliyorsa tekli boşluğa indir.

    **Veriyi değiştirmez** — sadece scan için geçici normalize form üretir.
    """
    # NFKD ayrıştır ve combining karakterleri at
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    folded = without_marks.casefold()
    leeted = folded.translate(_LEET_MAP)
    compressed = _REPEAT_COMPRESS.sub(r"\1\1", leeted)

    # Ardışık whitespace'leri tek boşluğa indir
    normalized = re.sub(r"\s+", " ", compressed).strip()
    return normalized


def _strip_whitespace(text: str) -> str:
    """Tüm whitespace'i sil — `k u m a r` gibi dağıtılmış kelimeleri yakala."""
    return re.sub(r"\s+", "", text)


@dataclass
class MatchedTerm:
    """Tek bir pattern match'ini raporla."""

    category: str
    severity: str
    language: str
    pattern: str
    fuzzy: bool


@dataclass
class ModerationResult:
    """Bir metin veya görsel taramasının sonucu.

    - `approved`: otomatik yayınlanabilir mi? (no matches veya sadece low severity)
    - `severity`: toplam en yüksek severity ("clean" eğer match yok)
    - `flags`: match eden kategori slug'ları (kumar, alkol, ...)
    - `requires_human_review`: insan moderatörü bakmalı mı?
    - `matched_terms`: tüm match'lerin detayı (debug/audit için)
    """

    approved: bool
    severity: str
    flags: list[str]
    requires_human_review: bool
    matched_terms: list[MatchedTerm] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSONField'a kaydedilebilir dict forma dönüştür."""
        return {
            "approved": self.approved,
            "severity": self.severity,
            "flags": self.flags,
            "requires_human_review": self.requires_human_review,
            "matched_terms": [
                {
                    "category": m.category,
                    "severity": m.severity,
                    "language": m.language,
                    "pattern": m.pattern,
                    "fuzzy": m.fuzzy,
                }
                for m in self.matched_terms
            ],
        }


def _iter_patterns() -> Iterable[tuple[str, str, str, str]]:
    """(category, severity, language, pattern) üzerinden iterasyon."""
    for category, meta in BANNED_CATEGORIES.items():
        severity = meta["severity"]
        for language, patterns in meta["patterns"].items():
            for pattern in patterns:
                yield category, severity, language, pattern


def _highest_severity(matches: list[MatchedTerm]) -> str:
    """Match listesinden en ciddi severity'yi seç."""
    if not matches:
        return "clean"
    for level in _SEVERITY_LADDER:
        if any(m.severity == level for m in matches):
            return level
    return matches[0].severity


def scan_text(text: str, language: str = "uz") -> ModerationResult:
    """Metni yasaklı içerik için tara.

    Args:
        text: Taranacak ham metin.
        language: Raporlama/istatistik için UI dili. Tarama her dildeki
                  pattern listesinde yapılır (dil bağımsız).

    Returns:
        ModerationResult — `approved` ve `flags` alanları moderasyon
        pipeline'ı tarafından tüketilir.
    """
    if not text or not text.strip():
        return ModerationResult(
            approved=True,
            severity="clean",
            flags=[],
            requires_human_review=False,
        )

    normalized = normalize_text(text)
    stripped = _strip_whitespace(normalized)

    matched: list[MatchedTerm] = []

    for category, severity, lang, pattern in _iter_patterns():
        # Geçiş 1 — word-boundary, whitespace korunur.
        if re.search(rf"\b{pattern}\b", normalized):
            matched.append(
                MatchedTerm(
                    category=category,
                    severity=severity,
                    language=lang,
                    pattern=pattern,
                    fuzzy=False,
                )
            )
            continue

        # Geçiş 2 — whitespace'siz, severity bir kademe düşük.
        # `\b` anchor whitespace-stripped metinde anlamsız olacağı için
        # düz `search` ile ararız; fuzzy match severity düşürülmüş olarak
        # raporlanır ki yanlış pozitifler kritik olmasın.
        if re.search(pattern, stripped):
            matched.append(
                MatchedTerm(
                    category=category,
                    severity=_downgrade_severity(severity),
                    language=lang,
                    pattern=pattern,
                    fuzzy=True,
                )
            )

    highest = _highest_severity(matched)
    flags = sorted({m.category for m in matched})

    auto_reject = highest in AUTO_REJECT_SEVERITIES
    needs_review = (not auto_reject) and highest in HUMAN_REVIEW_SEVERITIES
    approved = not matched  # Herhangi bir match varsa otomatik onay yok.

    result = ModerationResult(
        approved=approved,
        severity=highest,
        flags=flags,
        requires_human_review=needs_review,
        matched_terms=matched,
    )

    if matched:
        logger.info(
            "Moderation flagged content: severity=%s flags=%s language=%s",
            highest,
            flags,
            language,
        )

    return result


def scan_image(image_url: str) -> ModerationResult:
    """Görsel moderasyonu — FAZ 8'de AI vision ile dolacak.

    Şimdilik her görsel "taranmadı" bayrağıyla onaylanır; insan moderatör
    görsel içerikte kararı verir.
    """
    return ModerationResult(
        approved=True,
        severity="clean",
        flags=["not_scanned"],
        requires_human_review=False,
        matched_terms=[],
    )


def combined_result(results: Iterable[ModerationResult]) -> ModerationResult:
    """Birden çok ModerationResult'ı tek bir özet sonuca birleştir.

    Campaign seviyesinde her Ad için ayrı scan yapılır, ardından bu
    fonksiyon ile kampanya genelinde en kötü durumu elde ederiz.
    """
    results_list = list(results)
    if not results_list:
        return ModerationResult(
            approved=True,
            severity="clean",
            flags=[],
            requires_human_review=False,
        )

    all_terms: list[MatchedTerm] = []
    for r in results_list:
        all_terms.extend(r.matched_terms)

    highest = _highest_severity(all_terms)
    flags = sorted({f for r in results_list for f in r.flags if f != "not_scanned"})

    auto_reject = highest in AUTO_REJECT_SEVERITIES
    needs_review = (
        any(r.requires_human_review for r in results_list)
        or (not auto_reject and highest in HUMAN_REVIEW_SEVERITIES)
    )
    approved = all(r.approved for r in results_list) and not all_terms

    return ModerationResult(
        approved=approved,
        severity=highest,
        flags=flags,
        requires_human_review=needs_review,
        matched_terms=all_terms,
    )
