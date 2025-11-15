#!/bin/bash
# Startup script for MealMate with HTTPS support

# Check if SSL certificates exist
if [ -f "/app/certs/cert.pem" ] && [ -f "/app/certs/key.pem" ]; then
    echo "SSL certificates found. Starting HTTPS server on port 8443..."
    echo "Also starting HTTP server on port 8000 for backwards compatibility..."

    # Start HTTP server in background
    uvicorn app.main:app --host 0.0.0.0 --port 8000 &

    # Start HTTPS server in foreground
    uvicorn app.main:app --host 0.0.0.0 --port 8443 \
        --ssl-keyfile=/app/certs/key.pem \
        --ssl-certfile=/app/certs/cert.pem
else
    echo "SSL certificates not found. Starting HTTP-only server on port 8000..."
    uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
