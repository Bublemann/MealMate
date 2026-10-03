"""The barcode lookup (BAR-02, BAR-03, plan § 5.9): our own ingredients first, then Open Food
Facts.

A barcode we know goes straight to its ingredient. Otherwise Open Food Facts is asked, outside
any transaction, and its product becomes a *proposal* that is not saved: the app opens the
ingredient form prefilled with it, and the user may correct values before saving it with
`POST /api/ingredients` (with `off`), in one request.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.domain.units import BaseUnit, Unit
from app.integrations.off import LOOKUP_MAX_WAIT_SECONDS, OffClient, OffProduct
from app.repositories import ingredients as ingredients_repo
from app.repositories import users as users_repo
from app.schemas.ingredients import BarcodeLookup, NutritionBasisName, ProductProposal
from app.schemas.nutrition import NutrientValues
from app.services import ingredients
from app.services.off_refresh import DEFAULT_LANGUAGE
from app.services.principal import Principal


def _nutrition_basis_name(basis: BaseUnit | None) -> NutritionBasisName | None:
    match basis:
        case None:
            return None
        case BaseUnit.ML:
            return "ml"
        case _:
            return "g"


def proposal(found: OffProduct, barcode: str, language: str) -> ProductProposal:
    """The API view of a product from Open Food Facts, named in `language` if possible."""
    pack_quantity, pack_unit = found.pack
    return ProductProposal(
        barcode=barcode,
        name=found.name(language),
        brand=found.brands,
        quantity_text=found.quantity,
        pack_quantity=pack_quantity,
        pack_unit=None if pack_unit is None else Unit(pack_unit.value),
        nutrition_basis=_nutrition_basis_name(found.nutrition_basis),
        nutrients=NutrientValues.model_validate(found.nutrients),
        category_key=found.category_key,
        off_last_modified_at=found.last_modified_at,
    )


async def user_language(session: AsyncSession, principal: Principal) -> str:
    user = await users_repo.get(session, principal.user_id)
    return user.language if user is not None else DEFAULT_LANGUAGE


async def lookup(
    session: AsyncSession,
    off: OffClient,
    principal: Principal,
    text: str,
    *,
    own_only: bool = False,
) -> BarcodeLookup:
    """Look a barcode up (422 `invalid_format` if it is not a valid EAN/UPC code): an
    ingredient of ours, else Open Food Facts' proposal, else nothing (after a transient
    failure, Open Food Facts gets a second try before that, see `OffClient.fetch`). While too
    many lookups wait for Open Food Facts: 503 `off.busy`. With `own_only`, Open Food Facts
    isn't asked: the edit pop-up's scan only needs to know whether another ingredient has
    the barcode (BAR-03)."""
    barcode = ingredients.canonical_barcode(text, ("query", "barcode"))
    async with session.begin():
        row = await ingredients_repo.by_barcode(session, barcode)
        if row is not None:
            return BarcodeLookup(
                barcode=barcode,
                found_in="db",
                ingredient=await ingredients.detail(session, row),
                proposal=None,
                off_unavailable=False,
            )
        if own_only:
            return BarcodeLookup(
                barcode=barcode,
                found_in="none",
                ingredient=None,
                proposal=None,
                off_unavailable=False,
            )
        language = await user_language(session, principal)

    # The user waits for this answer: a transient failure gets a second try, "not found" none.
    response = await off.fetch(barcode, max_wait=LOOKUP_MAX_WAIT_SECONDS, retry=True)
    if response.status == "busy":
        raise ApiError(ErrorCode.OFF_BUSY, status_code=503)
    if response.product is None:
        return BarcodeLookup(
            barcode=barcode,
            found_in="none",
            ingredient=None,
            proposal=None,
            off_unavailable=response.status == "unavailable",
        )
    return BarcodeLookup(
        barcode=barcode,
        found_in="off",
        ingredient=None,
        proposal=proposal(response.product, barcode, language),
        off_unavailable=False,
    )
