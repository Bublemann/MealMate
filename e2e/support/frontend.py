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
