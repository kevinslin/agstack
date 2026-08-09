#!/usr/bin/env python3
"""Shared, versioned memory-base routing and index classification signals."""

from __future__ import annotations

import re


GENERIC_WORDS = frozenset(
    {
        "and",
        "at",
        "base",
        "docs",
        "for",
        "knowledge",
        "notes",
        "openai",
        "project",
        "references",
        "related",
        "rooted",
        "specifications",
        "specs",
        "tasks",
        "workspace",
    }
)

ARTIFACT_ALIASES: dict[str, tuple[str, ...]] = {
    "cook": ("cookbook", "guide"),
    "cookbook": ("cookbook", "guide"),
    "cookbooks": ("cookbook", "guide"),
    "decision": ("decision",),
    "decisions": ("decision",),
    "finding": ("finding",),
    "findings": ("finding",),
    "guide": ("guide",),
    "guides": ("guide",),
    "lesson": ("lesson",),
    "lessons": ("lesson",),
    "ref": ("reference",),
    "refs": ("reference",),
    "reference": ("reference",),
    "references": ("reference",),
    "report": ("report",),
    "reports": ("report",),
    "research": ("research",),
    "runbook": ("runbook",),
    "runbooks": ("runbook",),
    "spec": ("spec",),
    "specs": ("spec",),
}

# Keep existing query recognition while also recognizing every indexed alias.
ARTIFACT_WORDS = frozenset(ARTIFACT_ALIASES).union(
    kind for kinds in ARTIFACT_ALIASES.values() for kind in kinds
)


def normalized_words(value: str) -> list[str]:
    """Return case-folded ASCII alphanumeric routing tokens."""

    return re.findall(r"[a-z0-9]+", value.casefold())


def normalize_label(value: str) -> str:
    """Normalize an index label, rejecting empty and exclusively numeric labels."""

    words = normalized_words(value)
    if not words or all(word.isdecimal() for word in words):
        return ""
    return " ".join(words)
