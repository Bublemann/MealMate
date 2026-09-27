"""Test setup through the app's own API: accounts, couples, ingredients, meals, lists (plan § 9).

The journeys drive the UI; everything they merely need to exist (an admin, invited users, a couple)
is created here over HTTP, which is faster and keeps each test about one thing.
"""

import secrets
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import BrowserContext

# The refresh endpoint's CSRF guard; the web app sends it on every request.
CLIENT_HEADER = {"X-MealMate-Client": "web"}


@dataclass(frozen=True)
class Account:
    id: str
    username: str
    display_name: str
    password: str


def unique(prefix: str) -> str:
    """`prefix` plus a random suffix: all tests of a run share one database."""
    return f"{prefix}-{secrets.token_hex(3)}"


def new_password() -> str:
    """A random password that passes the rules (ACC-06); nothing secret is committed."""
    return f"e2e-{secrets.token_urlsafe(12)}"


def new_barcode() -> str:
    """A random EAN-13 with a valid check digit; prefix 20 is for in-store numbers (GS1)."""
    body = "20" + "".join(str(secrets.randbelow(10)) for _ in range(10))
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(body))
    return body + str((10 - total % 10) % 10)


def code_from_link(url: str) -> str:
    """The code of an invite or reset link (`…/join#<code>`)."""
    code = urlsplit(url).fragment
    if not code:
        raise ValueError(f"no code in the link {url!r}")
    return code


class CodeRequestBudget:
    """Keeps the suite under the app's limit for code endpoints (plan § 5.4).

    /api/auth/join, /api/auth/reset and /api/auth/codes/check allow 10 requests per minute and
    client IP, and every request of the suite comes from the same IP. `reserve(n)` blocks until n
    more requests fit into the sliding window, then counts them. The window is counted from before
    each request, so a second of margin covers the time until the request reaches the app.
    """

    LIMIT = 10
    WINDOW_SECONDS = 60.0
    MARGIN_SECONDS = 1.0

    def __init__(self) -> None:
        self._sent: deque[float] = deque()

    def reserve(self, count: int = 1) -> None:
        if count > self.LIMIT:
            raise ValueError(f"at most {self.LIMIT} code requests fit into one window")
        window = self.WINDOW_SECONDS + self.MARGIN_SECONDS
        while True:
            now = time.monotonic()
            while self._sent and now - self._sent[0] >= window:
                self._sent.popleft()
            if len(self._sent) + count <= self.LIMIT:
                break
            time.sleep(window - (now - self._sent[0]))
        self._sent.extend([time.monotonic()] * count)


CODE_REQUESTS = CodeRequestBudget()


class ApiError(AssertionError):
    """An unexpected answer of the app during test setup."""


class Api:
    """A plain HTTP client for the app; each call names the account's access token it uses."""

    def __init__(self, base_url: str) -> None:
        # trust_env=False: never send loopback requests through a proxy from the environment.
        self._client = httpx.Client(base_url=base_url, timeout=20.0, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def request(
        self, method: str, path: str, *, token: str | None = None, json: Any = None
    ) -> httpx.Response:
        headers = dict(CLIENT_HEADER)
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return self._client.request(method, path, headers=headers, json=json)
        finally:
            # No refresh cookies pile up here; browsers get their own through sign_in().
            self._client.cookies.clear()

    def call(self, method: str, path: str, *, token: str | None = None, json: Any = None) -> Any:
        """Like request(), but expects a 2xx answer and returns its JSON body (None for 204)."""
        response = self.request(method, path, token=token, json=json)
        if not response.is_success:
            raise ApiError(f"{method} {path}: {response.status_code} {response.text}")
        return None if response.status_code == 204 else response.json()

    def login(self, username: str, password: str) -> dict[str, Any]:
        """POST /api/auth/login; the LoginResponse ({access_token, expires_in, user})."""
        return self.call(
            "POST", "/api/auth/login", json={"username": username, "password": password}
        )

    def token(self, account: Account) -> str:
        """A fresh access token of `account` (valid for 15 minutes)."""
        return self.login(account.username, account.password)["access_token"]

    def create_invite(self, admin: Account) -> str:
        """An open invite link (`<PUBLIC_URL>/join#<code>`), created by `admin`."""
        created = self.call("POST", "/api/admin/invites", token=self.token(admin), json={})
        return created["url"]

    def join(
        self, invite_url: str, *, username: str, display_name: str, language: str = "en"
    ) -> Account:
        """Registers with the invite link's code, waiting out the rate limit if needed."""
        password = new_password()
        body = {
            "code": code_from_link(invite_url),
            "username": username,
            "display_name": display_name,
            "password": password,
            "language": language,
        }
        while True:
            CODE_REQUESTS.reserve()
            response = self.request("POST", "/api/auth/join", json=body)
            # Someone else (E2E_BASE_URL mode) may share the limit: wait as the app asks.
            if response.status_code != 429:
                break
            time.sleep(int(response.headers.get("Retry-After", "5")))
        if response.status_code != 201:
            raise ApiError(f"POST /api/auth/join: {response.status_code} {response.text}")
        user = response.json()["user"]
        return Account(
            id=user["id"], username=username, display_name=display_name, password=password
        )

    def invite_user(
        self, admin: Account, *, username: str, display_name: str, language: str = "en"
    ) -> Account:
        """`admin` creates an invite and a new user joins with it."""
        return self.join(
            self.create_invite(admin),
            username=username,
            display_name=display_name,
            language=language,
        )

    def make_couple(self, a: Account, b: Account) -> None:
        """`a` sends a couple request to `b`, and `b` accepts it."""
        state = self.call(
            "POST", "/api/couple/requests", token=self.token(a), json={"user_id": b.id}
        )
        request_id = state["outgoing"]["id"]
        accepted = self.call(
            "POST", f"/api/couple/requests/{request_id}/accept", token=self.token(b)
        )
        if (accepted["partner"] or {}).get("id") != a.id:
            raise ApiError(f"{b.username} is not a couple with {a.username}: {accepted}")

    def categories(self, account: Account) -> list[dict[str, Any]]:
        """GET /api/categories: every category in its walking order."""
        return self.call("GET", "/api/categories", token=self.token(account))

    def order_categories(self, admin: Account, category_ids: list[str]) -> None:
        """PUT /api/admin/categories/order."""
        self.call(
            "PUT",
            "/api/admin/categories/order",
            token=self.token(admin),
            json={"category_ids": category_ids},
        )

    def create_ingredient(
        self, account: Account, name: str, *, category_key: str = "other", **fields: Any
    ) -> dict[str, Any]:
        """POST /api/ingredients in the category `category_key`; the created Ingredient."""
        token = self.token(account)
        categories = self.call("GET", "/api/categories", token=token)
        [category_id] = [c["id"] for c in categories if c["key"] == category_key]
        body = {"name": name, "category_id": category_id, **fields}
        return self.call("POST", "/api/ingredients", token=token, json=body)

    def create_product(self, account: Account, ingredient_id: str, **fields: Any) -> dict[str, Any]:
        """POST /api/products with a new barcode; the created Product."""
        body = {"barcode": new_barcode(), "ingredient_id": ingredient_id, **fields}
        return self.call("POST", "/api/products", token=self.token(account), json=body)

    def update_me(self, account: Account, **fields: Any) -> dict[str, Any]:
        """PATCH /api/me, e.g. `meals_public=False`; the updated Me."""
        return self.call("PATCH", "/api/me", token=self.token(account), json=fields)

    def create_meal(self, account: Account, name: str, **fields: Any) -> dict[str, Any]:
        """POST /api/meals owned by `account`, e.g. with `ingredients=[{...}]`; the created Meal."""
        body = {"name": name, **fields}
        return self.call("POST", "/api/meals", token=self.token(account), json=body)

    def upload_meal_photo(
        self, account: Account, meal_id: str, image: bytes, *, content_type: str = "image/png"
    ) -> dict[str, Any]:
        """PUT /api/meals/{id}/photo as multipart field `file`; the updated Meal."""
        headers = {**CLIENT_HEADER, "Authorization": f"Bearer {self.token(account)}"}
        try:
            response = self._client.put(
                f"/api/meals/{meal_id}/photo",
                headers=headers,
                files={"file": ("photo.png", image, content_type)},
            )
        finally:
            self._client.cookies.clear()
        if not response.is_success:
            raise ApiError(
                f"PUT /api/meals/{meal_id}/photo: {response.status_code} {response.text}"
            )
        return response.json()

    def create_list(self, account: Account, name: str | None = None) -> dict[str, Any]:
        """POST /api/lists: a new draft of `account` (shared with a partner, CPL-02); ListDetail."""
        body = {} if name is None else {"name": name}
        return self.call("POST", "/api/lists", token=self.token(account), json=body)

    def get_list(self, account: Account, list_id: str) -> dict[str, Any]:
        """GET /api/lists/{id} as `account` sees it (ListDetail)."""
        return self.call("GET", f"/api/lists/{list_id}", token=self.token(account))

    def add_list_meal(
        self, account: Account, list_id: str, meal_id: str, *, servings: int | None = None
    ) -> dict[str, Any]:
        """POST /api/lists/{id}/meals (default servings: the meal's own); the ListDetail."""
        body: dict[str, Any] = {"meal_id": meal_id}
        if servings is not None:
            body["servings"] = servings
        return self.call(
            "POST", f"/api/lists/{list_id}/meals", token=self.token(account), json=body
        )

    def add_extra_item(self, account: Account, list_id: str, **fields: Any) -> dict[str, Any]:
        """POST /api/lists/{id}/extra-items, e.g. `ingredient_id=…, amount=450, unit="g"` or
        `text="Kerzen"`; the ListDetail."""
        return self.call(
            "POST", f"/api/lists/{list_id}/extra-items", token=self.token(account), json=fields
        )

    def hide_line(self, account: Account, list_id: str, line_key: str) -> dict[str, Any]:
        """POST /api/lists/{id}/lines/{key}/hide (LIST-07); the ListDetail."""
        return self.call(
            "POST", f"/api/lists/{list_id}/lines/{line_key}/hide", token=self.token(account)
        )


def sign_in(context: BrowserContext, account: Account) -> None:
    """Logs `account` in for every page of `context`: the refresh cookie lands in its jar.

    The app starts with a refresh from that cookie, as after a reload of a signed-in tab.
    """
    response = context.request.post(
        "/api/auth/login", data={"username": account.username, "password": account.password}
    )
    if not response.ok:
        raise ApiError(f"POST /api/auth/login: {response.status} {response.text()}")
