# MealMate

A comprehensive meal planning and grocery shopping list management web application. Designed for mobile-first use (optimized for iPhone) but works great on desktop too.

## Features

- **Multi-user support** with authentication
- **Meal planning** with recipes and ingredients
- **Shopping list management** with smart meal-to-grocery conversion
- **Search & filter** for items and meals
- **Export options**: Copy to clipboard or share directly to iOS Notes app
- **Database-driven** with SQLite (persistent across updates)
- **Docker deployment** optimized for Raspberry Pi 3
- **Mobile-first responsive design**

## Tech Stack

- **Backend**: Python + FastAPI
- **Frontend**: Vanilla JavaScript (no framework)
- **Database**: SQLite
- **Deployment**: Docker + Docker Compose
- **Target Platform**: Raspberry Pi 3 (ARM architecture)

## Project Structure

```
MealMate/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── models.py            # Database models
│   │   ├── database.py          # DB configuration
│   │   ├── routers/             # API endpoints
│   │   │   ├── items.py
│   │   │   ├── meals.py
│   │   │   ├── categories.py
│   │   │   ├── cuisines.py
│   │   │   ├── shopping_lists.py
│   │   │   ├── users.py
│   │   │   └── search.py
│   │   └── utils/
│   │       └── auth.py          # Authentication
│   ├── requirements.txt
│   └── test_data.py             # Sample data script
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js               # Main application logic
│       ├── api.js               # API communication
│       └── export.js            # Export utilities
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- For development: Python 3.11+

### Deployment on Raspberry Pi

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd MealMate
   ```

2. **Build and run with Docker Compose**:
   ```bash
   docker-compose up -d
   ```

3. **Access the application**:
   - From the same device: `http://localhost:8000`
   - From other devices on your network: `http://<raspberry-pi-ip>:8000`
   - The frontend is served at the root URL

4. **Create your first user**:
   - Open the app in your browser
   - Click "Register" and create an account

### Populate Test Data (Optional)

To add sample data for testing:

```bash
# Enter the running container
docker exec -it mealmate-app bash

# Run the test data script
python test_data.py

# Exit the container
exit
```

This creates:
- Test user (username: `test`, password: `test123`)
- 9 categories, 9 cuisines
- 30+ sample items
- 3 sample meals
- 1 sample shopping list

## Usage

### For Users

1. **Register/Login**: Create an account or log in
2. **Add Items & Meals**: Use the "Manage" tab to add:
   - Categories (e.g., Produce, Dairy)
   - Cuisines (e.g., Italian, Asian)
   - Items (with optional nutritional info)
   - Meals (with ingredients and recipes)

3. **Create Shopping Lists**:
   - Go to "Shopping List" tab
   - Click "New List"
   - Switch to "Add to List" tab
   - Search for meals or items
   - Add them to your list with quantities

4. **Export Your List**:
   - View your shopping list in the "Shopping List" tab
   - Click "Copy to Clipboard" to copy the text
   - Or click "Share to Notes" to share directly to iOS Notes app

### For Developers

#### Local Development (without Docker)

1. **Set up Python environment**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set database path** (optional):
   ```bash
   export DATABASE_PATH=/tmp/mealmate.db
   ```

3. **Run the backend**:
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Serve the frontend**:
   Open `frontend/index.html` in a browser, or use a simple HTTP server:
   ```bash
   cd frontend
   python -m http.server 8080
   ```

5. **Access**:
   - Backend API: `http://localhost:8000`
   - API docs: `http://localhost:8000/docs`
   - Frontend: `http://localhost:8080`

## Data Persistence

### How It Works

The database is stored in a **Docker named volume** called `mealmate_data`. This means:
- ✅ Data persists across container restarts
- ✅ Data persists when you update the code and rebuild
- ✅ Data is NOT deleted when you run `docker-compose down`

### Updating the Application

When you make changes to the code:

```bash
# Stop the container
docker-compose down

# Make your changes to the code...

# Rebuild and restart (database is preserved!)
docker-compose up -d --build
```

### Manual Backups (Recommended)

Create a backup:
```bash
docker run --rm \
  -v mealmate_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/mealmate-backup-$(date +%Y%m%d).tar.gz -C /data .
```

Restore from backup:
```bash
docker run --rm \
  -v mealmate_data:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/mealmate-backup-YYYYMMDD.tar.gz"
```

### Viewing/Copying the Database

```bash
# Copy database from volume to current directory
docker run --rm \
  -v mealmate_data:/data \
  -v $(pwd):/backup \
  alpine cp /data/mealmate.db /backup/mealmate.db
```

## API Documentation

Once the application is running, access the interactive API documentation:
- Swagger UI: `http://<your-ip>:8000/docs`
- ReDoc: `http://<your-ip>:8000/redoc`

### Key Endpoints

- **Authentication**:
  - `POST /api/users/register` - Register new user
  - `POST /api/users/login` - Login and get token
  - `GET /api/users/me` - Get current user

- **Items**:
  - `GET /api/items` - List items (with filters)
  - `POST /api/items` - Create item
  - `PUT /api/items/{id}` - Update item
  - `DELETE /api/items/{id}` - Delete item

- **Meals**:
  - `GET /api/meals` - List meals (with filters)
  - `POST /api/meals` - Create meal with ingredients
  - `GET /api/meals/{id}` - Get meal details
  - `PUT /api/meals/{id}` - Update meal
  - `DELETE /api/meals/{id}` - Delete meal

- **Shopping Lists**:
  - `GET /api/shopping-lists` - List shopping lists
  - `POST /api/shopping-lists` - Create shopping list
  - `POST /api/shopping-lists/{id}/add-meal` - Add meal to list
  - `POST /api/shopping-lists/{id}/add-item` - Add item to list
  - `POST /api/shopping-lists/{id}/add-custom` - Add custom text
  - `GET /api/shopping-lists/{id}/export` - Export as formatted text

- **Search**:
  - `GET /api/search?q=chicken&type=all` - Unified search

## Architecture Notes

### Multi-User Isolation

- **User-specific**: Meals and shopping lists are isolated per user
- **Shared**: Items, categories, and cuisines are shared across all users

### Database Schema

- **Users**: User accounts with password hashing
- **Items**: Grocery items with optional nutritional data
- **Meals**: Recipes with ingredients (many-to-many with items)
- **Shopping Lists**: Collections of meals and direct items
- **Categories & Cuisines**: Classification for items and meals

### Security

- Passwords are hashed using bcrypt
- JWT tokens for authentication
- Token-based API access
- Configurable secret key (set `SECRET_KEY` environment variable)

## Customization

### Change Port

Edit `docker-compose.yml`:
```yaml
ports:
  - "8080:8000"  # Change 8080 to your preferred port
```

### Set Secret Key

For production, set a secure random secret key:

```bash
# Generate a random key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set it in docker-compose.yml or as environment variable
export SECRET_KEY="your-secure-random-key"
docker-compose up -d
```

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs -f
```

### Can't access from other devices

1. Check Raspberry Pi firewall
2. Verify the Pi's IP address: `hostname -I`
3. Make sure you're on the same network

### Database errors

Reset the database (⚠️ deletes all data):
```bash
docker-compose down
docker volume rm mealmate_data
docker-compose up -d
```

### Frontend can't connect to backend

1. Check browser console for errors
2. Verify API_BASE_URL in `frontend/js/api.js`
3. Check CORS settings in `backend/app/main.py`

## Future Enhancements

Potential features to add:
- [ ] Full CRUD UI for items and meals in Manage tab
- [ ] Image upload for meals
- [ ] Meal calendar/planning
- [ ] Nutritional summaries
- [ ] Barcode scanning for items
- [ ] Shopping list sharing between users
- [ ] Dark mode

## License

See LICENSE file.

## Support

For issues or questions, please check the [PROJECT_STATUS.md](PROJECT_STATUS.md) file for development status and implementation details.
