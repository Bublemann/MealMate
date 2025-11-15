"""API router for shopping lists."""
from typing import List, Optional, Dict
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models import (
    ShoppingList, ShoppingListMeal, ShoppingListItem,
    Meal, Item, ItemCategory
)
from app.utils.auth import get_current_user, User

router = APIRouter()


# Pydantic schemas
class ShoppingListCreate(BaseModel):
    """Schema for creating a new shopping list."""
    name: str


class ShoppingListUpdate(BaseModel):
    """Schema for updating a shopping list."""
    name: str


class AddMealRequest(BaseModel):
    """Schema for adding a meal to shopping list."""
    meal_id: int
    quantity: int = 1


class AddItemRequest(BaseModel):
    """Schema for adding an item to shopping list."""
    item_id: int
    quantity: float
    unit: Optional[str] = None


class AddCustomRequest(BaseModel):
    """Schema for adding custom text to shopping list."""
    custom_text: str


class ShoppingListResponse(BaseModel):
    """Schema for shopping list summary."""
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MealInListResponse(BaseModel):
    """Schema for meal in shopping list."""
    id: int
    meal_id: int
    meal_name: str
    quantity: int
    servings: int

    class Config:
        from_attributes = True


class ItemInListResponse(BaseModel):
    """Schema for item in shopping list."""
    id: int
    item_id: Optional[int]
    item_name: Optional[str]
    custom_text: Optional[str]
    quantity: Optional[float]
    unit: Optional[str]

    class Config:
        from_attributes = True


class ShoppingListDetailResponse(BaseModel):
    """Schema for shopping list with full details."""
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    meals: List[MealInListResponse]
    items: List[ItemInListResponse]

    class Config:
        from_attributes = True


@router.get("", response_model=List[ShoppingListResponse])
def get_shopping_lists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all shopping lists for the current user, ordered by most recent."""
    lists = db.query(ShoppingList).filter(
        ShoppingList.user_id == current_user.id
    ).order_by(ShoppingList.updated_at.desc()).all()
    return lists


@router.get("/{list_id}", response_model=ShoppingListDetailResponse)
def get_shopping_list(
    list_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a shopping list with full details."""
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    # Format meals
    meals_response = []
    for list_meal in shopping_list.meals:
        meals_response.append({
            "id": list_meal.id,
            "meal_id": list_meal.meal_id,
            "meal_name": list_meal.meal.name,
            "quantity": list_meal.quantity,
            "servings": list_meal.meal.servings
        })

    # Format items
    items_response = []
    for list_item in shopping_list.items:
        items_response.append({
            "id": list_item.id,
            "item_id": list_item.item_id,
            "item_name": list_item.item.name if list_item.item else None,
            "custom_text": list_item.custom_text,
            "quantity": list_item.quantity,
            "unit": list_item.unit
        })

    return {
        **shopping_list.__dict__,
        "meals": meals_response,
        "items": items_response
    }


@router.post("", response_model=ShoppingListResponse, status_code=status.HTTP_201_CREATED)
def create_shopping_list(
    list_data: ShoppingListCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new shopping list."""
    new_list = ShoppingList(
        user_id=current_user.id,
        name=list_data.name
    )
    db.add(new_list)
    db.commit()
    db.refresh(new_list)
    return new_list


@router.put("/{list_id}", response_model=ShoppingListResponse)
def update_shopping_list(
    list_id: int,
    list_data: ShoppingListUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a shopping list name."""
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    shopping_list.name = list_data.name
    shopping_list.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(shopping_list)
    return shopping_list


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping_list(
    list_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a shopping list."""
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    db.delete(shopping_list)
    db.commit()


@router.post("/{list_id}/add-meal", status_code=status.HTTP_201_CREATED)
def add_meal_to_list(
    list_id: int,
    meal_data: AddMealRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a meal to the shopping list."""
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    # Verify meal exists and belongs to user
    meal = db.query(Meal).filter(
        Meal.id == meal_data.meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal with id {meal_data.meal_id} not found"
        )

    # Check if meal already in list
    existing = db.query(ShoppingListMeal).filter(
        ShoppingListMeal.shopping_list_id == list_id,
        ShoppingListMeal.meal_id == meal_data.meal_id
    ).first()

    if existing:
        # Update quantity
        existing.quantity = meal_data.quantity
    else:
        # Add new
        list_meal = ShoppingListMeal(
            shopping_list_id=list_id,
            meal_id=meal_data.meal_id,
            quantity=meal_data.quantity
        )
        db.add(list_meal)

    shopping_list.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Meal added to shopping list"}


@router.post("/{list_id}/add-item", status_code=status.HTTP_201_CREATED)
def add_item_to_list(
    list_id: int,
    item_data: AddItemRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add an item directly to the shopping list."""
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    # Verify item exists
    item = db.query(Item).filter(Item.id == item_data.item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_data.item_id} not found"
        )

    # Add item to list
    list_item = ShoppingListItem(
        shopping_list_id=list_id,
        item_id=item_data.item_id,
        quantity=item_data.quantity,
        unit=item_data.unit
    )
    db.add(list_item)

    shopping_list.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Item added to shopping list"}


@router.post("/{list_id}/add-custom", status_code=status.HTTP_201_CREATED)
def add_custom_to_list(
    list_id: int,
    custom_data: AddCustomRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a custom text entry to the shopping list."""
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    # Add custom text to list
    list_item = ShoppingListItem(
        shopping_list_id=list_id,
        custom_text=custom_data.custom_text
    )
    db.add(list_item)

    shopping_list.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Custom item added to shopping list"}


@router.get("/{list_id}/export")
def export_shopping_list(
    list_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export shopping list as formatted text.
    Returns plain text with items grouped by category and meals listed at the top.
    """
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.id == list_id,
        ShoppingList.user_id == current_user.id
    ).first()

    if not shopping_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list with id {list_id} not found"
        )

    # Build the export text
    lines = []
    lines.append(f"=== {shopping_list.name} ===")
    lines.append("")

    # Add meals section
    if shopping_list.meals:
        lines.append("MEALS:")
        for list_meal in shopping_list.meals:
            servings_text = f"{list_meal.meal.servings}x servings" if list_meal.meal.servings > 1 else "1x serving"
            lines.append(f"  • {list_meal.quantity}x {list_meal.meal.name} ({servings_text})")
        lines.append("")

    # Collect all items from meals and direct items
    # Group by category
    items_by_category: Dict[str, List[str]] = defaultdict(list)

    # Add items from meals
    for list_meal in shopping_list.meals:
        meal = list_meal.meal
        for ingredient in meal.ingredients:
            total_quantity = ingredient.quantity * list_meal.quantity
            unit = ingredient.unit or ""
            category_name = ingredient.item.category.name

            item_text = f"{total_quantity}{unit} {ingredient.item.name}"
            items_by_category[category_name].append(item_text)

    # Add direct items
    for list_item in shopping_list.items:
        if list_item.item_id:
            # Regular item
            quantity_text = f"{list_item.quantity}{list_item.unit or ''} " if list_item.quantity else ""
            category_name = list_item.item.category.name
            item_text = f"{quantity_text}{list_item.item.name}"
            items_by_category[category_name].append(item_text)
        else:
            # Custom text
            items_by_category["Other"].append(list_item.custom_text)

    # Output items grouped by category
    if items_by_category:
        lines.append("SHOPPING LIST:")
        for category_name in sorted(items_by_category.keys()):
            lines.append(f"\n{category_name}:")
            for item_text in items_by_category[category_name]:
                lines.append(f"  • {item_text}")

    lines.append("")
    lines.append(f"Created: {shopping_list.created_at.strftime('%d-%m-%Y %H:%M')}")

    text_output = "\n".join(lines)
    return {"text": text_output}
