"""API router for items."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Item, ItemCategory
from app.utils.auth import get_current_user, User

router = APIRouter()


# Pydantic schemas for request/response
class ItemCreate(BaseModel):
    """Schema for creating a new item."""
    name: str
    category_id: int
    calories_per_100: Optional[float] = None
    protein_per_100: Optional[float] = None
    sugar_per_100: Optional[float] = None


class ItemUpdate(BaseModel):
    """Schema for updating an item."""
    name: Optional[str] = None
    category_id: Optional[int] = None
    calories_per_100: Optional[float] = None
    protein_per_100: Optional[float] = None
    sugar_per_100: Optional[float] = None


class CategoryInfo(BaseModel):
    """Nested category info for item response."""
    id: int
    name: str

    class Config:
        from_attributes = True


class ItemResponse(BaseModel):
    """Schema for item response."""
    id: int
    name: str
    category_id: int
    category: CategoryInfo
    calories_per_100: Optional[float]
    protein_per_100: Optional[float]
    sugar_per_100: Optional[float]

    class Config:
        from_attributes = True


@router.get("", response_model=List[ItemResponse])
def get_items(
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    search: Optional[str] = Query(None, description="Search in item names"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all items with optional filtering.
    Items are shared across all users.
    """
    query = db.query(Item)

    # Apply filters
    if category_id is not None:
        query = query.filter(Item.category_id == category_id)

    if search:
        query = query.filter(Item.name.ilike(f"%{search}%"))

    items = query.order_by(Item.name).all()
    return items


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single item by ID."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )
    return item


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    item_data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new item."""
    # Verify category exists
    category = db.query(ItemCategory).filter(ItemCategory.id == item_data.category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {item_data.category_id} not found"
        )

    # Create new item
    new_item = Item(
        name=item_data.name,
        category_id=item_data.category_id,
        calories_per_100=item_data.calories_per_100,
        protein_per_100=item_data.protein_per_100,
        sugar_per_100=item_data.sugar_per_100
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.put("/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: int,
    item_data: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing item."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )

    # Verify new category exists if changing
    if item_data.category_id is not None and item_data.category_id != item.category_id:
        category = db.query(ItemCategory).filter(ItemCategory.id == item_data.category_id).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id {item_data.category_id} not found"
            )
        item.category_id = item_data.category_id

    # Update fields if provided
    if item_data.name is not None:
        item.name = item_data.name
    if item_data.calories_per_100 is not None:
        item.calories_per_100 = item_data.calories_per_100
    if item_data.protein_per_100 is not None:
        item.protein_per_100 = item_data.protein_per_100
    if item_data.sugar_per_100 is not None:
        item.sugar_per_100 = item_data.sugar_per_100

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete an item.
    Note: This will fail if the item is used in meals or shopping lists (foreign key constraint).
    """
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found"
        )

    try:
        db.delete(item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete item that is being used in meals or shopping lists"
        )
