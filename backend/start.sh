#!/bin/bash
# Startup script for MealMate with HTTPS

# Check if SSL certificates exist
if [ -f "/app/certs/cert.pem" ] && [ -f "/app/certs/key.pem" ]; then
    echo "SSL certificates found. Starting HTTPS server on port 8443..."
    uvicorn app.main:app --host 0.0.0.0 --port 8443 \
        --ssl-keyfile=/app/certs/key.pem \
        --ssl-certfile=/app/certs/cert.pem
else
    echo "ERROR: SSL certificates not found!"
    echo "Please generate certificates using the instructions in README.md"
    exit 1
fi
