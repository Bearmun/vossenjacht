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


## Running with Docker

This application can also be run as a Docker container.

1.  **Prerequisites:**
    *   Docker installed and running.

2.  **Build the Docker Image:**
    *   Open your terminal in the project root directory (where the `Dockerfile` is located).
    *   Run the build command:
        `docker build -t vreetvos-app .`
        (You can replace `vreetvos-app` with your preferred image name).

3.  **Run the Docker Container:**
    *   **Database Persistence:** To ensure your data persists across container restarts, you should use a Docker volume to store the `foxhunt.db` file. Create a directory on your host machine if it doesn't exist (e.g., `./vreetvos_data` or any other path).
        *   Example host directory creation (optional, Docker can create it): `mkdir ./vreetvos_data`
    *   Run the container with a volume mount:
        `docker run -d -p 8080:8080 -v $(pwd)/vreetvos_data:/data --name vreetvos-container vreetvos-app`
        *   `-d`: Run in detached mode (in the background).
        *   `-p 8080:8080`: Map port 8080 of the container to port 8080 on your host.
        *   `-v $(pwd)/vreetvos_data:/data`: Mount the `./vreetvos_data` directory from your host's current path into the `/data` directory inside the container. The `DATABASE_PATH` environment variable in the Dockerfile is set to `/data/foxhunt.db`, so the database file will be stored here.
        *   `--name vreetvos-container`: Assign a name to the container for easier management.
        *   `vreetvos-app`: The name of the image you built.
    *   **Windows Users Note:** For volume mounting on Windows (cmd/powershell), `$(pwd)` might not work as expected. You might need to use an absolute path or `${PWD}` in PowerShell, or `%cd%` in Command Prompt:
        *   PowerShell: `docker run -d -p 8080:8080 -v "${PWD}/vreetvos_data:/data" --name vreetvos-container vreetvos-app`
        *   CMD: `docker run -d -p 8080:8080 -v "%cd%/vreetvos_data:/data" --name vreetvos-container vreetvos-app`

4.  **Access the Application:**
    *   Open your web browser and go to `http://localhost:8080`.

5.  **Database Initialization (First Run with New Volume):**
    *   The application is configured to create the database and table if they don't exist at the path `/data/foxhunt.db` inside the container when it starts.
    *   Alternatively, to manually initialize or reset the database within the container (if needed):
        `docker exec -it vreetvos-container flask init-db`

6.  **Stopping and Starting the Container:**
    *   Stop: `docker stop vreetvos-container`
    *   Start: `docker start vreetvos-container`

7.  **Viewing Logs:**
    *   `docker logs vreetvos-container`

### Automated Docker Builds (GitHub Actions)

This project is configured with GitHub Actions to automatically build and push Docker images to the GitHub Container Registry (GHCR) whenever changes are pushed to the `main` branch.

**Image Location:**

*   The images are stored at: `ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME`
    *   **Note:** Replace `YOUR_GITHUB_USERNAME` with your GitHub username (or organization name) and `YOUR_REPO_NAME` with the name of this repository.

**Pulling the Latest Image:**

To pull the latest automatically built image, use the following command:

```sh
docker pull ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest
```

**Running the Automated Image:**

You can run the pulled image using the same `docker run` command as described above, just replace the image name at the end with the GHCR path:

```sh
docker run -d -p 8080:8080 -v $(pwd)/vreetvos_data:/data --name vreetvos-ghcr-container ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest
```
Remember to replace the placeholders and adjust the volume path `$(pwd)/vreetvos_data` as needed for your system.

**Using a Specific Version (Commit SHA):**

The workflow also tags images with the long Git commit SHA. You can pull a specific version by replacing `:latest` with the commit SHA if needed. You can find commit SHAs on GitHub in the commit history.
