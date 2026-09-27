"""Demo data for development and the migration tests (`mealmate seed-demo`, plan § 5.11).

- M2: an admin, a couple, a single user and one open invite (`seed_accounts`);
- M3: ingredients across most categories, about half of them with manual nutrition, and a few
  products entered by hand (`seed_catalog`): Spaghetti has two products (an average), Milch
  has manual values and a product (the hint).

Later milestones add meals, lists and history. The content is fixed; only ids, the password and
the invite code differ between runs.
"""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import hash_password
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize
from app.domain.units import Unit
from app.models import Couple, CoupleMember, Ingredient, Product
from app.repositories import reference as reference_repo
from app.repositories import users as users_repo
from app.schemas.users import Language, Role
from app.services import accounts, codes
from app.services.context import AuthConfig
from app.services.products import DATA_FIELDS

DEMO_USERS: tuple[tuple[str, str, Role, Language], ...] = (
    ("admin", "Admin", "admin", "de"),
    ("anna", "Anna", "user", "de"),
    ("ben", "Ben", "user", "en"),
    ("carl", "Carl", "user", "de"),
)
DEMO_COUPLE = ("anna", "ben")


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
    manual: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DemoProduct:
    barcode: str
    ingredient: str
    creator: str
    name: str
    brand: str
    quantity_text: str
    pack_quantity: float
    pack_unit: Unit
    nutrients: Mapping[str, float]


DEMO_INGREDIENTS: tuple[DemoIngredient, ...] = (
    DemoIngredient("Äpfel", "fruit_vegetables", "anna", piece_weight_g=180,
                   manual=_values(52, 0.3, 11.4, 10.4, 0.2)),
    DemoIngredient("Zwiebeln", "fruit_vegetables", "ben", piece_weight_g=150,
                   manual=_values(40, 1.1, 9.3, 4.2, 0.1)),
    DemoIngredient("Knoblauch", "fruit_vegetables", "carl", piece_weight_g=5),
    DemoIngredient("Tomaten", "fruit_vegetables", "anna", piece_weight_g=100,
                   manual=_values(18, 0.9, 3.9, 2.6, 0.2)),
    DemoIngredient("Kartoffeln", "fruit_vegetables", "ben", piece_weight_g=150,
                   manual=_values(77, 2.0, 17.0, 0.8, 0.1)),
    DemoIngredient("Karotten", "fruit_vegetables", "carl", piece_weight_g=80),
    DemoIngredient("Brot", "bread_bakery", "anna", manual=_values(245, 8.5, 45.0, 3.0, 1.6)),
    DemoIngredient("Milch", "dairy_eggs", "anna", base_unit="ml", density_g_per_ml=1.03,
                   manual=_values(64, 3.4, 4.8, 4.8, 3.5)),
    DemoIngredient("Eier", "dairy_eggs", "carl", piece_weight_g=60,
                   manual=_values(155, 13.0, 1.1, 1.1, 11.0)),
    DemoIngredient("Butter", "dairy_eggs", "ben"),
    DemoIngredient("Joghurt", "dairy_eggs", "ben"),
    DemoIngredient("Gouda", "cheese", "anna"),
    DemoIngredient("Parmesan", "cheese", "carl", manual=_values(392, 35.8, 3.2, 0.9, 25.8)),
    DemoIngredient("Hähnchenbrust", "meat_fish", "ben",
                   manual=_values(110, 23.0, 0.0, 0.0, 1.2)),
    DemoIngredient("Hackfleisch", "meat_fish", "anna"),
    DemoIngredient("Salami", "sausage_deli", "carl"),
    DemoIngredient("Tofu", "plant_based", "carl"),
    DemoIngredient("Spaghetti", "pasta_rice_grains", "anna"),
    DemoIngredient("Reis", "pasta_rice_grains", "ben", manual=_values(350, 7.0, 78.0, 0.2, 0.6)),
    DemoIngredient("Passierte Tomaten", "canned_jars", "anna"),
    DemoIngredient("Olivenöl", "sauces_spices_oils", "ben", base_unit="ml", density_g_per_ml=0.92),
    DemoIngredient("Salz", "sauces_spices_oils", "ben"),
    DemoIngredient("Pfeffer", "sauces_spices_oils", "carl"),
    DemoIngredient("Mehl", "baking", "carl"),
    DemoIngredient("Zucker", "baking", "anna", manual=_values(400, 0.0, 100.0, 100.0, 0.0)),
    DemoIngredient("Erdbeermarmelade", "breakfast_spreads", "ben"),
    DemoIngredient("Zartbitterschokolade", "snacks_sweets", "carl"),
    DemoIngredient("Erbsen (TK)", "frozen", "anna"),
    DemoIngredient("Kaffee", "drinks", "carl"),
)  # fmt: skip

DEMO_PRODUCTS: tuple[DemoProduct, ...] = (
    DemoProduct("8005516001475", "Spaghetti", "anna", "Spaghetti n.5", "Barilla", "500 g",
                500, Unit.G, _values(359, 12.0, 71.0, 3.5, 2.0)),
    DemoProduct("8002331045820", "Spaghetti", "ben", "Spaghetti n.12", "De Cecco", "500 g",
                500, Unit.G, _values(353, 13.0, 70.0, 3.5, 1.5)),
    DemoProduct("4028173104529", "Milch", "ben", "Frische Vollmilch 3,5 %", "Weihenstephan",
                "1 l", 1, Unit.L, _values(65, 3.5, 4.8, 4.8, 3.5)),
    DemoProduct("4061453007189", "Butter", "carl", "Original Irische Butter", "Kerrygold",
                "250 g", 250, Unit.G, _values(741, 0.6, 0.6, 0.6, 82.0)),
    DemoProduct("8004207009356", "Passierte Tomaten", "anna", "Passata", "Mutti", "700 g",
                700, Unit.G, _values(36, 1.6, 5.4, 4.8, 0.2)),
    DemoProduct("4017952000633", "Olivenöl", "ben", "Natives Olivenöl Extra", "Bertolli",
                "750 ml", 750, Unit.ML, _values(828, 0.0, 0.0, 0.0, 92.0)),
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


async def _insert_catalog(
    session: AsyncSession, user_ids: Mapping[str, str], *, now: datetime
) -> None:
    categories = {row.key: row.id for row in await reference_repo.categories_in_order(session)}
    ingredient_ids: dict[str, str] = {}
    for item in DEMO_INGREDIENTS:
        creator = user_ids[item.creator]
        ingredient = Ingredient(
            name=item.name,
            name_norm=normalize(item.name),
            category_id=categories[item.category],
            base_unit=item.base_unit,
            piece_weight_g=item.piece_weight_g,
            density_g_per_ml=item.density_g_per_ml,
            created_by=creator,
            updated_by=creator,
            created_at=now,
            updated_at=now,
        )
        ingredient.set_nutrients({key: item.manual.get(key) for key in NUTRIENT_KEYS})
        session.add(ingredient)
        await session.flush()
        ingredient_ids[item.name] = ingredient.id
    for demo in DEMO_PRODUCTS:
        base_unit = next(i.base_unit for i in DEMO_INGREDIENTS if i.name == demo.ingredient)
        creator = user_ids[demo.creator]
        product = Product(
            barcode=demo.barcode,
            ingredient_id=ingredient_ids[demo.ingredient],
            nutrition_basis=base_unit,
            name=demo.name,
            brand=demo.brand,
            quantity_text=demo.quantity_text,
            pack_quantity=demo.pack_quantity,
            pack_unit=demo.pack_unit.value,
            source="manual",
            user_edited_fields=[
                *DATA_FIELDS,
                *(f"nutrients.{key}" for key in NUTRIENT_KEYS),
            ],
            created_by=creator,
            updated_by=creator,
            created_at=now,
            updated_at=now,
        )
        product.set_nutrients(demo.nutrients)
        session.add(product)


async def seed_accounts(session: AsyncSession, config: AuthConfig, *, now: datetime) -> DemoSeed:
    """The demo users (all with one random password), the couple and an open invite."""
    password, password_hash = await _demo_password(config)
    async with session.begin():
        return await _insert_accounts(session, config, password, password_hash, now=now)


async def seed_catalog(
    session: AsyncSession, user_ids: Mapping[str, str], *, now: datetime
) -> None:
    """The demo ingredients and products, created by the demo users."""
    async with session.begin():
        await _insert_catalog(session, user_ids, now=now)


async def seed_demo(session: AsyncSession, config: AuthConfig, *, now: datetime) -> DemoSeed:
    """Accounts and catalog in one transaction: if anything fails, nothing is left behind and
    `seed-demo` can simply run again."""
    password, password_hash = await _demo_password(config)
    async with session.begin():
        seed = await _insert_accounts(session, config, password, password_hash, now=now)
        await _insert_catalog(session, seed.user_ids, now=now)
    return seed
