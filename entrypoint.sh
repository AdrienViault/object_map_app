#!/bin/bash
set -e

# Load environment variables from .env if available (only valid assignment lines)
if [ -f /app/.env ]; then
  echo "Loading environment variables from .env"
  export $(grep -v '^#' /app/.env | grep -E '^[A-Za-z_][A-Za-z0-9_]*=' | xargs)
fi

# Ensure required variables are set
if [ -z "$AZURE_STORAGE_ACCOUNT" ] || [ -z "$AZURE_STORAGE_KEY" ]; then
  echo "Error: AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_KEY must be set"
  exit 1
fi


# Execute the command passed to the container (e.g., start your app)
exec "$@"
