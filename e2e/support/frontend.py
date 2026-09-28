"""Test IDs and UI strings, read from the frontend sources so there is one source of truth.

Tests find elements by role, accessible name or test ID, never by CSS classes (QA-05). The test
IDs come from frontend/src/testIds.ts and the expected texts from frontend/src/i18n/<lang>.json.
"""

import json
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from types import MappingProxyType

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

_TEST_IDS_BLOCK = re.compile(r"export const testIds = \{(?P<body>.*?)\} as const", re.DOTALL)
_TEST_ID_ENTRY = re.compile(r"^\s*(\w+):\s*'([^']+)',?\s*$", re.MULTILINE)


def _load_test_ids() -> Mapping[str, str]:
    source = (FRONTEND_SRC / "testIds.ts").read_text(encoding="utf-8")
    block = _TEST_IDS_BLOCK.search(source)
    if block is None:
        raise RuntimeError("`export const testIds = { … } as const` not found in testIds.ts")
    return MappingProxyType(dict(_TEST_ID_ENTRY.findall(block["body"])))


TEST_IDS = _load_test_ids()


@cache
def translations(language: str) -> Mapping[str, str]:
    """The flat i18n resource of `language` (e.g. "de": {"nav.lists": "Listen", …})."""
    path = FRONTEND_SRC / "i18n" / f"{language}.json"
    return MappingProxyType(json.loads(path.read_text(encoding="utf-8")))


_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def text(key: str, language: str = "en", **params: str) -> str:
    """The UI string `key` with its `{{placeholders}}` filled in, as i18next renders it."""

    def fill(match: re.Match[str]) -> str:
        return params[match[1]]

    return _PLACEHOLDER.sub(fill, translations(language)[key])


def ingredient_label(name: str, brand: str | None = None) -> str:
    """An ingredient's name as the app shows it: "Milch (Weidehof)" (features/ingredients/label.ts).

    Two brands of the same thing are different ingredients, so the brand is part of the name
    everywhere (meal rows, list lines, the export, headings)."""
    brand = (brand or "").strip()
    return f"{name} ({brand})" if brand else name
