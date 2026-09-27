"""PERF-02 gate: response times of a big list while three phones poll it (plan § 9, M5b).

Against a running MealMate, as an existing user:

1. makes sure 150 ingredients `Perf 000` … `Perf 149` exist (created once, then reused: the
   ingredient wiki has no delete for users), spread over the categories;
2. creates 20 meals whose rows cover all of them (two in every meal, so lines merge), a list with
   all 20 meals and a few free-text items, i.e. 150 + N lines, and starts shopping (`--draft`
   keeps it a draft);
3. runs `--rounds` rounds, `--interval` seconds apart: three pollers send `GET /api/lists/{id}`
   with their last `If-None-Match` (304 while nothing changed) plus one cold GET without it
   (200), spread over the interval like independent phones (`--burst`: all at the same moment);
   every `--change-every` rounds a check-off op changes the list first, so the pollers get 200s
   too (not with `--draft`);
4. prints count, p50, p95 and max per kind (200, 304, ops) and deletes the list and the meals
   (`--keep` leaves them).

Exit code 1 if any p95 is above `--threshold-ms` (default 300, PERF-02). Run it from `e2e/`
with the suite's dependencies:

    uv run python perf/list_p95.py --base-url https://mealmate.<tailnet>.ts.net \\
        --username anna --password-file ~/.mealmate-perf
"""

import argparse
import math
import sys
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

INGREDIENTS = 150
MEALS = 20
EXTRAS = 5
POLLERS = 3
TIMEOUT_SECONDS = 30.0


@dataclass
class Session:
    """An API client of one "phone" that logs in again when its access token expires."""

    base_url: str
    username: str
    password: str
    client: httpx.Client = field(init=False)
    token: str = field(default="", init=False)

    def __post_init__(self) -> None:
        # trust_env=False: talk to the instance directly, never through a proxy of the shell.
        self.client = httpx.Client(base_url=self.base_url, timeout=TIMEOUT_SECONDS, trust_env=False)

    def login(self) -> None:
        response = self.client.post(
            "/api/auth/login", json={"username": self.username, "password": self.password}
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def request(
        self, method: str, url: str, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        if not self.token:
            self.login()
        response = self._send(method, url, headers, **kwargs)
        if response.status_code == 401:  # the access token expired: log in again
            self.login()
            response = self._send(method, url, headers, **kwargs)
        return response

    def _send(
        self, method: str, url: str, headers: dict[str, str] | None, **kwargs: Any
    ) -> httpx.Response:
        auth = {"Authorization": f"Bearer {self.token}"}
        return self.client.request(method, url, headers=auth | (headers or {}), **kwargs)

    def call(self, method: str, url: str, expected: int = 200, **kwargs: Any) -> Any:
        response = self.request(method, url, **kwargs)
        if response.status_code != expected:
            raise RuntimeError(f"{method} {url}: {response.status_code} {response.text}")
        return None if response.status_code == 204 else response.json()

    def close(self) -> None:
        self.client.close()


def ingredient_ids(api: Session) -> list[str]:
    """The ids of `Perf 000` … `Perf 149`, created where missing."""
    categories = [item["id"] for item in api.call("GET", "/api/categories")]
    existing = {item["name"]: item["id"] for item in api.call("GET", "/api/ingredients")}
    ids = []
    for index in range(INGREDIENTS):
        name = f"Perf {index:03d}"
        if name not in existing:
            body = {"name": name, "category_id": categories[index % len(categories)]}
            existing[name] = api.call("POST", "/api/ingredients", 201, json=body)["id"]
        ids.append(existing[name])
    return ids


def meal_rows(ingredients: list[str], meal: int) -> list[dict[str, Any]]:
    """Every 20th ingredient from `meal` on, plus the first two (merged into one line each)."""
    chosen = [0, 1, *(index for index in range(2, INGREDIENTS) if index % MEALS == meal)]
    return [
        {
            "ingredient_id": ingredients[index],
            "amount": 1 + index % 4 if index % 3 == 0 else 100 + index,
            "unit": "piece" if index % 3 == 0 else "g",
        }
        for index in chosen
    ]


def build_list(api: Session, run: str, *, shopping: bool) -> tuple[str, list[str], list[str]]:
    """The list, the ids of its meals and its line keys."""
    ingredients = ingredient_ids(api)
    meals = [
        api.call(
            "POST",
            "/api/meals",
            201,
            json={
                "name": f"Perf meal {meal:02d} {run}",
                "servings": 2,
                "ingredients": meal_rows(ingredients, meal),
            },
        )["id"]
        for meal in range(MEALS)
    ]
    list_id = api.call("POST", "/api/lists", 201, json={"name": f"Perf {run}"})["id"]
    for meal_id in meals:
        api.call("POST", f"/api/lists/{list_id}/meals", json={"meal_id": meal_id, "servings": 3})
    for index in range(EXTRAS):
        api.call("POST", f"/api/lists/{list_id}/extra-items", 201, json={"text": f"Extra {index}"})
    if shopping:
        detail = api.call("POST", f"/api/lists/{list_id}/start-shopping")
    else:
        detail = api.call("GET", f"/api/lists/{list_id}")
    return list_id, meals, [line["key"] for line in detail["lines"]]


def percentile(values: list[float], share: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


@dataclass
class Poller:
    api: Session
    etag: str | None = None

    def poll(self, list_id: str, *, cold: bool = False) -> tuple[int, float]:
        headers = {} if cold or self.etag is None else {"If-None-Match": self.etag}
        started = time.perf_counter()
        response = self.api.request("GET", f"/api/lists/{list_id}", headers=headers)
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code not in (200, 304):
            raise RuntimeError(f"GET list: {response.status_code} {response.text}")
        if not cold:
            self.etag = response.headers["etag"]
        return response.status_code, elapsed


def timed(action: Callable[[], httpx.Response]) -> float:
    started = time.perf_counter()
    response = action()
    elapsed = (time.perf_counter() - started) * 1000
    if response.status_code != 200:
        raise RuntimeError(f"ops: {response.status_code} {response.text}")
    return elapsed


def wait_until(moment: float) -> None:
    time.sleep(max(0.0, moment - time.monotonic()))


@dataclass
class Samples:
    """Response times in ms by kind (`200`, `304`, `ops`), filled from several threads."""

    values: dict[str, list[float]] = field(
        default_factory=lambda: {"200": [], "304": [], "ops": []}
    )
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, kind: str, elapsed: float) -> None:
        with self.lock:
            self.values[kind].append(elapsed)


def poll_rounds(
    poller: Poller, list_id: str, times: list[float], samples: Samples, *, cold: bool
) -> None:
    for moment in times:
        wait_until(moment)
        status, elapsed = poller.poll(list_id, cold=cold)
        samples.add(str(status), elapsed)


def run(args: argparse.Namespace, password: str) -> int:
    run_id = uuid.uuid4().hex[:6]
    owner = Session(args.base_url, args.username, password)
    phones = [Session(args.base_url, args.username, password) for _ in range(POLLERS + 1)]
    samples = Samples()
    list_id, meals = None, []
    try:
        print(f"Preparing {MEALS} meals and a list (run {run_id}) …", flush=True)
        list_id, meals, keys = build_list(owner, run_id, shopping=not args.draft)
        state = "draft" if args.draft else "shopping"
        print(f"List {list_id}: {len(meals)} meals, {len(keys)} lines, {state}", flush=True)
        for phone in phones:
            phone.login()
        pollers = [Poller(phone) for phone in phones]
        # Each round starts with the change (if any); the phones poll one after another, spread
        # over the interval like independent phones, or all at once half a second later
        # (`--burst`, the worst case). The last one sends no ETag (a phone opening the list).
        slots = len(pollers) + 1
        offsets = [
            0.5 if args.burst else (index + 1) * args.interval / slots
            for index in range(len(pollers))
        ]
        ops_url = f"/api/lists/{list_id}/ops"
        start = time.monotonic() + 1.0
        rounds = [start + number * args.interval for number in range(args.rounds)]
        with ThreadPoolExecutor(max_workers=len(pollers)) as pool:
            futures = [
                pool.submit(
                    poll_rounds,
                    poller,
                    list_id,
                    [moment + offset for moment in rounds],
                    samples,
                    cold=index == POLLERS,
                )
                for index, (poller, offset) in enumerate(zip(pollers, offsets, strict=True))
            ]
            for number, moment in enumerate(rounds):
                wait_until(moment)
                print(f"  round {number + 1}/{args.rounds}", end="\r", flush=True)
                if args.draft or number % args.change_every:
                    continue
                # Check the next line off: the list changes, the pollers get a 200.
                op = {
                    "op_id": str(uuid.uuid4()),
                    "type": "line.check",
                    "at": datetime.now(UTC).isoformat(),
                    "payload": {
                        "line_key": keys[number // args.change_every % len(keys)],
                        "checked": True,
                    },
                }
                samples.add(
                    "ops", timed(lambda op=op: owner.request("POST", ops_url, json={"ops": [op]}))
                )
            for future in futures:
                future.result()
        print()
    finally:
        if list_id is not None and not args.keep:
            owner.request("DELETE", f"/api/lists/{list_id}")
            for meal_id in meals:
                owner.request("DELETE", f"/api/meals/{meal_id}")
        for session in (owner, *phones):
            session.close()

    mode = "at once" if args.burst else "spread over the interval"
    print(f"{POLLERS} pollers + 1 cold GET every {args.interval:g} s ({mode})")
    print(f"{'':6}{'n':>5}{'p50':>9}{'p95':>9}{'max':>9}  (ms)")
    failed = []
    for kind, values in samples.values.items():
        if not values:
            print(f"{kind:6}{0:>5}")
            continue
        p95 = percentile(values, 0.95)
        print(
            f"{kind:6}{len(values):>5}{percentile(values, 0.5):>9.1f}{p95:>9.1f}{max(values):>9.1f}"
        )
        if p95 > args.threshold_ms:
            failed.append(kind)
    if failed:
        print(f"FAIL: p95 above {args.threshold_ms:g} ms for {', '.join(failed)}")
        return 1
    print(f"OK: every p95 within {args.threshold_ms:g} ms")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8080")
    parser.add_argument("--username", required=True, help="an existing user")
    secret = parser.add_mutually_exclusive_group(required=True)
    secret.add_argument("--password", help="their password (visible in the process list)")
    secret.add_argument("--password-file", type=Path, help="a file with their password")
    parser.add_argument("--rounds", type=int, default=24, help="polling rounds (default 24)")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between rounds")
    parser.add_argument(
        "--change-every", type=int, default=2, help="change the list every N rounds (default 2)"
    )
    parser.add_argument("--threshold-ms", type=float, default=300.0, help="p95 limit (300)")
    parser.add_argument("--draft", action="store_true", help="poll a draft, not a list in shop")
    parser.add_argument(
        "--burst", action="store_true", help="all phones poll at the same moment (worst case)"
    )
    parser.add_argument("--keep", action="store_true", help="keep the list and meals afterwards")
    args = parser.parse_args()
    if args.rounds < 1 or args.change_every < 1:
        parser.error("--rounds and --change-every must be at least 1")
    password = (
        args.password
        if args.password is not None
        else args.password_file.read_text(encoding="utf-8").strip()
    )
    return run(args, password)


if __name__ == "__main__":
    sys.exit(main())
