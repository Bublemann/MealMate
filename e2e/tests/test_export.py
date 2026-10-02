"""Export a list as text through the share sheet (QA-04 journey 8, EXP-01/02, LIST-14).

`navigator.share` is replaced by an init script that records the shared text, so the test sees
exactly what the share sheet would get. All tests of a run share one database, so names get a
unique tag, and the category order is read from the app.
"""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Page, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text

# Records what the app shares instead of opening a share sheet.
RECORD_SHARE = """
Object.defineProperty(navigator, 'share', {
  configurable: true,
  value: (data) => {
    window.__mealmateShared = data.text;
    return Promise.resolve();
  },
});
"""
# The browsers of the suite run in this time zone (conftest.py).
TIME_ZONE = ZoneInfo("Europe/Berlin")
DATE_FORMATS = {"en": "%d/%m/%Y", "de": "%d.%m.%Y"}
DECIMAL_SEPARATORS = {"en": ".", "de": ","}


@pytest.mark.parametrize("language", ["en", "de"])
def test_export_list_as_text(
    page: Page, api: Api, invite_user: Callable[..., Account], language: str
) -> None:
    """Name and date, meals with servings, lines by category (removed ones left out), reminder."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"), language=language)
    onions = api.create_ingredient(
        anna, f"Zwiebeln {tag}", category_key="fruit_vegetables", piece_weight_g=80
    )
    flour = api.create_ingredient(anna, f"Mehl {tag}", category_key="baking")
    salt = api.create_ingredient(anna, f"Salz {tag}", category_key="sauces_spices_oils")
    tart = api.create_meal(
        anna,
        f"Zwiebelkuchen {tag}",
        servings=2,
        ingredients=[
            {"ingredient_id": onions["id"], "amount": 1, "unit": "piece"},
            {"ingredient_id": flour["id"], "amount": 200, "unit": "g"},
            {"ingredient_id": salt["id"], "note": "to taste"},
        ],
    )
    draft = api.create_list(anna, f"Export {tag}")
    api.add_list_meal(anna, draft["id"], tart["id"], servings=4)
    api.add_extra_item(anna, draft["id"], ingredient_id=flour["id"], amount=1.1, unit="kg")
    candles = f"Kerzen {tag}"
    api.add_extra_item(anna, draft["id"], text=candles, amount_text="2 Packungen")
    pepper = f"Pfeffer {tag}"
    detail = api.add_extra_item(anna, draft["id"], text=pepper)
    [pepper_key] = [line["key"] for line in detail["lines"] if line["name"] == pepper]
    detail = api.hide_line(anna, draft["id"], pepper_key)

    page.add_init_script(RECORD_SHARE)
    sign_in(page.context, anna)
    page.goto(f"/lists/{draft['id']}")
    expect(page.get_by_test_id(TEST_IDS["listLines"])).to_be_visible()
    export = page.get_by_test_id(TEST_IDS["exportList"])
    expect(export).to_have_text(text("lists.detail.export", language))
    export.click()
    page.wait_for_function("() => window.__mealmateShared !== undefined")
    shared = page.evaluate("() => window.__mealmateShared")

    # 4 servings of a meal for 2: onions 1 x 2 = 2 pieces, flour 200 g x 2 + 1.1 kg = 1.5 kg,
    # salt without an amount; the candles keep their own amount, the pepper was removed.
    def line(name: str, amount: str | None = None) -> str:
        item = (
            name
            if amount is None
            else text("lists.export.item", language, name=name, amount=amount)
        )
        return text("lists.export.open", language, item=item)

    lines = {
        "fruit_vegetables": [line(onions["name"], f"2 {text('unit.piece', language)}")],
        "baking": [line(flour["name"], f"1{DECIMAL_SEPARATORS[language]}5 kg")],
        "sauces_spices_oils": [line(salt["name"])],
        "other": [line(candles, "2 Packungen")],
    }
    categories = [c for c in api.categories(anna) if c["key"] in lines]
    created = datetime.fromisoformat(detail["created_at"]).astimezone(TIME_ZONE)
    reminder = text(f"reminder.{detail['reminder_seed'] % 10 + 1}", language)
    expected = [
        f"{draft['name']} ({created.strftime(DATE_FORMATS[language])})",
        text("lists.export.meal", language, servings="4", name=tart["name"]),
        *("\n".join([c["names"][language], *lines[c["key"]]]) for c in categories),
        reminder,
    ]
    assert shared == "\n\n".join(expected)
