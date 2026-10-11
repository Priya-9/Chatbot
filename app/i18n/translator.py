"""Loads `locales/<code>.yaml` files and formats strings with fallback to the default language."""

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, full + "."))
        else:
            flat[full] = str(value)
    return flat


class Translator:
    def __init__(self, locales_dir: str | Path, languages: list[str], default_language: str = "en"):
        self.default_language = default_language
        self.strings: dict[str, dict[str, str]] = {}
        for code in languages:
            path = Path(locales_dir) / f"{code}.yaml"
            if not path.exists():
                log.warning("Locale file missing for language %r: %s", code, path)
                continue
            self.strings[code] = _flatten(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        if default_language not in self.strings:
            raise ValueError(f"Default language {default_language!r} has no locale file in {locales_dir}")

    @property
    def languages(self) -> list[str]:
        return list(self.strings)

    def language_name(self, code: str) -> str:
        """Native display name, e.g. 'Español'."""
        return self.strings.get(code, {}).get("_meta.name", code)

    def english_name(self, code: str) -> str:
        """English name - used to tell the LLM which language to answer in."""
        return self.strings.get(code, {}).get("_meta.english_name", code)

    def resolve(self, code: str | None) -> str:
        return code if code in self.strings else self.default_language

    def t(self, key: str, lang: str | None = None, **params) -> str:
        lang = self.resolve(lang)
        template = self.strings[lang].get(key) or self.strings[self.default_language].get(key)
        if template is None:
            log.warning("Missing translation key %r", key)
            return key
        return template.format_map(_SafeDict(params))
