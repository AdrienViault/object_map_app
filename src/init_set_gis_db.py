#!/usr/bin/env python3
"""
This script sets up the GIS environment on your Azure managed PostgreSQL database.
It loads connection details from a .env file, enables the PostGIS extension,
drops the existing 'markers' table if present, creates a new one with GIS columns,
and inserts a sample record for testing.
"""

import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor

# Load environment variables from .env
load_dotenv()

# Retrieve connection details from environment variables
DB_NAME = os.environ.get("DB_NAME", "geodb")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

# Connect to the Azure managed PostgreSQL database
try:
    conn = psycopg2.connect(
        database=DB_NAME,
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

# Enable the PostGIS extension to support GIS functionality
try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    conn.commit()
    print("[DEBUG] PostGIS extension enabled.")
except Exception as e:
    print("[DEBUG] Error enabling PostGIS extension:", e)
    conn.rollback()
    exit(1)

# Drop the existing markers table if it exists
drop_table_query = "DROP TABLE IF EXISTS markers;"
print("[DEBUG] Dropping table 'markers' if it exists...")
cur.execute(drop_table_query)
conn.commit()

# Create the markers table with GIS columns for point and polygon geometries
create_table_query = """
CREATE TABLE markers (
    id SERIAL PRIMARY KEY,
    label TEXT,
    score REAL,
    geom geometry(Point,4326),
    bounding_box geometry(Polygon,4326),
    projection_path TEXT,
    detection_path TEXT,
    crop_path TEXT,
    depth_path TEXT
);
"""
print("[DEBUG] Creating table 'markers' with GIS columns...")
cur.execute(create_table_query)
conn.commit()
print("[DEBUG] Table 'markers' created successfully.")

# Optionally, insert a sample record to test the setup
insert_query = """
INSERT INTO markers (label, score, geom, bounding_box, projection_path, detection_path, crop_path, depth_path)
VALUES (
    'Sample Marker', 
    0.95, 
    'SRID=4326;POINT(-0.1278 51.5074)', 
    NULL, 
    '/path/to/projection.jpg', 
    '/path/to/detection.jpg', 
    '/path/to/crop.jpg', 
    '/path/to/depth.jpg'
);
"""
print("[DEBUG] Inserting a sample record into 'markers'...")
cur.execute(insert_query)
conn.commit()
print("[DEBUG] Sample record inserted successfully.")

# Query the table to verify the record was inserted
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

# Optionally, print table structure information
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

# Close the database connection
conn.close()
print("[DEBUG] Database connection closed.")

print("""
[RECOMMENDATION]
The 'markers' table has been set up with the following columns:
 - id: Primary key.
 - label: Marker label.
 - score: Detection confidence score.
 - geom: PostGIS Point (latitude/longitude).
 - bounding_box: PostGIS Polygon for the bounding box.
 - projection_path: Path to the projection image.
 - detection_path: Path to the detection image.
 - crop_path: Path to the cropped image.
 - depth_path: Path to the depth map image.

You can now insert marker data and run spatial queries using PostGIS functions.
""")
