"""API router for cuisines."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Cuisine
from app.utils.auth import get_current_user, User

router = APIRouter()


# Pydantic schemas for request/response
class CuisineCreate(BaseModel):
    """Schema for creating a new cuisine."""
    name: str


class CuisineUpdate(BaseModel):
    """Schema for updating a cuisine."""
    name: str


class CuisineResponse(BaseModel):
    """Schema for cuisine response."""
    id: int
    name: str

    class Config:
        from_attributes = True


@router.get("", response_model=List[CuisineResponse])
def get_cuisines(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all cuisines.
    Cuisines are shared across all users.
    """
    cuisines = db.query(Cuisine).order_by(Cuisine.name).all()
    return cuisines


@router.get("/{cuisine_id}", response_model=CuisineResponse)
def get_cuisine(
    cuisine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single cuisine by ID."""
    cuisine = db.query(Cuisine).filter(Cuisine.id == cuisine_id).first()
    if not cuisine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cuisine with id {cuisine_id} not found"
        )
    return cuisine


@router.post("", response_model=CuisineResponse, status_code=status.HTTP_201_CREATED)
def create_cuisine(
    cuisine_data: CuisineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new cuisine."""
    # Check if cuisine with same name already exists
    existing = db.query(Cuisine).filter(Cuisine.name == cuisine_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cuisine with name '{cuisine_data.name}' already exists"
        )

    # Create new cuisine
    new_cuisine = Cuisine(name=cuisine_data.name)
    db.add(new_cuisine)
    db.commit()
    db.refresh(new_cuisine)
    return new_cuisine


@router.put("/{cuisine_id}", response_model=CuisineResponse)
def update_cuisine(
    cuisine_id: int,
    cuisine_data: CuisineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing cuisine."""
    cuisine = db.query(Cuisine).filter(Cuisine.id == cuisine_id).first()
    if not cuisine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cuisine with id {cuisine_id} not found"
        )

    # Check if new name conflicts with existing cuisine
    if cuisine_data.name != cuisine.name:
        existing = db.query(Cuisine).filter(Cuisine.name == cuisine_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cuisine with name '{cuisine_data.name}' already exists"
            )

    cuisine.name = cuisine_data.name
    db.commit()
    db.refresh(cuisine)
    return cuisine


@router.delete("/{cuisine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cuisine(
    cuisine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a cuisine.
    Note: This will fail if there are meals using this cuisine (foreign key constraint).
    """
    cuisine = db.query(Cuisine).filter(Cuisine.id == cuisine_id).first()
    if not cuisine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cuisine with id {cuisine_id} not found"
        )

    try:
        db.delete(cuisine)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete cuisine that is being used by meals"
        )
