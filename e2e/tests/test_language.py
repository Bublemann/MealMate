"""Language switch between German and English (I18N-02, QA-04 journey 10)."""

from playwright.sync_api import Page, expect

from support.frontend import TEST_IDS, translations


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


def test_language_switch_changes_labels_and_persists(page: Page) -> None:
    page.goto("/me")
    select = page.get_by_test_id(TEST_IDS["languageSelect"])
    expect_language(page, "en")

    select.select_option(label="Deutsch")
    expect_language(page, "de")
    page.reload()
    expect_language(page, "de")
    expect(select).to_have_value("de")

    select.select_option(label="English")
    expect_language(page, "en")
    page.reload()
    expect_language(page, "en")
    expect(select).to_have_value("en")
