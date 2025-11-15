# MealMate

A comprehensive meal planning and grocery shopping list management web application. Designed for mobile-first use (optimized for iPhone) with HTTPS support for secure Web Share API functionality.

## Features

- **Multi-user support** with authentication
- **Meal planning** with recipes and ingredients
- **Shopping list management** with smart meal-to-grocery conversion
- **Search & filter** for items and meals
- **Export options**: Copy to clipboard or share directly to iOS Notes app (via Web Share API)
- **Database-driven** with SQLite (persistent across updates)
- **Docker deployment** with HTTPS support
- **Mobile-first responsive design**
- **Secure HTTPS** - Required for iOS Web Share API

## Tech Stack

- **Backend**: Python + FastAPI
- **Frontend**: Vanilla JavaScript (no framework)
- **Database**: SQLite
- **Security**: HTTPS with self-signed SSL certificate
- **Deployment**: Docker + Docker Compose
- **Target Platform**: Raspberry Pi 3 (ARM architecture)

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- OpenSSL (for generating SSL certificates)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd MealMate
```

### 2. Generate SSL Certificates

**Important**: Replace `192.168.178.97` with your server's actual IP address.

```bash
# Create certificates directory
mkdir -p certs

# Generate self-signed certificate (valid for 365 days)
cd certs
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 \
  -subj "/C=DE/ST=State/L=City/O=MealMate/CN=mealmate.local" \
  -addext "subjectAltName=IP:192.168.178.97,DNS:mealmate.local,DNS:localhost"
cd ..
```

### 3. Build and Run with Docker Compose

```bash
docker-compose up -d --build
```

### 4. Access the Application

**From Desktop/Mac:**
- URL: `https://<your-server-ip>:8443`
- Example: `https://192.168.178.97:8443`
- You'll need to accept the self-signed certificate warning

**From iPhone/Mobile:**
1. Open Safari and navigate to `https://<your-server-ip>:8443`
2. You'll see a security warning - tap **"Show Details"** → **"visit this website"**
3. Accept the certificate (this is safe - it's your own certificate)
4. For best experience: Add to Home Screen (Share → Add to Home Screen)

### 5. Create Your First User

- Click "Register" and create an account
- Or use test data (see below)

## Populate Test Data (Optional)

Add sample data for testing:

```bash
docker-compose exec mealmate python test_data.py
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
   - **Copy to Clipboard**: Copy the text to paste anywhere
   - **Share to Notes** (iOS only): Opens iOS share sheet to select Notes or any other app

### Web Share API (iOS Share to Notes)

The "Share to Notes" button uses the native iOS share sheet, which requires HTTPS to work. This is why MealMate uses SSL certificates.

**On iPhone:**
- Access via `https://<ip>:8443`
- Accept the certificate
- Click "Share to Notes" → Select Notes app (or any other app)

**On Desktop:**
- The share button may show an error if Web Share API is not available
- Use "Copy to Clipboard" instead

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
│   ├── test_data.py             # Sample data script
│   └── start.sh                 # HTTPS startup script
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js               # Main application logic
│       ├── api.js               # API communication
│       └── export.js            # Export utilities
├── certs/                       # SSL certificates (generated)
│   ├── cert.pem
│   └── key.pem
├── Dockerfile
├── docker-compose.yml
└── README.md
```

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

## API Documentation

Once the application is running, access the interactive API documentation:
- Swagger UI: `https://<your-ip>:8443/docs`
- ReDoc: `https://<your-ip>:8443/redoc`

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

## SSL Certificate Management

### Regenerating Certificates

If your IP address changes or the certificate expires (365 days):

```bash
cd certs
rm cert.pem key.pem

# Replace with your new IP address
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 \
  -subj "/C=DE/ST=State/L=City/O=MealMate/CN=mealmate.local" \
  -addext "subjectAltName=IP:YOUR_NEW_IP,DNS:mealmate.local,DNS:localhost"

cd ..
docker-compose restart
```

### Certificate Details

- **Type**: Self-signed SSL certificate
- **Key size**: 4096-bit RSA
- **Validity**: 365 days
- **Location**: `./certs/` directory
- **Mounted in container**: Read-only at `/app/certs/`

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

- **HTTPS**: All traffic encrypted with SSL/TLS
- **Passwords**: Hashed using bcrypt
- **JWT tokens**: For authentication
- **CORS**: Configured to allow local network access
- **Secret key**: Configurable via environment variable

## Customization

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

### SSL certificate errors

Make sure certificates exist:
```bash
ls -la certs/
# Should show cert.pem and key.pem
```

If missing, regenerate them (see SSL Certificate Management section).

### Can't access from iPhone

1. Make sure you're using HTTPS: `https://<ip>:8443`
2. Accept the certificate warning in Safari
3. Check that iPhone is on the same WiFi network
4. Try adding to Home Screen for better experience

### Share to Notes not working

1. Verify you're using HTTPS (not HTTP)
2. Check browser console for errors (see debugging below)
3. Make sure you accepted the certificate
4. Try accessing from Home Screen app

### Debugging on iPhone

1. On iPhone: Settings → Safari → Advanced → Web Inspector (enable)
2. Connect iPhone to Mac via USB or WiFi
3. On Mac: Safari → Develop → [Your iPhone] → [MealMate page]
4. Check Console for debug messages

### Database errors

Reset the database (⚠️ deletes all data):
```bash
docker-compose down
docker volume rm mealmate_data
docker-compose up -d
```

## Future Enhancements

Potential features to add:
- [ ] Full CRUD UI for items and meals in Manage tab
- [ ] Image upload for meals
- [ ] Meal calendar/planning
- [ ] Nutritional summaries
- [ ] Barcode scanning for items
- [ ] Shopping list sharing between users
- [ ] Dark mode
- [ ] Let's Encrypt SSL certificate support

## License

See LICENSE file.
