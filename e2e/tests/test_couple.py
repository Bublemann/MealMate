"""Couples: request, accept and end (CPL-01, CPL-05, CPL-07; part of QA-04 journey 11)."""

from collections.abc import Callable

from playwright.sync_api import BrowserContext, Page, expect

from support.api import Account, sign_in, unique
from support.frontend import TEST_IDS, text


def open_me(context: BrowserContext, account: Account) -> Page:
    sign_in(context, account)
    page = context.new_page()
    page.goto("/me")
    expect(page.get_by_test_id(TEST_IDS["coupleSection"])).to_be_visible()
    return page


def test_couple_request_and_accept(
    context: BrowserContext,
    new_context: Callable[..., BrowserContext],
    invite_user: Callable[..., Account],
) -> None:
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))

    anna_page = open_me(context, anna)
    couple = anna_page.get_by_test_id(TEST_IDS["coupleSection"])
    couple.get_by_test_id(TEST_IDS["couplePicker"]).select_option(label=ben.display_name)
    couple.get_by_role("button", name=text("couple.send")).click()
    expect(couple).to_contain_text(text("couple.outgoing", name=ben.display_name))

    # Ben, on his own device.
    ben_page = open_me(new_context(), ben)
    ben_couple = ben_page.get_by_test_id(TEST_IDS["coupleSection"])
    ben_couple.get_by_role(
        "button", name=text("couple.acceptLabel", name=anna.display_name)
    ).click()
    expect(ben_couple.get_by_test_id(TEST_IDS["couplePartner"])).to_contain_text(anna.display_name)

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

    ben_page = open_me(new_context(), ben)
    expect(ben_page.get_by_test_id(TEST_IDS["couplePartner"])).to_contain_text(anna.display_name)

    anna_page = open_me(context, anna)
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
