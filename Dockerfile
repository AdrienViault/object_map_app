FROM python:3.9-slim

# Install prerequisites for blobfuse2 and basic tools
RUN apt-get update && \
    apt-get install -y wget dpkg apt-transport-https curl gnupg libfuse3-dev fuse3

# Add Microsoft package repository for blobfuse2 and install it
RUN wget https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    rm packages-microsoft-prod.deb && \
    apt-get update && \
    apt-get install -y blobfuse2 && \
    apt-get install tree

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the application code and the .env file into the container
COPY . /app/

# Copy the entrypoint script and make it executable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set environment variables for Flask
ENV FLASK_APP=src/app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5001
EXPOSE 5001

# Use the entrypoint script to mount blob storage and start Flask
ENTRYPOINT ["/entrypoint.sh"]
CMD ["flask", "run"]