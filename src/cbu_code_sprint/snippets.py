from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

UNKNOWN_LANGUAGE_LABEL = "아직 잘 모름"
UNKNOWN_LANGUAGE_TARGET = "Python"


@dataclass(frozen=True)
class Snippet:
    id: str
    language: str
    title: str
    code: str
    difficulty: str = "v1"


def canonical_language(language: str) -> str:
    clean = language.strip()
    if clean == UNKNOWN_LANGUAGE_LABEL:
        return UNKNOWN_LANGUAGE_TARGET
    return clean


def load_snippets(path: str | Path) -> list[Snippet]:
    snippet_path = Path(path)
    raw = json.loads(snippet_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("snippets.json must contain a list")

    snippets: list[Snippet] = []
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each snippet must be an object")
        snippet = Snippet(
            id=str(item["id"]),
            language=str(item["language"]),
            title=str(item["title"]),
            code=str(item["code"]),
            difficulty=str(item.get("difficulty", "v1")),
        )
        if snippet.id in seen_ids:
            raise ValueError(f"duplicate snippet id: {snippet.id}")
        if not snippet.code.strip():
            raise ValueError(f"snippet {snippet.id} has empty code")
        seen_ids.add(snippet.id)
        snippets.append(snippet)
    return snippets


def snippets_for_language(snippets: Iterable[Snippet], language: str) -> list[Snippet]:
    target = canonical_language(language)
    return [snippet for snippet in snippets if snippet.language == target]


def choose_snippet(snippets: Iterable[Snippet], language: str) -> Snippet:
    candidates = snippets_for_language(snippets, language)
    if not candidates:
        raise ValueError(f"no snippets configured for language: {language}")
    return random.choice(candidates)
