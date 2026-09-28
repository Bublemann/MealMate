"""`create-admin`, `reset-link`, `seed-demo`, `jobs cleanup` and `jobs off-refresh` (ACC-12,
BAR-05, plan § 5.11)."""

import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import bcrypt
import pytest
import respx
from sqlalchemy.exc import IntegrityError
from typer.testing import CliRunner

from app.cli import main
from app.db.migrations import upgrade_database
from app.domain.barcodes import normalize_barcode
from app.integrations.off import OffClient
from app.services import demo, off_refresh
from tests.off import OFF_URL, product_response, product_url

runner = CliRunner()
PUBLIC_URL = "https://mealmate.example.ts.net"
PASSWORD = "correct horse battery"  # noqa: S105 -- a test password


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, secret_key: str, data_dir: Path) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", secret_key)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEALMATE_BCRYPT_ROUNDS", "4")
    monkeypatch.setenv("MEALMATE_PUBLIC_URL", PUBLIC_URL)


@pytest.fixture
def database(data_dir: Path) -> Path:
    upgrade_database(data_dir)
    return data_dir / "mealmate.db"


def query(database: Path, sql: str, *params: object) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(sql, params).fetchall()


def create_admin(*args: str, stdin: str = PASSWORD + "\n") -> tuple[int, str]:
    result = runner.invoke(
        main,
        [
            "create-admin",
            "--password-stdin",
            "--username",
            "admin",
            "--display-name",
            "Admin",
            *args,
        ],
        input=stdin,
    )
    return result.exit_code, result.output


def test_account_commands_need_a_migrated_database(data_dir: Path) -> None:
    for args in (
        ["create-admin"],
        ["reset-link", "admin"],
        ["seed-demo"],
        ["jobs", "cleanup"],
        ["jobs", "off-refresh"],
    ):
        result = runner.invoke(main, args)
        assert result.exit_code == 1, args
        assert "run `mealmate db upgrade` first" in result.output


def test_create_admin_non_interactive(database: Path) -> None:
    code, output = create_admin("--language", "en")

    assert code == 0, output
    assert "Admin admin created." in output
    [(username, display_name, role, language, active, password_hash)] = query(
        database,
        "SELECT username, display_name, role, language, is_active, password_hash FROM users",
    )
    assert (username, display_name, role, language, active) == ("admin", "Admin", "admin", "en", 1)
    assert isinstance(password_hash, str)
    assert bcrypt.checkpw(PASSWORD.encode(), password_hash.encode())
    assert PASSWORD not in output


def test_create_admin_refuses_an_existing_username(database: Path) -> None:
    assert create_admin()[0] == 0
    code, output = create_admin()
    assert code == 1
    assert "username: taken" in output
    assert "display_name: taken" in output
    assert len(query(database, "SELECT id FROM users")) == 1


@pytest.mark.parametrize(
    ("stdin", "expected"),
    [("password\n", "password: too_common"), ("short\n", "password: too_short"), ("", "too_short")],
)
def test_create_admin_validates_like_join(database: Path, stdin: str, expected: str) -> None:
    code, output = create_admin(stdin=stdin)
    assert code == 1
    assert expected in output
    assert query(database, "SELECT id FROM users") == []


def test_create_admin_validates_the_username(database: Path) -> None:
    result = runner.invoke(
        main,
        ["create-admin", "--password-stdin", "--username", "Big Boss", "--display-name", "B"],
        input=PASSWORD + "\n",
    )
    assert result.exit_code == 1
    assert "username: invalid_format" in result.output


def test_password_stdin_needs_the_names(database: Path) -> None:
    result = runner.invoke(main, ["create-admin", "--password-stdin"], input=PASSWORD + "\n")
    assert result.exit_code == 2
    assert "needs --username and --display-name" in result.output


def test_create_admin_interactive(database: Path) -> None:
    result = runner.invoke(
        main,
        ["create-admin"],
        input=f"root\nThe Root\n{PASSWORD}\nmistyped password\n{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert "Username:" in result.output
    assert "Display name:" in result.output
    assert "do not match" in result.output
    assert PASSWORD not in result.output
    assert query(database, "SELECT username, display_name, role FROM users") == [
        ("root", "The Root", "admin")
    ]


def test_reset_link_reactivates_the_account(database: Path) -> None:
    create_admin()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE users SET is_active = 0")
        connection.commit()

    result = runner.invoke(main, ["reset-link", "ADMIN"])

    assert result.exit_code == 0, result.output
    url = result.output.strip()
    assert url.startswith(f"{PUBLIC_URL}/reset#")
    assert len(url.partition("#")[2]) == 43
    assert query(database, "SELECT is_active FROM users") == [(1,)]
    assert query(database, "SELECT kind, created_by FROM one_time_codes") == [("reset", None)]
    assert query(
        database, "SELECT action, actor_id, details FROM admin_events ORDER BY action"
    ) == [
        ("user.reactivate", None, '{"source": "cli"}'),
        ("user.reset_link", None, '{"source": "cli"}'),
    ]
    # A second link revokes the first; an active account is not "reactivated" again.
    assert runner.invoke(main, ["reset-link", "admin"]).exit_code == 0
    assert query(database, "SELECT count(*) FROM one_time_codes WHERE revoked_at IS NOT NULL") == [
        (1,)
    ]
    assert len(query(database, "SELECT id FROM admin_events")) == 3


def test_reset_link_for_an_unknown_user(database: Path) -> None:
    result = runner.invoke(main, ["reset-link", "nobody"])
    assert result.exit_code == 1
    assert "No user named 'nobody'" in result.output


def test_link_commands_need_the_public_url(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEALMATE_PUBLIC_URL")
    for args in (["reset-link", "admin"], ["seed-demo"]):
        result = runner.invoke(main, args)
        assert result.exit_code == 1
        assert "MEALMATE_PUBLIC_URL is not set" in result.output


def test_seed_demo(database: Path, data_dir: Path) -> None:
    result = runner.invoke(main, ["seed-demo"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    password = next(line for line in lines if line.startswith("Demo password")).split(": ")[1]
    invite = next(line for line in lines if line.startswith("Open invite")).split(": ")[1]
    assert invite.startswith(f"{PUBLIC_URL}/join#")
    users = dict(query(database, "SELECT username, role FROM users"))
    assert users == {"admin": "admin", "anna": "user", "ben": "user", "carl": "user"}
    [(password_hash,)] = query(database, "SELECT password_hash FROM users WHERE username = 'carl'")
    assert isinstance(password_hash, str)
    assert bcrypt.checkpw(password.encode(), password_hash.encode())
    members = query(
        database,
        "SELECT u.username FROM couple_members m JOIN users u ON u.id = m.user_id ORDER BY 1",
    )
    assert members == [("anna",), ("ben",)]
    assert query(database, "SELECT kind, used_at FROM one_time_codes") == [("invite", None)]
    assert "Demo ingredients: 30 (5 with a barcode)" in result.output

    ingredients = query(database, "SELECT name, brand, barcode, source FROM ingredients")
    assert len(ingredients) == 30
    # The same thing in two brands: two ingredients of the same name.
    assert sorted(
        (brand, barcode) for name, brand, barcode, _ in ingredients if name == "Spaghetti"
    ) == [("Barilla", "8005516001475"), ("De Cecco", "8002331045820")]
    assert {name for name, _, barcode, _ in ingredients if barcode} == {
        "Spaghetti",
        "Butter",
        "Passierte Tomaten",
        "Olivenöl",
    }
    assert {source for *_, source in ingredients} == {"manual"}  # never refreshed in development
    assert query(database, "SELECT kcal FROM ingredients WHERE name = 'Milch'") == [(64,)]
    categories = query(database, "SELECT count(DISTINCT category_id) FROM ingredients")
    assert categories == [(15,)]
    creators = query(
        database,
        "SELECT DISTINCT u.username FROM ingredients i JOIN users u ON u.id = i.created_by "
        "ORDER BY 1",
    )
    assert creators == [("anna",), ("ben",), ("carl",)]
    barcodes = [code for _, _, code, _ in ingredients if code is not None]
    assert all(normalize_barcode(code) == code for code in barcodes)

    assert "Demo meals: 9" in result.output
    meals = query(
        database,
        "SELECT u.username, m.name, m.photo_key, m.copied_from_meal_id IS NOT NULL, "
        "(SELECT count(*) FROM meal_ingredients r WHERE r.meal_id = m.id), "
        "(SELECT count(*) FROM meal_tags t WHERE t.meal_id = m.id) "
        "FROM meals m JOIN users u ON u.id = m.owner_id ORDER BY 1, 2",
    )
    assert [(owner, name) for owner, name, *_ in meals] == [
        ("admin", "Käsebrot"),
        ("anna", "Pfannkuchen"),
        ("anna", "Spaghetti Bolognese"),
        ("ben", "Hähnchen-Reis-Pfanne"),
        ("ben", "Tomatensalat"),
        ("carl", "Ofenkartoffeln mit Kräuterjoghurt"),
        ("carl", "Spaghetti Bolognese"),
        ("carl", "Spaghetti aglio e olio"),
        ("carl", "Tofu-Gemüse-Curry"),
    ]
    assert all(rows > 0 and tags > 0 for *_, rows, tags in meals)
    assert [name for _, name, _, copied, *_ in meals if copied] == ["Spaghetti Bolognese"]
    keys = [str(key) for _, _, key, *_ in meals if key is not None]
    assert len(keys) == len(set(keys)) == 4  # three photos and the copy's own copy
    media = data_dir / "media"
    assert {path.name for path in media.iterdir()} == {
        name for key in keys for name in (f"{key}.webp", f"{key}-thumb.webp")
    }
    private = query(database, "SELECT username FROM users WHERE NOT meals_public")
    assert private == [("carl",)]
    units = {unit for (unit,) in query(database, "SELECT DISTINCT unit FROM meal_ingredients")}
    assert units == {"g", "kg", "ml", "piece", "tbsp", None}

    assert "Demo lists: 6" in result.output
    lists = query(
        database,
        "SELECT u.username, l.name, l.shared_with_partner, l.status, l.reminder_seed, "
        "(SELECT count(*) FROM list_meals m WHERE m.list_id = l.id), "
        "(SELECT count(*) FROM list_extra_items e WHERE e.list_id = l.id), "
        "(SELECT count(*) FROM list_line_states s WHERE s.list_id = l.id AND s.hidden) "
        "FROM shopping_lists l JOIN users u ON u.id = l.owner_id ORDER BY 1, 2",
    )
    assert lists == [
        ("anna", "Salatabend", 1, "done", 4, 1, 1, 0),
        ("anna", "Wocheneinkauf", 1, "shopping", 21, 2, 3, 0),
        ("anna", "Wochenende", 1, "draft", 3, 2, 3, 1),
        ("ben", None, 0, "draft", 7, 2, 0, 0),
        ("carl", "Grillabend", 0, "draft", 12, 3, 1, 0),
        ("carl", "Vorrat", 0, "done", 58, 1, 1, 0),
    ]
    checks = query(
        database,
        "SELECT l.name, u.username, count(*) FROM list_line_states s "
        "JOIN shopping_lists l ON l.id = s.list_id JOIN users u ON u.id = s.checked_by "
        "WHERE s.checked GROUP BY 1, 2 ORDER BY 1, 2",
    )
    assert checks == [
        ("Salatabend", "anna", 3),
        ("Salatabend", "ben", 2),
        ("Vorrat", "carl", 6),
        ("Wocheneinkauf", "anna", 3),
        ("Wocheneinkauf", "ben", 1),
    ]
    # Shopping froze the meals, which keep their meal (LIST-11).
    frozen = query(
        database,
        "SELECT count(*) FROM list_meals WHERE frozen_at IS NOT NULL AND meal_id IS NOT NULL",
    )
    assert frozen == [(4,)]
    # The meal ben deleted stays on his draft, detached with its frozen rows (LIST-15).
    detached = query(
        database,
        "SELECT meal_id, meal_name_snapshot, detached_reason, "
        "(SELECT count(*) FROM list_meal_ingredients r WHERE r.list_meal_id = m.id) "
        "FROM list_meals m WHERE detached_reason IS NOT NULL",
    )
    assert detached == [(None, "Kartoffelsuppe", "deleted", 4)]
    assert query(database, "SELECT count(*) FROM meals WHERE name = 'Kartoffelsuppe'") == [(0,)]

    again = runner.invoke(main, ["seed-demo"])
    assert again.exit_code == 1
    assert "Refusing to seed demo data" in again.output
    assert len(query(database, "SELECT id FROM users")) == 4


def test_seed_demo_leaves_nothing_behind_when_it_fails(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accounts and catalog are one transaction, so a failed run can simply be repeated."""
    with monkeypatch.context() as patched:
        # A scanned ingredient twice: its barcode is unique, so the catalog fails after the
        # accounts.
        scanned = next(item for item in demo.DEMO_INGREDIENTS if item.barcode is not None)
        patched.setattr(demo, "DEMO_INGREDIENTS", (*demo.DEMO_INGREDIENTS, scanned))
        result = runner.invoke(main, ["seed-demo"])
    assert result.exit_code == 1
    assert isinstance(result.exception, IntegrityError)
    tables = ("users", "couples", "couple_members", "one_time_codes", "admin_events")
    catalog = ("ingredients", "tags", "meals", "meal_ingredients", "shopping_lists")
    for table in (*tables, *catalog):
        assert query(database, f"SELECT count(*) FROM {table}") == [(0,)], table  # noqa: S608

    again = runner.invoke(main, ["seed-demo"])
    assert again.exit_code == 0, again.output
    assert len(query(database, "SELECT id FROM users")) == 4


def test_create_admin_validates_the_display_name(database: Path) -> None:
    result = runner.invoke(
        main,
        ["create-admin", "--password-stdin", "--username", "boss", "--display-name", "  "],
        input=PASSWORD + "\n",
    )
    assert result.exit_code == 1
    assert "display_name: too_short" in result.output


def test_jobs_cleanup(database: Path, data_dir: Path) -> None:
    assert runner.invoke(main, ["seed-demo"]).exit_code == 0
    media = data_dir / "media"
    photos = {path.name for path in media.iterdir()}
    orphans = {"0" * 32 + ".webp", "0" * 32 + "-thumb.webp"}
    for name in orphans:
        (media / name).write_bytes(b"old")
    an_hour_ago = time.time() - 3601
    for path in media.iterdir():
        os.utime(path, (an_hour_ago, an_hour_ago))

    result = runner.invoke(main, ["jobs", "cleanup"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "Removed 2 orphaned media files.",
        "Removed 0 finished invites and reset links.",
        "Removed 0 expired refresh tokens.",
        "Removed 0 ended sessions.",
        "Removed 0 processed shopping ops.",
    ]
    assert {path.name for path in media.iterdir()} == photos
    assert "Removed 0 orphaned media files." in runner.invoke(main, ["jobs", "cleanup"]).output


def test_jobs_off_refresh(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEALMATE_OFF_BASE_URL", OFF_URL)
    monkeypatch.setenv("MEALMATE_VERSION", "2.0.0")
    assert runner.invoke(main, ["seed-demo"]).exit_code == 0
    [(found,), (down,), (broken,), *_] = query(
        database, "SELECT barcode FROM ingredients WHERE barcode IS NOT NULL ORDER BY barcode"
    )
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE ingredients SET source = 'off', fetched_at = NULL, user_edited_fields = '[]'"
            " WHERE barcode IN (?, ?, ?)",
            (found, down, broken),
        )
    jobs: list[tuple[int, int | None]] = []
    clients: list[OffClient] = []
    refresh_stale = off_refresh.refresh_stale
    apply_refresh = off_refresh.apply_refresh

    async def spy(database: Any, off: OffClient, **options: Any) -> Any:
        jobs.append((off.rate_limit.limit, options["max_ingredients"]))
        clients.append(off)
        outcomes = await refresh_stale(database, off, **options)
        assert off.is_open
        return outcomes

    def fails_for_broken(row: Any, found: Any, **options: Any) -> Any:
        if row.barcode == broken:
            raise RuntimeError("bug")
        return apply_refresh(row, found, **options)

    monkeypatch.setattr(off_refresh, "refresh_stale", spy)
    monkeypatch.setattr(off_refresh, "apply_refresh", fails_for_broken)

    with respx.mock(base_url=OFF_URL) as off_api:
        request = off_api.get(product_url(found)).respond(
            json=product_response(found, brands="Neu")
        )
        off_api.get(product_url(down)).respond(503)
        off_api.get(product_url(broken)).respond(json=product_response(broken))
        result = runner.invoke(main, ["jobs", "off-refresh"])

    assert result.exit_code == 0, result.output
    assert (
        "Refreshed 3 ingredients from Open Food Facts: 1 updated, 0 with newer values for "
        "user-edited fields, 0 unchanged, 1 kept for the next run (1 unavailable, 0 not found), "
        "1 failed with an error (see the log)."
    ) in result.output
    # The job's own rate limit (4 per minute, the app has 6), an hour's worth of ingredients.
    assert jobs == [(4, 240)]
    assert not clients[0].is_open  # the job closes its connections
    assert request.calls.last.request.headers["user-agent"] == (
        "MealMate/2.0.0 (https://github.com/Bublemann/MealMate)"
    )
    assert query(database, "SELECT brand FROM ingredients WHERE barcode = ?", found) == [("Neu",)]
    [(fetched_at,)] = query(database, "SELECT fetched_at FROM ingredients WHERE barcode = ?", down)
    assert fetched_at is None
