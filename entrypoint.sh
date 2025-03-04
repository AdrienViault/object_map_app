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

# Create a configuration file (config.yaml) using a structure similar to the official doc.
cat <<EOF > ./config.yaml
version: 2.0
logging:
  type: syslog
  level: log_debug
components:
  - libfuse
  - file_cache
  - attr_cache
  - azstorage
libfuse:
  attribute-expiration-sec: 120
  entry-expiration-sec: 120
  negative-entry-expiration-sec: 240
file_cache:
  path: ./cache_dir
  timeout-sec: 120
  max-size-mb: 4096
attr_cache:
  timeout-sec: 7200
azstorage:
  type: block
  mode: key
  account-name: ${AZURE_STORAGE_ACCOUNT}
  account-key: ${AZURE_STORAGE_KEY}
  container: utility-images-container
EOF

echo "Blobfuse2 configuration file:"
cat ./config.yaml

# Create mount and cache directories
mkdir -p ./mount_dir
mkdir -p ./cache_dir

# Mount the Azure Blob Storage container using blobfuse2 with additional parameters:
# --container-name: override container name to "blobfuse2b"
# --log-level and --log-file-path: set logging parameters.
echo "print where we are"
echo $(pwd)

echo "Mounting Azure Blob Storage container..."
ls -la /app/mount_dir
blobfuse2 mount /app/mount_dir --config-file=./config.yaml --log-file-path=./bobfuse2b.log
echo "Azure Blob Storage container mounted"
echo "show tree of depth 3 in the mounted dir : "
echo $(tree -L 2 /app/mount_dir)

#show content of images folder if it exists before mount
#first test existence of images folder and create it if it does not exist
if [ -d "/app/images" ]; then
  echo "Images directory exists before mount"
  echo "Images directory content before mount:"
  echo $(ls /app/images)
else
  echo "Images directory does not exist before mount"
  mkdir -p /app/images
  echo "Images directory created"
fi


ln -sf /app/mount_dir/SmallDataset/Grenoble /app/images/Grenoble
echo "Symbolic link created"
echo "Images directory:"
echo $(ls /app/images)
echo "content of Grenoble directory:"
echo $(ls /app/images/Grenoble/)
echo "content of Blueberry directory:"
echo $(ls /app/images/Grenoble/Blueberry/)


# Execute the command passed to the container (e.g., start your app)
exec "$@"
