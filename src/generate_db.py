import os
import json
import glob
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor

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
    and builds a list of marker dictionaries.
    It computes decimal latitude and longitude from the DMS values in computed_location.
    Additionally, it extracts bounding box information from the "bounding_box" key.
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

# Define the directory where your JSON metadata files are stored.
metadata_dir = "/media/adrien/Space/Datasets/Overhead/processed/"
markers = load_markers_from_metadata(metadata_dir)
print(f"[DEBUG] Loaded {len(markers)} markers from metadata.")

# Connect to PostgreSQL database.
try:
    conn = psycopg2.connect(dbname="geodb", user="postgres", password="D^A@cn5W", host="localhost")
    cur = conn.cursor()
    print("[DEBUG] Connected to the database.")
except Exception as e:
    print("[DEBUG] Database connection error:", e)
    exit(1)

# Drop the existing markers table if it exists.
drop_table_query = "DROP TABLE IF EXISTS markers;"
print("[DEBUG] Dropping the existing markers table if it exists...")
cur.execute(drop_table_query)
conn.commit()

# Create the markers table with an extra column for bounding box geometry and crop_path.
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
print("[DEBUG] Creating the markers table with bounding_box and crop_path columns...")
cur.execute(create_table_query)
conn.commit()
print("[DEBUG] Table created successfully.")

# Prepare a list of records for insertion.
records = []
for marker in markers:
    try:
        decimal_lat = marker["computed_location"]["decimal_lat"]
        decimal_lon = marker["computed_location"]["decimal_lon"]
    except KeyError:
        print("[DEBUG] Skipping marker with missing computed_location:", marker)
        continue

    # WKT for the point geometry.
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
        marker.get("projection_path", ""),
        marker.get("detection_path", marker.get("projection_path", "")),
        marker.get("crop_path", ""),
        marker.get("depth_path", "")
    )
    print("[DEBUG] Prepared record:", record)
    records.append(record)

print(f"[DEBUG] Prepared {len(records)} records for insertion.")

# Prepare the INSERT query.
insert_query = """
INSERT INTO markers (label, score, geom, bounding_box, projection_path, detection_path, crop_path, depth_path)
VALUES %s;
"""

# Insert the records using execute_values for efficiency.
try:
    print("[DEBUG] Inserting records into the database...")
    execute_values(cur, insert_query, records)
    conn.commit()
    print(f"[DEBUG] Inserted {len(records)} markers into the database.")
except Exception as e:
    conn.rollback()
    print("[DEBUG] Error inserting markers:", e)

# At the end, query the table to show what can be queried.
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

# Additionally, print information about the table structure.
try:
    print("[DEBUG] Querying table structure (column names) for 'markers':")
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

# Recommendations on how to use the table.
print("""
[RECOMMENDATION]
The 'markers' table now includes the following columns:
 - id: Primary key.
 - label: A description or label for the detected object.
 - score: The confidence score for the detection.
 - geom: A PostGIS Point representing the computed location (latitude/longitude).
 - bounding_box: A PostGIS Polygon representing the bounding box where the object was detected.
 - projection_path: The relative path to the full projection image.
 - detection_path: The relative path to the detection image (e.g., with bounding box overlay).
 - crop_path: The relative path to the cropped image of the object.
 - depth_path: The relative path to the depth map image of the object.

You can query this table to retrieve markers within a specific area using spatial functions.
For example, to get markers within a viewport:
  SELECT * FROM markers
  WHERE geom && ST_MakeEnvelope(lon_min, lat_min, lon_max, lat_max, 4326);

This table allows you to display full projection images (and draw the bounding_box on them), 
show the cropped object, and display the depth map for each object.
""")
