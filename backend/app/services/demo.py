"""Demo data for development and the migration tests (`mealmate seed-demo`, plan § 5.11).

- M2: an admin, a couple, a single user and one open invite (`seed_accounts`);
- M3: ingredients across most categories, about half of them with nutrition (`_insert_catalog`):
  most are generic, without a brand or barcode ("Zwiebeln"); butter, passata and olive oil have
  a brand, a barcode and pack sizes as if scanned (entered by hand, so nothing is refreshed from
  Open Food Facts in development); spaghetti comes in two brands, Barilla and De Cecco, two
  ingredients of the same name.
- M4: meals of every demo user (`_insert_meals`) with cuisines, tags and rows in all kinds of
  units (pieces with a piece weight, spoons, rows "to taste" without an amount, a spoon of
  butter that makes an estimate, bread in pieces without a piece weight that cannot be
  counted); three have photos drawn with Pillow and sent through the real pipeline, and carl
  copied anna's Bolognese ("based on"). carl's meals are private (VIS-02).
- M5a: drafts (`_insert_lists`): anna's "Wochenende", shared with ben, with her meal and one of
  ben's at other servings, a linked and a free-text extra item and a hidden line; ben's
  unshared draft without a name, with a meal he deleted afterwards (detached, "no longer
  available", through the real hook); carl's public "Grillabend" with two of his private
  meals, which others see as "Private meal (N servings)" (VIS-06), and anna's Bolognese: its
  Barilla spaghetti and the De Cecco spaghetti of carl's aglio e olio are two lines.
- M5b: shopping and done lists (`_insert_lists`, through the rules of `services.shopping`): anna's
  shared "Wocheneinkauf" being shopped, with lines checked off by anna and one by ben, a line
  that needs more (ben's meal got more servings after the onions were checked) and a new
  line (coffee, added while shopping); two done lists, finished in different weeks: anna's
  shared "Salatabend" (one line not bought) and carl's "Vorrat".

The content is fixed; only ids, the password, the invite code and the photo keys differ
between runs; the times of shopping and finishing are relative to the time of seeding.
"""

import io
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import hash_password
from app.db.ids import new_id
from app.domain.lists import ingredient_key, text_key
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize, sort_key
from app.domain.units import Unit
from app.media.store import MediaStore
from app.models import (
    Category,
    Couple,
    CoupleMember,
    Ingredient,
    ListExtraItem,
    ListLineState,
    ListMeal,
    Meal,
    MealIngredient,
    MealTag,
    ShoppingList,
    Tag,
)
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.repositories import users as users_repo
from app.schemas.users import Language, Role
from app.services import accounts, aggregation, codes, hooks, shopping
from app.services.context import AuthConfig
from app.services.off_fields import set_brand, set_name

DEMO_USERS: tuple[tuple[str, str, Role, Language], ...] = (
    ("admin", "Admin", "admin", "de"),
    ("anna", "Anna", "user", "de"),
    ("ben", "Ben", "user", "en"),
    ("carl", "Carl", "user", "de"),
)
DEMO_COUPLE = ("anna", "ben")
# Users whose *meals public* switch is off.
DEMO_PRIVATE_MEALS = ("carl",)


def _values(
    kcal: float, protein: float, carbs: float, sugar: float, fat: float
) -> dict[str, float]:
    return dict(zip(NUTRIENT_KEYS, (kcal, protein, carbs, sugar, fat), strict=True))


@dataclass(frozen=True)
class DemoIngredient:
    name: str
    category: str
    creator: str
    base_unit: str = "g"
    piece_weight_g: float | None = None
    density_g_per_ml: float | None = None
    nutrients: Mapping[str, float] = field(default_factory=dict)
    # A branded product as if scanned: brand, barcode, and the pack as text, quantity and unit.
    brand: str | None = None
    barcode: str | None = None
    pack: tuple[str, float, Unit] | None = None


DEMO_INGREDIENTS: tuple[DemoIngredient, ...] = (
    DemoIngredient("Äpfel", "fruit_vegetables", "anna", piece_weight_g=180,
                   nutrients=_values(52, 0.3, 11.4, 10.4, 0.2)),
    DemoIngredient("Zwiebeln", "fruit_vegetables", "ben", piece_weight_g=150,
                   nutrients=_values(40, 1.1, 9.3, 4.2, 0.1)),
    DemoIngredient("Knoblauch", "fruit_vegetables", "carl", piece_weight_g=5),
    DemoIngredient("Tomaten", "fruit_vegetables", "anna", piece_weight_g=100,
                   nutrients=_values(18, 0.9, 3.9, 2.6, 0.2)),
    DemoIngredient("Kartoffeln", "fruit_vegetables", "ben", piece_weight_g=150,
                   nutrients=_values(77, 2.0, 17.0, 0.8, 0.1)),
    DemoIngredient("Karotten", "fruit_vegetables", "carl", piece_weight_g=80),
    DemoIngredient("Brot", "bread_bakery", "anna", nutrients=_values(245, 8.5, 45.0, 3.0, 1.6)),
    DemoIngredient("Milch", "dairy_eggs", "anna", base_unit="ml", density_g_per_ml=1.03,
                   nutrients=_values(64, 3.4, 4.8, 4.8, 3.5)),
    DemoIngredient("Eier", "dairy_eggs", "carl", piece_weight_g=60,
                   nutrients=_values(155, 13.0, 1.1, 1.1, 11.0)),
    DemoIngredient("Butter", "dairy_eggs", "ben", nutrients=_values(741, 0.6, 0.6, 0.6, 82.0),
                   brand="Kerrygold", barcode="4061453007189", pack=("250 g", 250, Unit.G)),
    DemoIngredient("Joghurt", "dairy_eggs", "ben"),
    DemoIngredient("Gouda", "cheese", "anna"),
    DemoIngredient("Parmesan", "cheese", "carl", nutrients=_values(392, 35.8, 3.2, 0.9, 25.8)),
    DemoIngredient("Hähnchenbrust", "meat_fish", "ben",
                   nutrients=_values(110, 23.0, 0.0, 0.0, 1.2)),
    DemoIngredient("Hackfleisch", "meat_fish", "anna"),
    DemoIngredient("Salami", "sausage_deli", "carl"),
    DemoIngredient("Tofu", "plant_based", "carl"),
    DemoIngredient("Spaghetti", "pasta_rice_grains", "anna",
                   nutrients=_values(359, 12.0, 71.0, 3.5, 2.0),
                   brand="Barilla", barcode="8005516001475", pack=("500 g", 500, Unit.G)),
    DemoIngredient("Spaghetti", "pasta_rice_grains", "ben",
                   nutrients=_values(353, 13.0, 70.0, 3.5, 1.5),
                   brand="De Cecco", barcode="8002331045820", pack=("500 g", 500, Unit.G)),
    DemoIngredient("Reis", "pasta_rice_grains", "ben", nutrients=_values(350, 7.0, 78.0, 0.2, 0.6)),
    DemoIngredient("Passierte Tomaten", "canned_jars", "anna",
                   nutrients=_values(36, 1.6, 5.4, 4.8, 0.2),
                   brand="Mutti", barcode="8004207009356", pack=("700 g", 700, Unit.G)),
    DemoIngredient("Olivenöl", "sauces_spices_oils", "ben", base_unit="ml", density_g_per_ml=0.92,
                   nutrients=_values(828, 0.0, 0.0, 0.0, 92.0),
                   brand="Bertolli", barcode="4017952000633", pack=("750 ml", 750, Unit.ML)),
    DemoIngredient("Salz", "sauces_spices_oils", "ben"),
    DemoIngredient("Pfeffer", "sauces_spices_oils", "carl"),
    DemoIngredient("Mehl", "baking", "carl"),
    DemoIngredient("Zucker", "baking", "anna", nutrients=_values(400, 0.0, 100.0, 100.0, 0.0)),
    DemoIngredient("Erdbeermarmelade", "breakfast_spreads", "ben"),
    DemoIngredient("Zartbitterschokolade", "snacks_sweets", "carl"),
    DemoIngredient("Erbsen (TK)", "frozen", "anna"),
    DemoIngredient("Kaffee", "drinks", "carl"),
)  # fmt: skip


type RGB = tuple[int, int, int]


@dataclass(frozen=True)
class DemoRow:
    """A meal row; `brand` picks one of several ingredients of the same name."""

    ingredient: str
    amount: float | None = None
    unit: Unit | None = None
    note: str | None = None
    brand: str | None = None


@dataclass(frozen=True)
class DemoPhoto:
    """A simple picture: a vertical gradient, a plate and the food on it."""

    top: RGB
    bottom: RGB
    food: RGB


@dataclass(frozen=True)
class DemoMeal:
    name: str
    owner: str
    servings: int = 1
    cuisine: str | None = None
    tags: tuple[str, ...] = ()
    rows: tuple[DemoRow, ...] = ()
    instructions: str | None = None
    source_url: str | None = None
    photo: DemoPhoto | None = None
    # The name of another demo meal this one is a copy of (everything else comes from it).
    copy_of: str | None = None


_TO_TASTE = "nach Geschmack"

DEMO_MEALS: tuple[DemoMeal, ...] = (
    DemoMeal(
        "Spaghetti Bolognese", "anna", servings=4, cuisine="italian", tags=("Pasta", "Klassiker"),
        rows=(
            DemoRow("Spaghetti", 500, Unit.G, brand="Barilla"),
            DemoRow("Hackfleisch", 400, Unit.G),
            DemoRow("Passierte Tomaten", 700, Unit.G),
            DemoRow("Zwiebeln", 1, Unit.PIECE),
            DemoRow("Knoblauch", 2, Unit.PIECE, "fein gehackt"),
            DemoRow("Olivenöl", 2, Unit.TBSP),
            DemoRow("Parmesan", 50, Unit.G, "gerieben"),
            DemoRow("Salz", note=_TO_TASTE),
            DemoRow("Pfeffer", note=_TO_TASTE),
        ),
        instructions="Zwiebeln und Knoblauch in Olivenöl andünsten.\n"
        "Hackfleisch krümelig braten, passierte Tomaten dazugeben und 30 Minuten köcheln.\n"
        "Mit Salz und Pfeffer abschmecken, mit den Spaghetti und Parmesan servieren.",
        source_url="https://de.wikipedia.org/wiki/Sauce_bolognese",
        photo=DemoPhoto(top=(250, 214, 165), bottom=(196, 92, 58), food=(178, 44, 32)),
    ),
    DemoMeal(
        "Pfannkuchen", "anna", servings=2, cuisine="german", tags=("Süß", "Schnell"),
        rows=(
            DemoRow("Mehl", 200, Unit.G),
            DemoRow("Milch", 300, Unit.ML),
            DemoRow("Eier", 2, Unit.PIECE),
            DemoRow("Zucker", 1, Unit.TBSP),
            DemoRow("Salz", note="1 Prise"),
            DemoRow("Butter", 1, Unit.TBSP, "zum Braten"),
        ),
        instructions="Mehl, Milch, Eier, Zucker und Salz glatt rühren und 10 Minuten quellen "
        "lassen.\nIn Butter goldbraun ausbacken.",
        photo=DemoPhoto(top=(255, 243, 205), bottom=(233, 180, 76), food=(240, 196, 98)),
    ),
    DemoMeal(
        "Hähnchen-Reis-Pfanne", "ben", servings=2, cuisine="chinese", tags=("Schnell",),
        rows=(
            DemoRow("Hähnchenbrust", 300, Unit.G, "in Streifen"),
            DemoRow("Reis", 200, Unit.G),
            DemoRow("Erbsen (TK)", 150, Unit.G),
            DemoRow("Karotten", 2, Unit.PIECE),
            DemoRow("Zwiebeln", 1, Unit.PIECE),
            DemoRow("Olivenöl", 1, Unit.TBSP),
        ),
        instructions="Reis kochen. Hähnchen scharf anbraten, Gemüse dazugeben.\n"
        "Den Reis unterheben und alles kurz zusammen braten.",
    ),
    DemoMeal(
        "Tomatensalat", "ben", servings=2, cuisine="mediterranean", tags=("Vegetarisch", "Salat"),
        rows=(
            DemoRow("Tomaten", 4, Unit.PIECE),
            DemoRow("Zwiebeln", 0.5, Unit.PIECE),
            DemoRow("Olivenöl", 3, Unit.TBSP),
            DemoRow("Salz", note=_TO_TASTE),
            DemoRow("Pfeffer", note=_TO_TASTE),
        ),
        instructions="Tomaten in Scheiben, Zwiebel in feine Ringe schneiden.\n"
        "Mit Olivenöl, Salz und Pfeffer anmachen.",
        photo=DemoPhoto(top=(220, 239, 200), bottom=(84, 140, 70), food=(214, 58, 48)),
    ),
    DemoMeal(
        "Ofenkartoffeln mit Kräuterjoghurt", "carl", servings=3, cuisine="german",
        tags=("Vegetarisch",),
        rows=(
            DemoRow("Kartoffeln", 1, Unit.KG),
            DemoRow("Olivenöl", 2, Unit.TBSP),
            DemoRow("Joghurt", 250, Unit.G),
            DemoRow("Knoblauch", 1, Unit.PIECE),
            DemoRow("Salz", note=_TO_TASTE),
        ),
        instructions="Kartoffeln vierteln, mit Öl und Salz 40 Minuten bei 200 °C backen.\n"
        "Joghurt mit Knoblauch verrühren und dazu reichen.",
    ),
    DemoMeal(
        "Tofu-Gemüse-Curry", "carl", servings=2, cuisine="thai", tags=("Vegan",),
        rows=(
            DemoRow("Tofu", 400, Unit.G),
            DemoRow("Karotten", 3, Unit.PIECE),
            DemoRow("Zwiebeln", 1, Unit.PIECE),
            DemoRow("Reis", 250, Unit.G),
            DemoRow("Olivenöl", 1, Unit.TBSP),
        ),
    ),
    DemoMeal(
        "Käsebrot", "admin", cuisine="german", tags=("Frühstück", "Schnell"),
        rows=(
            DemoRow("Brot", 2, Unit.PIECE, "Scheiben"),
            DemoRow("Butter", 10, Unit.G),
            DemoRow("Gouda", 40, Unit.G),
        ),
    ),
    DemoMeal(
        "Spaghetti aglio e olio", "carl", servings=2, cuisine="italian", tags=("Pasta", "Schnell"),
        rows=(
            DemoRow("Spaghetti", 250, Unit.G, brand="De Cecco"),
            DemoRow("Knoblauch", 3, Unit.PIECE, "in Scheiben"),
            DemoRow("Olivenöl", 4, Unit.TBSP),
            DemoRow("Salz", note=_TO_TASTE),
        ),
    ),
    DemoMeal("Spaghetti Bolognese", "carl", copy_of="Spaghetti Bolognese"),
)  # fmt: skip


# Put on ben's draft and then deleted by him, so the list shows it as "no longer available".
DEMO_DELETED_MEAL = DemoMeal(
    "Kartoffelsuppe", "ben", servings=4, cuisine="german",
    rows=(
        DemoRow("Kartoffeln", 800, Unit.G),
        DemoRow("Karotten", 2, Unit.PIECE),
        DemoRow("Zwiebeln", 1, Unit.PIECE),
        DemoRow("Salz", note=_TO_TASTE),
    ),
)  # fmt: skip


@dataclass(frozen=True)
class DemoListMeal:
    owner: str
    meal: str
    servings: int


@dataclass(frozen=True)
class DemoExtra:
    """A linked extra item (`ingredient`) or a free-text one (`text`, category *Other*)."""

    ingredient: str | None = None
    brand: str | None = None
    amount: float | None = None
    unit: Unit | None = None
    text: str | None = None
    amount_text: str | None = None


@dataclass(frozen=True)
class DemoCheck:
    """A line checked off by `user`: an ingredient's name (and brand) or a free-text item's
    text."""

    line: str
    user: str
    brand: str | None = None


@dataclass(frozen=True)
class DemoShopping:
    """Shopping mode for a demo list: started `started_hours_ago`, lines checked off one
    minute apart, then meals with new servings (owner, meal, servings) and extra items added
    while shopping; `finished_days_ago` makes it done (it was shopped that day)."""

    started_hours_ago: int
    checks: tuple[DemoCheck, ...] = ()
    new_servings: tuple[tuple[str, str, int], ...] = ()
    added: tuple[DemoExtra, ...] = ()
    finished_days_ago: int | None = None


@dataclass(frozen=True)
class DemoList:
    owner: str
    name: str | None
    reminder_seed: int
    shared: bool = False
    meals: tuple[DemoListMeal, ...] = ()
    extras: tuple[DemoExtra, ...] = ()
    # Ingredient lines removed for this list (LIST-07).
    hidden: tuple[str, ...] = ()
    shopping: DemoShopping | None = None


DEMO_LISTS: tuple[DemoList, ...] = (
    DemoList(
        "anna", "Wochenende", reminder_seed=3, shared=True,
        meals=(
            DemoListMeal("anna", "Pfannkuchen", 4),
            DemoListMeal("ben", "Tomatensalat", 3),
        ),
        extras=(
            DemoExtra(ingredient="Äpfel", amount=6, unit=Unit.PIECE),
            DemoExtra(ingredient="Zwiebeln"),
            DemoExtra(text="Geburtstagskerzen", amount_text="1 Packung"),
        ),
        hidden=("Salz",),
    ),
    DemoList(
        "ben", None, reminder_seed=7,
        meals=(
            DemoListMeal("ben", "Hähnchen-Reis-Pfanne", 2),
            DemoListMeal("ben", DEMO_DELETED_MEAL.name, 4),
        ),
    ),
    DemoList(
        "carl", "Grillabend", reminder_seed=12,
        meals=(
            DemoListMeal("carl", "Tofu-Gemüse-Curry", 4),
            DemoListMeal("anna", "Spaghetti Bolognese", 2),
            DemoListMeal("carl", "Spaghetti aglio e olio", 4),
        ),
        extras=(DemoExtra(text="Grillkohle", amount_text="2 Säcke"),),
    ),
    DemoList(
        "anna", "Wocheneinkauf", reminder_seed=21, shared=True,
        meals=(
            DemoListMeal("anna", "Spaghetti Bolognese", 4),
            DemoListMeal("ben", "Hähnchen-Reis-Pfanne", 2),
        ),
        extras=(
            DemoExtra(ingredient="Milch", amount=1, unit=Unit.L),
            DemoExtra(text="Küchenrolle"),
        ),
        shopping=DemoShopping(
            started_hours_ago=1,
            checks=(
                DemoCheck("Spaghetti", "anna", brand="Barilla"),
                DemoCheck("Milch", "anna"),
                DemoCheck("Zwiebeln", "anna"),
                DemoCheck("Hackfleisch", "ben"),
            ),
            # Two onions were checked; now three are needed ("+1 Stk.").
            new_servings=(("ben", "Hähnchen-Reis-Pfanne", 4),),
            added=(DemoExtra(ingredient="Kaffee", amount=500, unit=Unit.G),),
        ),
    ),
    DemoList(
        "anna", "Salatabend", reminder_seed=4, shared=True,
        meals=(DemoListMeal("ben", "Tomatensalat", 4),),
        extras=(DemoExtra(ingredient="Brot", amount=1, unit=Unit.PIECE),),
        shopping=DemoShopping(
            started_hours_ago=2,
            checks=(
                DemoCheck("Tomaten", "ben"),
                DemoCheck("Zwiebeln", "ben"),
                DemoCheck("Olivenöl", "anna"),
                DemoCheck("Brot", "anna"),
                DemoCheck("Salz", "anna"),
            ),  # Pfeffer was not bought.
            finished_days_ago=2,
        ),
    ),
    DemoList(
        "carl", "Vorrat", reminder_seed=58,
        meals=(DemoListMeal("carl", "Tofu-Gemüse-Curry", 2),),
        extras=(DemoExtra(text="Spülmittel", amount_text="1 Flasche"),),
        shopping=DemoShopping(
            started_hours_ago=1,
            checks=(
                DemoCheck("Tofu", "carl"),
                DemoCheck("Karotten", "carl"),
                DemoCheck("Zwiebeln", "carl"),
                DemoCheck("Reis", "carl"),
                DemoCheck("Olivenöl", "carl"),
                DemoCheck("Spülmittel", "carl"),
            ),
            finished_days_ago=9,
        ),
    ),
)  # fmt: skip


class DemoRefusedError(RuntimeError):
    """The database already has users; demo data is only for empty installations."""


@dataclass(frozen=True, repr=False)
class DemoSeed:
    password: str
    invite_url: str
    user_ids: dict[str, str]


async def _demo_password(config: AuthConfig) -> tuple[str, str]:
    """The same random password for every demo user, and its hash."""
    codes.require_public_url(config)
    password = secrets.token_urlsafe(12)
    return password, await hash_password(password, rounds=config.bcrypt_rounds)


async def _insert_accounts(
    session: AsyncSession,
    config: AuthConfig,
    password: str,
    password_hash: str,
    *,
    now: datetime,
) -> DemoSeed:
    if await users_repo.any_exists(session):
        raise DemoRefusedError("the database already has users")
    ids: dict[str, str] = {}
    for username, display_name, role, language in DEMO_USERS:
        user = await accounts.insert_user(
            session,
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            role=role,
            language=language,
            now=now,
        )
        user.meals_public = username not in DEMO_PRIVATE_MEALS
        ids[username] = user.id
    requester, addressee = (ids[name] for name in DEMO_COUPLE)
    couple = Couple(
        requester_id=requester,
        addressee_id=addressee,
        status="accepted",
        accepted_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(couple)
    await session.flush()
    session.add_all(
        [
            CoupleMember(user_id=requester, couple_id=couple.id),
            CoupleMember(user_id=addressee, couple_id=couple.id),
        ]
    )
    invite = await codes.insert_invite(
        session, config, actor_id=ids["admin"], tailscale_share_url=None, now=now
    )
    return DemoSeed(password=password, invite_url=invite.url, user_ids=ids)


def _seeded_category_ids(rows: Iterable[Category]) -> dict[str, str]:
    """The seeded categories' ids by key; the demo uses no others."""
    return {row.key: row.id for row in rows if row.key is not None}


async def _insert_catalog(
    session: AsyncSession, user_ids: Mapping[str, str], *, now: datetime
) -> None:
    categories = _seeded_category_ids(await reference_repo.categories_in_order(session))
    for item in DEMO_INGREDIENTS:
        creator = user_ids[item.creator]
        quantity_text, pack_quantity, pack_unit = item.pack or (None, None, None)
        ingredient = Ingredient(
            barcode=item.barcode,
            category_id=categories[item.category],
            base_unit=item.base_unit,
            piece_weight_g=item.piece_weight_g,
            density_g_per_ml=item.density_g_per_ml,
            quantity_text=quantity_text,
            pack_quantity=pack_quantity,
            pack_unit=None if pack_unit is None else pack_unit.value,
            source="manual",
            user_edited_fields=[],
            created_by=creator,
            updated_by=creator,
            created_at=now,
            updated_at=now,
        )
        set_name(ingredient, item.name)
        set_brand(ingredient, item.brand)
        ingredient.set_nutrients({key: item.nutrients.get(key) for key in NUTRIENT_KEYS})
        session.add(ingredient)
    await session.flush()


def demo_picture(photo: DemoPhoto) -> bytes:
    """A 1200 x 900 JPEG, as a phone would upload it."""
    size = (1200, 900)
    mask = Image.linear_gradient("L").resize(size)
    picture = Image.composite(
        Image.new("RGB", size, photo.bottom), Image.new("RGB", size, photo.top), mask
    )
    draw = ImageDraw.Draw(picture)
    draw.ellipse((300, 150, 900, 750), fill=(246, 244, 238), outline=(205, 200, 190), width=14)
    draw.ellipse((410, 260, 790, 640), fill=photo.food)
    buffer = io.BytesIO()
    picture.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def _original(meal: DemoMeal) -> DemoMeal:
    return next(item for item in DEMO_MEALS if item.name == meal.copy_of and not item.copy_of)


async def _write_photos(media: MediaStore) -> list[str | None]:
    """The photo key of each demo meal (by index); the files are written first, outside the
    transaction. A copy gets its own copy of its original's files (MEAL-08)."""
    keys: list[str | None] = []
    for meal in DEMO_MEALS:
        if meal.copy_of is not None:
            original_key = keys[DEMO_MEALS.index(_original(meal))]
            keys.append(None if original_key is None else await media.copy_in_thread(original_key))
        elif meal.photo is not None:
            keys.append(await media.process_and_write(demo_picture(meal.photo)))
        else:
            keys.append(None)
    return keys


class _IngredientIds:
    """The demo ingredients' ids by name and brand; a name alone is enough while only one
    ingredient has it."""

    def __init__(self, rows: Iterable[tuple[str, str, str | None]]) -> None:
        self._ids: dict[str, dict[str | None, str]] = {}
        for row_id, name_norm, brand_norm in rows:
            self._ids.setdefault(name_norm, {})[brand_norm] = row_id

    def __call__(self, name: str, brand: str | None = None) -> str:
        by_brand = self._ids[normalize(name)]
        if brand is None:
            [only] = by_brand.values()
            return only
        return by_brand[normalize(brand)]


async def _ingredient_ids(session: AsyncSession) -> _IngredientIds:
    result = await session.execute(
        select(Ingredient.id, Ingredient.name_norm, Ingredient.brand_norm)
    )
    return _IngredientIds((row[0], row[1], row[2]) for row in result)


def _add_rows(
    session: AsyncSession,
    meal_id: str,
    rows: tuple[DemoRow, ...],
    ingredient_ids: _IngredientIds,
    *,
    now: datetime,
) -> None:
    session.add_all(
        MealIngredient(
            meal_id=meal_id,
            position=position,
            ingredient_id=ingredient_ids(row.ingredient, row.brand),
            amount=row.amount,
            unit=None if row.unit is None else row.unit.value,
            note=row.note,
            created_at=now,
            updated_at=now,
        )
        for position, row in enumerate(rows)
    )


async def _insert_meals(
    session: AsyncSession,
    user_ids: Mapping[str, str],
    photo_keys: list[str | None],
    *,
    now: datetime,
) -> None:
    ingredient_ids = await _ingredient_ids(session)
    cuisine_ids = {row.key: row.id for row in await reference_repo.all_cuisines(session)}
    tag_ids: dict[str, str] = {}
    meal_ids: dict[tuple[str, str], str] = {}
    for demo, photo_key in zip(DEMO_MEALS, photo_keys, strict=True):
        source = demo if demo.copy_of is None else _original(demo)
        meal = Meal(
            owner_id=user_ids[demo.owner],
            name=source.name,
            name_norm=normalize(source.name),
            name_sort=sort_key(source.name),
            instructions=source.instructions,
            source_url=source.source_url,
            servings=source.servings,
            cuisine_id=None if source.cuisine is None else cuisine_ids[source.cuisine],
            photo_key=photo_key,
            copied_from_meal_id=(
                None if demo.copy_of is None else meal_ids[(source.owner, source.name)]
            ),
            created_at=now,
            updated_at=now,
        )
        session.add(meal)
        await session.flush()
        meal_ids[(demo.owner, demo.name)] = meal.id
        for name in source.tags:
            if (name_norm := normalize(name)) not in tag_ids:
                tag = Tag(name=name, name_norm=name_norm, created_at=now, updated_at=now)
                session.add(tag)
                await session.flush()
                tag_ids[name_norm] = tag.id
            session.add(MealTag(meal_id=meal.id, tag_id=tag_ids[name_norm]))
        _add_rows(session, meal.id, source.rows, ingredient_ids, now=now)
    await session.flush()


async def _insert_deleted_meal(
    session: AsyncSession, user_ids: Mapping[str, str], *, now: datetime
) -> Meal:
    """`DEMO_DELETED_MEAL`, to be put on a list and deleted there."""
    demo = DEMO_DELETED_MEAL
    meal = Meal(
        owner_id=user_ids[demo.owner],
        name=demo.name,
        name_norm=normalize(demo.name),
        name_sort=sort_key(demo.name),
        servings=demo.servings,
        created_at=now,
        updated_at=now,
    )
    session.add(meal)
    await session.flush()
    _add_rows(session, meal.id, demo.rows, await _ingredient_ids(session), now=now)
    await session.flush()
    return meal


def _extra_item(
    shopping_list: ShoppingList,
    extra: DemoExtra,
    added_by: str,
    ingredient_ids: _IngredientIds,
    categories: Mapping[str, str],
    *,
    now: datetime,
) -> ListExtraItem:
    return ListExtraItem(
        list_id=shopping_list.id,
        ingredient_id=(
            None if extra.ingredient is None else ingredient_ids(extra.ingredient, extra.brand)
        ),
        text=extra.text,
        amount=extra.amount,
        unit=None if extra.unit is None else extra.unit.value,
        amount_text=extra.amount_text,
        category_id=None if extra.text is None else categories["other"],
        added_by=added_by,
        created_at=now,
        updated_at=now,
    )


async def _shop(
    session: AsyncSession,
    shopping_list: ShoppingList,
    demo: DemoShopping,
    user_ids: Mapping[str, str],
    ingredient_ids: _IngredientIds,
    *,
    now: datetime,
) -> None:
    """Start shopping a demo list, check lines off, change it while shopping and finish it,
    with the rules of shopping mode (plan § 5.7)."""
    day = now - timedelta(days=demo.finished_days_ago or 0)
    started = day - timedelta(hours=demo.started_hours_ago)
    shopping_list.created_at = started - timedelta(days=1)
    await shopping.start(session, shopping_list, now=started)
    content = await aggregation.load(session, [shopping_list])
    current = aggregation.current_lines(content, shopping_list)
    extras = {row.text: row for row in content.extras.get(shopping_list.id, []) if row.text}
    for minute, check in enumerate(demo.checks, start=1):
        text_extra = extras.get(check.line)
        line_key = (
            ingredient_key(ingredient_ids(check.line, check.brand))
            if text_extra is None
            else text_key(text_extra.id)
        )
        await shopping.set_checked(
            session,
            shopping_list,
            line_key,
            checked=True,
            snapshot=aggregation.check_snapshot(current[line_key], text_extra),
            user_id=user_ids[check.user],
            at=started + timedelta(minutes=minute),
            op_id=new_id(),
        )
    list_meals = {
        (row.meal_owner_id_snapshot, row.meal_name_snapshot): row
        for row in content.meals.get(shopping_list.id, [])
    }
    for owner, meal, servings in demo.new_servings:
        list_meals[(user_ids[owner], meal)].servings = servings
    categories = _seeded_category_ids(content.categories.values())
    added = [
        _extra_item(
            shopping_list, extra, shopping_list.owner_id, ingredient_ids, categories, now=day
        )
        for extra in demo.added
    ]
    session.add_all(added)
    await shopping.snapshot_extras(session, added)
    if demo.finished_days_ago is not None:
        shopping.finish(shopping_list, at=day, now=day)
    await session.flush()


async def _insert_lists(
    session: AsyncSession, user_ids: Mapping[str, str], *, now: datetime
) -> None:
    """The demo drafts; the meal that gets deleted goes through the real hook (LIST-15)."""
    ingredient_ids = await _ingredient_ids(session)
    categories = _seeded_category_ids(await reference_repo.categories_in_order(session))
    deleted = await _insert_deleted_meal(session, user_ids, now=now)
    every_meal = await meals_repo.search(
        session, owner_ids=list(user_ids.values()), query="", cuisine_ids=(), tag_ids=()
    )
    meals = {
        (meal.owner_id, meal.name): meal for meal in every_meal if meal.copied_from_meal_id is None
    }
    for demo in DEMO_LISTS:
        owner_id = user_ids[demo.owner]
        shopping_list = ShoppingList(
            owner_id=owner_id,
            name=demo.name,
            status="draft",
            shared_with_partner=demo.shared,
            version=0,
            reminder_seed=demo.reminder_seed,
            created_at=now,
            updated_at=now,
        )
        session.add(shopping_list)
        await session.flush()
        for position, item in enumerate(demo.meals):
            meal = meals[(user_ids[item.owner], item.meal)]
            session.add(
                ListMeal(
                    list_id=shopping_list.id,
                    meal_id=meal.id,
                    servings=item.servings,
                    meal_servings_snapshot=meal.servings,
                    meal_name_snapshot=meal.name,
                    meal_owner_id_snapshot=meal.owner_id,
                    added_by=owner_id,
                    last_added_at=now,
                    position=position,
                    created_at=now,
                    updated_at=now,
                )
            )
        for extra in demo.extras:
            session.add(
                _extra_item(shopping_list, extra, owner_id, ingredient_ids, categories, now=now)
            )
        session.add_all(
            ListLineState(
                list_id=shopping_list.id,
                line_key=ingredient_key(ingredient_ids(name)),
                checked=False,
                hidden=True,
            )
            for name in demo.hidden
        )
        await session.flush()
        if demo.shopping is not None:
            await _shop(session, shopping_list, demo.shopping, user_ids, ingredient_ids, now=now)
    await session.flush()
    await hooks.on_meal_deleted(session, deleted.id, now=now)
    await session.delete(deleted)
    await session.flush()


async def seed_accounts(session: AsyncSession, config: AuthConfig, *, now: datetime) -> DemoSeed:
    """The demo users (all with one random password), the couple and an open invite."""
    password, password_hash = await _demo_password(config)
    async with session.begin():
        return await _insert_accounts(session, config, password, password_hash, now=now)


async def seed_demo(
    session: AsyncSession, config: AuthConfig, media: MediaStore, *, now: datetime
) -> DemoSeed:
    """Accounts, catalog, meals and lists in one transaction: if anything fails, nothing is left
    behind (but photo files, which `mealmate jobs cleanup` removes) and `seed-demo` can simply
    run again."""
    password, password_hash = await _demo_password(config)
    photo_keys = await _write_photos(media)
    async with session.begin():
        seed = await _insert_accounts(session, config, password, password_hash, now=now)
        await _insert_catalog(session, seed.user_ids, now=now)
        await session.flush()
        await _insert_meals(session, seed.user_ids, photo_keys, now=now)
        await _insert_lists(session, seed.user_ids, now=now)
    return seed
