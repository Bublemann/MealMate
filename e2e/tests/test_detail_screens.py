"""Detail screens: the strip pinned at the top with the back link to the parent (UI-01, D-46)."""

import re
from collections.abc import Callable

from playwright.sync_api import BrowserContext, Locator, Page, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text
from support.ui import open_more_menu

# The largest iPhone text size (53 px body text, simulated as in test_ingredients.py): the
# content grows, so every screen scrolls, while the strip stops growing (D-29).
LARGEST_TEXT = "html { font-size: 53px !important; }"


def leave_after_scrolling(page: Page, loaded: Locator, parent: str, url: str, screen: str) -> None:
    """Scrolls to the end of the screen once `loaded` shows, where the strip still offers the
    back link, and leaves through it."""
    page.add_style_tag(content=LARGEST_TEXT)
    back = page.get_by_test_id(TEST_IDS["backLink"])
    expect(back).to_have_accessible_name(parent)
    expect(loaded).to_be_visible()
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert page.evaluate("window.scrollY") > 0, "the screen should be long enough to scroll"

    viewport = page.viewport_size
    assert viewport is not None
    expect(back).to_be_in_viewport()
    strip = page.get_by_test_id(TEST_IDS["detailStrip"]).bounding_box()
    assert strip is not None
    # Stuck at the top, and slim: most of the screen stays for the content.
    assert abs(strip["y"]) < 1
    assert strip["height"] < viewport["height"] * 0.2

    back.click()
    expect(page).to_have_url(re.compile(f"{re.escape(url)}$"))
    expect(page.get_by_test_id(TEST_IDS[screen])).to_be_visible()


def test_back_link_leaves_a_list_a_meal_and_an_admin_page_after_scrolling(
    page: Page,
    api: Api,
    admin: Account,
    invite_user: Callable[..., Account],
    new_context: Callable[..., BrowserContext],
) -> None:
    tag = unique("strip")
    anna = invite_user(unique("anna"), unique("Anna"))
    flour = api.create_ingredient(anna, f"Mehl {tag}", category_key="baking")
    meal = api.create_meal(
        anna,
        f"Brot {tag}",
        servings=4,
        ingredients=[{"ingredient_id": flour["id"], "amount": 500, "unit": "g"}],
        instructions="\n".join(f"Schritt {step}." for step in range(1, 13)),
    )
    shopping_list = api.create_list(anna, f"Wochenende {tag}")
    api.add_list_meal(anna, shopping_list["id"], meal["id"])
    for item in ("Kerzen", "Servietten", "Eiswürfel", "Grillkohle"):
        api.add_extra_item(anna, shopping_list["id"], text=f"{item} {tag}")
    sign_in(page.context, anna)

    # Opened from a link, so going back in the history would leave the app (D-46).
    page.goto(f"/lists/{shopping_list['id']}")
    last_item = page.get_by_text(f"Grillkohle {tag}", exact=True).first
    leave_after_scrolling(page, last_item, text("lists.detail.back"), "/lists", "screenLists")

    page.goto(f"/meals/{meal['id']}")
    instructions = page.get_by_test_id(TEST_IDS["mealInstructions"])
    leave_after_scrolling(page, instructions, text("meals.detail.back"), "/meals", "screenMeals")

    admin_page = new_context().new_page()
    sign_in(admin_page.context, admin)
    admin_page.goto("/me/admin/categories")
    categories = admin_page.get_by_test_id(TEST_IDS["adminCategoryList"])
    leave_after_scrolling(admin_page, categories, text("nav.me"), "/me", "screenMe")


def test_long_name_is_cut_on_one_line(page: Page, api: Api, member: Account) -> None:
    """D-46: the meal form's back link names the meal; a name too long for the strip is cut
    with "…" and read in full, and the strip keeps its height."""
    # Names have up to 80 characters; this one is 77.
    name = unique("Omas sonntägliche Lasagne mit drei Sorten Käse und frischem Basilikum")
    meal = api.create_meal(member, name, servings=4)
    sign_in(page.context, member)

    # The meal's own screen, whose back link "All meals" fits, sets the strip's height.
    page.goto(f"/meals/{meal['id']}")
    expect(page.get_by_role("heading", level=1, name=name)).to_be_visible()
    one_line = strip_height(page)

    page.goto(f"/meals/{meal['id']}/edit")
    back = page.get_by_test_id(TEST_IDS["backLink"])
    expect(back).to_have_accessible_name(name)
    expect(back).to_have_attribute("href", f"/meals/{meal['id']}")
    assert strip_height(page) == one_line
    viewport = page.viewport_size
    assert viewport is not None
    link = back.bounding_box()
    assert link is not None
    assert link["x"] + link["width"] <= viewport["width"]
    # The whole name, laid out on one line, is wider than the link shows: it is cut.
    assert back.evaluate(
        """link => {
            const text = document.createRange();
            text.selectNodeContents(link);
            return text.getBoundingClientRect().width > link.getBoundingClientRect().width;
        }"""
    )


def strip_height(page: Page) -> float:
    strip = page.get_by_test_id(TEST_IDS["detailStrip"])
    expect(strip).to_be_visible()
    box = strip.bounding_box()
    assert box is not None
    return box["height"]


def test_menu_fits_the_screen_at_the_largest_text_size(
    page: Page, api: Api, member: Account
) -> None:
    """D-39, UI-01: at the largest text size the ⋯ menu's items wrap within the screen's width
    and the menu scrolls within its height; the floating bar stays above the tab bar."""
    draft = api.create_list(member, f"Wochenende {unique('menu')}")
    sign_in(page.context, member)
    page.goto(f"/lists/{draft['id']}")
    bar = page.get_by_test_id(TEST_IDS["floatingBar"])
    expect(bar).to_be_visible()
    page.add_style_tag(content=LARGEST_TEXT)

    menu = open_more_menu(page)
    viewport = page.viewport_size
    assert viewport is not None
    box = menu.bounding_box()
    assert box is not None
    # 16 px from the screen's edges, give or take rounding.
    assert box["x"] >= 15
    assert box["x"] + box["width"] <= viewport["width"] - 15
    assert box["y"] + box["height"] <= viewport["height"] - 15
    assert menu.evaluate("menu => menu.scrollWidth <= menu.clientWidth")
    delete = menu.get_by_test_id(TEST_IDS["deleteList"])
    delete.scroll_into_view_if_needed()
    expect(delete).to_be_in_viewport()

    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    bar_box = bar.bounding_box()
    nav_box = page.get_by_role("navigation", name=text("nav.label")).bounding_box()
    assert bar_box is not None
    assert nav_box is not None
    assert bar_box["y"] + bar_box["height"] <= nav_box["y"]


def test_add_fields_fit_the_screen_at_the_largest_text_size(
    page: Page, api: Api, member: Account
) -> None:
    """D-41, UI-01: at the largest text size the list's two add fields, their options and their
    pop-ups stay within the screen's width; nothing makes the page scroll sideways."""
    tag = unique("fields")
    meal = api.create_meal(member, f"Omas sonntägliche Gemüselasagne {tag}", servings=4)
    draft = api.create_list(member, f"Wochenende {tag}")
    sign_in(page.context, member)
    page.goto(f"/lists/{draft['id']}")
    meal_field = page.get_by_test_id(TEST_IDS["mealField"])
    expect(meal_field).to_be_visible()
    page.add_style_tag(content=LARGEST_TEXT)
    viewport = page.viewport_size
    assert viewport is not None

    def fits(locator: Locator) -> None:
        box = locator.bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= viewport["width"] + 0.5
        no_sideways = "document.documentElement.scrollWidth <= window.innerWidth"
        assert page.evaluate(no_sideways), "the page scrolls sideways"

    meal_field.fill(meal["name"])
    create = page.get_by_test_id(TEST_IDS["mealFieldCreate"])
    expect(create).to_be_visible()
    fits(page.get_by_test_id(TEST_IDS["mealFieldPanel"]))
    fits(meal_field)
    page.get_by_role("button", name=text("lists.addField.plus", name=meal["name"])).click()
    servings = page.get_by_test_id(TEST_IDS["servingsDialog"])
    expect(servings).to_be_visible()
    fits(servings)
    page.keyboard.press("Escape")
    expect(servings).to_be_hidden()

    item_field = page.get_by_test_id(TEST_IDS["extraItemInput"])
    item_field.fill(f"Geburtstagskerzen {tag}")
    fits(page.get_by_test_id(TEST_IDS["itemFieldNewIngredient"]))
    item_field.press("Enter")
    free_text = page.get_by_test_id(TEST_IDS["freeTextDialog"])
    expect(free_text).to_be_visible()
    fits(free_text)
