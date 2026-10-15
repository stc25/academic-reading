"""Configuration loading: config.yaml plus .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .languages import resolve

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


@dataclass(frozen=True)
class Level:
    """How hard a text is — a property of the text, not of the reader."""

    id: str
    label: str
    aliases: tuple[str, ...] = ()

    def matches(self, value: str) -> bool:
        key = (value or "").strip().casefold()
        return key == self.id or key == self.label.casefold() or key in self.aliases


@dataclass(frozen=True)
class Activity:
    id: str
    number: int
    label: str
    description: str
    interactive: bool
    stance: str = "after"
    spoilers: bool = False
    submit_label: str = "Send for comment"
    render: str = "pane"

    @property
    def display(self) -> str:
        return f"{self.number}. {self.label}"


@dataclass(frozen=True)
class Config:
    models: dict
    levels: list[Level]
    default_level_id: str
    texts: dict
    activities: list[Activity]
    reading: dict

    # -- models ----------------------------------------------------------- #
    def model_for(self, lang: str, backend: str | None = None) -> str:
        """The model configured for a language, or the block's default.

        by_language may be keyed by code or by English name; both are tried, so
        `zh:` and `Chinese:` behave identically.
        """
        block = self.models.get(backend or self.backend, {})
        routes = {
            str(key).strip().casefold(): value
            for key, value in (block.get("by_language") or {}).items()
        }
        code, name = resolve(lang)
        for key in (code, name.casefold()):
            if key and key in routes:
                return routes[key]
        return block.get("default", "")

    def alternatives(self, backend: str | None = None) -> list[str]:
        block = self.models.get(backend or self.backend, {})
        return list(block.get("alternatives", []))

    @property
    def backend(self) -> str:
        return self.models.get("backend", "local")

    @property
    def backends(self) -> list[str]:
        return [b for b in ("local", "cloud") if b in self.models]

    # -- levels ----------------------------------------------------------- #
    @property
    def default_level(self) -> Level:
        return self.level(self.default_level_id)

    def level(self, value: str) -> Level:
        """The level a source.cfg entry names, falling back to the default.

        Unknown and missing values fall back rather than failing: a catalogue
        with a typo in it should still open its texts.
        """
        for lv in self.levels:
            if lv.matches(value):
                return lv
        return next(
            (lv for lv in self.levels if lv.id == self.default_level_id), self.levels[0]
        )


def load_config(path: Path = CONFIG_PATH) -> Config:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    levels = [
        Level(
            id=lv["id"],
            label=lv["label"],
            aliases=tuple(str(a).casefold() for a in lv.get("aliases", [])),
        )
        for lv in raw.get("levels", [])
    ]
    return Config(
        models=raw.get("models", {}),
        levels=levels,
        default_level_id=raw.get("default_level", levels[0].id if levels else ""),
        texts=raw.get("texts", {}),
        activities=[Activity(**a) for a in raw.get("activities", [])],
        reading=raw.get("reading", {}),
    )


def cloud_api_key() -> str | None:
    """Ollama Cloud key from .env / the environment, if one is set."""
    load_dotenv(ROOT / ".env")
    return os.environ.get("OLLAMA_API_KEY") or None
