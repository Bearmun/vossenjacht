import sqlite3
import click
from flask import Flask, render_template, request, redirect, url_for, g, current_app
from datetime import datetime

# DATABASE = 'foxhunt.db' # Replaced by config
app = Flask(__name__)
# Ensure MAX_ODOMETER_READING is in app.config if not set by tests
app.config.setdefault('MAX_ODOMETER_READING', 1000.0)
app.config.setdefault('DATABASE_FILENAME', 'foxhunt.db') # Default DB filename

def get_db():
    """Connect to the application's configured database. The connection
    is unique for each request and will be reused if this is called
    again.
    """
    if 'db' not in g:
        db_path = current_app.config.get('DATABASE', current_app.config['DATABASE_FILENAME'])
        g.db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """If this request connected to the database, close the
    connection.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Clear existing data and create new tables."""
    db = get_db()
    # For simplicity, schema is here. Could also execute a .sql file.
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
    """Clear existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def init_app(flask_app):
    """Register database functions with the Flask app. This is called by
    the application factory.
    """
    flask_app.teardown_appcontext(close_db)
    flask_app.cli.add_command(init_db_command)

init_app(app) # Register with the current app instance

@app.route('/')
def index():
    return redirect(url_for('results'))

@app.route('/input')
def input_form():
    return render_template('input.html')

@app.route('/add_entry', methods=['POST'])
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

    # Convert Row objects to behave more like dictionaries for sorting compatibility if needed,
    # though direct access x['key'] works with sqlite3.Row.
    # No explicit conversion needed if sqlite3.Row is used directly.

    # Sort entries: primary key calculated_km (ascending), secondary key duration_minutes (ascending)
    # sqlite3.Row objects are dict-like, so x.get should not be necessary if columns always exist.
    # Using x['duration_minutes'] directly if we are sure the column is there.
    # For robustness with potentially missing data (not expected with new schema), .get is safer.
    # However, sqlite3.Row does not have .get(). Direct access is fine due to schema.
    sorted_entries = sorted(entries_rows, key=lambda x: (x['calculated_km'], x['duration_minutes']))

    # Add rank to entries - Standard Dense Ranking
    ranked_entries_with_dense_rank = []
    last_score = None
    current_dense_rank = 0
    if sorted_entries: # Ensure there are entries before trying to rank
        for entry in sorted_entries:
            # Make sure duration_minutes is handled if it could be None, though schema says NOT NULL
            # Using x.get('duration_minutes', float('inf'))) was for old list-based data.
            # With sqlite3.Row and NOT NULL, direct access x['duration_minutes'] is fine.
            current_score = (entry['calculated_km'], entry['duration_minutes'])
            if current_score != last_score:
                current_dense_rank += 1 # Increment rank for new distinct score
                last_score = current_score

            mutable_entry = dict(entry) # Convert sqlite3.Row to a mutable dict to add 'rank'
            mutable_entry['rank'] = current_dense_rank
            ranked_entries_with_dense_rank.append(mutable_entry)

    total_kilometers_all = sum(entry['calculated_km'] for entry in ranked_entries_with_dense_rank)

    return render_template('results.html', entries=ranked_entries_with_dense_rank, total_kilometers_all_participants=round(total_kilometers_all, 1))

if __name__ == '__main__':
    # Note: app.run() is not called here if using `flask run` command.
    # For direct `python app.py` execution, it would be needed.
    # The init_app call handles CLI setup.
    app.run(debug=True, host='0.0.0.0', port=8080)
