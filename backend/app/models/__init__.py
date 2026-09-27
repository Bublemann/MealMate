"""SQLAlchemy models, one module per aggregate.

Every model is imported here so that `Base.metadata` is complete for Alembic.
"""

from app.db.base import Base
from app.models.admin_event import AdminEvent
from app.models.app_meta import AppMeta
from app.models.auth_session import AuthSession, SessionToken
from app.models.couple import Couple, CoupleMember
from app.models.ingredient import Ingredient, Product
from app.models.meal import Meal, MealIngredient, MealTag
from app.models.one_time_code import OneTimeCode
from app.models.reference import Category, Cuisine, Tag
from app.models.shopping_list import (
    ListExtraItem,
    ListLineState,
    ListMeal,
    ListMealIngredient,
    ShoppingList,
)
from app.models.user import User

__all__ = [
    "AdminEvent",
    "AppMeta",
    "AuthSession",
    "Base",
    "Category",
    "Couple",
    "CoupleMember",
    "Cuisine",
    "Ingredient",
    "ListExtraItem",
    "ListLineState",
    "ListMeal",
    "ListMealIngredient",
    "Meal",
    "MealIngredient",
    "MealTag",
    "OneTimeCode",
    "Product",
    "SessionToken",
    "ShoppingList",
    "Tag",
    "User",
]
