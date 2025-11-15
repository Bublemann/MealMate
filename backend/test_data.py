"""
Test Data Script for MealMate
Populates the database with sample data for testing and development.

Usage:
    python test_data.py
"""

import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models import (
    User, ItemCategory, Item, Cuisine, Meal, MealIngredient,
    ShoppingList, ShoppingListMeal, ShoppingListItem
)
from app.utils.auth import hash_password


def clear_database(db):
    """Clear all data from database (use with caution!)"""
    print("Clearing existing data...")
    db.query(ShoppingListItem).delete()
    db.query(ShoppingListMeal).delete()
    db.query(ShoppingList).delete()
    db.query(MealIngredient).delete()
    db.query(Meal).delete()
    db.query(Item).delete()
    db.query(ItemCategory).delete()
    db.query(Cuisine).delete()
    db.query(User).delete()
    db.commit()
    print("Database cleared!")


def create_test_data():
    """Create comprehensive test data."""
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    try:
        # Optional: Clear existing data
        # Uncomment the next line if you want to start fresh
        # clear_database(db)

        print("\n=== Creating Test Data ===\n")

        # 1. Create test user
        print("Creating test user...")
        test_user = db.query(User).filter(User.username == "test").first()
        if test_user:
            print(f"✓ User 'test' already exists, using existing user")
        else:
            test_user = User(
                username="test",
                password_hash=hash_password("test123")
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            print(f"✓ Created user: {test_user.username}")

        # 2. Create categories
        print("\nCreating categories...")
        categories_data = [
            "Produce", "Dairy & Eggs", "Meat & Seafood", "Bakery",
            "Pantry", "Frozen Foods", "Beverages", "Snacks", "Other"
        ]
        categories = {}
        for cat_name in categories_data:
            cat = db.query(ItemCategory).filter(ItemCategory.name == cat_name).first()
            if cat:
                print(f"✓ Category '{cat_name}' already exists")
            else:
                cat = ItemCategory(name=cat_name)
                db.add(cat)
                db.commit()
                db.refresh(cat)
                print(f"✓ Created category: {cat_name}")
            categories[cat_name] = cat

        # 3. Create cuisines
        print("\nCreating cuisines...")
        cuisines_data = [
            "Italian", "Asian", "American", "Mexican", "Mediterranean",
            "Indian", "French", "German", "Japanese"
        ]
        cuisines = {}
        for cuisine_name in cuisines_data:
            cuisine = db.query(Cuisine).filter(Cuisine.name == cuisine_name).first()
            if cuisine:
                print(f"✓ Cuisine '{cuisine_name}' already exists")
            else:
                cuisine = Cuisine(name=cuisine_name)
                db.add(cuisine)
                db.commit()
                db.refresh(cuisine)
                print(f"✓ Created cuisine: {cuisine_name}")
            cuisines[cuisine_name] = cuisine

        # 4. Create items
        print("\nCreating items...")
        items_data = [
            # Produce
            ("Tomatoes", "Produce", 18, 0.9, 2.6),
            ("Onions", "Produce", 40, 1.1, 4.2),
            ("Garlic", "Produce", 149, 6.4, 1.0),
            ("Bell Peppers", "Produce", 31, 1.0, 4.6),
            ("Lettuce", "Produce", 15, 1.4, 2.1),
            ("Carrots", "Produce", 41, 0.9, 4.7),
            ("Potatoes", "Produce", 77, 2.0, 0.8),
            ("Basil", "Produce", 23, 3.2, 0.3),

            # Dairy & Eggs
            ("Milk", "Dairy & Eggs", 42, 3.4, 5.0),
            ("Eggs", "Dairy & Eggs", 155, 13.0, 1.1),
            ("Butter", "Dairy & Eggs", 717, 0.9, 0.1),
            ("Cheese (Cheddar)", "Dairy & Eggs", 402, 25.0, 1.3),
            ("Mozzarella", "Dairy & Eggs", 280, 28.0, 2.2),
            ("Yogurt", "Dairy & Eggs", 59, 10.0, 3.6),

            # Meat & Seafood
            ("Chicken Breast", "Meat & Seafood", 165, 31.0, 0.0),
            ("Ground Beef", "Meat & Seafood", 250, 26.0, 0.0),
            ("Bacon", "Meat & Seafood", 541, 37.0, 1.4),
            ("Salmon", "Meat & Seafood", 208, 20.0, 0.0),
            ("Shrimp", "Meat & Seafood", 99, 24.0, 0.2),

            # Bakery
            ("Bread", "Bakery", 265, 9.0, 5.0),
            ("Pasta", "Pantry", 371, 13.0, 2.7),
            ("Pizza Dough", "Bakery", 275, 9.0, 3.0),

            # Pantry
            ("Olive Oil", "Pantry", 884, 0.0, 0.0),
            ("Rice", "Pantry", 130, 2.7, 0.1),
            ("Soy Sauce", "Pantry", 53, 10.5, 0.4),
            ("Salt", "Pantry", 0, 0.0, 0.0),
            ("Black Pepper", "Pantry", 251, 10.4, 0.6),
            ("Canned Tomatoes", "Pantry", 32, 1.6, 4.2),

            # Other
            ("Toilet Paper", "Other", None, None, None),
        ]

        items = {}
        for item_name, cat_name, cal, prot, sugar in items_data:
            item = db.query(Item).filter(Item.name == item_name).first()
            if item:
                print(f"✓ Item '{item_name}' already exists")
            else:
                item = Item(
                    name=item_name,
                    category_id=categories[cat_name].id,
                    calories_per_100=cal,
                    protein_per_100=prot,
                    sugar_per_100=sugar
                )
                db.add(item)
                db.commit()
                db.refresh(item)
                print(f"✓ Created item: {item_name}")
            items[item_name] = item

        # 5. Create meals
        print("\nCreating meals...")

        # Spaghetti Bolognese
        meal1 = db.query(Meal).filter(Meal.name == "Spaghetti Bolognese", Meal.user_id == test_user.id).first()
        if meal1:
            print(f"✓ Meal 'Spaghetti Bolognese' already exists")
        else:
            meal1 = Meal(
                user_id=test_user.id,
                name="Spaghetti Bolognese",
                cuisine_id=cuisines["Italian"].id,
                servings=4,
                recipe="1. Cook pasta\n2. Brown ground beef\n3. Add tomatoes and simmer\n4. Serve with pasta"
            )
            db.add(meal1)
            db.commit()
            db.refresh(meal1)

            meal1_ingredients = [
                (items["Pasta"], 400, "g"),
                (items["Ground Beef"], 500, "g"),
                (items["Canned Tomatoes"], 400, "g"),
                (items["Onions"], 100, "g"),
                (items["Garlic"], 10, "g"),
            ]
            for item, qty, unit in meal1_ingredients:
                ing = MealIngredient(meal_id=meal1.id, item_id=item.id, quantity=qty, unit=unit)
                db.add(ing)
            db.commit()
            print(f"✓ Created meal: Spaghetti Bolognese")

        # Chicken Stir Fry
        meal2 = db.query(Meal).filter(Meal.name == "Chicken Stir Fry", Meal.user_id == test_user.id).first()
        if meal2:
            print(f"✓ Meal 'Chicken Stir Fry' already exists")
        else:
            meal2 = Meal(
                user_id=test_user.id,
                name="Chicken Stir Fry",
                cuisine_id=cuisines["Asian"].id,
                servings=3,
                recipe="1. Cut chicken into strips\n2. Stir fry vegetables\n3. Add chicken and soy sauce\n4. Serve with rice"
            )
            db.add(meal2)
            db.commit()
            db.refresh(meal2)

            meal2_ingredients = [
                (items["Chicken Breast"], 500, "g"),
                (items["Bell Peppers"], 200, "g"),
                (items["Onions"], 100, "g"),
                (items["Soy Sauce"], 50, "ml"),
                (items["Rice"], 300, "g"),
            ]
            for item, qty, unit in meal2_ingredients:
                ing = MealIngredient(meal_id=meal2.id, item_id=item.id, quantity=qty, unit=unit)
                db.add(ing)
            db.commit()
            print(f"✓ Created meal: Chicken Stir Fry")

        # Simple Salad
        meal3 = db.query(Meal).filter(Meal.name == "Caesar Salad", Meal.user_id == test_user.id).first()
        if meal3:
            print(f"✓ Meal 'Caesar Salad' already exists")
        else:
            meal3 = Meal(
                user_id=test_user.id,
                name="Caesar Salad",
                cuisine_id=cuisines["American"].id,
                servings=2,
                recipe="1. Chop lettuce\n2. Add cheese\n3. Drizzle with olive oil\n4. Season with salt and pepper"
            )
            db.add(meal3)
            db.commit()
            db.refresh(meal3)

            meal3_ingredients = [
                (items["Lettuce"], 200, "g"),
                (items["Cheese (Cheddar)"], 50, "g"),
                (items["Olive Oil"], 30, "ml"),
            ]
            for item, qty, unit in meal3_ingredients:
                ing = MealIngredient(meal_id=meal3.id, item_id=item.id, quantity=qty, unit=unit)
                db.add(ing)
            db.commit()
            print(f"✓ Created meal: Caesar Salad")

        # 6. Create a sample shopping list
        print("\nCreating sample shopping list...")
        shopping_list = db.query(ShoppingList).filter(ShoppingList.name == "Weekly Shopping", ShoppingList.user_id == test_user.id).first()
        if shopping_list:
            print(f"✓ Shopping list 'Weekly Shopping' already exists")
        else:
            shopping_list = ShoppingList(
                user_id=test_user.id,
                name="Weekly Shopping"
            )
            db.add(shopping_list)
            db.commit()
            db.refresh(shopping_list)

            # Add meals to shopping list
            list_meal1 = ShoppingListMeal(
                shopping_list_id=shopping_list.id,
                meal_id=meal1.id,
                quantity=1
            )
            list_meal2 = ShoppingListMeal(
                shopping_list_id=shopping_list.id,
                meal_id=meal2.id,
                quantity=2
            )
            db.add_all([list_meal1, list_meal2])

            # Add some direct items
            list_item1 = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                item_id=items["Milk"].id,
                quantity=2,
                unit="L"
            )
            list_item2 = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                item_id=items["Eggs"].id,
                quantity=12,
                unit="x"
            )
            list_item3 = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                custom_text="Paper towels"
            )
            db.add_all([list_item1, list_item2, list_item3])
            db.commit()
            print(f"✓ Created shopping list: {shopping_list.name}")

        print("\n" + "="*50)
        print("✓ Test data created successfully!")
        print("="*50)
        print(f"\nTest user credentials:")
        print(f"  Username: test")
        print(f"  Password: test123")
        print(f"\nCreated:")
        print(f"  - 1 user")
        print(f"  - {len(categories_data)} categories")
        print(f"  - {len(cuisines_data)} cuisines")
        print(f"  - {len(items_data)} items")
        print(f"  - 3 meals with ingredients")
        print(f"  - 1 shopping list")
        print()

    except Exception as e:
        print(f"\n❌ Error creating test data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_test_data()
