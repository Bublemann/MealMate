"""Administration: a deactivated user is logged out and can't log in (ADM-02, ACC-11)."""

import re
from collections.abc import Callable

from playwright.sync_api import BrowserContext, Page, expect

from support.api import Account, sign_in, unique
from support.frontend import TEST_IDS, text
from support.ui import log_in


def test_deactivated_user_is_logged_out_and_refused(
    page: Page,
    new_context: Callable[..., BrowserContext],
    admin: Account,
    invite_user: Callable[..., Account],
) -> None:
    carl = invite_user(unique("carl"), unique("Carl"))
    sign_in(page.context, carl)
    page.goto("/lists")
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()

    # The admin, on another device.
    admin_context = new_context()
    sign_in(admin_context, admin)
    admin_page = admin_context.new_page()
    admin_page.goto("/me/admin/users")
    users = admin_page.get_by_test_id(TEST_IDS["adminUserList"])
    users.get_by_role(
        "button", name=text("admin.users.deactivateLabel", name=carl.display_name)
    ).click()
    dialog = admin_page.get_by_role(
        "alertdialog", name=text("admin.users.deactivateTitle", name=carl.display_name)
    )
    dialog.get_by_role("button", name=text("admin.users.deactivate")).click()
    expect(
        users.get_by_role(
            "button", name=text("admin.users.reactivateLabel", name=carl.display_name)
        )
    ).to_be_visible()

    # Carl's next request ends his session.
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    expect(page).to_have_url(re.compile(r"/login$"))
    expect(page.get_by_test_id(TEST_IDS["loginReason"])).to_have_text(
        text("auth.login.reason.revoked")
    )

    log_in(page, carl)
    expect(page.get_by_role("alert")).to_have_text(text("error.auth.account_deactivated"))
    expect(page).to_have_url(re.compile(r"/login$"))
