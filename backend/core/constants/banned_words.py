"""
Yasaklı ve kısıtlı içerik kategorileri (FAZ 2).

Özbekistan Reklam Kanunu (Reklama To'g'risida, 1998, 2022 tadilatı) ve
ilgili yönetmeliklere dayalı kategorizasyon. Hukuki liste niteliğindedir;
ciddi değişiklikler yapmadan önce legal ile gözden geçirilmelidir.

Severity seviyeleri:
- critical → reklam tamamen yasak (otomatik reject)
- high     → ciddi kısıtlama, insan moderasyonu şart (flagged)
- medium   → kısıtlı, inceleme gerekli (flagged)
- low      → şüpheli, bayrak + inceleme (human_review)

Patternler normalize edilmiş metin (lowercase + leetspeak + diakritik
temizliği sonrası) üzerinde \\b ... \\b word-boundary ile aranır.
Aralıklı/bozulmuş varyasyonlar için `ads.moderation.normalize_text`
whitespace'i silerek ikinci geçiş yapar.
"""

from __future__ import annotations

# Her kategori için:
#   severity: {critical, high, medium, low}
#   patterns: dil kodu → kelime listesi. Latin ve Cyrillic alfabesindeki
#             patternler dil etiketinden bağımsız tüm metinlerde taranır;
#             dil etiketi yalnızca raporlama için.

BANNED_CATEGORIES = {
    "gambling": {
        "severity": "critical",
        "label": "Qimor va bahis",
        "patterns": {
            "uz": [
                r"qimor", r"qimorxona", r"tikish", r"pul tikish",
                r"bukmeker", r"kazino",
            ],
            "ru": [
                r"казино", r"азартн\w*", r"ставк\w*", r"букмекер\w*",
                r"игорн\w*", r"тотализатор",
            ],
            "tr": [r"kumar", r"bahis", r"iddia", r"şans oyun\w*"],
            "en": [
                r"casino", r"gambling", r"betting", r"bookmaker",
                r"poker", r"blackjack", r"roulette", r"slots?",
                r"1xbet", r"melbet", r"mostbet", r"pari?match",
            ],
        },
    },
    "alcohol": {
        "severity": "high",
        "label": "Alkogolli ichimliklar",
        "patterns": {
            "uz": [r"aroq", r"konyak", r"vino", r"pivo", r"viski", r"vodka"],
            "ru": [
                r"водк\w*", r"коньяк", r"вино", r"пиво", r"виски",
                r"ликер", r"шампанск\w*", r"алкогол\w*",
            ],
            "tr": [r"rakı", r"votka", r"şarap", r"bira", r"viski"],
            "en": [
                r"vodka", r"whisk(?:e)?y", r"cognac", r"rum", r"tequila",
                r"beer", r"wine", r"champagne", r"alcohol\w*",
            ],
        },
    },
    "tobacco": {
        "severity": "critical",
        "label": "Tamaki mahsulotlari",
        "patterns": {
            "uz": [r"sigaret", r"tamaki", r"nasvay", r"hookah", r"kalyon"],
            "ru": [
                r"сигарет\w*", r"табак\w*", r"насвай", r"кальян",
                r"вейп", r"электронн\w+ сигарет\w*",
            ],
            "tr": [r"sigara", r"tütün", r"nargile", r"puro"],
            "en": [
                r"cigarettes?", r"tobacco", r"vape", r"e-?cigarette",
                r"hookah", r"shisha", r"cigars?",
            ],
        },
    },
    "prescription_drug": {
        "severity": "high",
        "label": "Retsept bilan beriladigan dori",
        "patterns": {
            "uz": [r"retsept", r"antibiotik", r"gormonal"],
            "ru": [r"рецептурн\w*", r"антибиотик\w*", r"гормональн\w*"],
            "tr": [r"reçeteli", r"antibiyotik"],
            "en": [
                r"prescription (?:drug|medicine|med)", r"antibiotics?",
                r"opioid\w*", r"oxycodone", r"tramadol",
            ],
        },
    },
    "crypto": {
        "severity": "medium",
        "label": "Kriptovalyuta va investitsiya",
        "patterns": {
            "uz": [r"kripto", r"bitkoin", r"trading"],
            "ru": [
                r"криптовалют\w*", r"биткоин\w*", r"трейдинг",
                r"форекс", r"инвестиц\w*",
            ],
            "tr": [r"kripto", r"bitcoin", r"forex"],
            "en": [
                r"crypto(?:currenc\w*)?", r"bitcoin", r"ethereum",
                r"forex", r"trading signals?", r"pump(?: and | & )dump",
            ],
        },
    },
    "adult": {
        "severity": "critical",
        "label": "Kattalar uchun kontent",
        "patterns": {
            "uz": [r"porno", r"erotik", r"seksual"],
            "ru": [r"порно", r"эротик\w*", r"интим(?:ные)? услуг\w*"],
            "tr": [r"porno", r"erotik", r"yetişkin"],
            "en": [
                r"porn\w*", r"xxx", r"escort", r"erotic",
                r"adult (?:content|only|18\+)",
            ],
        },
    },
    "weapons": {
        "severity": "critical",
        "label": "Qurol-yarog'",
        "patterns": {
            "uz": [r"qurol", r"pistolet", r"miltiq"],
            "ru": [r"оруж\w*", r"пистолет\w*", r"автомат\w*", r"карабин\w*"],
            "tr": [r"silah", r"tabanca", r"tüfek"],
            "en": [
                r"firearms?", r"handguns?", r"rifles?", r"pistols?",
                r"ammunition", r"ammo",
            ],
        },
    },
    "scam_loans": {
        "severity": "high",
        "label": "Shubhali kredit/MFI",
        "patterns": {
            "uz": [r"tez qarz", r"zudlik bilan kredit"],
            "ru": [
                r"быстр\w+ кредит", r"займ без проверк\w*",
                r"микрозайм\w*", r"кредит за \d+ минут",
            ],
            "tr": [r"hızlı kredi"],
            "en": [r"payday loans?", r"instant loans?", r"no credit check"],
        },
    },
}


# Severity → bool: otomatik reddedilmeli mi?
AUTO_REJECT_SEVERITIES = {"critical"}

# Severity → bool: insan moderatör incelemesine yollansın mı?
HUMAN_REVIEW_SEVERITIES = {"high", "medium", "low"}
