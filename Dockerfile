# Multi-stage Dockerfile for MealMate
# Optimized for Raspberry Pi 3 (ARM architecture)

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app /app/app
COPY backend/test_data.py /app/test_data.py
COPY backend/start.sh /app/start.sh

# Make startup script executable
RUN chmod +x /app/start.sh

# Copy frontend files
COPY frontend /app/frontend

# Create data directory for SQLite database
RUN mkdir -p /data

# Set environment variables
ENV DATABASE_PATH=/data/mealmate.db
ENV PYTHONUNBUFFERED=1

# Expose ports (HTTP and HTTPS)
EXPOSE 8000 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application using startup script
CMD ["/app/start.sh"]
