"""
Hash contract JS↔Python parity testi (FAZ 5 Adım 2).

Aynı `pixel/fixtures/hash_fixtures.json` dosyasını:
  - Node tarafı `pixel/test/hash.test.js` ile doğruluyor
  - Python tarafı bu test ile doğruluyor

İki taraf aynı ground truth'a karşı bağımsız olarak çalışır. Herhangi bir
sapma → iki side'dan birinin bug'ı → cross-device attribution sessizce
bozulur. Her CI run'ında her iki test de geçmek zorunda.

Failure stratejisi: tüm vektörleri tara, hatalı olanları topla, TEK
assertion ile kısa rapor ver (çıktı okunması kolay).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixel.services import hash_for_matching, normalize_for_hash


# Monorepo root / pixel / fixtures / hash_fixtures.json
#
# Django BASE_DIR = backend/. Fixture pixel/ (repo root'ta) altında,
# yani BASE_DIR.parent / "pixel" / ...
BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_PATH = BACKEND_DIR.parent / "pixel" / "fixtures" / "hash_fixtures.json"


def _load_fixtures() -> dict:
    assert FIXTURE_PATH.exists(), (
        f"Fixture missing at {FIXTURE_PATH}. "
        f"JS↔Python parity cannot be verified."
    )
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_all_29_parity_vectors_match_fixture():
    """Her vektör için normalize + hash çıktıları fixture ile BİREBİR."""
    fixture = _load_fixtures()
    failures: list[str] = []
    total = 0

    for kind, cases in fixture["cases"].items():
        for case in cases:
            total += 1
            tag = f"{kind}/{case['name']}"
            raw = case["raw"]

            actual_norm = normalize_for_hash(raw, kind)
            if actual_norm != case["normalized"]:
                failures.append(
                    f"{tag} normalize: expected={case['normalized']!r} "
                    f"got={actual_norm!r} (raw={raw!r})"
                )
                continue  # hash'e bakmanın anlamı yok, normalize zaten yanlış

            actual_hash = hash_for_matching(raw, kind)
            if actual_hash != case["hash"]:
                failures.append(
                    f"{tag} hash: expected={case['hash'] or '(empty)'} "
                    f"got={actual_hash or '(empty)'} (normalized={actual_norm!r})"
                )

    # Tek assertion — tüm failure'ları birlikte raporla.
    assert not failures, (
        f"\n{len(failures)}/{total} parity vectors FAILED:\n"
        + "\n".join(f"  - {m}" for m in failures)
    )


def test_fixture_version_pinned():
    """Fixture şeması değişirse test explicit olarak fail olmalı.

    Yeni version'a geçerken JS + Python implementasyonlarının ikisi de
    güncellenmek zorunda; bu test bunu zorlar.
    """
    fixture = _load_fixtures()
    assert fixture["version"] == 1


def test_nfd_to_nfc_idempotency_independent():
    """Fixture'dan bağımsız — NFD decomposed input, NFC precomposed ile aynı hash."""
    h_nfc = hash_for_matching("Café", "name")
    h_nfd = hash_for_matching("cafe\u0301", "name")  # combining acute
    assert h_nfc == h_nfd, "NFC normalization broken in Python"


def test_phone_unicode_digits_stripped_independent():
    """Fixture'dan bağımsız — 6 input (3 ASCII separator + 3 unicode digit)
    tek bir hash'te birleşmeli (regex [^0-9] doğru çalışıyor)."""
    base = "998901234567"
    hashes = {
        hash_for_matching("+998 (90) 123-45-67", "phone"),
        hash_for_matching("998-90-123-45-67", "phone"),
        hash_for_matching(base, "phone"),
        hash_for_matching(f"+{base}\u0660", "phone"),   # Arabic ٠
        hash_for_matching(f"+{base}\u09ec", "phone"),   # Bengali ৬
        hash_for_matching(f"+{base}\u0967", "phone"),   # Devanagari १
    }
    assert len(hashes) == 1, f"phone strip produced {len(hashes)} hashes: {hashes}"


def test_empty_input_produces_empty_hash():
    """Boş/whitespace-only input → boş hash (SHA-256(empty) DEĞİL)."""
    assert hash_for_matching("", "email") == ""
    assert hash_for_matching("   ", "email") == ""
    assert hash_for_matching("   ", "phone") == ""
    assert hash_for_matching(None, "name") == ""


def test_external_id_case_preserved():
    """external_id hash'i case-sensitive olmalı — distinct case = distinct hash."""
    a = hash_for_matching("USR_12345", "external_id")
    b = hash_for_matching("usr_12345", "external_id")
    assert a and b and a != b


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        normalize_for_hash("foo", "unknown_kind")
