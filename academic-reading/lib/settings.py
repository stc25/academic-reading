"""Configuration loading: config.yaml plus .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
TEXTS_DIR = ROOT / "texts"


@dataclass(frozen=True)
class Level:
    id: str
    label: str
    cefr: str

    @property
    def display(self) -> str:
        return f"{self.label} ({self.cefr})"


@dataclass(frozen=True)
class Activity:
    id: str
    number: int
    label: str
    description: str
    response_language: str
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
    activities: list[Activity]
    reading: dict

    def model_for(self, lang: str, backend: str | None = None) -> str:
        """The configured model for a language, falling back if unmapped."""
        backend = backend or self.models.get("backend", "local")
        block = self.models.get(backend, {})
        return block.get(lang) or block.get("fallback", "")

    def alternatives(self, backend: str | None = None) -> list[str]:
        backend = backend or self.models.get("backend", "local")
        return list(self.models.get(backend, {}).get("alternatives", []))

    @property
    def backends(self) -> list[str]:
        return [b for b in ("local", "cloud") if b in self.models]

    def level(self, level_id: str) -> Level:
        return next(lv for lv in self.levels if lv.id == level_id)


def load_config(path: Path = CONFIG_PATH) -> Config:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Config(
        models=raw.get("models", {}),
        levels=[Level(**lv) for lv in raw.get("levels", [])],
        activities=[Activity(**a) for a in raw.get("activities", [])],
        reading=raw.get("reading", {}),
    )


def cloud_api_key() -> str | None:
    """Ollama Cloud key from .env / the environment, if one is set."""
    load_dotenv(ROOT / ".env")
    return os.environ.get("OLLAMA_API_KEY") or None
