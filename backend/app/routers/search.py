"""API router for unified search across items and meals."""
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Item, Meal
from app.utils.auth import get_current_user, User

router = APIRouter()


# Pydantic schemas
class SearchItemResult(BaseModel):
    """Schema for item search result."""
    type: Literal["item"] = "item"
    id: int
    name: str
    category_id: int
    category_name: str

    class Config:
        from_attributes = True


class SearchMealResult(BaseModel):
    """Schema for meal search result."""
    type: Literal["meal"] = "meal"
    id: int
    name: str
    cuisine_id: int
    cuisine_name: str
    servings: int
    image_url: Optional[str]

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Schema for combined search response."""
    items: List[SearchItemResult]
    meals: List[SearchMealResult]


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query", min_length=1),
    type: Literal["items", "meals", "all"] = Query("all", description="What to search"),
    limit: int = Query(10, description="Max results per type", ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Unified search across items and meals.

    Args:
        q: Search query string
        type: What to search - "items", "meals", or "all"
        limit: Maximum number of results per type

    Returns:
        Combined search results with items and meals
    """
    items_results = []
    meals_results = []

    # Search items (if requested)
    if type in ["items", "all"]:
        items = db.query(Item).filter(
            Item.name.ilike(f"%{q}%")
        ).limit(limit).all()

        items_results = [
            {
                "type": "item",
                "id": item.id,
                "name": item.name,
                "category_id": item.category_id,
                "category_name": item.category.name
            }
            for item in items
        ]

    # Search meals (if requested)
    if type in ["meals", "all"]:
        meals = db.query(Meal).filter(
            Meal.user_id == current_user.id,
            Meal.name.ilike(f"%{q}%")
        ).limit(limit).all()

        meals_results = [
            {
                "type": "meal",
                "id": meal.id,
                "name": meal.name,
                "cuisine_id": meal.cuisine_id,
                "cuisine_name": meal.cuisine.name,
                "servings": meal.servings,
                "image_url": meal.image_url
            }
            for meal in meals
        ]

    return {
        "items": items_results,
        "meals": meals_results
    }


@router.get("/suggestions")
def get_suggestions(
    q: str = Query(..., description="Search query", min_length=1),
    limit: int = Query(5, description="Max suggestions", ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get search suggestions for autocomplete.
    Returns top matching items and meals combined.
    """
    items = db.query(Item).filter(
        Item.name.ilike(f"%{q}%")
    ).limit(limit).all()

    meals = db.query(Meal).filter(
        Meal.user_id == current_user.id,
        Meal.name.ilike(f"%{q}%")
    ).limit(limit).all()

    suggestions = []

    # Add item suggestions
    for item in items:
        suggestions.append({
            "type": "item",
            "id": item.id,
            "name": item.name,
            "label": f"{item.name} (item)"
        })

    # Add meal suggestions
    for meal in meals:
        suggestions.append({
            "type": "meal",
            "id": meal.id,
            "name": meal.name,
            "label": f"{meal.name} (meal - {meal.servings}x)"
        })

    return {"suggestions": suggestions[:limit]}
