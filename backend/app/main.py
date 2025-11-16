"""Main FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import init_db
import os

# Initialize FastAPI app
app = FastAPI(
    title="MealMate API",
    description="API for meal planning and grocery shopping list management",
    version="1.0.0"
)

# Configure CORS - Allow access from local network
# This allows your Raspberry Pi to serve the API to devices on your local network
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development/local network use
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup."""
    print("Starting MealMate API...")
    init_db()
    print("Database initialized successfully")


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


# Import and include routers
from app.routers import items, categories, cuisines, meals, shopping_lists, users, search

app.include_router(items.router, prefix="/api/items", tags=["items"])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(cuisines.router, prefix="/api/cuisines", tags=["cuisines"])
app.include_router(meals.router, prefix="/api/meals", tags=["meals"])
app.include_router(shopping_lists.router, prefix="/api/shopping-lists", tags=["shopping-lists"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(search.router, prefix="/api/search", tags=["search"])


# Mount static files for frontend (CSS, JS)
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_path, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_path, "js")), name="js")

# Mount meal images directory
meal_images_path = os.getenv("MEAL_IMAGES_PATH", "/data/meal_images")
if not os.path.exists(meal_images_path):
    os.makedirs(meal_images_path, exist_ok=True)
app.mount("/meal-images", StaticFiles(directory=meal_images_path), name="meal-images")


# Serve index.html at root
@app.get("/")
async def serve_frontend():
    """Serve the frontend application."""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": "MealMate API is running",
        "version": "1.0.0",
        "status": "healthy",
        "note": "Frontend not found. Access API docs at /docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
