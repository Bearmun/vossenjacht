#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

# Initialize the database; creates tables if they don't exist.
# FLASK_APP is already set as an ENV in the Dockerfile.
echo "Attempting to initialize database..."
flask init-db
echo "Database initialization attempt complete."

# Now, run the main application.
# FLASK_RUN_HOST and FLASK_RUN_PORT are also set in Dockerfile.
echo "Starting Flask application..."
exec flask run
