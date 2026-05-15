"""
i18n — JSON tabanlı cevirme moduli.
"""

import json
import os
from pathlib import Path

_translations: dict[str, dict[str, str]] = {}

LOCALES_DIR = Path(__file__).parent.parent / "locales"


def _load_translations():
    """Barcha til dosyalarini yuklaydi."""
    global _translations
    for lang_dir in LOCALES_DIR.iterdir():
        if lang_dir.is_dir():
            lang = lang_dir.name
            messages_file = lang_dir / "messages.json"
            if messages_file.exists():
                with open(messages_file, "r", encoding="utf-8") as f:
                    _translations[lang] = json.load(f)


def t(key: str, lang: str = "uz", **kwargs) -> str:
    """Kalit bo'yicha tarjima qaytaradi.

    Args:
        key: Tarjima kaliti (masalan: "welcome", "help")
        lang: Til kodi ("uz" yoki "ru")
        **kwargs: Format uchun o'zgaruvchilar

    Returns:
        Tarjima qilingan matn
    """
    if not _translations:
        _load_translations()

    messages = _translations.get(lang, _translations.get("uz", {}))
    text = messages.get(key, _translations.get("uz", {}).get(key, key))

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


# Modul yuklanganda tarjimalarni yuklash
_load_translations()
