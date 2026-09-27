"""axe finds no serious or critical violations on the main screens (A11Y-03)."""

from dataclasses import dataclass
from typing import Literal

import pytest
from playwright.sync_api import Page, expect

from support.a11y import serious_violations
from support.api import CODE_REQUESTS, Account, Api, code_from_link, sign_in
from support.frontend import TEST_IDS, text

Visitor = Literal["anonymous", "member", "admin"]


@dataclass(frozen=True)
class Screen:
    path: str
    visitor: Visitor
    # Shown once the screen's data has loaded, so the whole screen is checked.
    ready: tuple[str, ...]


SCREENS = [
    Screen("/login", "anonymous", (TEST_IDS["screenLogin"],)),
    # The invite code is appended in the test: /join#<code>.
    Screen("/join", "anonymous", (TEST_IDS["screenJoin"],)),
    Screen("/lists", "member", (TEST_IDS["screenLists"],)),
    Screen("/meals", "member", (TEST_IDS["screenMeals"],)),
    Screen("/ingredients", "member", (TEST_IDS["screenIngredients"],)),
    Screen("/me", "member", (TEST_IDS["appVersion"], TEST_IDS["sessionList"])),
    Screen("/me/admin/users", "admin", (TEST_IDS["adminUserList"],)),
    Screen("/me/admin/invites", "admin", (TEST_IDS["inviteList"], TEST_IDS["shareLinkUrl"])),
    Screen("/me/admin/events", "admin", (TEST_IDS["eventList"],)),
]


@pytest.mark.parametrize("color_scheme", ["light", "dark"])
@pytest.mark.parametrize("screen", SCREENS, ids=lambda screen: screen.path)
def test_no_serious_violations(
    page: Page,
    request: pytest.FixtureRequest,
    screen: Screen,
    color_scheme: Literal["light", "dark"],
) -> None:
    page.emulate_media(color_scheme=color_scheme)
    path = screen.path
    if screen.visitor != "anonymous":
        account: Account = request.getfixturevalue(screen.visitor)
        sign_in(page.context, account)
    if path == "/join":
        api: Api = request.getfixturevalue("api")
        link = api.create_invite(request.getfixturevalue("admin"))
        CODE_REQUESTS.reserve()  # the join screen checks the code
        path = f"/join#{code_from_link(link)}"

    page.goto(path)
    if screen.path == "/join":
        # The form appears once the code has been checked.
        expect(page.get_by_role("button", name=text("auth.join.submit"))).to_be_visible()
    if screen.path == "/me/admin/invites":
        # Also check the created link with its share button.
        page.get_by_test_id(TEST_IDS["createInviteButton"]).click()
    for test_id in screen.ready:
        expect(page.get_by_test_id(test_id)).to_be_visible()

    assert serious_violations(page) == []
