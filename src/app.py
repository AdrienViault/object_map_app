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
AZURE_STORAGE_KEY = os.getenv("AZURE_STORAGE_KEY")
AZURE_BLOB_NAME = os.getenv("AZURE_BLOB_NAME", "utility-images-container")
AZURE_BLOB_PREFIX = os.getenv("AZURE_BLOB_PREFIX", "Grenoble")

# Initialize the BlobServiceClient
blob_service_client = BlobServiceClient(
    account_url=f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net",
    credential=AZURE_STORAGE_KEY
)

# Set up Flask with the correct template folder
template_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'templates')
static_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'static')

app = Flask(
    __name__,
    template_folder=template_dir,
    static_folder=static_dir
)

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
    return render_template('index.html')

@app.route('/categories')
def categories():
    query = "SELECT DISTINCT label FROM markers ORDER BY label;"
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query)
        results = cur.fetchall()
        cur.close()
        conn.close()
        cats = [row[0] for row in results]
        return jsonify(cats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/markers')
def markers():
    try:
        minlat = float(request.args.get('minlat'))
        minlon = float(request.args.get('minlon'))
        maxlat = float(request.args.get('maxlat'))
        maxlon = float(request.args.get('maxlon'))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid bounding box parameters."}), 400

    envelope = f"ST_MakeEnvelope({minlon}, {minlat}, {maxlon}, {maxlat}, 4326)"
    # Include source_path and object_depth in the select query.
    base_query = f"""
        SELECT id, label, score, projection_path, detection_path, crop_path, depth_path,
               source_path, object_depth,
               ST_AsGeoJSON(geom) AS geom,
               ST_AsGeoJSON(bounding_box) AS bounding_box
        FROM markers
        WHERE geom && {envelope}
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(base_query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/markers_clustered')
def markers_clustered():
    """
    Returns clusters of markers using server-side clustering.
    Markers within cluster_distance (in degrees) are grouped together.
    For each cluster, returns the centroid geometry and the number of markers in that cluster.
    Also applies category filtering if provided.
    """
    try:
        minlat = float(request.args.get('minlat'))
        minlon = float(request.args.get('minlon'))
        maxlat = float(request.args.get('maxlat'))
        maxlon = float(request.args.get('maxlon'))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid bounding box parameters."}), 400

    try:
        cluster_distance = float(request.args.get('cluster_distance', 0.05))
    except ValueError:
        cluster_distance = 0.05

    categories_param = request.args.get('categories')
    label_clause = ""
    label_params = []
    if categories_param:
        cat_list = [cat.strip() for cat in categories_param.split(',') if cat.strip()]
        if cat_list:
            placeholders = ",".join(["%s"] * len(cat_list))
            label_clause = f" AND label IN ({placeholders})"
            label_params = cat_list

    envelope = f"ST_MakeEnvelope({minlon}, {minlat}, {maxlon}, {maxlat}, 4326)"
    query = f"""
    WITH filtered AS (
      SELECT geom
      FROM markers
      WHERE geom && {envelope} {label_clause}
    ),
    clusters AS (
      SELECT unnest(ST_ClusterWithin(geom, %s)) AS cluster
      FROM filtered
    )
    SELECT 
      ST_AsGeoJSON(ST_Centroid(cluster)) AS geom,
      ST_NumGeometries(cluster) AS cluster_count
    FROM clusters;
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, (*label_params, cluster_distance))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        import traceback
        print("Error in /markers_clustered:", traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/markers_sample')
def markers_sample():
    """
    Returns a sample of markers from the database for debugging.
    This helps verify that the marker values (e.g., labels, geometries) are as expected.
    """
    sample_query = """
    SELECT id, label, score, ST_AsText(geom) AS geom, ST_AsText(bounding_box) AS bounding_box,
           projection_path, detection_path, crop_path, depth_path,
           source_path, gps_img_direction, object_depth, object_relative_angle 
    FROM markers
    ORDER BY id ASC
    LIMIT 10;
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sample_query)
        sample_rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(sample_rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/image/<path:filename>')
def serve_image(filename):
    container_name = AZURE_BLOB_NAME
    prefix = AZURE_BLOB_PREFIX.rstrip('/')
    subfolder = os.path.basename(prefix)
    if filename.startswith(f"{subfolder}/"):
        filename = filename[len(subfolder) + 1:]
    
    blob_path = f"{prefix}/{filename}"
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        download_stream = blob_client.download_blob()
        image_data = download_stream.readall()
        mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            mimetype = 'application/octet-stream'
        return send_file(BytesIO(image_data), download_name=filename, mimetype=mimetype)
    except Exception as e:
        return jsonify({"error": f"Error retrieving image: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
