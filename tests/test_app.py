import unittest
import sys
import os

# Add the parent directory to the Python path to allow module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, get_db, init_db # Import get_db, init_db

class FoxHuntTrackerDBTests(unittest.TestCase): # Renamed class

    def setUp(self):
        """Set up test client, in-memory DB, and app context before each test."""
        app.config.update({
            "TESTING": True,
            "DATABASE": ":memory:",  # Use in-memory SQLite for tests
            "MAX_ODOMETER_READING": 1000.0,  # Consistent for most tests
            "WTF_CSRF_ENABLED": False, # Disable CSRF for simpler form posts in tests
            "DEBUG": False # Ensure debug is off unless specifically testing it
        })
        self.client = app.test_client()

        # Push an application context to use get_db and init_db
        self.app_context = app.app_context()
        self.app_context.push()

        # Initialize the schema in the in-memory database
        init_db()

    def tearDown(self):
        """Close DB and pop application context after each test."""
        # No explicit db.close() needed if using get_db() and app context teardown
        self.app_context.pop()

    def _get_db_for_test(self):
        """Helper to get DB instance within test, ensures app context is active."""
        if not hasattr(g, 'db') and self.app_context: # g might not be available directly
             return get_db() # Relies on app_context being pushed
        return g.db


    def test_01_index_redirects_to_results(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/results', response.location)

    def test_02_input_route_loads_dutch(self):
        response = self.client.get('/input')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data)

    def test_03_add_valid_entry_check_db_and_ui(self):
        """Test adding a single valid entry, check DB and UI."""
        response = self.client.post('/add_entry', data={
            'name': 'Team Alfa DB', 'start_km': '100.0', 'end_km': '150.5', 'arrival_time_last_fox': '13:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check UI
        self.assertIn(b'Vossenjacht Resultaten', response.data)
        self.assertIn(b'Team Alfa DB', response.data)
        self.assertIn(b'50.5', response.data) # calculated_km
        self.assertIn(b'60', response.data)   # duration_minutes

        # Check DB
        db = get_db()
        cursor = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Alfa DB',))
        entry_from_db = cursor.fetchone()
        self.assertIsNotNone(entry_from_db)
        self.assertEqual(entry_from_db['calculated_km'], 50.5)
        self.assertEqual(entry_from_db['duration_minutes'], 60)

    def test_04_kilometer_calculation_direct_check_db(self):
        self.client.post('/add_entry', data={
            'name': 'Team Bravo DB', 'start_km': '200.3', 'end_km': '210.7', 'arrival_time_last_fox': '12:30'
        }) # calc_km = 10.4, duration = 30
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Bravo DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 10.4)
        self.assertEqual(entry['duration_minutes'], 30)

    def test_05_sorting_logic_km_then_duration_check_ui(self):
        self.client.post('/add_entry', data={'name': 'Hunter B', 'start_km': '0.0', 'end_km': '30.0', 'arrival_time_last_fox': '13:30'}) # 30km, 90min
        self.client.post('/add_entry', data={'name': 'Hunter A', 'start_km': '0.0', 'end_km': '50.0', 'arrival_time_last_fox': '14:00'}) # 50km, 120min
        self.client.post('/add_entry', data={'name': 'Hunter C', 'start_km': '0.0', 'end_km': '50.0', 'arrival_time_last_fox': '13:00'}) # 50km, 60min

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        data_str = response.data.decode('utf-8')

        hunter_b_pos = data_str.find('Hunter B')
        hunter_c_pos = data_str.find('Hunter C')
        hunter_a_pos = data_str.find('Hunter A')

        self.assertTrue(hunter_b_pos != -1 and hunter_c_pos != -1 and hunter_a_pos != -1)
        self.assertTrue(hunter_b_pos < hunter_c_pos < hunter_a_pos, "Sorting error: expected B, C, A")

    def test_06_error_non_numeric_km_redirects_check_db_empty(self):
        self.client.post('/add_entry', data={
            'name': 'Error Team Numeric', 'start_km': 'abc', 'end_km': '100.0', 'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_07_total_kilometers_calculation_dutch_ui(self):
        self.client.post('/add_entry', data={'name': 'Auto 1', 'start_km': '0.0', 'end_km': '10.5', 'arrival_time_last_fox': '12:10'})
        self.client.post('/add_entry', data={'name': 'Auto 2', 'start_km': '100.0', 'end_km': '120.3', 'arrival_time_last_fox': '12:20'})
        response = self.client.get('/results')
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 30.8 km', response.data)

    def test_08_empty_results_page_dutch_ui(self):
        response = self.client.get('/results')
        self.assertIn(b'Nog geen ritten ingevoerd.', response.data)
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 0 km', response.data)
        db = get_db() # Check DB is indeed empty
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)


    def test_09_add_multiple_entries_dutch_ui_duration_check_ui_and_db_count(self):
        self.client.post('/add_entry', data={'name': 'Rijder X', 'start_km': '50.0', 'end_km': '60.0', 'arrival_time_last_fox': '14:00'})
        self.client.post('/add_entry', data={'name': 'Rijder Y', 'start_km': '70.0', 'end_km': '75.5', 'arrival_time_last_fox': '12:30'})
        self.client.post('/add_entry', data={'name': 'Rijder Z', 'start_km': '80.0', 'end_km': '95.0', 'arrival_time_last_fox': '13:00'})

        db = get_db()
        entries_count = db.execute('SELECT COUNT(id) FROM entries').fetchone()[0]
        self.assertEqual(entries_count, 3)

        response = self.client.get('/results')
        self.assertIn(b'Rijder X', response.data)
        self.assertIn(b'120', response.data) # duration for X
        self.assertIn(b'Rijder Y', response.data)
        self.assertIn(b'30', response.data)  # duration for Y
        self.assertIn(b'Rijder Z', response.data)
        self.assertIn(b'60', response.data)  # duration for Z
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 30.5 km', response.data)

    def test_10_odometer_rollover_calculation_check_db(self):
        # MAX_ODOMETER_READING is 1000.0 from setUp
        self.client.post('/add_entry', data={
            'name': 'Rollover Car DB', 'start_km': '950.0', 'end_km': '50.0', 'arrival_time_last_fox': '13:00'
        }) # Expected calc_km: (50.0 + 1000.0) - 950.0 = 100.0 km
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Rollover Car DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 100.0)
        self.assertEqual(entry['start_km'], 950.0) # Original start_km
        self.assertEqual(entry['end_km'], 50.0)   # Original end_km

    def test_11_negative_calculated_km_after_rollover_redirects_check_db_empty(self):
        original_max_odom = app.config['MAX_ODOMETER_READING']
        app.config['MAX_ODOMETER_READING'] = 50.0 # Temp set for this test

        response = self.client.post('/add_entry', data={
            'name': 'Negative KM Team', 'start_km': '100.0', 'end_km': '10.0', 'arrival_time_last_fox': '13:00'
        }, follow_redirects=True)

        app.config['MAX_ODOMETER_READING'] = original_max_odom # Reset

        self.assertEqual(response.status_code, 200) # Redirects to input form
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data)

        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_12_invalid_time_format_redirects_to_input_check_db_empty(self):
        self.client.post('/add_entry', data={
            'name': 'Time Error Team', 'start_km': '10.0', 'end_km': '20.0', 'arrival_time_last_fox': '99:99'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_13_duration_calculation_various_times_check_db(self):
        self.client.post('/add_entry', data={'name': 'Team Noon', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:00'})
        self.client.post('/add_entry', data={'name': 'Team Noon Plus One', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:01'})
        self.client.post('/add_entry', data={'name': 'Team Late', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '23:59'})
        self.client.post('/add_entry', data={'name': 'Team Early', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '11:00'})

        db = get_db()
        noon_entry = db.execute('SELECT duration_minutes FROM entries WHERE name = ?', ('Team Noon',)).fetchone()
        self.assertEqual(noon_entry['duration_minutes'], 0)

        noon_plus_one_entry = db.execute('SELECT duration_minutes FROM entries WHERE name = ?', ('Team Noon Plus One',)).fetchone()
        self.assertEqual(noon_plus_one_entry['duration_minutes'], 1)

        late_entry = db.execute('SELECT duration_minutes FROM entries WHERE name = ?', ('Team Late',)).fetchone()
        self.assertEqual(late_entry['duration_minutes'], 719)

        early_entry = db.execute('SELECT duration_minutes FROM entries WHERE name = ?', ('Team Early',)).fetchone()
        self.assertEqual(early_entry['duration_minutes'], -60)

if __name__ == '__main__':
    unittest.main()
