"""Language switch between German and English (I18N-01, I18N-02, QA-04 journey 10)."""

from collections.abc import Callable

from playwright.sync_api import BrowserContext, Page, expect

from support.api import Account, Api, sign_in
from support.frontend import TEST_IDS, translations
from support.ui import log_in, log_out


def expect_language(page: Page, language: str) -> None:
    strings = translations(language)
    expect(page.locator("html")).to_have_attribute("lang", language)
    for key, tab in [
        ("nav.lists", TEST_IDS["tabLists"]),
        ("nav.meals", TEST_IDS["tabMeals"]),
        ("nav.ingredients", TEST_IDS["tabIngredients"]),
        ("nav.me", TEST_IDS["tabMe"]),
    ]:
        expect(page.get_by_test_id(tab)).to_have_text(strings[key])


def switch_language(page: Page, label: str) -> None:
    """Picks `label` in Me and waits until the server has stored it."""
    with page.expect_response(
        lambda response: response.url.endswith("/api/me") and response.request.method == "PATCH"
    ) as saved:
        page.get_by_test_id(TEST_IDS["languageSelect"]).select_option(label=label)
    assert saved.value.ok


def test_language_is_kept_by_the_account(
    page: Page,
    new_context: Callable[..., BrowserContext],
    api: Api,
    invite_user: Callable[..., Account],
) -> None:
    user = invite_user(language="en")
    sign_in(page.context, user)
    page.goto("/me")
    select = page.get_by_test_id(TEST_IDS["languageSelect"])
    expect_language(page, "en")

    switch_language(page, "Deutsch")
    expect_language(page, "de")
    page.reload()
    expect_language(page, "de")
    expect(select).to_have_value("de")

    log_out(page)

    # Another device knows nothing of the choice until the user logs in there.
    other = new_context().new_page()
    other.goto("/login")
    expect(other.locator("html")).to_have_attribute("lang", "en")
    log_in(other, user)
    expect_language(other, "de")
    other.get_by_test_id(TEST_IDS["tabMe"]).click()
    expect(other.get_by_test_id(TEST_IDS["languageSelect"])).to_have_value("de")

    switch_language(other, "English")
    expect_language(other, "en")
    other.reload()
    expect_language(other, "en")
    me = api.call("GET", "/api/me", token=api.token(user))
    assert me["language"] == "en"
