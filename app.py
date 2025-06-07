import sqlite3
import click # For CLI commands
from flask import Flask, render_template, request, redirect, url_for, g, current_app, session # Added session
from datetime import datetime
import os # Import os module
from functools import wraps # Added wraps

app = Flask(__name__)

# Secret key for session management - IMPORTANT: set via ENV for production
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
# Admin password - IMPORTANT: set via ENV for production
app.config['VREETVOS_ADMIN_PASSWORD'] = os.environ.get('VREETVOS_ADMIN_PASSWORD', 'vreetvos_admin')

# Determine database path: prioritize DATABASE_PATH env var, then default.
database_actual_path = os.environ.get('DATABASE_PATH', 'foxhunt.db')
app.config.setdefault('DATABASE_FILENAME', database_actual_path) # Use determined path
app.config.setdefault('MAX_ODOMETER_READING', 1000) # Changed to int


def get_db():
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE', current_app.config['DATABASE_FILENAME'])
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    # Use executescript for CREATE TABLE IF NOT EXISTS to be safe,
    # though a single execute would also work for a single statement.
    db.executescript('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_km REAL NOT NULL,
            end_km REAL NOT NULL,
            arrival_time_last_fox TEXT NOT NULL,
            calculated_km REAL NOT NULL,
            duration_minutes INTEGER NOT NULL
        );
    ''')
    # No explicit commit is strictly needed for CREATE TABLE IF NOT EXISTS
    # when autocommit is often on or if it's the only command.
    # However, keeping db.commit() doesn't harm and ensures it if other
    # schema modifications were added later in the same transaction.
    # For simplicity and safety, let's keep the commit.
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
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == current_app.config['VREETVOS_ADMIN_PASSWORD']:
            session['logged_in'] = True
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
            error = 'Ongeldig wachtwoord. Probeer opnieuw.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('results'))

@app.route('/')
def index():
    return redirect(url_for('results'))

@app.route('/input')
@login_required # Protect this route
def input_form():
    # Get current time formatted as HH:MM for pre-filling the form
    now = datetime.now()
    current_time_str = now.strftime('%H:%M')
    return render_template('input.html', current_time_for_form=current_time_str)

@app.route('/add_entry', methods=['POST'])
@login_required # Protect this route
def add_entry():
    try:
        name = request.form['name']
        start_km = int(float(request.form['start_km'])) # Handle potential float input (e.g. "10.0") then cast to int
        end_km = int(float(request.form['end_km']))     # Handle potential float input then cast to int
        arrival_time_str = request.form['arrival_time_last_fox']

        max_odom_reading = int(current_app.config.get('MAX_ODOMETER_READING', 1000)) # Ensure int
        actual_end_km = end_km
        if end_km < start_km: # Odometer rollover
            actual_end_km += max_odom_reading

        calculated_km = int(round(actual_end_km - start_km)) # Calculate as int

        if calculated_km < 0:
            print(f"Warning: Negative calculated_km for {name}. Start: {start_km}, End: {end_km}. Adjusted End: {actual_end_km}")
            return redirect(url_for('input_form'))

        try:
            arrival_dt = datetime.strptime(arrival_time_str, '%H:%M')
            start_dt = datetime.strptime('12:00', '%H:%M')
            duration_delta = arrival_dt - start_dt
            duration_minutes = int(duration_delta.total_seconds() / 60)
        except ValueError:
            print(f"Error: Invalid time format for {name}. Time: {arrival_time_str}")
            return redirect(url_for('input_form'))

        db = get_db()
        db.execute(
            'INSERT INTO entries (name, start_km, end_km, arrival_time_last_fox, calculated_km, duration_minutes)'
            ' VALUES (?, ?, ?, ?, ?, ?)',
            (name, start_km, end_km, arrival_time_str, calculated_km, duration_minutes)
        )
        db.commit()
        return redirect(url_for('results'))

    except ValueError: # For float conversion errors
        print("Error: Non-numeric input for kilometer fields.")
        return redirect(url_for('input_form'))
    except Exception as e:
        print(f"An error occurred in add_entry: {e}")
        return redirect(url_for('input_form'))

@app.route('/results')
def results():
    db = get_db()
    entries_rows = db.execute('SELECT * FROM entries').fetchall()

    sorted_entries = sorted(entries_rows, key=lambda x: (x['calculated_km'], x['duration_minutes']))

    ranked_entries_with_dense_rank = []
    last_score = None
    current_dense_rank = 0
    if sorted_entries:
        for entry in sorted_entries:
            current_score = (entry['calculated_km'], entry['duration_minutes'])
            if current_score != last_score:
                current_dense_rank += 1
                last_score = current_score

            mutable_entry = dict(entry)
            mutable_entry['rank'] = current_dense_rank
            # Ensure km values are integers for the template
            mutable_entry['start_km'] = int(mutable_entry['start_km'])
            mutable_entry['end_km'] = int(mutable_entry['end_km'])
            mutable_entry['calculated_km'] = int(mutable_entry['calculated_km'])
            ranked_entries_with_dense_rank.append(mutable_entry)

    total_kilometers_all = int(sum(entry['calculated_km'] for entry in ranked_entries_with_dense_rank))

    return render_template('results.html', entries=ranked_entries_with_dense_rank, total_kilometers_all_participants=int(total_kilometers_all))

# Add this new route in app.py
@app.route('/settings')
@login_required
def settings():
    db = get_db()
    # Fetch entries, similar to /results.
    entries_rows = db.execute('SELECT * FROM entries ORDER BY calculated_km ASC, duration_minutes ASC').fetchall()

    entries_list = [dict(row) for row in entries_rows]

    # Re-use ranking logic from /results route for consistency
    ranked_entries = []
    last_score = None
    current_dense_rank = 0
    if entries_list: # Ensure there are entries before trying to rank
        for entry_data in entries_list: # Renamed to avoid conflict with outer 'entry' if copy-pasting
            # Ensure numeric fields are integers for consistent display/logic
            entry_data['start_km'] = int(entry_data['start_km'])
            entry_data['end_km'] = int(entry_data['end_km'])
            entry_data['calculated_km'] = int(entry_data['calculated_km'])
            entry_data['duration_minutes'] = int(entry_data['duration_minutes'])

            current_score = (entry_data['calculated_km'], entry_data['duration_minutes'])
            if current_score != last_score:
                current_dense_rank += 1
                last_score = current_score

            mutable_entry = dict(entry_data) # Already a dict, but ensures it's a mutable copy
            mutable_entry['rank'] = current_dense_rank
            ranked_entries.append(mutable_entry)

    return render_template('settings.html', entries=ranked_entries)

@app.route('/delete_entry/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    db = get_db()
    # Check if entry exists before deleting (optional, but good practice)
    entry = db.execute('SELECT id FROM entries WHERE id = ?', (entry_id,)).fetchone()
    if entry:
        db.execute('DELETE FROM entries WHERE id = ?', (entry_id,))
        db.commit()
        # Optionally, add a flash message here: flash('Rit succesvol verwijderd.', 'success')
    # else:
        # Optionally, flash an error if entry not found: flash('Rit niet gevonden.', 'error')
    # else:
        # Optionally, flash an error if entry not found: flash('Rit niet gevonden.', 'error')
    return redirect(url_for('settings'))

@app.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST']) # Added 'POST'
@login_required
def edit_entry(entry_id):
    db = get_db()
    # Fetch existing entry for GET or if POST fails and needs to re-render form
    entry_data = db.execute(
        'SELECT id, name, start_km, end_km, arrival_time_last_fox '
        'FROM entries WHERE id = ?',
        (entry_id,)
    ).fetchone()

    if entry_data is None:
        # flash('Rit niet gevonden.', 'error')
        return redirect(url_for('settings'))

    # Convert to mutable dict for form pre-filling and potential re-render
    entry_dict = dict(entry_data)
    # Ensure km fields are int for form pre-filling (on GET or if POST fails)
    entry_dict['start_km'] = int(entry_dict['start_km'])
    entry_dict['end_km'] = int(entry_dict['end_km'])


    if request.method == 'POST':
        try:
            # Retrieve and process form data
            name = request.form['name']
            start_km = int(float(request.form['start_km']))
            end_km = int(float(request.form['end_km']))
            arrival_time_str = request.form['arrival_time_last_fox']

            # Recalculate driven_km and duration
            max_odom_reading = int(current_app.config.get('MAX_ODOMETER_READING', 1000))
            actual_end_km = end_km
            if end_km < start_km:  # Odometer rollover
                actual_end_km += max_odom_reading

            calculated_km = int(round(actual_end_km - start_km))

            if calculated_km < 0:
                # flash('Negatieve gereden kilometers na aanpassing. Controleer de kilometerstanden.', 'error')
                # Re-render form with error and existing (modified by user) data
                # For this, we need to pass back the current form values, not just original entry_dict
                form_data_for_template = {
                    'id': entry_id, # Keep id for the form action
                    'name': name,
                    'start_km': start_km,
                    'end_km': end_km,
                    'arrival_time_last_fox': arrival_time_str
                }
                # return render_template('edit_entry.html', entry=form_data_for_template, error='Negatieve berekende kilometers.')
                # Simpler for now: redirect to GET, losing user's invalid input but avoiding complex error render
                print(f"Warning: Negative calculated_km for entry {entry_id} edit. User input: Name={name}, StartKM={start_km}, EndKM={end_km}")
                return redirect(url_for('edit_entry', entry_id=entry_id))


            arrival_dt = datetime.strptime(arrival_time_str, '%H:%M')
            start_dt = datetime.strptime('12:00', '%H:%M')
            duration_delta = arrival_dt - start_dt
            duration_minutes = int(duration_delta.total_seconds() / 60)

            # Update database
            db.execute(
                'UPDATE entries SET name = ?, start_km = ?, end_km = ?, '
                'arrival_time_last_fox = ?, calculated_km = ?, duration_minutes = ? '
                'WHERE id = ?',
                (name, start_km, end_km, arrival_time_str, calculated_km, duration_minutes, entry_id)
            )
            db.commit()
            # flash('Rit succesvol bijgewerkt.', 'success')
            return redirect(url_for('settings'))

        except ValueError: # For float/int conversion or time parsing errors
            # flash('Ongeldige invoer. Controleer de velden.', 'error')
            # Re-render form with an error and original data (or redirect to GET)
            # For simplicity, redirect to GET which re-fetches original data.
            # A more advanced implementation would re-render with user's (invalid) data.
            print(f"ValueError during edit for entry {entry_id}: Likely invalid number or time format.")
            return redirect(url_for('edit_entry', entry_id=entry_id))
        except Exception as e:
            # Log the exception e
            print(f"Error updating entry {entry_id}: {e}")
            # flash('Er is een fout opgetreden bij het bijwerken.', 'error')
            return redirect(url_for('edit_entry', entry_id=entry_id))

    # For GET request, or if POST had an error and redirected to GET:
    return render_template('edit_entry.html', entry=entry_dict)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
