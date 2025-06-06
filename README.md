# Fox Hunt Statistics Tracker

A simple web application built with Flask to track statistics for a fox hunt.
Participants can enter their name, start/end kilometer readings, and arrival time.
The application calculates driven kilometers, total duration from a 12:00 PM start,
and displays sorted results. Data is stored in an SQLite database.

The application is primarily in Dutch.

## Features

*   Web interface for data entry and viewing results.
*   Calculation of driven kilometers, including odometer rollover (assumes max 1000km per rollover).
*   Calculation of hunt duration in minutes from a 12:00 PM start time.
*   Results sorted by kilometers driven (ascending), then by duration (ascending).
*   User interface in Dutch.
*   Persistent data storage using SQLite (`foxhunt.db`).

## Setup and Running

1.  **Prerequisites:**
    *   Python 3.x
    *   Flask: Install using pip: `pip install Flask`

2.  **Initialize the Database:**
    *   Before running the application for the first time, or to reset the database, initialize it using the Flask CLI.
    *   Open your terminal in the project root directory.
    *   Set the `FLASK_APP` environment variable:
        *   On Linux/macOS: `export FLASK_APP=app.py`
        *   On Windows (cmd): `set FLASK_APP=app.py`
        *   On Windows (PowerShell): `$env:FLASK_APP = "app.py"`
    *   Run the database initialization command:
        `flask init-db`
        (or `python -m flask init-db`)
    *   This will create a `foxhunt.db` file in the project root if it doesn't exist, and set up the necessary tables.

3.  **Run the Application:**
    *   Ensure `FLASK_APP` is still set as above.
    *   Run the Flask development server:
        `flask run --host=0.0.0.0 --port=8080`
        (or `python -m flask run --host=0.0.0.0 --port=8080`)
    *   Open your web browser and go to `http://localhost:8080` or `http://<your-machine-ip>:8080`.

## Database

*   The application uses an SQLite database named `foxhunt.db` located in the project root to store all entries.

## Running Tests (Optional)

*   To run the unit tests, navigate to the project root in your terminal and execute:
    `python -m unittest tests/test_app.py`
