to run pipe (ona few example, otherwise remove test option): 

 python -m src.pipeline.pipe --test




# Object Map App

This project is a containerized Flask application that displays markers (and related images) on a map. The project consists of two main services:

- **Web (Flask) Service:** Runs the Flask application that serves the map and images.
- **Database (PostgreSQL with PostGIS) Service:** Hosts a PostgreSQL database with PostGIS enabled to store marker data, including spatial geometries.

This guide explains how to set up, run, and manage the application using Docker Compose.

## Prerequisites

Ensure you have the following installed before proceeding:

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- Basic knowledge of Docker and Docker Compose
- (Optional) Python 3.x for running the database initialization script manually

## Project Structure

object_map_app/ ├── data/ # (Optional) Data files for markers or initial data ├── images/ # Local images directory (mounted into the web container) │ ├── example.jpg │ └── Grenoble -> /path/to/external/Grenoble (symlink; see below) ├── initdb/ # (Optional) SQL scripts for automatic DB initialization ├── src/
│ ├── app.py # Your Flask application │ └── generate_db.py # Script to generate/populate the markers table ├── Dockerfile # Dockerfile for the Flask web app ├── docker-compose.yml # Compose file for the web and database containers ├── .dockerignore # Exclude files/directories from being copied into images └── README.md # This documentation file


> **Note:**  
> If your `images` folder contains a symlink (e.g., `images/G

## Docker Setup

### Dockerfile

The `Dockerfile` defines how to build the Flask application image.

```dockerfile
# Use a lightweight official Python image.
FROM python:3.9-slim

# Environment variables for Python.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory.
WORKDIR /app

# Copy and install dependencies.
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the entire project (excluding files/directories listed in .dockerignore).
COPY . /app/

# Expose the port your Flask app will run on.
EXPOSE 5000

# Set environment variables for Flask.
ENV FLASK_APP=src/app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Start the Flask app.
CMD ["flask", "run"]


### **5. Docker Compose Configuration (`docker_compose.md`)**
```markdown
## Docker Compose

The `docker-compose.yml` file orchestrates the two containers: one for PostgreSQL (with PostGIS) and one for your Flask app. It also mounts your local images folder into the web container.

```yaml
version: "3.9"

services:
  db:
    image: postgis/postgis:13-3.1-alpine
    container_name: postgres_db
    restart: always
    environment:
      POSTGRES_DB: geodb
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: D^A@cn5W  # Replace with a secure password
    volumes:
      - db_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: flask_app
    restart: always
    environment:
      DB_NAME: geodb
      DB_USER: postgres
      DB_PASS: D^A@cn5W
      DB_HOST: db
    ports:
      - "5000:5000"
    depends_on:
      - db
    volumes:
      - /home/adrien/Documents/Dev/object_map_app/images:/app/images
      # Optionally, if your symlink points outside, mount that target too:
      - /media/adrien/Space/Datasets/Overhead/processed/Grenoble:/app/images/Grenoble
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G

volumes:
  db_data:


---

### 5. Database Initialization

```markdown
## Database Initialization

There are two approaches to initializing the database:

### Automatic Initialization via Docker Entrypoint
Place your SQL scripts (e.g., `01_create_tables.sql`) in the `initdb/` directory and mount it into the PostgreSQL container. The official PostgreSQL image will run these scripts on the first start when the data volume is empty.

### Manual Initialization
Alternatively, run your custom database generation script manually once the containers are running:

1. Start the containers:
   ```bash
   docker-compose up --build

    In another terminal, run:

docker exec -it flask_app python /app/src/generate_db.py

Verify the database by connecting to the DB container:

docker exec -it postgres_db psql -U postgres -d geodb

Then in psql:

    \dt
    SELECT * FROM markers LIMIT 10;


---

### 6. Running the Application

```markdown
## Running the Application

1. **Start the Containers:**
   ```bash
   docker-compose up --build

    Initialize the Database (if using manual initialization): Run your generate_db.py script:

    docker exec -it flask_app python /app/src/generate_db.py

    Access the Web App: Open your browser and navigate to http://localhost:5000.


---

### 7. Persistent Volumes and Data Persistence

```markdown
## Persistent Volumes and Data Persistence

The `db_data` volume (defined in `docker-compose.yml`) persists your PostgreSQL data between container restarts. If you run:

```bash
docker-compose down -v

the -v flag will remove the volume and erase the database data. For regular use, avoid using -v unless you want to reset the database.


---

### 8. Troubleshooting

```markdown
## Troubleshooting

- **Images Not Loading:**
  - Verify that the images directory is correctly mounted:
    ```bash
    docker exec -it flask_app ls -l /app/images
    ```
  - Ensure the directory structure matches the paths in your metadata.
  - Check that symlinks point to valid, accessible directories.

- **Database Table Not Found:**
  - Make sure your initialization script has run and the "markers" table exists:
    ```bash
    docker exec -it postgres_db psql -U postgres -d geodb
    \dt
    SELECT * FROM markers LIMIT 10;
    ```

- **Environment Variables:**
  - Use a `.env` file for sensitive data, and update your docker-compose.yml to load those variables.

9. Further Notes

## Further Notes

- **Container Networking:**  
  The web container connects to the database container using the service name `db` defined in Docker Compose.

- **Production Deployment:**  
  For production, consider using a managed database service instead of a containerized PostgreSQL, and use orchestration tools like Kubernetes for container management.
  
- **Secrets Management:**  
  Use a `.env` file or Docker Secrets (if using Docker Swarm) for managing sensitive environment variables securely.

10. Recommendations

## Recommendations

- **Initialization Workflow:**  
  For development, it's acceptable to start the containers, manually initialize the database (using your generate_db.py script), and then access the app via the browser.
  
- **Volume Mounts:**  
  Mount only the necessary directories into each container to keep images external and data persistent.
  
- **Documentation:**  
  Keep this README.md updated with any changes in setup, initialization, or deployment processes.
