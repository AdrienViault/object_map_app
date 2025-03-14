import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import time

# Load environment variables from .env file.
load_dotenv()

def get_db_connection():
    """
    Connects to the PostgreSQL database using credentials from the .env file.
    Make sure your .env contains:
      DB_HOST, DB_PORT, DB_NAME, DB_USER, and DB_PASSWORD.
    """
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT")
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASS")
    
    print(f"DEBUG: Attempting connection to DB at {db_host}:{db_port} using database '{db_name}' and user '{db_user}'.")
    
    try:
        start_time = time.time()
        connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
            sslmode="require",       # Azure PostgreSQL requires SSL.
            connect_timeout=10       # Set a 10-second timeout to avoid hanging.
        )
        elapsed = time.time() - start_time
        print(f"DEBUG: Database connection established successfully in {elapsed:.2f} seconds.")
        return connection
    except Exception as e:
        print("ERROR: Could not connect to the database.")
        print(f"DEBUG: Exception details: {e}")
        raise

def get_categories():
    """
    Queries the database for distinct category labels from the markers table.
    Adjust the query if your app stores categories in a different table or column.
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = "SELECT DISTINCT label FROM markers ORDER BY label;"
            print(f"DEBUG: Executing query: {query}")
            cursor.execute(query)
            rows = cursor.fetchall()
            print(f"DEBUG: Query returned {len(rows)} rows.")
            categories = [row["label"] for row in rows]
            print(f"DEBUG: Categories extracted: {categories}")
            return categories
    except Exception as e:
        print("ERROR: Failed to execute query or process results.")
        print(f"DEBUG: Exception details: {e}")
        raise
    finally:
        conn.close()
        print("DEBUG: Database connection closed.")

if __name__ == "__main__":
    try:
        categories = get_categories()
        print(json.dumps(categories, indent=2))
    except Exception as e:
        print("ERROR: An error occurred during the execution of the script.")
        print(f"DEBUG: Exception details: {e}")
