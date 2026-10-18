"""Regelmäßige Artikel: making ingredients recurring on the settings page and from the ingredient's
⋯ menu, the row's value, editing, and the notice when an admin deletes one (LIST-16, D-42, D-51,
UI-07); a due item in a draft's "Fällig" box, bought and no longer due (LIST-16, QA-04)."""

import re
from collections.abc import Callable
from datetime import date, timedelta

from playwright.sync_api import Locator, Page, expect

from support.a11y import serious_violations
from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, ingredient_label, text
from support.ui import choose_from_menu, floating_bar_button, open_settings_page, settings_row


def recurring_dialog(page: Page, name: str) -> Locator:
    dialog = page.get_by_role("dialog", name=name)
    expect(dialog).to_be_visible()
    return dialog


def weeks_field(dialog: Locator) -> Locator:
    return dialog.get_by_role(
        "spinbutton",
        name=f"{text('recurring.dialog.every')} {text('recurring.dialog.weeks')}",
    )


def row_of(page: Page, name: str) -> Locator:
    return (
        page.get_by_test_id(TEST_IDS["recurringList"])
        .get_by_test_id(TEST_IDS["recurringItem"])
        .filter(has_text=name)
    )


def test_recurring_items_from_the_page_and_the_menu_with_a_deletion_notice(
    page: Page, api: Api, admin: Account, invite_user: Callable[..., Account]
) -> None:
    tag = unique("rec")
    anna = invite_user(unique("anna"), unique("Anna"))
    paper = api.create_ingredient(anna, f"Klopapier {tag}")
    paste = api.create_ingredient(anna, f"Zahnpasta {tag}", brand="Elmex")
    paste_name = f"{paste['name']} (Elmex)"
    sign_in(page.context, anna)
    page.goto("/me")

    # Nothing recurring yet: the row has no value, the page shows the hint (nothing is seeded).
    expect(settings_row(page, "recurring.title")).to_have_accessible_name(text("recurring.title"))
    screen = open_settings_page(page, "recurring.title", "screenRecurring")
    expect(screen.get_by_text(text("recurring.empty"))).to_be_visible()
    assert serious_violations(page) == []

    # From the page: search, pick, add with the defaults.
    field = screen.get_by_test_id(TEST_IDS["recurringInput"])
    field.fill(paper["name"])
    expect(screen.get_by_test_id(TEST_IDS["recurringNewIngredient"])).to_have_text(
        text("recurring.field.newIngredient", name=paper["name"])
    )
    screen.get_by_role("button", name=re.compile(f"^{re.escape(paper['name'])}")).click()
    dialog = recurring_dialog(page, paper["name"])
    expect(weeks_field(dialog)).to_have_value("4")
    dialog.get_by_role("button", name=text("recurring.dialog.add"), exact=True).click()
    expect(dialog).to_be_hidden()
    expect(field).to_have_value("")
    expect(row_of(page, paper["name"])).to_contain_text(
        f"{text('recurring.interval.weeksAuto_other', count='4')} · "
    )
    expect(row_of(page, paper["name"])).to_contain_text(text("recurring.due.in_other", count="28"))

    # From the ingredient's ⋯ menu, last bought five weeks ago: due.
    page.goto(f"/ingredients/{paste['id']}")
    expect(page.get_by_role("heading", level=1, name=paste_name)).to_be_visible()
    choose_from_menu(page, "buyRegularly")
    dialog = recurring_dialog(page, paste_name)
    dialog.get_by_label(text("recurring.dialog.lastBought"), exact=True).fill(
        (date.today() - timedelta(weeks=5)).isoformat()
    )
    dialog.get_by_role("button", name=text("recurring.dialog.add"), exact=True).click()
    expect(dialog).to_be_hidden()

    # The row counts the due one.
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    due = text("recurring.dueCount_one", count="1")
    expect(settings_row(page, "recurring.title")).to_have_accessible_name(
        f"{text('recurring.title')} {due}"
    )

    # Edit: a new interval is set by hand, so "Adjust automatically" goes off.
    settings_row(page, "recurring.title").click()
    row_of(page, paper["name"]).click()
    dialog = recurring_dialog(page, paper["name"])
    weeks_field(dialog).fill("2")
    expect(
        dialog.get_by_role("switch", name=text("recurring.dialog.automatic"))
    ).not_to_be_checked()
    dialog.get_by_role("button", name=text("common.save"), exact=True).click()
    expect(dialog).to_be_hidden()
    expect(row_of(page, paper["name"])).to_contain_text(
        f"{text('recurring.interval.weeks_other', count='2')} · "
    )
    # The due one comes first, as the server sorts.
    expect(page.get_by_test_id(TEST_IDS["recurringItem"]).first).to_contain_text(paste_name)
    assert serious_violations(page) == []

    # An admin deletes the recurring Zahnpasta: Anna gets a notice, counted on the gear.
    api.call("DELETE", f"/api/admin/ingredients/{paste['id']}", token=api.token(admin))
    page.reload()
    gear = page.get_by_test_id(TEST_IDS["tabMe"])
    expect(gear).to_have_accessible_name(text("nav.meCount_one", count="1"))
    notice = text("recurring.noticeDeleted", name=paste_name)
    screen = page.get_by_test_id(TEST_IDS["screenRecurring"])
    notices = screen.get_by_test_id(TEST_IDS["recurringNotices"])
    expect(notices).to_contain_text(notice)
    expect(row_of(page, paste_name)).to_have_count(0)
    assert serious_violations(page) == []

    gear.click()
    expect(settings_row(page, "recurring.title")).to_have_accessible_name(
        f"{text('recurring.title')} {text('recurring.noticeCount_one', count='1')}"
    )
    settings_row(page, "recurring.title").click()
    notices.get_by_role("button", name=text("recurring.dismissNotice", name=paste_name)).click()
    expect(notices).to_be_hidden()
    expect(gear).to_have_accessible_name(text("nav.me"))
    expect(row_of(page, paper["name"])).to_be_visible()


def due_box(page: Page) -> Locator:
    return page.get_by_test_id(TEST_IDS["dueBox"])


def test_a_due_item_is_suggested_on_a_draft_added_bought_and_then_no_longer_due(
    page: Page, api: Api, invite_user: Callable[..., Account]
) -> None:
    tag = unique("due")
    anna = invite_user(unique("anna"), unique("Anna"))
    paper = api.create_ingredient(anna, f"Klopapier {tag}", base_unit="piece")
    name = ingredient_label(paper["name"])
    # Last bought five weeks ago, every four weeks: due for a week.
    bought = date.today() - timedelta(weeks=5)
    api.call(
        "POST",
        "/api/recurring-items",
        token=api.token(anna),
        json={
            "ingredient_id": paper["id"],
            "interval_weeks": 4,
            "last_purchased_on": bought.isoformat(),
        },
    )
    draft = api.create_list(anna, f"Einkauf {tag}")
    sign_in(page.context, anna)
    page.goto(f"/lists/{draft['id']}")

    # The draft's "Due" box, below the item field, with the row's due line (LIST-16).
    box = due_box(page)
    expect(box).to_be_visible()
    expect(box.get_by_role("heading", name=text("lists.due.title"))).to_be_visible()
    row = box.get_by_test_id(TEST_IDS["dueItem"]).filter(has_text=name)
    last = (
        bought.strftime("%d/%m")
        if bought.year == date.today().year
        else bought.strftime("%d/%m/%Y")
    )
    expect(row).to_contain_text(
        f"{text('recurring.due.since_other', count='7')} · "
        f"{text('recurring.lastBought', date=last)}"
    )
    expect(row.get_by_role("button", name=text("lists.due.hide", name=name))).to_be_enabled()
    assert serious_violations(page) == []

    # The plus opens the item field's amount pop-up; nothing bought yet, so no amount is filled in.
    row.get_by_role("button", name=text("lists.due.add", name=name)).click()
    dialog = page.get_by_test_id(TEST_IDS["amountDialog"])
    expect(dialog).to_have_accessible_name(name)
    amount = dialog.get_by_label(text("lists.extra.amount"), exact=True)
    expect(amount).to_have_value("")
    amount.fill("12")
    dialog.get_by_role("button", name=text("lists.addField.add"), exact=True).click()
    expect(dialog).to_be_hidden()
    # On the list now, so it leaves the box, and the box with it.
    expect(box).to_have_count(0)
    lines = page.get_by_test_id(TEST_IDS["listLines"]).get_by_test_id(TEST_IDS["listLine"])
    expect(lines.filter(has_text=name)).to_contain_text("12 pcs")

    # Shopping: no box; check it off, the last line, which offers to finish (SHOP-04).
    floating_bar_button(page, "startShopping").click()
    page.get_by_role("checkbox", name=text("lists.shop.check", name=name)).click()
    finish = page.get_by_role("dialog", name=text("lists.shop.finishTitle"))
    expect(finish).to_be_visible()
    expect(due_box(page)).to_have_count(0)
    finish.get_by_role("button", name=text("lists.shop.finishConfirm"), exact=True).click()
    expect(page.get_by_test_id(TEST_IDS["listDone"])).to_be_visible()
    expect(due_box(page)).to_have_count(0)

    # Bought today: a new draft suggests nothing.
    page.goto("/lists")
    page.get_by_test_id(TEST_IDS["newList"]).click()
    expect(page).not_to_have_url(re.compile(f"/lists/{draft['id']}$"))
    expect(page.get_by_test_id(TEST_IDS["extraItemInput"])).to_be_visible()
    expect(floating_bar_button(page, "startShopping")).to_be_visible()
    expect(due_box(page)).to_have_count(0)
