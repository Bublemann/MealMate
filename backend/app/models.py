"""SQLAlchemy database models for MealMate."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """User model for multi-user support."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    meals = relationship("Meal", back_populates="user", cascade="all, delete-orphan")
    shopping_lists = relationship("ShoppingList", back_populates="user", cascade="all, delete-orphan")


class ItemCategory(Base):
    """Category for items (e.g., Produce, Dairy, Meat, Pantry)."""
    __tablename__ = "item_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    items = relationship("Item", back_populates="category")


class Item(Base):
    """
    Item model - shared across all users.
    Represents individual grocery items with optional nutritional data.
    """
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("item_categories.id"), nullable=False)

    # Nutritional data (optional) - per 100g/100ml
    calories_per_100 = Column(Float, nullable=True)
    protein_per_100 = Column(Float, nullable=True)
    sugar_per_100 = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    category = relationship("ItemCategory", back_populates="items")
    meal_ingredients = relationship("MealIngredient", back_populates="item")
    shopping_list_items = relationship("ShoppingListItem", back_populates="item")


class Cuisine(Base):
    """Cuisine type (e.g., Italian, Asian, American)."""
    __tablename__ = "cuisines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    meals = relationship("Meal", back_populates="cuisine")


class Meal(Base):
    """
    Meal model - user-specific.
    Represents a recipe/meal with ingredients and serving information.
    """
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False, index=True)
    cuisine_id = Column(Integer, ForeignKey("cuisines.id"), nullable=False)
    servings = Column(Integer, nullable=False, default=1)  # How many times you can eat from it
    recipe = Column(Text, nullable=True)  # Step-by-step cooking instructions
    image_url = Column(String, nullable=True)  # URL or path to meal image
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="meals")
    cuisine = relationship("Cuisine", back_populates="meals")
    ingredients = relationship("MealIngredient", back_populates="meal", cascade="all, delete-orphan")
    shopping_list_meals = relationship("ShoppingListMeal", back_populates="meal")


class MealIngredient(Base):
    """
    Join table connecting meals to items with quantities.
    Represents the ingredients list for a meal.
    """
    __tablename__ = "meal_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=True)  # e.g., "g", "ml", "x", "cup", "tbsp"

    # Relationships
    meal = relationship("Meal", back_populates="ingredients")
    item = relationship("Item", back_populates="meal_ingredients")


class ShoppingList(Base):
    """
    Shopping list model - user-specific.
    Container for a collection of meals and items to shop for.
    """
    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="shopping_lists")
    meals = relationship("ShoppingListMeal", back_populates="shopping_list", cascade="all, delete-orphan")
    items = relationship("ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan")


class ShoppingListMeal(Base):
    """
    Join table connecting shopping lists to meals.
    Tracks how many times a meal should be included.
    """
    __tablename__ = "shopping_list_meals"

    id = Column(Integer, primary_key=True, index=True)
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False)
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)  # How many times to include this meal

    # Relationships
    shopping_list = relationship("ShoppingList", back_populates="meals")
    meal = relationship("Meal", back_populates="shopping_list_meals")


class ShoppingListItem(Base):
    """
    Items in a shopping list.
    Can be either:
    1. A reference to an existing Item (item_id set, custom_text null)
    2. A custom free-form text entry (item_id null, custom_text set)
    """
    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, index=True)
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)  # Nullable for custom entries
    custom_text = Column(String, nullable=True)  # For free-form additions
    quantity = Column(Float, nullable=True)
    unit = Column(String, nullable=True)

    # Relationships
    shopping_list = relationship("ShoppingList", back_populates="items")
    item = relationship("Item", back_populates="shopping_list_items")
