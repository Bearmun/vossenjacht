# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP app.py
ENV FLASK_RUN_HOST 0.0.0.0
ENV FLASK_RUN_PORT 8080
# Define a directory for the database that can be mounted as a volume
ENV DATABASE_PATH /data/foxhunt.db

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# This includes app.py, static/, templates/, init_db.py
COPY . .

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Ensure the /data directory exists for the database
RUN mkdir -p /data

# Define the command to run the app
# The init-db command should be run by the user when setting up the volume first time.
# Or the app's auto-init will handle it if the DB file doesn't exist at DATABASE_PATH.
CMD ["flask", "run"]
