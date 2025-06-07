# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set Timezone
ENV TZ="Europe/Amsterdam"

# Install tzdata for timezone support
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata && \
    rm -rf /var/lib/apt/lists/*

# Set Flask environment variables
ENV FLASK_APP app.py
ENV FLASK_RUN_HOST 0.0.0.0
ENV FLASK_RUN_PORT 8080
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

# Copy the startup script specifically and make it executable
COPY startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Define the command to run the app using the startup script
CMD ["/app/startup.sh"]
