from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Global list to store hunt entries
hunt_entries = []

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
        arrival_time_last_fox = request.form['arrival_time_last_fox'] # Expected format HH:MM

        if end_km < start_km:
            # Ideally, pass an error message to the template
            return redirect(url_for('input_form'))

        calculated_km = round(end_km - start_km, 1)

        entry = {
            'name': name,
            'start_km': start_km,
            'end_km': end_km,
            'arrival_time_last_fox': arrival_time_last_fox,
            'calculated_km': calculated_km
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
    # Sort entries: primary key calculated_km (ascending), secondary key arrival_time_last_fox (ascending)
    # For time sorting, ensure consistent format e.g., "HH:MM"
    sorted_entries = sorted(hunt_entries, key=lambda x: (x['calculated_km'], x['arrival_time_last_fox']))

    total_kilometers_all = sum(entry['calculated_km'] for entry in sorted_entries)

    return render_template('results.html', entries=sorted_entries, total_kilometers_all_participants=round(total_kilometers_all, 1))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
