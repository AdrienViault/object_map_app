#!/usr/bin/env python3
"""
This script processes JSON metadata files and inserts marker records into a PostGIS-enabled PostgreSQL database.
It creates the markers table with a unique constraint on projection_path (adjust this as needed) so that duplicate
objects (markers) are not inserted multiple times.
"""

import os
import json
import glob
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Retrieve connection details from environment variables
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
METADATA_DIR = os.environ.get("METADATA_DIR", "./metadata")
print(f"[DEBUG] Using metadata directory: {METADATA_DIR}")

def convert_dms_to_decimal(dms, ref):
    """
    Convert a DMS dictionary to a decimal degree value.
    dms should be a dict with keys "degrees", "minutes", "seconds".
    """
    try:
        degrees = float(dms.get("degrees", 0))
        minutes = float(dms.get("minutes", 0))
        seconds = float(dms.get("seconds", 0))
    except Exception as e:
        print(f"[DEBUG] Error converting DMS values: {e}")
        raise e
    decimal = degrees + minutes / 60 + seconds / 3600
    if ref in ['S', 'W']:
        decimal = -decimal
    print(f"[DEBUG] Converted DMS {dms} with ref '{ref}' to decimal: {decimal}")
    return decimal

def load_markers_from_metadata(metadata_dir):
    """
    Scans through all JSON metadata files in metadata_dir (and subdirectories)
    and builds a list of marker dictionaries. Computes decimal latitude/longitude 
    and extracts bounding box information.
    """
    markers = []
    metadata_files = glob.glob(os.path.join(metadata_dir, "**", "*_metadata.json"), recursive=True)
    print(f"[DEBUG] Found {len(metadata_files)} metadata files in {metadata_dir}.")

    for filepath in metadata_files:
        print(f"[DEBUG] Processing file: {filepath}")
        try:
            with open(filepath, "r") as f:
                meta = json.load(f)
        except Exception as e:
            print(f"[DEBUG] Error reading {filepath}: {e}")
            continue
        
        # Process each detected object in the metadata file.
        for obj in meta.get("objects", []):
            comp = obj.get("computed_location", {})
            lat_dms = comp.get("GPSLatitude", {})
            lon_dms = comp.get("GPSLongitude", {})
            lat_ref = comp.get("GPSLatitudeRef", "N")
            lon_ref = comp.get("GPSLongitudeRef", "E")
            
            try:
                decimal_lat = convert_dms_to_decimal(lat_dms, lat_ref)
                decimal_lon = convert_dms_to_decimal(lon_dms, lon_ref)
            except Exception as e:
                print(f"[DEBUG] Error converting DMS to decimal in {filepath}: {e}")
                continue
            
            # Update computed_location with decimal values.
            obj.setdefault("computed_location", {})["decimal_lat"] = decimal_lat
            obj["computed_location"]["decimal_lon"] = decimal_lon
            print(f"[DEBUG] Updated computed_location with decimals: lat={decimal_lat}, lon={decimal_lon}")

            # Extract bounding box information from the key "bounding_box".
            bb = obj.get("bounding_box")
            if bb:
                try:
                    xmin = float(bb.get("xmin"))
                    ymin = float(bb.get("ymin"))
                    xmax = float(bb.get("xmax"))
                    ymax = float(bb.get("ymax"))
                    # Create a WKT polygon for the bounding box.
                    bbox_wkt = f'POLYGON(({xmin} {ymin}, {xmax} {ymin}, {xmax} {ymax}, {xmin} {ymax}, {xmin} {ymin}))'
                    obj["bbox_wkt"] = bbox_wkt
                    print(f"[DEBUG] Processed bounding_box for marker: {bbox_wkt}")
                except Exception as e:
                    print(f"[DEBUG] Error processing bounding_box in {filepath}: {e}")
                    obj["bbox_wkt"] = None
            else:
                obj["bbox_wkt"] = None
                print(f"[DEBUG] No bounding_box found for marker in {filepath}.")
            
            markers.append(obj)
    
    return markers

# Load markers from metadata files
markers = load_markers_from_metadata(METADATA_DIR)
print(f"[DEBUG] Loaded {len(markers)} markers from metadata.")

# Connect to the remote Azure managed PostgreSQL database
try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    cur = conn.cursor()
    print("[DEBUG] Successfully connected to the database.")
except Exception as e:
    print("[DEBUG] Error connecting to the database:", e)
    exit(1)

# Enable the PostGIS extension (if not already enabled)
try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    conn.commit()
    print("[DEBUG] PostGIS extension enabled.")
except Exception as e:
    print("[DEBUG] Error enabling PostGIS extension:", e)
    conn.rollback()

# Create the markers table if it does not exist, with a unique constraint on projection_path
create_table_query = """
CREATE TABLE IF NOT EXISTS markers (
    id SERIAL PRIMARY KEY,
    label TEXT,
    score REAL,
    geom geometry(Point,4326),
    bounding_box geometry(Polygon,4326),
    projection_path TEXT UNIQUE,
    detection_path TEXT,
    crop_path TEXT,
    depth_path TEXT
);
"""

print("[DEBUG] Creating table 'markers' if it does not exist...")
cur.execute(create_table_query)
conn.commit()
print("[DEBUG] Table 'markers' is ready.")

# Create an index on the label column to speed up queries filtering by category
create_index_query = "CREATE INDEX idx_markers_label ON markers(label);"
cur.execute(create_index_query)
conn.commit()


# Prepare a list of records for insertion from the markers data
records = []
for marker in markers:
    try:
        decimal_lat = marker["computed_location"]["decimal_lat"]
        decimal_lon = marker["computed_location"]["decimal_lon"]
    except KeyError:
        print("[DEBUG] Skipping marker with missing computed_location:", marker)
        continue

    # Build WKT for the point geometry.
    point_wkt = f'SRID=4326;POINT({decimal_lon} {decimal_lat})'
    
    # Get bounding box WKT if available.
    bbox_wkt = marker.get("bbox_wkt")
    if bbox_wkt:
        bbox_wkt = f"SRID=4326;{bbox_wkt}"
        print(f"[DEBUG] Using bounding_box WKT: {bbox_wkt}")
    else:
        bbox_wkt = None
        print("[DEBUG] No bounding_box WKT for marker, setting to NULL.")

    record = (
        marker.get("label", "Unknown"),
        marker.get("score", 0.0),
        point_wkt,
        bbox_wkt,
        marker.get("projection_path", ""),  # Ensure that each marker has a unique projection_path
        marker.get("detection_path", marker.get("projection_path", "")),
        marker.get("crop_path", ""),
        marker.get("depth_path", "")
    )
    print("[DEBUG] Prepared record:", record)
    records.append(record)

print(f"[DEBUG] Prepared {len(records)} records for insertion.")

# Prepare the INSERT query using execute_values for efficient bulk insert.
# This query uses ON CONFLICT DO NOTHING so that if a marker (by projection_path) already exists, it is skipped.
insert_query = """
INSERT INTO markers (label, score, geom, bounding_box, projection_path, detection_path, crop_path, depth_path)
VALUES %s
ON CONFLICT (projection_path) DO NOTHING;
"""

try:
    print("[DEBUG] Inserting records into the database with conflict checking...")
    execute_values(cur, insert_query, records)
    conn.commit()
    print(f"[DEBUG] Inserted records into the database (duplicates were skipped).")
except Exception as e:
    conn.rollback()
    print("[DEBUG] Error inserting markers:", e)

# Query the table to verify the inserted data
try:
    print("[DEBUG] Querying the first 10 markers from the database:")
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, label, score, ST_AsText(geom) AS geom, 
               ST_AsText(bounding_box) AS bounding_box, 
               projection_path, detection_path, crop_path, depth_path 
        FROM markers LIMIT 10;
    """)
    rows = cur.fetchall()
    for row in rows:
        print("[DEBUG] Queried marker:", row)
    cur.close()
except Exception as e:
    print("[DEBUG] Error querying markers:", e)

# Optionally, display the table structure information
try:
    print("[DEBUG] Querying table structure for 'markers':")
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'markers';
    """)
    columns = cur.fetchall()
    print("[DEBUG] Table 'markers' columns:")
    for col in columns:
        print(f"   {col[0]} ({col[1]})")
    cur.close()
except Exception as e:
    print("[DEBUG] Error querying table structure:", e)

conn.close()
print("[DEBUG] Database connection closed.")

print("""
[RECOMMENDATION]
The 'markers' table is now maintained without dropping existing records. Each marker is identified by its
projection_path (or another unique field if you change the constraint), so new markers are added only if they
do not already exist. This method scales well even with 150k objects, provided you have an appropriate index.
If your workflow involves incremental updates, this approach is more efficient than dropping and recreating the table.
""")
