# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt /app/

# Install dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the application code
COPY . /app/

# Expose port 5000
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=src/app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Use gunicorn in production (or flask run for development)
CMD ["flask", "run"]
