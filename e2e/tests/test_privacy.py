"""No request leaves the app's origin (SEC-08)."""

import re
from urllib.parse import urlsplit

from playwright.sync_api import Page, Request, expect

from support.api import CODE_REQUESTS, Account, Api, unique
from support.frontend import TEST_IDS, text
from support.ui import log_in, log_out

LOCAL_SCHEMES = frozenset({"data", "blob"})


def test_no_request_leaves_the_origin(page: Page, base_url: str, api: Api, admin: Account) -> None:
    """Every screen so far: join, the four tabs, Me, login and the admin screens."""
    origin = urlsplit(base_url)
    requested: list[str] = []

    def record(request: Request) -> None:
        requested.append(request.url)

    # Context-wide, so requests of the service worker count as well.
    page.context.on("request", record)

    link = api.create_invite(admin)
    CODE_REQUESTS.reserve(2)  # code check and join
    page.goto(link)
    join = page.get_by_test_id(TEST_IDS["screenJoin"])
    join.get_by_label(text("auth.field.username"), exact=True).fill(unique("privacy"))
    join.get_by_label(text("auth.field.displayName"), exact=True).fill(unique("Privacy"))
    join.get_by_label(text("auth.field.password"), exact=True).fill(unique("privacy-password"))
    join.get_by_role("button", name=text("auth.join.submit")).click()
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()

    for tab, screen in [
        (TEST_IDS["tabMeals"], TEST_IDS["screenMeals"]),
        (TEST_IDS["tabIngredients"], TEST_IDS["screenIngredients"]),
        (TEST_IDS["tabMe"], TEST_IDS["screenMe"]),
        (TEST_IDS["tabLists"], TEST_IDS["screenLists"]),
    ]:
        page.get_by_test_id(tab).click()
        expect(page.get_by_test_id(screen)).to_be_visible()
    page.goto("/me")
    expect(page.get_by_test_id(TEST_IDS["appVersion"])).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["sessionList"])).to_be_visible()
    page.get_by_test_id(TEST_IDS["languageSelect"]).select_option("de")
    page.reload()
    expect(page.get_by_test_id(TEST_IDS["appVersion"])).to_be_visible()

    log_out(page)
    log_in(page, admin, language="de")
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    admin_links = page.get_by_test_id(TEST_IDS["adminEntry"])
    admin_links.get_by_role("link", name=text("admin.users.title")).click()
    expect(page.get_by_test_id(TEST_IDS["adminUserList"])).to_be_visible()
    page.get_by_role("link", name=text("admin.invites.title")).click()
    page.get_by_test_id(TEST_IDS["createInviteButton"]).click()
    expect(page.get_by_test_id(TEST_IDS["shareLinkUrl"])).to_be_visible()
    page.get_by_role("link", name=text("admin.events.title")).click()
    expect(page.get_by_test_id(TEST_IDS["eventList"])).to_be_visible()
    expect(page).to_have_url(re.compile(r"/me/admin/events$"))

    assert requested
    foreign = [
        url
        for url in requested
        if (parts := urlsplit(url)).scheme not in LOCAL_SCHEMES
        and (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc)
    ]
    assert foreign == []
