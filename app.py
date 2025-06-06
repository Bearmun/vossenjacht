from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime

app = Flask(__name__)

from flask import current_app # Import current_app

# Global list to store hunt entries
hunt_entries = []

# MAX_ODOMETER_READING = 1000.0 # Will be accessed via app.config

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
        arrival_time_str = request.form['arrival_time_last_fox'] # HH:MM format

        actual_end_km = end_km
        max_odom_reading = current_app.config.get('MAX_ODOMETER_READING', 1000.0)
        if end_km < start_km: # Odometer rollover detected
            actual_end_km += max_odom_reading

        calculated_km = round(actual_end_km - start_km, 1)

        # Calculate duration from 12:00 PM
        try:
            arrival_dt = datetime.strptime(arrival_time_str, '%H:%M')
            start_dt = datetime.strptime('12:00', '%H:%M')

            duration_delta = arrival_dt - start_dt
            duration_minutes = int(duration_delta.total_seconds() / 60)

            # Assuming arrival times are always >= 12:00 on the same day.
            # Negative duration implies arrival before 12:00, which should ideally be handled
            # or prevented at input if the hunt strictly starts at 12:00.
            # For now, we allow it as calculated.
            # if duration_minutes < 0:
            #     pass # Or handle as an error, e.g. return redirect(url_for('input_form'))

        except ValueError:
            # Invalid time format
            return redirect(url_for('input_form')) # Redirect, ideally with error

        # Ensure calculated_km is not negative if MAX_ODOMETER_READING is too small
        # or start_km was already after a rollover and end_km is small.
        # This simple model assumes at most one rollover.
        if calculated_km < 0:
            # This might indicate a data entry error or more than one rollover.
            # For now, redirect to input. A more robust solution might log an error
            # or pass a specific error message to the user.
            print(f"Warning: Negative calculated_km for {name}. Start: {start_km}, End: {end_km}. Adjusted End: {actual_end_km}")
            return redirect(url_for('input_form')) # Or an error page/message

        entry = {
            'name': name,
            'start_km': start_km,
            'end_km': end_km, # Store original end_km
            'arrival_time_last_fox': arrival_time_str, # Store as string
            'calculated_km': calculated_km,
            'duration_minutes': duration_minutes
        }
        hunt_entries.append(entry)
        return redirect(url_for('results'))
    except ValueError:
        # Ideally, pass an error message to the template
        return redirect(url_for('input_form'))
    except Exception as e:
        print(f"An error occurred in add_entry: {e}")
        return redirect(url_for('input_form'))

@app.route('/results')
def results():
    # Sort entries: primary key calculated_km (ascending), secondary key duration_minutes (ascending)
    sorted_entries = sorted(hunt_entries, key=lambda x: (x['calculated_km'], x.get('duration_minutes', float('inf'))))

    total_kilometers_all = sum(entry['calculated_km'] for entry in sorted_entries)

    return render_template('results.html', entries=sorted_entries, total_kilometers_all_participants=round(total_kilometers_all, 1))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
