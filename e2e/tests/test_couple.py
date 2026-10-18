"""Couples: request, accept and end (CPL-01, CPL-05, CPL-07; part of QA-04 journey 11)."""

from collections.abc import Callable

from playwright.sync_api import BrowserContext, Page, expect

from support.api import Account, sign_in, unique
from support.frontend import TEST_IDS, text
from support.ui import settings_row


def open_couple(context: BrowserContext, account: Account) -> Page:
    """Signs in on `context` and opens Settings → Paar."""
    sign_in(context, account)
    page = context.new_page()
    page.goto("/me/couple")
    expect(page.get_by_test_id(TEST_IDS["coupleSection"])).to_be_visible()
    return page


def test_couple_request_and_accept(
    context: BrowserContext,
    new_context: Callable[..., BrowserContext],
    invite_user: Callable[..., Account],
) -> None:
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))

    anna_page = open_couple(context, anna)
    couple = anna_page.get_by_test_id(TEST_IDS["coupleSection"])
    couple.get_by_test_id(TEST_IDS["couplePicker"]).select_option(label=ben.display_name)
    couple.get_by_role("button", name=text("couple.send")).click()
    expect(couple).to_contain_text(text("couple.outgoing", name=ben.display_name))

    # Ben, on his own device: the gear counts the request, and the Paar row names it (D-51).
    ben_context = new_context()
    sign_in(ben_context, ben)
    ben_page = ben_context.new_page()
    ben_page.goto("/me")
    gear = ben_page.get_by_test_id(TEST_IDS["tabMe"])
    expect(gear).to_have_accessible_name(text("nav.meCount_one", count="1"))
    couple_row = settings_row(ben_page, "couple.title")
    expect(couple_row).to_have_accessible_name(
        f"{text('couple.title')} {text('couple.requests_one', count='1')}"
    )
    couple_row.click()
    ben_couple = ben_page.get_by_test_id(TEST_IDS["coupleSection"])
    ben_couple.get_by_role(
        "button", name=text("couple.acceptLabel", name=anna.display_name)
    ).click()
    expect(ben_couple.get_by_test_id(TEST_IDS["couplePartner"])).to_contain_text(anna.display_name)
    # Accepted: neither the count nor the request is left; the row names the partner.
    expect(gear).to_have_accessible_name(text("nav.me"))
    ben_page.get_by_test_id(TEST_IDS["backLink"]).click()
    expect(couple_row).to_have_accessible_name(f"{text('couple.title')} {anna.display_name}")
    expect(gear).to_have_accessible_name(text("nav.me"))

    anna_page.reload()
    expect(couple.get_by_test_id(TEST_IDS["couplePartner"])).to_contain_text(ben.display_name)


def test_ending_the_couple(
    context: BrowserContext,
    new_context: Callable[..., BrowserContext],
    invite_user: Callable[..., Account],
    make_couple: Callable[[Account, Account], None],
) -> None:
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))
    make_couple(anna, ben)

    ben_page = open_couple(new_context(), ben)
    expect(ben_page.get_by_test_id(TEST_IDS["couplePartner"])).to_contain_text(anna.display_name)

    anna_page = open_couple(context, anna)
    couple = anna_page.get_by_test_id(TEST_IDS["coupleSection"])
    expect(couple.get_by_test_id(TEST_IDS["couplePartner"])).to_contain_text(ben.display_name)
    couple.get_by_role("button", name=text("couple.end")).click()
    dialog = anna_page.get_by_role(
        "alertdialog", name=text("couple.endTitle", name=ben.display_name)
    )
    dialog.get_by_role("button", name=text("couple.endConfirm")).click()
    expect(couple.get_by_test_id(TEST_IDS["couplePicker"])).to_be_visible()
    expect(couple.get_by_test_id(TEST_IDS["couplePartner"])).to_have_count(0)

    ben_page.reload()
    ben_couple = ben_page.get_by_test_id(TEST_IDS["coupleSection"])
    expect(ben_couple.get_by_test_id(TEST_IDS["couplePicker"])).to_be_visible()
    expect(ben_couple.get_by_test_id(TEST_IDS["couplePartner"])).to_have_count(0)
