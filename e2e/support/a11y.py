"""Accessibility check with axe-core (A11Y-03)."""

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

BLOCKING_IMPACTS = frozenset({"serious", "critical"})

_axe = Axe()


def serious_violations(page: Page) -> list[str]:
    """axe violations of impact serious or critical on the current page, one line each."""
    results = _axe.run(page)
    return [
        f"{violation['id']} ({violation['impact']}): {violation['help']} "
        f"at {[node['target'] for node in violation['nodes']]}"
        for violation in results.response["violations"]
        if violation["impact"] in BLOCKING_IMPACTS
    ]
