"""Configuration loading: config.yaml plus .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# reading/logic/settings.py -> logic -> reading -> academic_reading_django/
ROOT = Path(__file__).resolve().parent.parent.parent
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

    # Ollama Cloud only — there is no backend toggle in the Django build.
    def model_for(self, lang: str) -> str:
        """The configured model for a language, falling back if unmapped."""
        block = self.models.get("cloud", {})
        return block.get(lang) or block.get("fallback", "")

    def level(self, level_id: str) -> Level:
        return next((lv for lv in self.levels if lv.id == level_id), self.levels[0])

    @property
    def default_level(self) -> Level:
        # The original app defaulted its sidebar radio to index 1 (Intermediate).
        return self.levels[1] if len(self.levels) > 1 else self.levels[0]


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
