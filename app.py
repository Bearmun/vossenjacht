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
app.config.setdefault('MAX_ODOMETER_READING', 1000.0)


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
    db.executescript('''
        DROP TABLE IF EXISTS entries;
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_km REAL NOT NULL,
            end_km REAL NOT NULL,
            arrival_time_last_fox TEXT NOT NULL,
            calculated_km REAL NOT NULL,
            duration_minutes INTEGER NOT NULL
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
    return render_template('input.html')

@app.route('/add_entry', methods=['POST'])
@login_required # Protect this route
def add_entry():
    try:
        name = request.form['name']
        start_km = float(request.form['start_km'])
        end_km = float(request.form['end_km'])
        arrival_time_str = request.form['arrival_time_last_fox']

        max_odom_reading = current_app.config.get('MAX_ODOMETER_READING', 1000.0)
        actual_end_km = end_km
        if end_km < start_km: # Odometer rollover
            actual_end_km += max_odom_reading

        calculated_km = round(actual_end_km - start_km, 1)

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
            ranked_entries_with_dense_rank.append(mutable_entry)

    total_kilometers_all = sum(entry['calculated_km'] for entry in ranked_entries_with_dense_rank)

    return render_template('results.html', entries=ranked_entries_with_dense_rank, total_kilometers_all_participants=round(total_kilometers_all, 1))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
