"""No request leaves the app's origin (SEC-08)."""

from urllib.parse import urlsplit

from playwright.sync_api import Page, Request, expect

from support.frontend import TEST_IDS

LOCAL_SCHEMES = frozenset({"data", "blob"})


def test_no_request_leaves_the_origin(page: Page, base_url: str) -> None:
    origin = urlsplit(base_url)
    requested: list[str] = []

    def record(request: Request) -> None:
        requested.append(request.url)

    # Context-wide, so requests of the service worker count as well.
    page.context.on("request", record)

    page.goto("/")
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
    page.get_by_test_id(TEST_IDS["languageSelect"]).select_option("de")
    page.reload()
    expect(page.get_by_test_id(TEST_IDS["appVersion"])).to_be_visible()

    assert requested
    foreign = [
        url
        for url in requested
        if (parts := urlsplit(url)).scheme not in LOCAL_SCHEMES
        and (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc)
    ]
    assert foreign == []
