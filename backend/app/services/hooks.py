"""Lifecycle hooks between aggregates (plan § 6, deletion and lifecycle rules).

The account, ingredient and meal rules call these hooks at the right point of their write
transaction. Meals (M4) fill in the ingredient references; shopping lists (M5a) do not exist
yet, so the hooks that detach meals from lists are documented no-ops until then.
Each hook runs inside the caller's transaction and must not commit.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import meals as meals_repo


async def on_couple_ended(session: AsyncSession, user_a_id: str, user_b_id: str) -> None:
    """Runs when a couple ends, before its rows are deleted (CPL-05).

    To be filled in (M5a):
    - set `shared_with_partner = false` on all lists of both users;
    - detach each ex-partner's meals from the other's not-yet-frozen lists where they are no
      longer visible (LIST-15).
    """


async def on_meals_made_private(session: AsyncSession, user_id: str) -> None:
    """Runs when a user switches *meals public* off (VIS-02).

    To be filled in (M5a): detach the owner's meals from not-yet-frozen lists owned by users who
    are neither the owner nor the partner.
    """


async def on_lists_made_private(session: AsyncSession, user_id: str) -> None:
    """Runs when a user switches *lists public* off (VIS-02).

    Visibility is computed on read, so nothing needs to change today; M5a may use this hook for
    derived data (e.g. cached list views of other users).
    """


async def before_user_deleted(session: AsyncSession, user_id: str) -> None:
    """Runs first when an admin deletes a user (ADM-03), before the couple ends.

    To be filled in (M5a):
    - move the lists they share with their partner to the partner (`owner_id` changes and
      `shared_with_partner` becomes false);
    - detach their meals from every not-yet-frozen list they do not own, including the lists
      that just moved.
    Their own meals, remaining lists and sessions then go by `ON DELETE CASCADE`; their photo
    files are removed by `mealmate jobs cleanup`.
    """


async def on_meal_deleted(session: AsyncSession, meal_id: str) -> None:
    """Runs when the owner deletes a meal (MEAL-07), before its row is deleted.

    To be filled in (M5a): detach it from every not-yet-frozen list (LIST-15). Its rows and
    tags go by `ON DELETE CASCADE`; copies keep existing without their "based on".
    """


async def ingredient_references(session: AsyncSession, ingredient_id: str) -> dict[str, int]:
    """References to an ingredient other than its products, counted per kind; any of them
    blocks deleting it (ING-05) and is reported in the `ingredient.in_use` params.

    - `meals`: the meals with rows (`meal_ingredients`) of this ingredient.

    To be filled in (M5a): `lists`, the lists with frozen rows (`list_meal_ingredients`) or
    linked extra items (`list_extra_items`) of this ingredient.
    """
    return {"meals": await meals_repo.count_with_ingredient(session, ingredient_id)}


async def on_ingredients_merged(session: AsyncSession, from_id: str, into_id: str) -> None:
    """Runs when an admin merges ingredient `from_id` into `into_id` (ING-05), after the
    products moved and before `from_id` is deleted.

    Meal rows (`meal_ingredients`) are repointed, keeping their positions; a meal may then
    have two rows of the same ingredient, which is allowed.

    To be filled in (M5a): repoint `list_meal_ingredients` and `list_extra_items`, and rewrite
    `list_line_states.line_key` from `i:<from_id>` to `i:<into_id>`, merging the check states
    (checked only if both were checked).
    """
    await meals_repo.repoint_ingredient(session, from_id, into_id)
