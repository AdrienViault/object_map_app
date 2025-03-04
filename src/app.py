import os
import json
import psycopg2
from flask import Flask, render_template, jsonify, request, send_from_directory
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Retrieve database connection settings from environment variables
DB_NAME = os.getenv("DB_NAME", "geodb")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "defaultpassword")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

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
    images_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'images')
    full_path = os.path.join(images_dir, filename)
    print(f"[DEBUG] Serving image from: {full_path}")
    if not os.path.exists(full_path):
        print("[DEBUG] File does not exist:", full_path)
    return send_from_directory(images_dir, filename)

if __name__ == '__main__':
    print("[DEBUG] Starting Flask app in debug mode.")
    app.run(debug=True, port=5001)