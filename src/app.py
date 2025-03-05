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
AZURE_BLOB_PREFIX = os.getenv("AZURE_BLOB_PREFIX", "SmallDataset/Grenoble")

# Initialize the BlobServiceClient
blob_service_client = BlobServiceClient(
    account_url=f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net",
    credential=AZURE_STORAGE_KEY
)

# Set up Flask with the correct template folder
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
    base_query = f"""
        SELECT id, label, score, projection_path, detection_path, crop_path, depth_path,
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
        # Parse and log bounding box parameters.
        minlat = float(request.args.get('minlat'))
        minlon = float(request.args.get('minlon'))
        maxlat = float(request.args.get('maxlat'))
        maxlon = float(request.args.get('maxlon'))
        print("[DEBUG] Bounding box parameters received:",
              f"minlat={minlat}, minlon={minlon}, maxlat={maxlat}, maxlon={maxlon}")
    except (TypeError, ValueError) as e:
        print("[DEBUG] Error parsing bounding box parameters:", e)
        return jsonify({"error": "Missing or invalid bounding box parameters."}), 400

    try:
        cluster_distance = float(request.args.get('cluster_distance', 0.05))
        print("[DEBUG] Cluster distance parameter:", cluster_distance)
    except ValueError as e:
        print("[DEBUG] Error parsing cluster_distance, defaulting to 0.05:", e)
        cluster_distance = 0.05

    # Process and strip the category values.
    categories_param = request.args.get('categories')
    label_clause = ""
    label_params = []
    if categories_param:
        # This strips leading/trailing whitespace for each category
        cat_list = [cat.strip() for cat in categories_param.split(',') if cat.strip()]
        print("[DEBUG] Categories received:", cat_list)
        if cat_list:
            placeholders = ",".join(["%s"] * len(cat_list))
            label_clause = f" AND label IN ({placeholders})"
            label_params = cat_list
            print("[DEBUG] Constructed label filtering clause:", label_clause)
    else:
        print("[DEBUG] No category filtering applied.")

    envelope = f"ST_MakeEnvelope({minlon}, {minlat}, {maxlon}, {maxlat}, 4326)"
    print("[DEBUG] Constructed envelope:", envelope)

    # --- Extra Debug: Count markers in filtered set ---
    count_query = f"""
    SELECT COUNT(*) FROM markers
    WHERE geom && {envelope} {label_clause};
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        formatted_count_query = cur.mogrify(count_query, label_params).decode("utf-8")
        print("[DEBUG] Executing count query:", formatted_count_query)
        cur.execute(count_query, label_params)
        count = cur.fetchone()[0]
        print("[DEBUG] Count of markers in filtered set:", count)
        cur.close()
        conn.close()
    except Exception as e:
        print("[DEBUG] Error executing count query:", e)

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
        print("[DEBUG] Executing clustering query:")
        print(query)
        params = (*label_params, cluster_distance)
        formatted_query = cur.mogrify(query, params).decode("utf-8")
        print("[DEBUG] Formatted clustering query:", formatted_query)
        print("[DEBUG] Query parameters:", params)
        cur.execute(query, params)
        rows = cur.fetchall()
        print("[DEBUG] Clustering query returned rows:", rows)
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        import traceback
        print("[DEBUG] Error in /markers_clustered:", traceback.format_exc())
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
        print("[DEBUG] Executing sample query for markers:")
        print(sample_query)
        cur.execute(sample_query)
        sample_rows = cur.fetchall()
        print("[DEBUG] Sample markers returned:", sample_rows)
        cur.close()
        conn.close()
        return jsonify(sample_rows)
    except Exception as e:
        print("[DEBUG] Error in /markers_sample:", e)
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
