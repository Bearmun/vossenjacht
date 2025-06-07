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
*   Basic password protection for data entry forms.
*   A password-protected "Instellingen" (Settings) page for data management, including:
    *   Listing all entries with options to edit or delete individual entries.
    *   Functionality to clear the entire database (with strong confirmation).

## Configuration

The application can be configured using environment variables.

*   **`FLASK_SECRET_KEY`**:
    *   **Purpose**: A secret key used by Flask to sign session cookies for security. This is crucial for the login functionality.
    *   **Default**: A randomly generated value (not suitable for production if instances are restarted often, as sessions would invalidate).
    *   **Recommendation**: Set a strong, persistent random string in your production environment.
    *   Example: `export FLASK_SECRET_KEY='your_very_strong_random_secret_string'`

*   **`VREETVOS_ADMIN_PASSWORD`**:
    *   **Purpose**: The password used to log in to access the data entry forms.
    *   **Default**: `vreetvos_admin` (Change this for any real deployment!)
    *   **Recommendation**: Set a strong password in your production environment.
    *   Example: `export VREETVOS_ADMIN_PASSWORD='your_secure_admin_password'`

*   **`DATABASE_PATH`**:
    *   **Purpose**: Specifies the full path to the SQLite database file within the container.
    *   **Default (in Dockerfile)**: `/data/foxhunt.db`
    *   **Default (local `app.py`)**: `foxhunt.db`
    *   **Note**: When running with Docker/Docker Compose, this path inside the container is mapped to a host directory or Docker volume for persistence.

*   **`TZ`**:
    *   **Purpose**: Sets the timezone for the Docker container and thus for the application running inside it. This affects how current time is determined (e.g., for pre-filling forms).
    *   **Default (in Dockerfile)**: `Europe/Amsterdam`
    *   **Recommendation**: If you are in a different timezone, you can override this when running the container.
    *   Example (in `.env` for Docker Compose): `TZ=America/New_York`
    *   Example (with `docker run`): `-e TZ="America/New_York"`

**Setting Environment Variables for Docker/Docker Compose:**

*   **With `docker run`:**
    Use the `-e` flag for each variable:
    ```sh
    docker run -d -p 8080:8080 \
      -e FLASK_SECRET_KEY='your_very_strong_random_secret_string' \
      -e VREETVOS_ADMIN_PASSWORD='your_secure_admin_password' \
      -v $(pwd)/vreetvos_data:/data \
      --name vreetvos-container ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest
    ```

*   **With `docker-compose.yml`:**
    You can create an `.env` file in the same directory as your `docker-compose.yml` file with the following content:
    ```env
    FLASK_SECRET_KEY=your_very_strong_random_secret_string
    VREETVOS_ADMIN_PASSWORD=your_secure_admin_password
    # DATABASE_PATH is already set in the Dockerfile ENV, so not typically needed here
    # unless you want to override the default for a specific compose setup.
    ```
    Docker Compose will automatically pick up variables from an `.env` file.
    Alternatively, you can add an `environment` section directly in `docker-compose.yml` (less secure for secrets if committed):
    ```yaml
    services:
      vreetvos-app:
        # ... other config ...
        environment:
          - FLASK_SECRET_KEY=your_very_strong_random_secret_string
          - VREETVOS_ADMIN_PASSWORD=your_secure_admin_password
    ```

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

## Instellingen (Settings Page)

The application includes a password-protected settings page accessible at `/settings` for managing hunt entries. You must be logged in to access this page.

From the settings page, you can:

*   **View all entries:** A comprehensive list of all submitted fox hunt results is displayed.
*   **Edit an entry:** Each entry has an "Bewerk" (Edit) option, allowing you to modify its details (name, kilometer readings, arrival time). Changes will automatically recalculate driven kilometers and duration.
*   **Delete an entry:** Each entry has a "Verwijder" (Delete) option. A confirmation prompt will appear before the entry is permanently removed.
*   **Clear Entire Database:**
    *   A section under "Database Beheer" (Database Management) allows for the deletion of ALL entries from the database.
    *   **Warning:** This action is irreversible and permanently deletes all data.
    *   To prevent accidental data loss, you must:
        1.  Confirm via a browser pop-up dialog.
        2.  Type the exact phrase "VERWIJDER ALLES" into a confirmation text box.
    *   Only proceed if you are absolutely certain you want to erase all records.

All administrative actions on the settings page require you to be logged in.

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
*   **Multi-Arch Support:** The published images are multi-arch, supporting both `linux/amd64` (for standard PCs/servers) and `linux/arm64` (e.g., for Raspberry Pi 4 64-bit and other 64-bit ARM devices). Docker will automatically pull the appropriate image for your system's architecture.

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

## Running with Docker Compose

For easier local development and management, a `docker-compose.yml` file is provided. This setup uses pre-built Docker images from GitHub Container Registry (GHCR) that are automatically created by GitHub Actions.

1.  **Prerequisites:**
    *   Docker installed and running.
    *   Docker Compose installed.

2.  **Configuration (Important!):**
    *   The `docker-compose.yml` file is configured to use an image from GHCR: `image: ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest`.
        *   **You MUST replace `YOUR_GITHUB_USERNAME` and `YOUR_REPO_NAME` in the `docker-compose.yml` file with your actual GitHub username (or organization) and repository name.**
        *   Similarly, replace these placeholders in any `docker pull` commands mentioned.
    *   The `docker-compose.yml` file also includes an `environment:` section that sets default or placeholder values for:
        *   `TZ: "Europe/Amsterdam"`
        *   `FLASK_SECRET_KEY: "your_very_strong_and_unique_secret_key_here_please_change_me"`
        *   `VREETVOS_ADMIN_PASSWORD: "vreetvos_admin"`
        *   `DATABASE_PATH: "/data/foxhunt.db"`
    *   **Security Warning:**
        *   The default values for `FLASK_SECRET_KEY` and `VREETVOS_ADMIN_PASSWORD` in `docker-compose.yml` are **NOT secure** and **MUST be changed** for any real deployment.
    *   **Recommended Configuration Method (using an `.env` file):**
        *   For better security, especially for secrets, create a file named `.env` in the same directory as `docker-compose.yml`. Docker Compose automatically loads environment variables from this file.
        *   **Do NOT commit your `.env` file to version control if it contains real secrets.** Add `.env` to your `.gitignore` file.
        *   Example `.env` file content:
            ```env
            FLASK_SECRET_KEY=a_truly_random_and_strong_secret_key_generated_by_you
            VREETVOS_ADMIN_PASSWORD=your_chosen_strong_admin_password
            # You can also override TZ or DATABASE_PATH here if needed, e.g.:
            # TZ=America/New_York
            ```
        *   Values set in the `.env` file will override those defined directly in the `environment:` section of `docker-compose.yml`.

3.  **Pull the Latest Image (Recommended):**
    *   Before starting the services, it's good practice to pull the latest image from GHCR:
        `docker pull ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest`
        *(Remember to replace placeholders!)*

4.  **Run the Application:**
    *   Open your terminal in the project root directory (where `docker-compose.yml` is located).
    *   Run the following command to start the service(s) in detached mode:
        `docker-compose up -d`
        *   This command will attempt to pull the image if it's not already present locally.
        *   `-d`: Run in detached mode (in the background).

5.  **Access the Application:**
    *   Open your web browser and go to `http://localhost:8080`.

6.  **Database Persistence:**
    *   The `docker-compose.yml` file defines a named volume called `vreetvos_db_data`. This volume is used to store the SQLite database (`foxhunt.db` located at `/data/foxhunt.db` inside the container).
    *   Your data will persist even if you stop and remove the container, as long as the named volume `vreetvos_db_data` is not explicitly deleted.

7.  **Database Initialization (First Run with New Volume):**
    *   The application is configured to create the database and table if they don't exist when it starts.
    *   If you ever need to manually initialize or reset the database within the container managed by Docker Compose:
        `docker-compose exec vreetvos-app flask init-db`
        *   `vreetvos-app` is the service name defined in `docker-compose.yml`.

8.  **Viewing Logs:**
    *   To view the logs from the running application service:
        `docker-compose logs -f vreetvos-app`
        *   `-f`: Follow log output.

9.  **Stopping the Application:**
    *   To stop the services defined in `docker-compose.yml`:
        `docker-compose down`
        *   This command stops and removes the containers. Network and volumes are not removed by default.
    *   To stop and remove the named volume (deleting all data):
        `docker-compose down -v`

10. **Updating the Image:**
    *   To update to a newer version of the image from GHCR:
        1.  Pull the latest image: `docker pull ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest`
        2.  Restart your services: `docker-compose up -d` (Compose will detect the new image and recreate the container).
