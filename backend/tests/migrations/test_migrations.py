import asyncio
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, event
from typer.testing import CliRunner

from app.cli import main
from app.core.config import Settings
from app.db import migrations
from app.db.base import utcnow
from app.db.migrations import (
    ForeignKeyViolationError,
    alembic_config,
    alembic_ini_path,
    create_migration_engine,
    current_revision,
    head_revision,
    upgrade_database,
)
from app.db.session import Database
from app.domain.reference import CATEGORY_KEYS, CUISINE_KEYS, SEEDED_CATEGORIES
from app.main import create_app
from app.models import Base
from app.services import demo
from app.services.context import AuthConfig
from tests.accounts import Account, login, password_hash
from tests.support import TEST_SECRET_KEY, serve

HEAD = "0009"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
ACCOUNT_TABLES = {
    "alembic_version",
    "app_meta",
    "users",
    "sessions",
    "session_tokens",
    "one_time_codes",
    "couples",
    "couple_members",
    "admin_events",
}
CATALOG_TABLES = ACCOUNT_TABLES | {"categories", "cuisines", "tags", "ingredients", "products"}
MEAL_TABLES = CATALOG_TABLES | {"meals", "meal_ingredients", "meal_tags"}
LIST_TABLES = {
    "shopping_lists",
    "list_meals",
    "list_meal_ingredients",
    "list_extra_items",
    "list_line_states",
}
TABLES_0006 = MEAL_TABLES | LIST_TABLES | {"processed_ops"}
# 0007 merges the products into the ingredients; 0008 and 0009 only add columns.
HEAD_TABLES = TABLES_0006 - {"products"}


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "mealmate.db"


@pytest.fixture
def config(database_path: Path) -> Config:
    return alembic_config(database_path)


def tables(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def assert_clean(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert not {name for name in tables(path) if name.startswith("_alembic_tmp_")}


def test_alembic_ini_is_found_from_the_package() -> None:
    assert alembic_ini_path() == Path(__file__).resolve().parents[2] / "alembic.ini"


def test_missing_alembic_ini(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(migrations, "_ALEMBIC_INI_CANDIDATES", (tmp_path / "alembic.ini",))
    with pytest.raises(FileNotFoundError, match=r"alembic\.ini"):
        alembic_ini_path()


def test_upgrade_downgrade_upgrade(config: Config, database_path: Path) -> None:
    assert head_revision(config) == HEAD

    command.upgrade(config, "head")
    assert tables(database_path) == HEAD_TABLES
    assert current_revision(database_path) == HEAD
    assert_clean(database_path)

    command.downgrade(config, "base")
    assert tables(database_path) == {"alembic_version"}
    assert current_revision(database_path) is None

    command.upgrade(config, "head")
    assert tables(database_path) == HEAD_TABLES
    assert_clean(database_path)


def test_each_revision_steps_down_and_up(config: Config, database_path: Path) -> None:
    command.upgrade(config, "0001")
    assert tables(database_path) == {"alembic_version", "app_meta"}
    command.upgrade(config, "0002")
    assert tables(database_path) == ACCOUNT_TABLES
    command.upgrade(config, "0003")
    assert tables(database_path) == CATALOG_TABLES
    command.upgrade(config, "0004")
    assert tables(database_path) == MEAL_TABLES
    command.upgrade(config, "0005")
    assert tables(database_path) == MEAL_TABLES | LIST_TABLES
    command.upgrade(config, "0006")
    assert tables(database_path) == TABLES_0006
    command.upgrade(config, "0007")
    assert tables(database_path) == HEAD_TABLES
    command.upgrade(config, "0008")
    assert tables(database_path) == HEAD_TABLES
    command.upgrade(config, "0009")
    assert tables(database_path) == HEAD_TABLES
    command.downgrade(config, "0008")
    assert tables(database_path) == HEAD_TABLES
    command.downgrade(config, "0007")
    assert tables(database_path) == HEAD_TABLES
    command.downgrade(config, "0006")
    assert tables(database_path) == TABLES_0006
    command.downgrade(config, "0005")
    assert tables(database_path) == MEAL_TABLES | LIST_TABLES
    command.downgrade(config, "0004")
    assert tables(database_path) == MEAL_TABLES
    command.downgrade(config, "0003")
    assert tables(database_path) == CATALOG_TABLES
    command.downgrade(config, "0002")
    assert tables(database_path) == ACCOUNT_TABLES
    command.downgrade(config, "0001")
    assert tables(database_path) == {"alembic_version", "app_meta"}
    assert_clean(database_path)


def query(path: Path, sql: str) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(sql).fetchall()


def test_reference_data_is_seeded(config: Config, database_path: Path) -> None:
    """The migration spells out the seeds; they agree with the domain constants, and a
    downgrade and upgrade seeds them again."""
    for _ in range(2):
        command.upgrade(config, "head")
        categories = query(
            database_path, "SELECT key, name_de, name_en, sort_order FROM categories ORDER BY 4"
        )
        assert categories == [
            (*category, position) for position, category in enumerate(SEEDED_CATEGORIES)
        ]
        cuisines = query(database_path, "SELECT key, name, name_norm FROM cuisines ORDER BY id")
        assert cuisines == [(key, None, key) for key in CUISINE_KEYS]
        ids = query(database_path, "SELECT id FROM categories UNION ALL SELECT id FROM cuisines")
        assert all(uuid.UUID(str(row_id)).version == 7 for (row_id,) in ids)
        command.downgrade(config, "0002")
        assert tables(database_path) == ACCOUNT_TABLES


# --- populated databases (QA-02) -------------------------------------------------------------


def row_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]  # noqa: S608
            for table in sorted(tables(path) - {"alembic_version"})
        }


def non_null_foreign_keys(path: Path) -> dict[str, int]:
    """Per nullable FK column, how many rows reference something (ON DELETE SET NULL or a
    careless table rebuild would lower these)."""
    counts: dict[str, int] = {}
    with closing(sqlite3.connect(path)) as connection:
        for table in sorted(tables(path) - {"alembic_version"}):
            nullable = {
                row[1]: not row[3] for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            for foreign_key in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
                column = foreign_key[3]
                if nullable[column]:
                    counts[f"{table}.{column}"] = connection.execute(
                        f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL'  # noqa: S608
                    ).fetchone()[0]
    return counts


def demo_settings(data_dir: Path) -> Settings:
    return Settings(
        secret_key=TEST_SECRET_KEY,
        data_dir=data_dir,
        public_url="https://mealmate.example.ts.net",
        bcrypt_rounds=4,
    )


def seed_accounts(data_dir: Path) -> dict[str, str]:
    """The M2 part of seed-demo, which works at revision 0002."""

    async def run() -> dict[str, str]:
        database = Database.open(data_dir)
        try:
            async with database.write_sessions() as session:
                config = AuthConfig.from_settings(demo_settings(data_dir))
                seed = await demo.seed_accounts(session, config, now=utcnow())
                return seed.user_ids
        finally:
            await database.dispose()

    return asyncio.run(run())


def seed_demo(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEALMATE_PUBLIC_URL", "https://mealmate.example.ts.net")
    monkeypatch.setenv("MEALMATE_BCRYPT_ROUNDS", "4")
    result = CliRunner().invoke(main, ["seed-demo"])
    assert result.exit_code == 0, result.output


def test_accounts_survive_the_catalog_migration(tmp_path: Path) -> None:
    """seed-demo's accounts at 0002: 0003 seeds the reference data and keeps every row and
    reference; stepping back keeps the accounts."""
    data_dir = tmp_path / "data"
    path = data_dir / "mealmate.db"
    config = alembic_config(path)
    data_dir.mkdir()
    command.upgrade(config, "0002")
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("INSERT INTO app_meta (key, value) VALUES ('sentinel', 'kept')")
        connection.commit()
    seed_accounts(data_dir)
    counts, references = row_counts(path), non_null_foreign_keys(path)
    assert counts["users"] == 4
    assert counts["couple_members"] == 2
    assert references["one_time_codes.created_by"] == 1

    command.upgrade(config, "0003")
    seeded = {"categories": 17, "cuisines": 13, "tags": 0, "ingredients": 0, "products": 0}
    assert row_counts(path) == counts | seeded
    assert non_null_foreign_keys(path) == references | {
        "cuisines.created_by": 0,
        "ingredients.created_by": 0,
        "ingredients.updated_by": 0,
        "products.created_by": 0,
        "products.updated_by": 0,
    }
    assert_clean(path)
    command.downgrade(config, "0002")
    assert row_counts(path) == counts
    assert non_null_foreign_keys(path) == references
    command.upgrade(config, "head")
    assert_clean(path)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT value FROM app_meta").fetchall() == [("kept",)]


def load_demo_0006(path: Path) -> None:
    """The database `seed-demo` made at 0006 (`fixtures/demo-0006.sql`): accounts, the old
    catalog with products (Spaghetti with two, Milch, Butter, Passierte Tomaten and Olivenöl
    with one each), meals with photos, drafts, a list being shopped and done lists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript((FIXTURES / "demo-0006.sql").read_text(encoding="utf-8"))
    assert current_revision(path) == "0006"


def test_demo_data_at_0006_survives_the_earlier_migrations(tmp_path: Path) -> None:
    """seed-demo data at 0006, stepped down and up again: 0006 → 0005 drops only the (empty)
    `processed_ops`, 0005 → 0004 the lists, 0004 → 0003 the meals (their tags stay); each
    upgrade adds its tables empty and keeps the older data and every reference."""
    path = tmp_path / "data" / "mealmate.db"
    config = alembic_config(path)
    load_demo_0006(path)
    at_0006, references_0006 = row_counts(path), non_null_foreign_keys(path)
    assert at_0006["products"] == 6
    assert at_0006["list_meal_ingredients"] > 0
    assert references_0006["list_line_states.checked_by"] > 0
    assert_clean(path)

    command.downgrade(config, "0005")
    with_lists, list_references = row_counts(path), non_null_foreign_keys(path)
    assert with_lists == {
        table: count for table, count in at_0006.items() if table != "processed_ops"
    }
    assert list_references == references_0006
    command.downgrade(config, "0004")
    with_meals = row_counts(path)
    assert with_meals == {
        table: count for table, count in with_lists.items() if table not in LIST_TABLES
    }
    command.downgrade(config, "0003")
    catalog = row_counts(path)
    assert catalog == {
        table: count
        for table, count in with_meals.items()
        if table not in {"meals", "meal_ingredients", "meal_tags"}
    }
    assert catalog["tags"] > 0
    assert_clean(path)

    command.upgrade(config, "0004")
    assert row_counts(path) == catalog | {"meals": 0, "meal_ingredients": 0, "meal_tags": 0}
    command.upgrade(config, "0005")
    assert row_counts(path) == row_counts(path) | dict.fromkeys(LIST_TABLES, 0)
    command.upgrade(config, "0006")
    assert row_counts(path)["processed_ops"] == 0
    assert_clean(path)


def rows_of(path: Path, table: str) -> list[dict[str, object]]:
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        statement = f'SELECT * FROM "{table}" ORDER BY id'  # noqa: S608
        return [dict(row) for row in connection.execute(statement)]


def ingredients_by_name(path: Path) -> dict[str, list[dict[str, object]]]:
    by_name: dict[str, list[dict[str, object]]] = {}
    for row in rows_of(path, "ingredients"):
        by_name.setdefault(str(row["name"]), []).append(row)
    return by_name


def test_0007_merges_the_demo_products_into_ingredients(tmp_path: Path) -> None:
    """seed-demo data at 0006 → 0007 (plan § 9): the row counts change only by design, i.e.
    `ingredients` gains one row per product of an ingredient with several (Spaghetti's two)
    and `products` is gone; every other table keeps its rows and references."""
    path = tmp_path / "data" / "mealmate.db"
    config = alembic_config(path)
    load_demo_0006(path)
    before, references = row_counts(path), non_null_foreign_keys(path)

    command.upgrade(config, "0007")

    after = row_counts(path)
    assert after == {
        **{table: count for table, count in before.items() if table != "products"},
        "ingredients": before["ingredients"] + 2,
    }
    assert non_null_foreign_keys(path) == {
        **{
            column: count
            for column, count in references.items()
            if not column.startswith("products.")
        },
        "ingredients.created_by": references["ingredients.created_by"] + 2,
        "ingredients.updated_by": references["ingredients.updated_by"] + 2,
    }
    assert_clean(path)

    ingredients = ingredients_by_name(path)
    # Rule 3: Spaghetti keeps its id and the average of its two products; they are new
    # ingredients with their own names, brands, barcodes and values.
    [spaghetti] = ingredients["Spaghetti"]
    assert (spaghetti["barcode"], spaghetti["brand"], spaghetti["kcal"]) == (None, None, 356)
    [barilla] = ingredients["Spaghetti n.5"]
    assert (barilla["brand"], barilla["barcode"], barilla["kcal"]) == (
        "Barilla",
        "8005516001475",
        359,
    )
    assert (barilla["category_id"], barilla["base_unit"]) == (
        spaghetti["category_id"],
        spaghetti["base_unit"],
    )
    assert uuid.UUID(str(barilla["id"])).version == 7
    # Rule 2: Milch took over its product and kept its name and manual values.
    [milk] = ingredients["Milch"]
    assert (milk["brand"], milk["barcode"], milk["kcal"], milk["pack_unit"]) == (
        "Weihenstephan",
        "4028173104529",
        64,
        "l",
    )
    # Rule 2 for an ingredient without manual values: the product's.
    [butter] = ingredients["Butter"]
    assert (butter["brand"], butter["kcal"], butter["fat"]) == ("Kerrygold", 741, 82)
    assert all(
        "nutrition_basis" not in str(row["user_edited_fields"])
        for rows in ingredients.values()
        for row in rows
    )
    assert query(path, "SELECT count(*) FROM list_meal_ingredients WHERE "
                 "ingredient_brand_snapshot IS NOT NULL") == [(0,)]  # fmt: skip

    # Back to 0006: a product for every ingredient with a barcode, linked to itself.
    command.downgrade(config, "0006")
    assert row_counts(path) == before | {"ingredients": after["ingredients"], "products": 6}
    assert query(path, "SELECT count(*) FROM products p JOIN ingredients i "
                 "ON i.id = p.ingredient_id AND i.name = p.name") == [(6,)]  # fmt: skip
    assert_clean(path)
    command.upgrade(config, "0007")
    assert row_counts(path) == after
    assert_clean(path)


async def _visit_everything(settings: Settings) -> int:
    """Every demo user logs in and opens every meal and list they see; returns how many."""
    app = create_app(settings)
    opened = 0
    async with serve(app, base_url="https://testserver.local") as client:
        for username in ("admin", "anna", "ben", "carl"):
            user = Account(id="", username=username, display_name=username)
            await login(client, user)
            for kind in ("meals", "lists"):
                response = await client.get(f"/api/{kind}", headers=user.headers)
                assert response.status_code == 200, response.text
                # The list feed's first page holds every demo list one sees.
                items = response.json()["lists"] if kind == "lists" else response.json()
                for item in items:
                    item_response = await client.get(
                        f"/api/{kind}/{item['id']}", headers=user.headers
                    )
                    assert item_response.status_code == 200, item_response.text
                    opened += 1
    return opened


def test_meals_and_lists_keep_working_after_0007(tmp_path: Path) -> None:
    """The migrated demo data through the API: every meal (with its nutrition) and every list
    (with its lines) opens."""
    data_dir = tmp_path / "data"
    path = data_dir / "mealmate.db"
    load_demo_0006(path)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE users SET password_hash = ?", (password_hash(),))
    upgrade_database(data_dir)

    assert asyncio.run(_visit_everything(demo_settings(data_dir))) > 10


# --- 0008 -----------------------------------------------------------------------------------


def meals_and_ingredients(path: Path) -> dict[str, list[dict[str, object]]]:
    return {table: rows_of(path, table) for table in ("meals", "ingredients")}


def test_0008_adds_the_sort_keys_and_changes_nothing_else(tmp_path: Path) -> None:
    """seed-demo data at 0007 → 0008 (D-27): every meal and ingredient gets the sort key of its
    name, and an ingredient with a brand that of its brand; no row and no other value changes,
    and the downgrade drops the keys again."""
    path = tmp_path / "data" / "mealmate.db"
    config = alembic_config(path)
    load_demo_0006(path)
    command.upgrade(config, "0007")
    counts, references = row_counts(path), non_null_foreign_keys(path)
    before = meals_and_ingredients(path)

    command.upgrade(config, "0008")

    assert row_counts(path) == counts
    assert non_null_foreign_keys(path) == references
    assert_clean(path)
    after = meals_and_ingredients(path)
    for table, rows in after.items():
        without_keys = [
            {column: value for column, value in row.items() if not column.endswith("_sort")}
            for row in rows
        ]
        assert without_keys == before[table]
    assert {row["name"]: row["name_sort"] for row in after["meals"]} == {
        "Hähnchen-Reis-Pfanne": "hahnchen-reis-pfanne",
        "Käsebrot": "kasebrot",
        "Ofenkartoffeln mit Kräuterjoghurt": "ofenkartoffeln mit krauterjoghurt",
        "Pfannkuchen": "pfannkuchen",
        "Spaghetti Bolognese": "spaghetti bolognese",
        "Tofu-Gemüse-Curry": "tofu-gemuse-curry",
        "Tomatensalat": "tomatensalat",
    }
    ingredients = {
        (row["name"], row["brand"]): (row["name_sort"], row["brand_sort"])
        for row in after["ingredients"]
    }
    assert ingredients[("Äpfel", None)] == ("apfel", None)
    assert ingredients[("Hähnchenbrust", None)] == ("hahnchenbrust", None)
    assert ingredients[("Erbsen (TK)", None)] == ("erbsen (tk)", None)
    assert ingredients[("Olivenöl", "Bertolli")] == ("olivenol", "bertolli")
    assert ingredients[("Spaghetti n.12", "De Cecco")] == ("spaghetti n.12", "de cecco")
    assert all(name_sort for name_sort, _ in ingredients.values())
    assert all((brand is None) == (keys[1] is None) for (_, brand), keys in ingredients.items())

    command.downgrade(config, "0007")
    assert meals_and_ingredients(path) == before
    assert row_counts(path) == counts
    assert_clean(path)


# --- 0009 -----------------------------------------------------------------------------------

# Requirements appendix A, as the translations `category.<key>` had them.
SEEDED_CATEGORY_NAMES = {
    "fruit_vegetables": ("Obst & Gemüse", "Fruit & vegetables"),
    "bread_bakery": ("Brot & Backwaren", "Bread & bakery"),
    "dairy_eggs": ("Milchprodukte & Eier", "Dairy & eggs"),
    "cheese": ("Käse", "Cheese"),
    "meat_fish": ("Fleisch & Fisch", "Meat & fish"),
    "sausage_deli": ("Wurst & Aufschnitt", "Sausage & deli"),
    "plant_based": ("Tofu & pflanzliche Alternativen", "Tofu & plant-based"),
    "pasta_rice_grains": ("Nudeln, Reis & Getreide", "Pasta, rice & grains"),
    "canned_jars": ("Konserven & Gläser", "Canned & jarred"),
    "sauces_spices_oils": ("Soßen, Gewürze & Öle", "Sauces, spices & oils"),
    "baking": ("Backzutaten", "Baking"),
    "breakfast_spreads": ("Frühstück & Aufstriche", "Breakfast & spreads"),
    "snacks_sweets": ("Süßes & Snacks", "Snacks & sweets"),
    "frozen": ("Tiefkühl", "Frozen"),
    "drinks": ("Getränke", "Drinks"),
    "household_hygiene": ("Drogerie & Haushalt", "Household & toiletries"),
    "other": ("Sonstiges", "Other"),
}


def test_0009_names_every_category_and_changes_nothing_else(tmp_path: Path) -> None:
    """seed-demo data at 0008 → 0009 (D-31): every seeded category gets its German and English
    name of appendix A, each with its normalised form; the key stays, no row and no other value
    changes, and the downgrade drops the names again."""
    path = tmp_path / "data" / "mealmate.db"
    config = alembic_config(path)
    load_demo_0006(path)
    command.upgrade(config, "0008")
    counts, references = row_counts(path), non_null_foreign_keys(path)
    before = rows_of(path, "categories")

    command.upgrade(config, "0009")

    assert row_counts(path) == counts
    assert non_null_foreign_keys(path) == references
    assert_clean(path)
    after = rows_of(path, "categories")
    without_names = [
        {column: value for column, value in row.items() if not column.startswith("name_")}
        for row in after
    ]
    assert without_names == before
    assert {row["key"]: (row["name_de"], row["name_en"]) for row in after} == (
        SEEDED_CATEGORY_NAMES
    )
    norms = {row["key"]: (row["name_de_norm"], row["name_en_norm"]) for row in after}
    assert norms["fruit_vegetables"] == ("obst & gemuese", "fruit & vegetables")
    assert norms["sauces_spices_oils"] == ("sossen, gewuerze & oele", "sauces, spices & oils")
    assert norms["frozen"] == ("tiefkuehl", "frozen")

    command.downgrade(config, "0008")
    assert rows_of(path, "categories") == before
    assert row_counts(path) == counts
    assert_clean(path)


@pytest.mark.parametrize("language", ["de", "en"])
def test_category_names_are_unique_per_language(
    config: Config, database_path: Path, language: str
) -> None:
    """REF-01: no two categories share a name in one language (compared normalised)."""
    command.upgrade(config, "0009")
    column = f"name_{language}_norm"
    with (
        closing(sqlite3.connect(database_path)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="UNIQUE"),
    ):
        connection.execute(
            f"UPDATE categories SET {column} = "  # noqa: S608
            f"(SELECT {column} FROM categories WHERE key = 'other') WHERE key = 'cheese'"
        )


# --- 0007, rule by rule ----------------------------------------------------------------------

NOW = "2026-09-01 10:00:00.000000"
# 60 characters, the most an ingredient name has.
LONG_RICE = "Basmati-Reis aus kontrolliert biologischem Anbau, extra lang"


def insert(connection: sqlite3.Connection, table: str, **values: object) -> str:
    row_id = str(values.setdefault("id", str(uuid.uuid7())))
    values.setdefault("created_at", NOW)
    values.setdefault("updated_at", NOW)
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({marks})",  # noqa: S608
        tuple(values.values()),
    )
    return row_id


def ingredient_0006(
    connection: sqlite3.Connection, name: str, category_id: str, user_id: str, **values: object
) -> str:
    return insert(
        connection,
        "ingredients",
        name=name,
        name_norm=name.lower(),
        category_id=category_id,
        base_unit="g",
        created_by=user_id,
        updated_by=user_id,
        **values,
    )


def product_0006(
    connection: sqlite3.Connection, barcode: str, ingredient_id: str, **values: object
) -> str:
    return insert(
        connection,
        "products",
        barcode=barcode,
        ingredient_id=ingredient_id,
        nutrition_basis="g",
        **({"source": "manual", "user_edited_fields": "[]"} | values),
    )


@pytest.fixture
def rules_database(config: Config, database_path: Path) -> dict[str, str]:
    """A database at 0006 with an ingredient without products (Zwiebeln), one with a product
    from Open Food Facts (Butter) and one with a manual product (Eier), and two with several
    (Nudeln; a long rice name with products without a name), the first three used in a meal
    and on a list (a frozen row, extra items and the checked and hidden lines)."""
    command.upgrade(config, "0006")
    ids: dict[str, str] = {}
    with closing(sqlite3.connect(database_path)) as connection, connection:
        [(category_id,)] = connection.execute("SELECT id FROM categories WHERE key = 'other'")
        user_id = insert(
            connection,
            "users",
            username="anna",
            username_norm="anna",
            display_name="Anna",
            display_name_norm="anna",
            password_hash="!",  # noqa: S106 -- no password at all
            role="user",
            language="de",
            is_active=1,
            meals_public=1,
            lists_public=1,
            filter_hidden='{"meals": [], "lists": []}',
        )
        ids["onions"] = ingredient_0006(
            connection, "Zwiebeln", category_id, user_id, kcal=40, piece_weight_g=150
        )
        ids["butter"] = ingredient_0006(connection, "Butter", category_id, user_id, kcal=700)
        ids["pasta"] = ingredient_0006(
            connection, "Nudeln", category_id, user_id, fat=1.8, density_g_per_ml=0.5
        )
        ids["butter_product"] = product_0006(
            connection,
            "4061453007189",
            ids["butter"],
            name="Irische Butter",
            brand="Kerrygold",
            quantity_text="250 g",
            pack_quantity=250,
            pack_unit="g",
            kcal=741,
            protein=0.6,
            fat=82,
            source="off",
            off_last_modified_at="2026-01-01 00:00:00.000000",
            fetched_at="2026-08-01 00:00:00.000000",
            user_edited_fields='["nutrition_basis", "brand", "name"]',
            pending_update=json.dumps(
                {
                    "nutrition_basis": {"current": "g", "proposed": "ml"},
                    "name": {"current": "Irische Butter", "proposed": "Irische Süßrahmbutter"},
                    "nutrients.protein": {"current": 0.6, "proposed": 0.7},
                }
            ),
            created_by=user_id,
        )
        ids["eggs"] = ingredient_0006(connection, "Eier", category_id, user_id)
        product_0006(
            connection, "4388844009943", ids["eggs"], name="Freilandeier", brand="REWE", kcal=137
        )
        product_0006(
            connection,
            "8005516001475",
            ids["pasta"],
            name="Spaghetti n.5 " + "sehr lange Bezeichnung " * 5,
            brand="Barilla",
            kcal=350,
            fat=2,
            created_by=user_id,
            updated_by=user_id,
        )
        product_0006(connection, "8002331045820", ids["pasta"], brand="De Cecco", kcal=360, sugar=3)
        ids["rice"] = ingredient_0006(connection, LONG_RICE, category_id, user_id)
        # Without a name, from Open Food Facts: with a brand, without one (whose pending name
        # is too long for an ingredient), and a manual one without either.
        product_0006(connection, "4000000001001", ids["rice"], brand="Uncle Ben's", source="off")
        product_0006(
            connection,
            "4000000001002",
            ids["rice"],
            source="off",
            pending_update=json.dumps(
                {"name": {"current": None, "proposed": "Basmati " + "Reis lang " * 10}}
            ),
        )
        product_0006(connection, "4000000001003", ids["rice"], kcal=350)
        meal_id = insert(
            connection, "meals", owner_id=user_id, name="Pasta", name_norm="pasta", servings=2
        )
        for position, key in enumerate(("onions", "butter", "pasta")):
            insert(
                connection,
                "meal_ingredients",
                meal_id=meal_id,
                position=position,
                ingredient_id=ids[key],
                amount=100,
                unit="g",
            )
        list_id = insert(
            connection,
            "shopping_lists",
            owner_id=user_id,
            status="shopping",
            shared_with_partner=0,
            version=1,
            reminder_seed=1,
        )
        list_meal_id = insert(
            connection,
            "list_meals",
            list_id=list_id,
            meal_id=meal_id,
            servings=2,
            meal_servings_snapshot=2,
            meal_name_snapshot="Pasta",
            last_added_at=NOW,
            position=0,
            frozen_at=NOW,
        )
        insert(
            connection,
            "list_meal_ingredients",
            list_meal_id=list_meal_id,
            position=0,
            ingredient_id=ids["pasta"],
            ingredient_name_snapshot="Nudeln",
            base_unit_snapshot="g",
            category_id_snapshot=category_id,
            amount=100,
            unit="g",
        )
        for key in ("onions", "butter"):
            insert(connection, "list_extra_items", list_id=list_id, ingredient_id=ids[key])
        for key, checked, hidden in (("pasta", 1, 0), ("butter", 0, 1)):
            connection.execute(
                "INSERT INTO list_line_states (list_id, line_key, checked, hidden) "
                "VALUES (?, ?, ?, ?)",
                (list_id, f"i:{ids[key]}", checked, hidden),
            )
    return ids


def one(path: Path, ingredient_id: str) -> dict[str, object]:
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        return dict(
            connection.execute(
                "SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)
            ).fetchone()
        )


def references_of(path: Path) -> list[tuple[object, ...]]:
    return query(
        path,
        "SELECT 'meal', ingredient_id FROM meal_ingredients UNION ALL "
        "SELECT 'frozen', ingredient_id FROM list_meal_ingredients UNION ALL "
        "SELECT 'extra', ingredient_id FROM list_extra_items UNION ALL "
        "SELECT 'line', line_key FROM list_line_states ORDER BY 1, 2",
    )


def test_rule_1_an_ingredient_without_products_stays(
    config: Config, database_path: Path, rules_database: dict[str, str]
) -> None:
    before = one(database_path, rules_database["onions"])
    references = references_of(database_path)
    # The checked and hidden lines keep their keys (`i:<ingredient id>`, the ids stay).
    assert [key for kind, key in references if kind == "line"] == sorted(
        f"i:{rules_database[key]}" for key in ("pasta", "butter")
    )

    command.upgrade(config, "0007")

    onions = one(database_path, rules_database["onions"])
    assert {key: onions[key] for key in before} == before
    assert (onions["barcode"], onions["brand"], onions["brand_norm"]) == (None, None, None)
    assert (onions["source"], onions["user_edited_fields"]) == ("manual", "[]")
    assert (onions["pending_update"], onions["fetched_at"]) == (None, None)
    assert references_of(database_path) == references
    assert_clean(database_path)


def test_rule_2_an_ingredient_absorbs_its_only_product(
    config: Config, database_path: Path, rules_database: dict[str, str]
) -> None:
    references = references_of(database_path)

    command.upgrade(config, "0007")

    butter = one(database_path, rules_database["butter"])
    # Its name and manual kcal stay; the rest comes from the product.
    assert (butter["name"], butter["brand"], butter["brand_norm"]) == (
        "Butter",
        "Kerrygold",
        "kerrygold",
    )
    assert (butter["barcode"], butter["quantity_text"], butter["pack_quantity"]) == (
        "4061453007189",
        "250 g",
        250,
    )
    assert (butter["kcal"], butter["protein"], butter["fat"], butter["carbs"]) == (
        700,
        0.6,
        82,
        None,
    )
    assert (butter["source"], butter["off_last_modified_at"], butter["fetched_at"]) == (
        "off",
        "2026-01-01 00:00:00.000000",
        "2026-08-01 00:00:00.000000",
    )
    # The product's edits without the basis, plus the name and kcal the user chose, which a
    # refresh must not overwrite.
    assert json.loads(str(butter["user_edited_fields"])) == ["name", "brand", "nutrients.kcal"]
    # Without the proposed name: the ingredient's name never was the product's.
    assert json.loads(str(butter["pending_update"])) == {
        "nutrients.protein": {"current": 0.6, "proposed": 0.7}
    }
    assert references_of(database_path) == references
    assert_clean(database_path)


def test_rule_2_a_manual_product_with_another_name(
    config: Config, database_path: Path, rules_database: dict[str, str]
) -> None:
    """The ingredient's name stays; a manual ingredient has no user-edited fields."""
    command.upgrade(config, "0007")

    eggs = one(database_path, rules_database["eggs"])
    assert (eggs["name"], eggs["name_norm"], eggs["brand"], eggs["barcode"], eggs["kcal"]) == (
        "Eier",
        "eier",
        "REWE",
        "4388844009943",
        137,
    )
    assert (eggs["source"], eggs["user_edited_fields"], eggs["pending_update"]) == (
        "manual",
        "[]",
        None,
    )
    assert_clean(database_path)


def test_rule_3_an_ingredient_with_several_products_splits(
    config: Config, database_path: Path, rules_database: dict[str, str]
) -> None:
    references = references_of(database_path)
    [(count,)] = query(database_path, "SELECT count(*) FROM ingredients")

    command.upgrade(config, "0007")

    pasta = one(database_path, rules_database["pasta"])
    # Its manual fat, else the average (kcal) or the only value (sugar) of its products.
    assert (pasta["kcal"], pasta["sugar"], pasta["fat"], pasta["protein"]) == (355, 3, 1.8, None)
    assert (pasta["barcode"], pasta["brand"], pasta["source"]) == (None, None, "manual")
    rows = query(
        database_path,
        "SELECT name, name_norm, brand, barcode, kcal, sugar, fat, category_id, density_g_per_ml "
        "FROM ingredients WHERE barcode LIKE '800%' ORDER BY barcode",
    )
    # The product's name, cut at a word boundary to the 60 characters of an ingredient name.
    long_name = "Spaghetti n.5 sehr lange Bezeichnung sehr lange Bezeichnung"
    assert rows == [
        # No name of its own: the ingredient's.
        ("Nudeln", "nudeln", "De Cecco", "8002331045820", 360, 3, None, pasta["category_id"], 0.5),
        (long_name, long_name.lower(), "Barilla", "8005516001475", 350, None, 2,
         pasta["category_id"], 0.5),
    ]  # fmt: skip
    [(after,)] = query(database_path, "SELECT count(*) FROM ingredients")
    assert after == count + 2 + 3  # the pasta's and the rice's products
    # Meals and lists keep pointing at the original ingredient.
    assert references_of(database_path) == references
    assert_clean(database_path)


def test_rule_3_products_without_a_name(
    config: Config, database_path: Path, rules_database: dict[str, str]
) -> None:
    """They take the ingredient's name, plus the barcode's last four digits when they have no
    brand either, so that they can be told apart; on products from Open Food Facts that name
    is user-edited, so a refresh does not silently rename them. A pending name is cut like a
    name from Open Food Facts."""
    command.upgrade(config, "0007")

    rows = query(
        database_path,
        "SELECT name, brand, source, user_edited_fields, pending_update FROM ingredients "
        "WHERE barcode LIKE '4000000001%' ORDER BY barcode",
    )
    cut = "Basmati-Reis aus kontrolliert biologischem Anbau"
    assert [(*row[:3], json.loads(str(row[3]))) for row in rows] == [
        (LONG_RICE, "Uncle Ben's", "off", ["name"]),
        (f"{cut} (1002)", None, "off", ["name"]),
        (f"{cut} (1003)", None, "manual", []),
    ]
    proposed = "Basmati Reis lang Reis lang Reis lang Reis lang Reis lang"
    assert json.loads(str(rows[1][4])) == {"name": {"current": None, "proposed": proposed}}
    assert all(len(name) <= 60 for name, *_ in rows)
    assert_clean(database_path)


def test_a_failing_0007_changes_nothing(
    config: Config, database_path: Path, rules_database: dict[str, str]
) -> None:
    """The upgrade runs in one transaction: when a row cannot be moved half-way through (here
    a product whose user-edited fields are not JSON), the database stays at 0006 as it was."""
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "UPDATE products SET user_edited_fields = '[broken' WHERE barcode = '4000000001003'"
        )
    counts = row_counts(database_path)
    [ingredient_columns] = query(database_path, "SELECT group_concat(name) FROM "
                                 "pragma_table_info('ingredients')")  # fmt: skip

    with pytest.raises(json.JSONDecodeError):
        command.upgrade(config, "0007")

    assert current_revision(database_path) == "0006"
    assert row_counts(database_path) == counts
    assert query(database_path, "SELECT group_concat(name) FROM "
                 "pragma_table_info('ingredients')") == [ingredient_columns]  # fmt: skip
    assert "products" in tables(database_path)
    assert query(database_path, "SELECT count(*) FROM ingredients WHERE kcal = 355") == [(0,)]
    assert_clean(database_path)


def test_the_downgrade_needs_unique_names(config: Config, database_path: Path) -> None:
    """Names may repeat from 0007 on; going back to unique names fails with a clear message
    and changes nothing, until the duplicates are merged or renamed."""
    command.upgrade(config, "head")
    with closing(sqlite3.connect(database_path)) as connection, connection:
        [(category_id,)] = connection.execute("SELECT id FROM categories WHERE key = 'other'")
        for brand in ("Weihenstephan", "Landliebe"):
            insert(
                connection,
                "ingredients",
                name="Milch",
                name_norm="milch",
                name_sort="milch",
                brand=brand,
                category_id=category_id,
                base_unit="ml",
                source="manual",
                user_edited_fields="[]",
            )

    with pytest.raises(RuntimeError, match=r"several ingredients share a name \('milch'\)"):
        command.downgrade(config, "0006")

    assert current_revision(database_path) == HEAD
    assert "products" not in tables(database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("UPDATE ingredients SET name_norm = 'milch landliebe' "
                           "WHERE brand = 'Landliebe'")  # fmt: skip
    command.downgrade(config, "0006")
    assert query(database_path, "SELECT count(*) FROM products") == [(0,)]


def test_full_demo_data_with_lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed-demo` at head, then down to the base (once the two spaghetti brands have names of
    their own) and up again leaves a clean database."""
    data_dir = tmp_path / "data"
    path = data_dir / "mealmate.db"
    upgrade_database(data_dir)
    seed_demo(data_dir, monkeypatch)
    references = non_null_foreign_keys(path)
    assert references["ingredients.created_by"] == len(demo.DEMO_INGREDIENTS)
    assert references["meals.cuisine_id"] == len(demo.DEMO_MEALS)
    assert references["meals.copied_from_meal_id"] == 1
    assert references["list_meals.meal_id"] > 0
    assert references["list_extra_items.ingredient_id"] > 0
    assert_clean(path)

    command.upgrade(alembic_config(path), "head")
    assert non_null_foreign_keys(path) == references
    with pytest.raises(RuntimeError, match="share a name"):
        command.downgrade(alembic_config(path), "base")
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE ingredients SET name_norm = name_norm || ' ' || brand_norm "
                           "WHERE brand_norm IS NOT NULL")  # fmt: skip
    command.downgrade(alembic_config(path), "base")
    command.upgrade(alembic_config(path), "head")
    assert_clean(path)
    assert row_counts(path)["categories"] == len(CATEGORY_KEYS)


def test_models_match_migrations(config: Config, database_path: Path) -> None:
    command.upgrade(config, "head")
    command.check(config)  # raises if autogenerate would produce a migration

    engine = create_migration_engine(database_path)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    engine.dispose()


@pytest.fixture
def begin_probe(database_path: Path) -> Iterator[list[int]]:
    """`PRAGMA foreign_keys` as seen at every BEGIN on any engine for our database file."""
    seen: list[int] = []

    def probe(connection: Connection) -> None:
        if connection.engine.url.database == str(database_path):
            seen.append(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())

    event.listen(Engine, "begin", probe)
    yield seen
    event.remove(Engine, "begin", probe)


def test_env_keeps_foreign_keys_off(config: Config, begin_probe: list[int]) -> None:
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert begin_probe
    assert set(begin_probe) == {0}


def test_migration_engine(database_path: Path) -> None:
    statements: list[str] = []
    engine = create_migration_engine(database_path)
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    with engine.connect() as connection, connection.begin():
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
    engine.dispose()
    assert statements == ["BEGIN IMMEDIATE", "PRAGMA foreign_keys"]


def test_foreign_key_violations_roll_the_upgrade_back(config: Config, database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (parent_id INTEGER REFERENCES parent (id));
            INSERT INTO child VALUES (42);
            """
        )

    with pytest.raises(ForeignKeyViolationError, match=r"child\.rowid=1 -> parent"):
        command.upgrade(config, "head")

    assert tables(database_path) == {"parent", "child"}


def test_offline_mode_is_refused(config: Config) -> None:
    with pytest.raises(SystemExit, match="not supported"):
        command.upgrade(config, "head", sql=True)
