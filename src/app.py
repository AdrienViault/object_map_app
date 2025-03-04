import os
import json
import psycopg2
import mimetypes
from io import BytesIO
from flask import Flask, render_template, jsonify, request, send_file
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Load environment variables from .env
load_dotenv()

# Database configuration
DB_NAME = os.getenv("DB_NAME", "geodb")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "defaultpassword")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# Azure Blob Storage configuration
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT", "streetutilityimagesacct")
AZURE_STORAGE_KEY = os.getenv("AZURE_STORAGE_KEY")  # Set this in your .env
AZURE_BLOB_NAME = os.getenv("AZURE_BLOB_NAME", "utility-images-container")
# Folder/prefix inside the blob container where your images are stored
AZURE_BLOB_PREFIX = os.getenv("AZURE_BLOB_PREFIX", "SmallDataset/Grenoble")

# Initialize the BlobServiceClient using the storage account details
blob_service_client = BlobServiceClient(
    account_url=f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net",
    credential=AZURE_STORAGE_KEY
)

# Set up Flask with the correct template folder (one level above src)
template_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'templates')
app = Flask(__name__, template_folder=template_dir)

def get_db_connection():
    """Establish a connection to the PostgreSQL database using environment settings."""
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    return conn

@app.route('/')
def index():
    print("[DEBUG] Rendering index.html")
    return render_template('index.html')

@app.route('/markers')
def markers():
    print("[DEBUG] Received request for /markers")
    try:
        minlat = float(request.args.get('minlat'))
        minlon = float(request.args.get('minlon'))
        maxlat = float(request.args.get('maxlat'))
        maxlon = float(request.args.get('maxlon'))
        print(f"[DEBUG] Received bounding box: minlat={minlat}, minlon={minlon}, maxlat={maxlat}, maxlon={maxlon}")
    except (TypeError, ValueError) as e:
        print("[DEBUG] Missing or invalid bounding box parameters:", e)
        return jsonify({"error": "Missing or invalid bounding box parameters."}), 400

    # Create bounding box using ST_MakeEnvelope (note: lon, lat order)
    envelope = f"ST_MakeEnvelope({minlon}, {minlat}, {maxlon}, {maxlat}, 4326)"
    query = f"""
        SELECT id, label, score, projection_path, detection_path, crop_path, depth_path,
               ST_AsGeoJSON(geom) AS geom,
               ST_AsGeoJSON(bounding_box) AS bounding_box
        FROM markers
        WHERE geom && {envelope};
    """
    print("[DEBUG] Executing SQL query:\n", query)
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query)
        rows = cur.fetchall()
        print(f"[DEBUG] Fetched {len(rows)} markers from the database.")
        for idx, row in enumerate(rows):
            print(f"[DEBUG] Marker {idx} keys: {list(row.keys())}")
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        print("[DEBUG] Error executing query:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/image/<path:filename>')
def serve_image(filename):
    """
    Retrieves images from Azure Blob Storage. It assumes images are stored under the prefix
    defined in AZURE_BLOB_PREFIX (e.g., "SmallDataset/Grenoble") inside the blob container.
    If the incoming filename already includes the subfolder (e.g., "Grenoble/"), that part
    is removed to avoid duplication.
    """
    container_name = AZURE_BLOB_NAME
    # Ensure the prefix does not end with a slash
    prefix = AZURE_BLOB_PREFIX.rstrip('/')
    # Get the subfolder name from the prefix (e.g., "Grenoble")
    subfolder = os.path.basename(prefix)
    # If filename already starts with the subfolder name, remove it
    if filename.startswith(f"{subfolder}/"):
        filename = filename[len(subfolder) + 1:]
    
    # Build the full blob path
    blob_path = f"{prefix}/{filename}"
    print(f"[DEBUG] Attempting to fetch blob: container={container_name}, blob={blob_path}")

    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        download_stream = blob_client.download_blob()
        image_data = download_stream.readall()
        # Determine MIME type based on filename
        mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            mimetype = 'application/octet-stream'
        print(f"[DEBUG] Serving image {filename} with mimetype {mimetype}")
        return send_file(BytesIO(image_data), download_name=filename, mimetype=mimetype)
    except Exception as e:
        print(f"[DEBUG] Error retrieving blob {blob_path}: {e}")
        return jsonify({"error": f"Error retrieving image: {str(e)}"}), 500

if __name__ == '__main__':
    print("[DEBUG] Starting Flask app in debug mode.")
    app.run(debug=True, port=5001)
