import sqlite3
import click # For CLI commands
from flask import Flask, render_template, request, redirect, url_for, g, current_app, session # Added session
from datetime import datetime
import os # Import os module
from functools import wraps # Added wraps
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Secret key for session management - IMPORTANT: set via ENV for production
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Determine database path: prioritize DATABASE_PATH env var, then default.
database_actual_path = os.environ.get('DATABASE_PATH', 'foxhunt.db')
app.config.setdefault('DATABASE_FILENAME', database_actual_path) # Use determined path
app.config.setdefault('MAX_ODOMETER_READING', 1000) # Changed to int


def get_db():
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE', current_app.config['DATABASE_FILENAME'])
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;") # Enforce FKs for every connection
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    # Enable foreign key support
    db.execute("PRAGMA foreign_keys = ON;")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'moderator'))
        );

        CREATE TABLE IF NOT EXISTS vossenjachten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            creator_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed')),
            type TEXT NOT NULL CHECK (type IN ('kilometers', 'time', 'both')),
            FOREIGN KEY (creator_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_km REAL NOT NULL,
            end_km REAL NOT NULL,
            arrival_time_last_fox TEXT NOT NULL,
            calculated_km REAL NOT NULL,
            duration_minutes INTEGER NOT NULL,
            vossenjacht_id INTEGER,
            user_id INTEGER,
            FOREIGN KEY (vossenjacht_id) REFERENCES vossenjachten (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    ''')
    db.commit()

@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Initialized the database.')

def init_app(flask_app):
    flask_app.teardown_appcontext(close_db)
    flask_app.cli.add_command(init_db_command)

init_app(app)

# Login required decorator
def set_password(password):
    return generate_password_hash(password)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            # flash('Admin access required.', 'danger') # Assuming you have flash messaging
            return redirect(url_for('results')) # Or some other appropriate page
        return f(*args, **kwargs)
    return decorated_function

# Moderator required decorator
def moderator_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') not in ['admin', 'moderator']:
            # flash('Moderator or Admin access required.', 'danger') # Assuming you have flash messaging
            return redirect(url_for('results')) # Or some other appropriate page
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.clear() # Clear old session data
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            next_url = request.args.get('next')
            # Basic protection against open redirect
            if next_url and ':' not in next_url and '@' not in next_url and '.' in next_url.split('/')[-1]: # very basic check
                 pass # Potentially unsafe, consider more robust validation or allowlisting
            elif next_url: # Check if next_url is a local path
                # A better check would be to use urlparse and check netloc
                from urllib.parse import urlparse
                if not urlparse(next_url).netloc: # If no netloc, it's likely a local path
                    return redirect(next_url)
            return redirect(url_for('input_form')) # Default redirect
        else:
            error = 'Ongeldige gebruikersnaam of wachtwoord. Probeer opnieuw.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('results'))

@app.route('/')
def index():
    return redirect(url_for('results'))

@app.route('/input')
@login_required # Protect this route
def input_form():
    now = datetime.now()
    current_time_str = now.strftime('%H:%M')
    db = get_db()
    active_vossenjachten = db.execute(
        "SELECT id, name FROM vossenjachten WHERE status = 'active' ORDER BY name"
    ).fetchall()
    # return render_template('input.html', current_time_for_form=current_time_str, active_vossenjachten=active_vossenjachten)
    return f"Placeholder for input form. Active Vossenjachten: {[(vj['id'], vj['name']) for vj in active_vossenjachten]}"

@app.route('/add_entry', methods=['POST'])
@login_required # Protect this route
def add_entry():
    try:
        name = request.form['name']
        start_km = int(float(request.form['start_km']))
        end_km = int(float(request.form['end_km']))
        arrival_time_str = request.form['arrival_time_last_fox']
        vossenjacht_id = request.form.get('vossenjacht_id', type=int)

        if not vossenjacht_id:
            # flash('Vossenjacht selection is required.', 'danger')
            return redirect(url_for('input_form')) # Or return error string

        # Fetch and check vossenjacht status
        vossenjacht = get_vossenjacht_or_abort(vossenjacht_id, check_owner=False)
        if vossenjacht['status'] != 'active':
            # flash('Selected vossenjacht is not active.', 'danger')
            return "Error: Selected Vossenjacht is not active. <a href='/input'>Try again</a>"

        max_odom_reading = int(current_app.config.get('MAX_ODOMETER_READING', 1000))
        actual_end_km = end_km
        if end_km < start_km: # Odometer rollover
            actual_end_km += max_odom_reading
        calculated_km = int(round(actual_end_km - start_km))

        if calculated_km < 0:
            # flash('Negative calculated kilometers. Check odometer readings.', 'danger')
            print(f"Warning: Negative calculated_km for {name}. Start: {start_km}, End: {end_km}. Adjusted End: {actual_end_km}")
            return redirect(url_for('input_form'))

        arrival_dt = datetime.strptime(arrival_time_str, '%H:%M')
        start_dt = datetime.strptime('12:00', '%H:%M') # Assuming fixed start time for duration calculation
        duration_delta = arrival_dt - start_dt
        duration_minutes = int(duration_delta.total_seconds() / 60)

        user_id = session['user_id']
        db = get_db()
        db.execute(
            'INSERT INTO entries (name, start_km, end_km, arrival_time_last_fox, calculated_km, duration_minutes, vossenjacht_id, user_id)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (name, start_km, end_km, arrival_time_str, calculated_km, duration_minutes, vossenjacht_id, user_id)
        )
        db.commit()
        # flash('Entry added successfully!', 'success')
        return redirect(url_for('results'))

    except ValueError: # For float conversion or time parsing errors
        # flash('Invalid data submitted. Check kilometer fields and time format.', 'danger')
        print("Error: Non-numeric input for kilometer fields or invalid time format.")
        return redirect(url_for('input_form'))
    except sqlite3.Error as e:
        # flash(f'Database error: {e}', 'danger')
        print(f"Database error in add_entry: {e}")
        return redirect(url_for('input_form'))
    except Exception as e:
        # flash(f'An unexpected error occurred: {e}', 'danger')
        print(f"An error occurred in add_entry: {e}")
        return redirect(url_for('input_form'))

@app.route('/results')
def results():
    db = get_db()
    selected_vj_id = request.args.get('vj_id', type=int)

    all_vossenjachten = db.execute("SELECT id, name FROM vossenjachten ORDER BY name").fetchall()

    base_query = "SELECT e.*, vj.name as vossenjacht_name FROM entries e JOIN vossenjachten vj ON e.vossenjacht_id = vj.id"
    params = []

    if selected_vj_id:
        base_query += " WHERE e.vossenjacht_id = ?"
        params.append(selected_vj_id)

    entries_rows = db.execute(base_query, params).fetchall()

    sorted_entries = sorted(entries_rows, key=lambda x: (x['calculated_km'], x['duration_minutes']))

    ranked_entries_with_dense_rank = []
    last_score = None
    current_dense_rank = 0
    if sorted_entries:
        for entry_row in sorted_entries: # Changed from 'entry' to 'entry_row' to avoid conflict
            current_score = (entry_row['calculated_km'], entry_row['duration_minutes'])
            if current_score != last_score:
                current_dense_rank += 1
                last_score = current_score

            mutable_entry = dict(entry_row) # Use entry_row here
            mutable_entry['rank'] = current_dense_rank
            mutable_entry['start_km'] = int(mutable_entry['start_km'])
            mutable_entry['end_km'] = int(mutable_entry['end_km'])
            mutable_entry['calculated_km'] = int(mutable_entry['calculated_km'])
            ranked_entries_with_dense_rank.append(mutable_entry)

    total_kilometers_all = int(sum(entry['calculated_km'] for entry in ranked_entries_with_dense_rank))

    current_vossenjacht_name = None
    current_vossenjacht_type = None # Initialize type
    if selected_vj_id:
        # Fetch details for the selected vossenjacht to get its type
        vj_details = db.execute("SELECT name, type FROM vossenjachten WHERE id = ?", (selected_vj_id,)).fetchone()
        if vj_details:
            current_vossenjacht_name = vj_details['name']
            current_vossenjacht_type = vj_details['type']

    # Conditional sorting logic
    if selected_vj_id and current_vossenjacht_type:
        if current_vossenjacht_type == 'time':
            sorted_entries = sorted(entries_rows, key=lambda x: (x['duration_minutes'], x['calculated_km']))
            def get_score(entry): return (entry['duration_minutes'], entry['calculated_km'])
        else:  # 'kilometers' or 'both'
            sorted_entries = sorted(entries_rows, key=lambda x: (x['calculated_km'], x['duration_minutes']))
            def get_score(entry): return (entry['calculated_km'], entry['duration_minutes'])
    else:  # Global view or if vj_id provided but type couldn't be fetched
        sorted_entries = sorted(entries_rows, key=lambda x: (x['calculated_km'], x['duration_minutes']))
        def get_score(entry): return (entry['calculated_km'], entry['duration_minutes'])

    # Re-calculate ranked_entries_with_dense_rank based on the new sorting and scoring
    ranked_entries_with_dense_rank = [] # Clear previous calculation if any
    last_score = None
    current_dense_rank = 0
    if sorted_entries:
        for entry_row in sorted_entries:
            current_score = get_score(entry_row) # Use the dynamically defined get_score
            if current_score != last_score:
                current_dense_rank += 1
                last_score = current_score

            mutable_entry = dict(entry_row)
            mutable_entry['rank'] = current_dense_rank
            mutable_entry['start_km'] = int(mutable_entry['start_km'])
            mutable_entry['end_km'] = int(mutable_entry['end_km'])
            mutable_entry['calculated_km'] = int(mutable_entry['calculated_km'])
            ranked_entries_with_dense_rank.append(mutable_entry)

    total_kilometers_all = int(sum(entry['calculated_km'] for entry in ranked_entries_with_dense_rank))


    return render_template('results.html',
                           entries=ranked_entries_with_dense_rank,
                           total_kilometers_all_participants=int(total_kilometers_all),
                           all_vossenjachten=all_vossenjachten, # Already fetched
                           selected_vj_id=selected_vj_id,
                           current_vossenjacht_name=current_vossenjacht_name,
                           current_vossenjacht_type=current_vossenjacht_type, # Pass type to template for info
                           title="Results")

# Add this new route in app.py
@app.route('/settings')
@login_required
def settings():
    db = get_db()
    entries_query_sql = "SELECT e.*, vj.name as vossenjacht_name FROM entries e JOIN vossenjachten vj ON e.vossenjacht_id = vj.id"
    params = []

    if session.get('role') == 'moderator':
        entries_query_sql += " WHERE vj.creator_id = ?"
        params.append(session['user_id'])

    entries_query_sql += " ORDER BY e.calculated_km ASC, e.duration_minutes ASC"

    entries_rows = db.execute(entries_query_sql, params).fetchall()
    entries_list = [dict(row) for row in entries_rows]

    ranked_entries = []
    last_score = None
    current_dense_rank = 0
    if entries_list:
        for entry_data in entries_list:
            entry_data['start_km'] = int(entry_data['start_km'])
            entry_data['end_km'] = int(entry_data['end_km'])
            entry_data['calculated_km'] = int(entry_data['calculated_km'])
            entry_data['duration_minutes'] = int(entry_data['duration_minutes'])
            current_score = (entry_data['calculated_km'], entry_data['duration_minutes'])
            if current_score != last_score:
                current_dense_rank += 1
                last_score = current_score
            mutable_entry = dict(entry_data)
            mutable_entry['rank'] = current_dense_rank
            ranked_entries.append(mutable_entry)

    # return render_template('settings.html', entries=ranked_entries)
    return f"Placeholder for settings page. Entries (count: {len(ranked_entries)}): {ranked_entries}"


def check_entry_permission(entry_id):
    db = get_db()
    entry = db.execute('SELECT * FROM entries WHERE id = ?', (entry_id,)).fetchone()
    if not entry:
        abort(404) # Entry not found

    vossenjacht = get_vossenjacht_or_abort(entry['vossenjacht_id'], check_owner=False) # Get VJ without owner check first

    if session.get('role') == 'admin':
        return entry, vossenjacht # Admin has permission

    if session.get('role') == 'moderator':
        if vossenjacht['creator_id'] == session.get('user_id'):
            return entry, vossenjacht # Moderator owns the Vossenjacht
        else:
            abort(403) # Moderator does not own the Vossenjacht

    # If user is not admin or moderator who owns the VJ, they don't have permission
    # This could be expanded if regular users were allowed to edit/delete their own entries
    abort(403)


@app.route('/delete_entry/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    check_entry_permission(entry_id) # Will abort if no permission

    db = get_db()
    db.execute('DELETE FROM entries WHERE id = ?', (entry_id,))
    db.commit()
    # flash('Entry deleted successfully.', 'success')
    return redirect(url_for('settings'))

@app.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
    entry_data, _ = check_entry_permission(entry_id) # Will abort if no permission

    entry_dict = dict(entry_data)
    entry_dict['start_km'] = int(entry_dict['start_km'])
    entry_dict['end_km'] = int(entry_dict['end_km'])

    if request.method == 'POST':
        try:
            name = request.form['name']
            start_km = int(float(request.form['start_km']))
            end_km = int(float(request.form['end_km']))
            arrival_time_str = request.form['arrival_time_last_fox']

            max_odom_reading = int(current_app.config.get('MAX_ODOMETER_READING', 1000))
            actual_end_km = end_km
            if end_km < start_km:  # Odometer rollover
                actual_end_km += max_odom_reading
            calculated_km = int(round(actual_end_km - start_km))

            if calculated_km < 0:
                # flash('Negative calculated kilometers. Check odometer readings.', 'danger')
                # return render_template('edit_entry.html', entry=entry_dict, error='Negative calculated kilometers.')
                return f"Error: Negative calculated km. <a href='{url_for('edit_entry', entry_id=entry_id)}'>Try again</a>"

            arrival_dt = datetime.strptime(arrival_time_str, '%H:%M')
            start_dt = datetime.strptime('12:00', '%H:%M') # Assuming fixed start time for duration
            duration_delta = arrival_dt - start_dt
            duration_minutes = int(duration_delta.total_seconds() / 60)

            db = get_db()
            db.execute(
                'UPDATE entries SET name = ?, start_km = ?, end_km = ?, '
                'arrival_time_last_fox = ?, calculated_km = ?, duration_minutes = ? '
                'WHERE id = ?',
                (name, start_km, end_km, arrival_time_str, calculated_km, duration_minutes, entry_id)
            )
            db.commit()
            # flash('Entry updated successfully.', 'success')
            return redirect(url_for('settings'))

        except ValueError:
            # flash('Invalid data. Check fields.', 'danger')
            # return render_template('edit_entry.html', entry=entry_dict, error='Invalid data.')
            return f"Error: Invalid data. <a href='{url_for('edit_entry', entry_id=entry_id)}'>Try again</a>"
        except Exception as e:
            # flash(f'Error updating entry: {e}', 'danger')
            print(f"Error updating entry {entry_id}: {e}")
            return redirect(url_for('edit_entry', entry_id=entry_id))

    # GET request
    # return render_template('edit_entry.html', entry=entry_dict)
    return f"Placeholder for edit entry form. Entry ID: {entry_id}, Data: {entry_dict}"

@app.route('/clear_database', methods=['POST'])
@login_required
def clear_database():
    confirmation_text = request.form.get('confirm_text')
    # Server-side validation of the confirmation text
    if confirmation_text == "VERWIJDER ALLES":
        db = get_db()
        try:
            db.execute('DELETE FROM entries')
            db.commit()
            # flash('Alle ritten zijn succesvol verwijderd uit de database.', 'success')
            print("Database cleared successfully by user.") # Server log
        except Exception as e:
            # Log the exception e
            print(f"Error clearing database: {e}")
            # flash('Er is een fout opgetreden bij het wissen van de database.', 'error')
    else:
        # flash('Database niet gewist. Bevestigingstekst was incorrect.', 'warning')
        print(f"Database clear attempt failed due to incorrect confirmation text: '{confirmation_text}'") # Server log

    return redirect(url_for('settings'))

# User Management Routes
@app.route('/admin/users')
@login_required
@admin_required
def manage_users_page():
    db = get_db()
    users_data = db.execute("SELECT id, username, role FROM users ORDER BY username").fetchall()
    return render_template('admin/manage_users.html', users=users_data, title="Manage Users")

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user_page():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        error = None

        if not username or not password:
            error = "Username and password are required."
        elif role not in ['admin', 'moderator']:
            error = "Invalid role specified."

        if error:
            return render_template('admin/add_user.html', error=error, username=username, role=role, title="Add New User")

        db = get_db()
        existing_user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            error = "Username already exists."
            return render_template('admin/add_user.html', error=error, username=username, role=role, title="Add New User")

        hashed_password = generate_password_hash(password)
        try:
            db.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                       (username, hashed_password, role))
            db.commit()
            # flash('User added successfully.', 'success') # Optional: add flash messaging
            return redirect(url_for('manage_users_page'))
        except sqlite3.Error as e:
            error = f"Database error: {e}"
            return render_template('admin/add_user.html', error=error, username=username, role=role, title="Add New User")

    # GET request
    return render_template('admin/add_user.html', title="Add New User")

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user_page(user_id):
    if session.get('user_id') == user_id:
        # flash("You cannot delete your own account.", 'danger')
        return redirect(url_for('manage_users_page'))

    db = get_db()
    # Check if user exists before attempting delete
    user_to_delete = db.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
    if user_to_delete:
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        db.commit()
        # flash('User deleted successfully.', 'success')
    # else:
        # flash('User not found.', 'warning')
    return redirect(url_for('manage_users_page'))

# Helper function for Vossenjacht access
from flask import abort

def get_vossenjacht_or_abort(vj_id, check_owner=True):
    db = get_db()
    vossenjacht = db.execute(
        'SELECT vj.*, u.username as creator_username FROM vossenjachten vj JOIN users u ON vj.creator_id = u.id WHERE vj.id = ?',
        (vj_id,)
    ).fetchone()

    if vossenjacht is None:
        abort(404)  # Not found

    if check_owner and session.get('role') == 'moderator':
        if vossenjacht['creator_id'] != session.get('user_id'):
            abort(403)  # Forbidden

    # Admins bypass the owner check if check_owner is True but role is admin
    # No explicit check needed here for admin, as they are not 'moderator' role for the above condition.

    return vossenjacht

# Vossenjacht Management Routes
@app.route('/vossenjachten')
@login_required
def list_vossenjachten_page():
    db = get_db()
    # Fetch all vossenjachten, joining with users to get creator's username
    vossenjachten = db.execute(
        'SELECT vj.id, vj.name, vj.creation_date, vj.status, vj.type, u.username as creator_username '
        'FROM vossenjachten vj JOIN users u ON vj.creator_id = u.id ORDER BY vj.creation_date DESC'
    ).fetchall()
    # Fetch all vossenjachten, joining with users to get creator's username
    vossenjachten_data = db.execute(
        'SELECT vj.id, vj.name, vj.creation_date, vj.status, vj.type, u.username as creator_username, vj.creator_id '
        'FROM vossenjachten vj JOIN users u ON vj.creator_id = u.id ORDER BY vj.creation_date DESC'
    ).fetchall()
    return render_template('vossenjacht/list_vossenjachten.html', vossenjachten=vossenjachten_data, title="Vossenjachten Overview")

@app.route('/vossenjachten/new', methods=['GET', 'POST'])
@login_required
@moderator_required # Moderators and Admins can create
def create_vossenjacht_page():
    if request.method == 'POST':
        name = request.form.get('name')
        type = request.form.get('type')
        error = None

        if not name:
            error = "Name is required."
        elif type not in ['kilometers', 'time', 'both']:
            error = "Invalid vossenjacht type specified."

        if error:
            return render_template('vossenjacht/create_vossenjacht.html', error=error, name=name, type=type, title="Create Vossenjacht")

        creator_id = session['user_id']
        db = get_db()
        try:
            db.execute(
                'INSERT INTO vossenjachten (name, type, creator_id) VALUES (?, ?, ?)',
                (name, type, creator_id)
            )
            db.commit()
            # flash('Vossenjacht created successfully!', 'success')
            return redirect(url_for('list_vossenjachten_page'))
        except sqlite3.Error as e:
            error = f"Database error: {e}"
            return render_template('vossenjacht/create_vossenjacht.html', error=error, name=name, type=type, title="Create Vossenjacht")
    # GET request
    return render_template('vossenjacht/create_vossenjacht.html', title="Create New Vossenjacht")

@app.route('/vossenjachten/edit/<int:vj_id>', methods=['GET', 'POST'])
@login_required
@moderator_required # Ensures user is at least a moderator
def edit_vossenjacht_page(vj_id):
    vossenjacht = get_vossenjacht_or_abort(vj_id, check_owner=True)
    # vossenjacht is a Row object, convert to dict for easier template use if needed, or access by key
    vj_dict = dict(vossenjacht)

    if request.method == 'POST':
        name = request.form.get('name')
        type = request.form.get('type')
        status = request.form.get('status')
        error = None

        if not name:
            error = "Name is required."
        elif type not in ['kilometers', 'time', 'both']:
            error = "Invalid vossenjacht type."
        elif status not in ['active', 'completed']:
            error = "Invalid status."

        if error:
            # Pass current form values back to template, along with original vossenjacht for ID
            return render_template('vossenjacht/edit_vossenjacht.html', error=error, vossenjacht=vj_dict, title=f"Edit {vj_dict['name']}")

        db = get_db()
        try:
            db.execute(
                'UPDATE vossenjachten SET name = ?, type = ?, status = ? WHERE id = ?',
                (name, type, status, vj_id)
            )
            db.commit()
            # flash('Vossenjacht updated successfully!', 'success')
            return redirect(url_for('list_vossenjachten_page'))
        except sqlite3.Error as e:
            error = f"Database error: {e}"
            return render_template('vossenjacht/edit_vossenjacht.html', error=error, vossenjacht=vj_dict, title=f"Edit {vj_dict['name']}")

    # GET request
    return render_template('vossenjacht/edit_vossenjacht.html', vossenjacht=vj_dict, title=f"Edit {vj_dict['name']}")

@app.route('/vossenjachten/delete/<int:vj_id>', methods=['POST'])
@login_required
@moderator_required # Ensures user is at least a moderator
def delete_vossenjacht_page(vj_id):
    # get_vossenjacht_or_abort will handle 404 and basic permission for moderators
    get_vossenjacht_or_abort(vj_id, check_owner=True)

    db = get_db()
    try:
        # For now, we accept orphaned entries. Future: check for entries or use CASCADE.
        db.execute('DELETE FROM vossenjachten WHERE id = ?', (vj_id,))
        db.commit()
        # flash('Vossenjacht deleted successfully.', 'success')
    except sqlite3.Error as e:
        # Log error
        # flash(f'Error deleting vossenjacht: {e}', 'danger')
        pass # Fall through to redirect
    return redirect(url_for('list_vossenjachten_page'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
