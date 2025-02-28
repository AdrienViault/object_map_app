import os
import json
import psycopg2
from flask import Flask, render_template, jsonify, request, send_from_directory
from psycopg2.extras import RealDictCursor

# Set up Flask with the correct template folder (one level above src)
template_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'templates')
app = Flask(__name__, template_folder=template_dir)

# Database connection parameters – update these with your actual values.
DB_NAME = "geodb"
DB_USER = "postgres"
DB_PASS = "D^A@cn5W"
DB_HOST = "localhost"

def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST
    )
    return conn

@app.route('/')
def index():
    # Render index.html from the templates folder.
    return render_template('index.html')

@app.route('/markers')
def markers():
    """
    Expects query parameters:
      minlat, minlon, maxlat, maxlon (bounding box in decimal degrees).
    Returns markers (as JSON) that intersect the bounding box.
    """
    try:
        minlat = float(request.args.get('minlat'))
        minlon = float(request.args.get('minlon'))
        maxlat = float(request.args.get('maxlat'))
        maxlon = float(request.args.get('maxlon'))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid bounding box parameters."}), 400

    # Build bounding box using ST_MakeEnvelope (note: longitude first, then latitude)
    envelope = f"ST_MakeEnvelope({minlon}, {minlat}, {maxlon}, {maxlat}, 4326)"
    query = f"""
        SELECT id, label, score, projection_path, detection_path, depth_path,
               ST_AsGeoJSON(geom) AS geom
        FROM markers
        WHERE geom && {envelope};
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/image/<path:filename>')
def serve_image(filename):
    """
    Serves images from the images folder.
    Your images folder contains a symlink 'Grenoble' pointing to the actual storage location.
    """
    images_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'images')
    return send_from_directory(images_dir, filename)

if __name__ == '__main__':
    app.run(debug=True)
