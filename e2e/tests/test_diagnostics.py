"""The temporary diagnostics screen of the M1 platform spike (plan § 12, removed in M9).

The suite's container runs with MEALMATE_DIAGNOSTICS_ENABLED=true, so the endpoints answer.
"""

from typing import Literal

import pytest
from playwright.sync_api import Locator, Page, expect

from support.a11y import serious_violations
from support.frontend import TEST_IDS, text


def result(page: Page, key: str) -> Locator:
    """The result line labelled with the translation `key` (its <dt>)."""
    label = page.get_by_text(text(key), exact=True)
    return page.get_by_test_id(TEST_IDS["diagResult"]).filter(has=label)


@pytest.mark.parametrize("color_scheme", ["light", "dark"])
def test_diagnostics_work_signed_out(page: Page, color_scheme: Literal["light", "dark"]) -> None:
    """/diag is public and outside the tab layout; the cookie test and the request echo work."""
    page.emulate_media(color_scheme=color_scheme)
    page.goto("/diag")

    expect(page.get_by_test_id(TEST_IDS["screenDiagnostics"])).to_be_visible()
    expect(page.get_by_role("heading", level=1, name=text("diag.title"))).to_be_visible()
    expect(page.get_by_role("navigation")).to_have_count(0)
    expect(result(page, "diag.result.env.colorScheme")).to_contain_text(color_scheme)
    ok = text("diag.status.ok")
    expect(result(page, "diag.result.env.version")).to_contain_text(ok)
    # Plain HTTP on the suite's container, so only "info"; on the Pi this must be https (O-3).
    expect(result(page, "diag.result.server.request")).to_contain_text("scheme=http ")

    page.get_by_role("button", name=text("diag.cookie.set")).click()
    expect(result(page, "diag.result.cookie.set")).to_contain_text(f"{ok} set in browser")
    page.get_by_role("button", name=text("diag.cookie.check")).click()
    expect(result(page, "diag.result.cookie.check")).to_contain_text(f"{ok} present in browser")

    expect(page.get_by_test_id(TEST_IDS["diagReport"])).to_contain_text(
        "[ok] cookie.check: present in browser"
    )
    # Temporary, but used on the phone in both colour schemes (A11Y-03).
    assert serious_violations(page) == []
