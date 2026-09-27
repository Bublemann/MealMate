"""Accounts: registration with an invite link and a session that lasts (QA-04 journeys 1 and 2)."""

import re

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from support.api import CODE_REQUESTS, Account, Api, unique
from support.frontend import TEST_IDS, text
from support.ui import log_in, log_out

REFRESH_COOKIE = "mm_refresh"


def refresh_cookies(context: BrowserContext) -> list[dict]:
    return [cookie for cookie in context.cookies() if cookie["name"] == REFRESH_COOKIE]


def test_register_with_invite_link(page: Page, api: Api, admin: Account) -> None:
    """Journey 1 (ACC-01, ACC-04, ACC-05): the link's code is in the fragment, used once."""
    link = api.create_invite(admin)
    username = unique("anna")
    display_name = unique("Anna")
    CODE_REQUESTS.reserve(2)  # the screen checks the code, then joins with it

    page.goto(link)

    screen = page.get_by_test_id(TEST_IDS["screenJoin"])
    expect(screen).to_be_visible()
    # The code leaves the address bar right away, so it stays out of the history.
    expect(page).to_have_url(re.compile(r"/join$"))
    username_field = screen.get_by_label(text("auth.field.username"), exact=True)
    username_field.fill(username.capitalize())
    expect(username_field).to_have_value(username)  # usernames are lower case
    screen.get_by_label(text("auth.field.displayName"), exact=True).fill(display_name)
    screen.get_by_label(text("auth.field.password"), exact=True).fill(f"{username}-secret-7")
    screen.get_by_role("button", name=text("auth.join.submit")).click()

    expect(page).to_have_url(re.compile(r"/lists$"))
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    expect(page.get_by_test_id(TEST_IDS["displayNameInput"])).to_have_value(display_name)
    expect(page.get_by_test_id(TEST_IDS["screenMe"])).to_contain_text(username)

    # Opening a link while signed in asks to log out first; after that the link is used up.
    CODE_REQUESTS.reserve()
    page.goto(link)
    screen = page.get_by_test_id(TEST_IDS["screenJoin"])
    expect(screen.get_by_role("status")).to_have_text(text("auth.link.signedIn", name=display_name))
    screen.get_by_role("button", name=text("me.logout")).click()
    expect(page.get_by_test_id(TEST_IDS["linkInvalid"])).to_be_visible()


@pytest.mark.parametrize("path", ["/", "/lists", "/meals", "/me", "/me/admin/users"])
def test_signed_out_visitors_are_sent_to_login(page: Page, path: str) -> None:
    page.goto(path)

    expect(page).to_have_url(re.compile(r"/login$"))
    expect(page.get_by_test_id(TEST_IDS["screenLogin"])).to_be_visible()
    expect(page.get_by_role("navigation")).to_have_count(0)


def test_login_survives_reload_until_logout(
    page: Page, context: BrowserContext, member: Account
) -> None:
    """Journey 2 (ACC-08, ACC-09): the refresh cookie keeps the session; logout ends it."""
    page.goto("/me")
    log_in(page, member)

    # Back where the visitor wanted to go.
    expect(page).to_have_url(re.compile(r"/me$"))
    expect(page.get_by_test_id(TEST_IDS["screenMe"])).to_be_visible()
    [cookie] = refresh_cookies(context)
    assert cookie["httpOnly"]
    assert cookie["sameSite"] == "Strict"
    assert cookie["path"] == "/api/auth"

    # The access token lives in memory only; the cookie brings the session back.
    page.reload()
    expect(page.get_by_test_id(TEST_IDS["screenMe"])).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["displayNameInput"])).to_have_value(member.display_name)

    log_out(page)
    expect(page.get_by_test_id(TEST_IDS["loginReason"])).to_have_text(
        text("auth.login.reason.loggedOut")
    )
    assert refresh_cookies(context) == []

    page.reload()
    expect(page.get_by_test_id(TEST_IDS["screenLogin"])).to_be_visible()
    page.goto("/lists")
    expect(page).to_have_url(re.compile(r"/login$"))


def test_wrong_password_is_refused(page: Page, member: Account) -> None:
    page.goto("/login")
    log_in(page, Account(member.id, member.username, member.display_name, "not-the-password"))

    expect(page.get_by_role("alert")).to_have_text(text("error.auth.invalid_credentials"))
    expect(page).to_have_url(re.compile(r"/login$"))
