"""Talking to Ollama Cloud. The Django build has no local backend."""

from __future__ import annotations

from collections.abc import Iterator

from ollama import Client, ResponseError

from .settings import cloud_api_key

CLOUD_HOST = "https://ollama.com"


class LLMError(RuntimeError):
    """Anything that went wrong that the reader should see in plain words."""


def make_client() -> Client:
    key = cloud_api_key()
    if not key:
        raise LLMError("No OLLAMA_API_KEY found — add one to .env.")
    return Client(host=CLOUD_HOST, headers={"Authorization": f"Bearer {key}"})


def stream_reply(
    model: str,
    system: str,
    user: str,
    options: dict | None = None,
) -> Iterator[str]:
    """Yield the model's reply in pieces, with any reasoning trace removed."""
    if not model:
        raise LLMError("No model configured for this language — check config.yaml.")
    client = make_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        stream = client.chat(
            model=model, messages=messages, stream=True, options=options or {}
        )
        yield from _without_thinking(_content(stream))
    except ResponseError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise LLMError(
                f"Model `{model}` is not available on Ollama Cloud."
            ) from exc
        raise LLMError(f"Ollama returned an error: {message}") from exc
    except ConnectionError as exc:
        raise LLMError("Could not reach Ollama Cloud.") from exc


def _content(stream) -> Iterator[str]:
    for chunk in stream:
        piece = getattr(getattr(chunk, "message", None), "content", None)
        if piece:
            yield piece


_OPEN, _CLOSE = "<think>", "</think>"


def _without_thinking(pieces: Iterator[str]) -> Iterator[str]:
    """Drop <think>…</think> spans, which some models emit inline."""
    buffer = ""
    thinking = False
    for piece in pieces:
        buffer += piece
        while buffer:
            if thinking:
                end = buffer.find(_CLOSE)
                if end == -1:
                    buffer = ""
                    break
                buffer = buffer[end + len(_CLOSE) :]
                thinking = False
                continue
            start = buffer.find(_OPEN)
            if start == -1:
                emit, buffer = _hold_partial_tag(buffer)
                if emit:
                    yield emit
                break
            if start:
                yield buffer[:start]
            buffer = buffer[start + len(_OPEN) :]
            thinking = True
    if buffer and not thinking:
        yield buffer


def _hold_partial_tag(buffer: str) -> tuple[str, str]:
    """Keep back a trailing fragment that might be the start of a tag."""
    for n in range(min(len(buffer), len(_CLOSE)), 0, -1):
        tail = buffer[-n:]
        if _OPEN.startswith(tail) or _CLOSE.startswith(tail):
            return buffer[:-n], tail
    return buffer, ""
