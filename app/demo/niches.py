"""Loads `demo/niches.yaml`. Any text value may be a plain string or a {language_code: string} map."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def pick(value: Any, lang: str, default_lang: str = "en") -> Any:
    """Resolve a value that is either language-neutral or a {lang: value} map."""
    if isinstance(value, dict):
        return value.get(lang) or value.get(default_lang) or next(iter(value.values()), "")
    return value


@dataclass
class Niche:
    id: str
    raw: dict

    @property
    def knowledge(self) -> str:
        """Sub-folder of KNOWLEDGE_DIR that retrieval is scoped to."""
        return self.raw.get("knowledge", self.id)

    @property
    def aliases(self) -> list[str]:
        return [a.lower() for a in self.raw.get("aliases", [])]

    def text(self, key: str, lang: str) -> str:
        """Dotted lookup, e.g. text("booking.label", "hi")."""
        value: Any = self.raw
        for part in key.split("."):
            value = value.get(part, "") if isinstance(value, dict) else ""
        return str(pick(value, lang) or "")

    def params(self, lang: str) -> dict[str, str]:
        """Placeholders available to every locale string once a niche is chosen."""
        examples = pick(self.raw.get("examples", []), lang) or []
        return {
            "business": self.text("business", lang),
            "niche_title": self.text("title", lang),
            "book_label": self.text("booking.label", lang),
            "book_ask_detail": self.text("booking.ask_detail", lang),
            "book_ask_when": self.text("booking.ask_when", lang),
            "examples": "\n".join(f"• {e}" for e in examples),
        }

    def matches(self, text: str, lang: str) -> bool:
        text = text.strip().lower()
        if text in {self.id, self.text("title", lang).lower(), self.text("title", "en").lower()}:
            return True
        words = set(re.findall(r"\w+", text))
        return any(a in words or (" " in a and a in text) for a in self.aliases)


def load_niches(path: str | Path) -> dict[str, Niche]:
    if not path:
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    niches: dict[str, Niche] = {}
    for item in data.get("niches", []):
        if item["id"] in niches:
            raise ValueError(f"Duplicate niche id {item['id']!r} in {path}")
        niches[item["id"]] = Niche(id=item["id"], raw=item)
    return niches
