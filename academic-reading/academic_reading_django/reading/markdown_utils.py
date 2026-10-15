"""Rendering the model's markdown output as sanitised HTML.

The model runs under our own system prompt and rarely emits anything
adversarial, but its output still becomes `mark_safe` HTML in a template, so
it is cleaned through an allowlist regardless — defence in depth.
"""

from __future__ import annotations

import bleach
import markdown as md
from django.utils.safestring import mark_safe

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "blockquote", "code", "pre",
    "table", "thead", "tbody", "tr", "th", "td", "hr", "a", "sup",
]
ALLOWED_ATTRS = {"a": ["href", "title"]}


def render_markdown(text: str) -> str:
    """Markdown -> sanitised HTML, marked safe for direct template output."""
    html = md.markdown(text or "", extensions=["tables"])
    cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    return mark_safe(cleaned)
