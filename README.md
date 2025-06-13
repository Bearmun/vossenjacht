# Fox Hunt Statistics Tracker

A simple web application built with Flask to track statistics for a fox hunt.
Participants can enter their name, start/end kilometer readings, and arrival time.
The application calculates driven kilometers, hunt duration,
and displays sorted results. Data is stored in an SQLite database.

The application is primarily in Dutch.

## Features

*   Web interface for data entry, viewing results, and administration.
*   **Multi-user system** with 'admin' and 'moderator' roles:
    *   Secure login system for all users.
    *   Admins can manage users (add/delete users, assign roles).
    *   Initial admin user can be created via environment variables (`INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`).
*   **Vossenjacht (Fox Hunt Event) Management**:
    *   Admins and moderators can create, edit, and delete Vossenjachten.
    *   Each Vossenjacht has attributes:
        *   Name
        *   Type: 'kilometers' (sort by km), 'time' (sort by duration), or 'both' (sort by km, then duration).
        *   Status: 'active' or 'completed'.
        *   Specific start time (e.g., "13:00"), crucial for duration calculations.
    *   Moderators can only manage Vossenjachten they created.
*   **Entry Management**:
    *   Entries are linked to specific Vossenjachten.
    *   Calculation of driven kilometers, including odometer rollover (assumes max 1000km per rollover).
    *   **Calculation of hunt duration** in minutes, based on the selected Vossenjacht's specific start time.
    *   Admins have full access to edit/delete any entry.
    *   Moderators can edit/delete entries associated with Vossenjachten they manage.
*   **Results Display**:
    *   Results can be filtered to show entries for a specific Vossenjacht.
    *   **Results sorting is dynamic**:
        *   If a Vossenjacht is selected, sorting respects its 'type' (kilometers, time, or both).
        *   Global view (all entries) sorts by kilometers then duration by default.
*   User interface primarily in Dutch.
*   Persistent data storage using SQLite (`foxhunt.db`).
*   The "Instellingen" (Settings) page is dedicated to managing entries, with permissions based on user roles (see dedicated section below).
*   Separate sections for managing Users and Vossenjachten.

## Configuration

The application can be configured using environment variables. These are the primary variables you might need to set:

*   **`FLASK_SECRET_KEY`**:
    *   **Purpose**: A secret key used by Flask to sign session cookies for security, crucial for the login and session management functionality.
    *   **Default**: A randomly generated value via `os.urandom(24)` if not set (note: this means sessions will invalidate if the application restarts, making it unsuitable for production).
    *   **Recommendation**: Set a strong, persistent random string in your production environment.
    *   Example: `export FLASK_SECRET_KEY='your_very_strong_random_secret_string'`

*   **`DATABASE_PATH`**:
    *   **Purpose**: Specifies the full path to the SQLite database file.
    *   **Default (local `app.py`)**: `foxhunt.db` (in the current working directory).
    *   **Default (in Dockerfile)**: `/data/foxhunt.db` (when running inside the Docker container).
    *   **Note**: When running with Docker/Docker Compose, this path inside the container is typically mapped to a host directory or Docker volume for data persistence.

*   **`TZ`**:
    *   **Purpose**: Sets the timezone for the application environment (e.g., Docker container). This affects how current time is determined by the application (e.g., for pre-filling form fields or logging timestamps).
    *   **Default (in Dockerfile)**: `Europe/Amsterdam`
    *   **Recommendation**: If you are in a different timezone, override this when running the container or on your host system.
    *   Example (in `.env` for Docker Compose): `TZ=America/New_York`
    *   Example (with `docker run`): `-e TZ="America/New_York"`

*   **`INITIAL_ADMIN_USERNAME`**:
    *   **Purpose**: Used to create an initial administrator account if no admin users exist in the database on startup.
    *   **Details**: See the "Initial Admin User Setup" section for more information.
    *   **Recommendation**: Set this along with `INITIAL_ADMIN_PASSWORD` for the first run, then consider unsetting or securing these variables.

*   **`INITIAL_ADMIN_PASSWORD`**:
    *   **Purpose**: The password for the initial administrator account created if no admin users exist.
    *   **Details**: See the "Initial Admin User Setup" section for more information.
    *   **Recommendation**: Choose a strong password. Set this along with `INITIAL_ADMIN_USERNAME` for the first run, then consider unsetting or securing these variables.

*   **`MAX_ODOMETER_READING`**:
    *   **Purpose**: Defines the maximum value on the vehicle's odometer before it rolls over (e.g., from 999km back to 0km). This is used to correctly calculate driven kilometers if a rollover occurs during a hunt.
    *   **Default**: `1000` (as set in `app.py`).
    *   **Recommendation**: Adjust if your odometers have a different rollover point (e.g., `100000` for a car that rolls over at 99,999.9 km). The value should be an integer.

### Obsolete Variables

*   **`VREETVOS_ADMIN_PASSWORD`**:
    *   **Status**: No longer used.
    *   **Reason**: The application has been updated to a multi-user system with username/password authentication for different roles (admin, moderator). The initial admin user is now configured using `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` as described in the "Initial Admin User Setup" section. This variable can be safely removed from your environment.

### Development/Local Run Environment Variables

When running the Flask application directly (e.g., via `flask run` or `python app.py`) without Docker, the following standard Flask environment variables are useful:

*   **`FLASK_APP`**:
    *   **Purpose**: Tells Flask where your application instance is.
    *   **Value**: Should be set to `app.py` (or just `app` if your file is `app.py`).
    *   Example: `export FLASK_APP=app.py`
    *   **Note**: This is mentioned in the "Setup and Running" section.

*   **`FLASK_RUN_HOST`**:
    *   **Purpose**: Specifies the host IP address the Flask development server should bind to.
    *   **Default**: `127.0.0.1` (localhost, only accessible from your own machine).
    *   **Recommendation**: Set to `0.0.0.0` to make the server accessible from other devices on your network (e.g., `flask run --host=0.0.0.0`).
    *   Example: `export FLASK_RUN_HOST=0.0.0.0`

*   **`FLASK_RUN_PORT`**:
    *   **Purpose**: Specifies the port the Flask development server should listen on.
    *   **Default**: `5000`.
    *   **Recommendation**: The "Setup and Running" section uses `8080` (e.g., `flask run --port=8080`).
    *   Example: `export FLASK_RUN_PORT=8080`

**Setting Environment Variables for Docker/Docker Compose:**

*   **With `docker run`:**
    Use the `-e` flag for each variable. Note that `VREETVOS_ADMIN_PASSWORD` is no longer needed.
    ```sh
    docker run -d -p 8080:8080 \
      -e FLASK_SECRET_KEY='your_very_strong_random_secret_string' \
      -e INITIAL_ADMIN_USERNAME='admin' \
      -e INITIAL_ADMIN_PASSWORD='your_secure_password' \
      -e DATABASE_PATH='/data/foxhunt.db' \
      -e TZ='Europe/Amsterdam' \
      -v $(pwd)/vreetvos_data:/data \
      --name vreetvos-container ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest
    ```

*   **With `docker-compose.yml`:**
    You can create an `.env` file in the same directory as your `docker-compose.yml` file. Note that `VREETVOS_ADMIN_PASSWORD` should be removed.
    Example `.env` file content:
    ```env
    FLASK_SECRET_KEY=your_very_strong_random_secret_string
    INITIAL_ADMIN_USERNAME=admin
    INITIAL_ADMIN_PASSWORD=your_secure_password
    DATABASE_PATH=/data/foxhunt.db
    TZ=Europe/Amsterdam
    # MAX_ODOMETER_READING=1000 (optional, if default is fine)
    ```
    Docker Compose will automatically pick up variables from an `.env` file.
    Alternatively, you can add or update an `environment` section directly in `docker-compose.yml` (less secure for secrets if committed):
    ```yaml
    services:
      vreetvos-app:
        # ... other config ...
        environment:
          - FLASK_SECRET_KEY=${FLASK_SECRET_KEY} # Example of referencing from .env
          - INITIAL_ADMIN_USERNAME=${INITIAL_ADMIN_USERNAME}
          - INITIAL_ADMIN_PASSWORD=${INITIAL_ADMIN_PASSWORD}
          - DATABASE_PATH=/data/foxhunt.db
          - TZ=${TZ:-Europe/Amsterdam} # Use TZ from .env or default
          # - MAX_ODOMETER_READING=${MAX_ODOMETER_READING:-1000}
    ```

## Initial Admin User Setup

If no admin user exists in the database when the application starts for the first time (or after the database is initialized), it can automatically create an initial admin user. This process is controlled by the `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` environment variables, as listed in the main "Configuration" section.

Set these environment variables before running the application for the first time (e.g., in your `.env` file for Docker Compose, or directly in your environment for local execution).

The application will output messages to the console (or application logs) indicating:
- If an admin user already exists (in which case, no new user is created).
- If the initial admin user is created successfully using the provided environment variables.
- If the environment variables are not set and no admin user exists (in this scenario, you would need to set the variables and restart, or find an alternative way to create a user if the application structure allowed, though currently it does not provide a UI for this without being logged in).

**Important Security Note:** It's strongly recommended to unset or remove these `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` environment variables from your configuration after the first successful startup and admin user creation, especially in production environments. Leaving them set could pose a security risk if the database were to be reset or if an attacker gained access to the environment variables.

If these variables are not set and no admin user exists (e.g., on a subsequent run after they've been cleared), you will need to log in with an existing admin or moderator account to manage users or create new ones via the `/admin/users/add` page. If no users exist at all and the initial admin variables are not set, you'll be unable to log in to create users.

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

The application includes a settings page accessible at `/settings` once logged in. This page is **primarily focused on managing individual hunt entries**. Management of Vossenjachten and Users is handled in separate, dedicated sections of the application.

Access and capabilities on the Settings page depend on user roles:

*   **Viewing Entries:**
    *   **Admins** can view all entries from all Vossenjachten.
    *   **Moderators** can view entries associated with Vossenjachten they created/manage.
*   **Editing an Entry:**
    *   Each listed entry has an "Bewerk" (Edit) option.
    *   **Admins** can edit any entry.
    *   **Moderators** can edit entries belonging to Vossenjachten they manage.
    *   Changes will automatically recalculate driven kilometers and duration (using the Vossenjacht's start time).
*   **Deleting an Entry:**
    *   Each listed entry has a "Verwijder" (Delete) option with a confirmation prompt.
    *   **Admins** can delete any entry.
    *   **Moderators** can delete entries belonging to Vossenjachten they manage.
*   **Clear All Entries (Database Beheer):**
    *   A section under "Database Beheer" (Database Management) allows for the deletion of ALL entries from the database.
    *   **Warning:** This action is irreversible and permanently deletes all entry data.
    *   To prevent accidental data loss, strict confirmation is required (typing "VERWIJDER ALLES").
    *   This function is typically restricted to users with higher privileges (e.g., admins).

All actions on the settings page require an active login session. User and Vossenjacht management have their own interfaces and permissions.

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
    *   **Image Source**: The `docker-compose.yml` file is configured to use a pre-built image from GitHub Container Registry (GHCR). The line looks like:
        `image: ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest`
        *   **CRITICAL STEP:** You **MUST** replace `YOUR_GITHUB_USERNAME` and `YOUR_REPO_NAME` in this line within your `docker-compose.yml` file with your actual GitHub username (or organization name) and the name of this repository. Failure to do so will result in Docker Compose being unable to pull the image.
        *   This same placeholder replacement applies to any standalone `docker pull ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest` commands mentioned in this guide.
    *   **Environment Variables**: The `docker-compose.yml` file includes an `environment:` section. It is highly recommended to manage the values for these variables using an `.env` file for better security and flexibility, especially for secrets.
        Example `environment` section in `docker-compose.yml` designed to pick up values from an `.env` file:
        ```yaml
        environment:
          - TZ=${TZ:-Europe/Amsterdam}
          - FLASK_SECRET_KEY=${FLASK_SECRET_KEY}
          - INITIAL_ADMIN_USERNAME=${INITIAL_ADMIN_USERNAME}
          - INITIAL_ADMIN_PASSWORD=${INITIAL_ADMIN_PASSWORD}
          - DATABASE_PATH=${DATABASE_PATH:-/data/foxhunt.db}
          - MAX_ODOMETER_READING=${MAX_ODOMETER_READING:-1000}
        ```
    *   **Security Warning:**
        *   Default placeholder values for secrets like `FLASK_SECRET_KEY` and `INITIAL_ADMIN_PASSWORD` that might be commented out or present in a template `docker-compose.yml` are **NOT secure** and **MUST be changed** for any real deployment by setting them in your `.env` file or directly if appropriate for your setup.
    *   **Recommended Configuration Method (using an `.env` file):**
        *   For better security, especially for secrets, create a file named `.env` in the same directory as `docker-compose.yml`. Docker Compose automatically loads environment variables from this file.
        *   **Do NOT commit your `.env` file to version control if it contains real secrets.** Add `.env` to your `.gitignore` file.
        *   Example `.env` file content:
            ```env
            FLASK_SECRET_KEY=a_truly_random_and_strong_secret_key_generated_by_you
            INITIAL_ADMIN_USERNAME=admin_user
            INITIAL_ADMIN_PASSWORD=a_very_secure_password_!@#$
            DATABASE_PATH=/data/foxhunt.db # Or keep default from compose if suitable
            TZ=Europe/Amsterdam
            # MAX_ODOMETER_READING=1000 # Only if different from default
            ```
        *   Values set in the `.env` file will override any defaults defined directly in the `environment:` section of `docker-compose.yml` if the compose file is set up to reference them (e.g., `FLASK_SECRET_KEY=${FLASK_SECRET_KEY}`).

3.  **Pull the Latest Image (Recommended):**
    *   Before starting the services, it's good practice to pull the latest image from GHCR:
        `docker pull ghcr.io/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:latest`
        *(Remember to replace the `YOUR_GITHUB_USERNAME` and `YOUR_REPO_NAME` placeholders!)*

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
