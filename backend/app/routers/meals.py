"""API router for meals."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from app.database import get_db
from app.models import Meal, MealIngredient, Cuisine, Item
from app.utils.auth import get_current_user, User
import os
import uuid
from datetime import datetime
from PIL import Image
import io

router = APIRouter()


# Pydantic schemas for request/response
class IngredientCreate(BaseModel):
    """Schema for creating an ingredient in a meal."""
    item_id: int
    quantity: float
    unit: Optional[str] = None


class IngredientResponse(BaseModel):
    """Schema for ingredient response with item details."""
    id: int
    item_id: int
    item_name: str
    quantity: float
    unit: Optional[str]

    class Config:
        from_attributes = True


class CuisineInfo(BaseModel):
    """Nested cuisine info."""
    id: int
    name: str

    class Config:
        from_attributes = True


class MealCreate(BaseModel):
    """Schema for creating a new meal."""
    name: str
    cuisine_id: int
    servings: int = 1
    recipe: Optional[str] = None
    image_url: Optional[str] = None
    ingredients: List[IngredientCreate]


class MealUpdate(BaseModel):
    """Schema for updating a meal."""
    name: Optional[str] = None
    cuisine_id: Optional[int] = None
    servings: Optional[int] = None
    recipe: Optional[str] = None
    image_url: Optional[str] = None
    ingredients: Optional[List[IngredientCreate]] = None


class MealListResponse(BaseModel):
    """Schema for meal in list view (without ingredients)."""
    id: int
    name: str
    cuisine_id: int
    cuisine: CuisineInfo
    servings: int
    image_url: Optional[str]

    class Config:
        from_attributes = True


class MealDetailResponse(BaseModel):
    """Schema for meal detail view (with ingredients and recipe)."""
    id: int
    name: str
    cuisine_id: int
    cuisine: CuisineInfo
    servings: int
    recipe: Optional[str]
    image_url: Optional[str]
    ingredients: List[IngredientResponse]

    class Config:
        from_attributes = True


@router.get("", response_model=List[MealListResponse])
def get_meals(
    cuisine_id: Optional[int] = Query(None, description="Filter by cuisine ID"),
    search: Optional[str] = Query(None, description="Search in meal names"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all meals for the current user with optional filtering.
    Each user only sees their own meals.
    """
    query = db.query(Meal).options(joinedload(Meal.cuisine)).filter(Meal.user_id == current_user.id)

    # Apply filters
    if cuisine_id is not None:
        query = query.filter(Meal.cuisine_id == cuisine_id)

    if search:
        query = query.filter(Meal.name.ilike(f"%{search}%"))

    meals = query.order_by(Meal.name).all()
    return meals


@router.get("/{meal_id}", response_model=MealDetailResponse)
def get_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single meal by ID with full details including ingredients."""
    meal = db.query(Meal).options(
        joinedload(Meal.cuisine),
        joinedload(Meal.ingredients)
    ).filter(
        Meal.id == meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal with id {meal_id} not found"
        )

    # Format ingredients with item names
    ingredients_response = []
    for ingredient in meal.ingredients:
        ingredients_response.append({
            "id": ingredient.id,
            "item_id": ingredient.item_id,
            "item_name": ingredient.item.name,
            "quantity": ingredient.quantity,
            "unit": ingredient.unit
        })

    return {
        **meal.__dict__,
        "ingredients": ingredients_response
    }


@router.post("", response_model=MealDetailResponse, status_code=status.HTTP_201_CREATED)
def create_meal(
    meal_data: MealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new meal with ingredients."""
    # Verify cuisine exists
    cuisine = db.query(Cuisine).filter(Cuisine.id == meal_data.cuisine_id).first()
    if not cuisine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cuisine with id {meal_data.cuisine_id} not found"
        )

    # Verify all items exist
    for ingredient in meal_data.ingredients:
        item = db.query(Item).filter(Item.id == ingredient.item_id).first()
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item with id {ingredient.item_id} not found"
            )

    # Create meal
    new_meal = Meal(
        user_id=current_user.id,
        name=meal_data.name,
        cuisine_id=meal_data.cuisine_id,
        servings=meal_data.servings,
        recipe=meal_data.recipe,
        image_url=meal_data.image_url
    )
    db.add(new_meal)
    db.flush()  # Flush to get meal.id without committing

    # Create ingredients
    for ingredient_data in meal_data.ingredients:
        ingredient = MealIngredient(
            meal_id=new_meal.id,
            item_id=ingredient_data.item_id,
            quantity=ingredient_data.quantity,
            unit=ingredient_data.unit
        )
        db.add(ingredient)

    db.commit()
    db.refresh(new_meal)

    # Return with formatted ingredients
    return get_meal(new_meal.id, db, current_user)


@router.put("/{meal_id}", response_model=MealDetailResponse)
def update_meal(
    meal_id: int,
    meal_data: MealUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing meal."""
    meal = db.query(Meal).filter(
        Meal.id == meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal with id {meal_id} not found"
        )

    # Update basic fields
    if meal_data.name is not None:
        meal.name = meal_data.name

    if meal_data.cuisine_id is not None:
        cuisine = db.query(Cuisine).filter(Cuisine.id == meal_data.cuisine_id).first()
        if not cuisine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cuisine with id {meal_data.cuisine_id} not found"
            )
        meal.cuisine_id = meal_data.cuisine_id

    if meal_data.servings is not None:
        meal.servings = meal_data.servings

    if meal_data.recipe is not None:
        meal.recipe = meal_data.recipe

    if meal_data.image_url is not None:
        meal.image_url = meal_data.image_url

    # Update ingredients if provided
    if meal_data.ingredients is not None:
        # Verify all items exist
        for ingredient in meal_data.ingredients:
            item = db.query(Item).filter(Item.id == ingredient.item_id).first()
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Item with id {ingredient.item_id} not found"
                )

        # Delete old ingredients and create new ones
        db.query(MealIngredient).filter(MealIngredient.meal_id == meal_id).delete()

        for ingredient_data in meal_data.ingredients:
            ingredient = MealIngredient(
                meal_id=meal_id,
                item_id=ingredient_data.item_id,
                quantity=ingredient_data.quantity,
                unit=ingredient_data.unit
            )
            db.add(ingredient)

    db.commit()
    db.refresh(meal)

    return get_meal(meal_id, db, current_user)


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a meal.
    This will also delete associated ingredients (cascade).
    """
    meal = db.query(Meal).filter(
        Meal.id == meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal with id {meal_id} not found"
        )

    db.delete(meal)
    db.commit()


@router.post("/upload-image")
async def upload_meal_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload and optimize a meal image.

    Accepts: PNG, JPG, JPEG, WEBP
    Returns: Path to the optimized image

    The image will be:
    - Resized to max 800x800 pixels (maintaining aspect ratio)
    - Converted to JPEG format
    - Compressed with quality 85
    - Saved with a unique filename
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )

    # Validate file size (max 10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10MB limit"
        )

    try:
        # Open image with Pillow
        image = Image.open(io.BytesIO(contents))

        # Convert to RGB if necessary (removes alpha channel)
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize image maintaining aspect ratio (max 800x800)
        max_size = (800, 800)
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"user{current_user.id}_{timestamp}_{unique_id}.jpg"

        # Get images directory
        images_dir = os.getenv("MEAL_IMAGES_PATH", "/data/meal_images")
        if not os.path.exists(images_dir):
            os.makedirs(images_dir, exist_ok=True)

        # Save optimized image
        filepath = os.path.join(images_dir, filename)
        image.save(filepath, "JPEG", quality=85, optimize=True)

        # Calculate file size for info
        file_size_kb = os.path.getsize(filepath) / 1024

        # Return the URL path
        image_url = f"/meal-images/{filename}"

        return {
            "image_url": image_url,
            "filename": filename,
            "size_kb": round(file_size_kb, 2),
            "dimensions": f"{image.width}x{image.height}"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process image: {str(e)}"
        )
