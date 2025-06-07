import unittest
import sys
import os

# Add the parent directory to the Python path to allow module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, get_db, init_db # Import get_db, init_db
# from flask import g # g is not typically used directly in tests this way

class FoxHuntTrackerDBTests(unittest.TestCase):

    def setUp(self):
        """Set up test client, in-memory DB, and app context before each test."""
        app.config.update({
            "TESTING": True,
            "DATABASE": ":memory:",
            "MAX_ODOMETER_READING": 1000.0,
            "FLASK_SECRET_KEY": "test_secret_key_for_sessions", # Essential for session
            "VREETVOS_ADMIN_PASSWORD": "test_password", # For auth tests
            "SERVER_NAME": "localhost.localdomain", # For url_for with next param if needed
            "WTF_CSRF_ENABLED": False, # Already here, good for tests
            "DEBUG": False
        })
        self.client = app.test_client()

        self.app_context = app.app_context()
        self.app_context.push()

        init_db()

    def tearDown(self):
        self.app_context.pop()

    # Helper methods for login/logout
    def login(self, password="test_password"):
        return self.client.post('/login', data=dict(password=password), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # Removed _get_db_for_test, use get_db() from app directly

    def test_01_index_redirects_to_results(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/results', response.location)

    def test_02_input_route_loads_dutch_after_login(self): # Renamed
        self.login() # Log in first
        response = self.client.get('/input')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data)
        # Check for logout link now that we are logged in
        self.assertIn(b'Uitloggen', response.data)

    def test_03_add_valid_entry_check_db_and_ui(self):
        """Test adding a single valid entry, check DB and UI after login."""
        self.login() # Log in first
        response = self.client.post('/add_entry', data={
            'name': 'Team Alfa DB', 'start_km': '100.0', 'end_km': '150.5', 'arrival_time_last_fox': '13:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)

        # Check UI on results page for the new column order and rank
        # Expected order: Plaats, Naam, Gereden KM, Duur, Begin KM, Eind KM, Aankomsttijd
        # Example for one entry: <tr><td>1</td><td>Team Alfa DB</td><td>50.5</td><td>60</td><td>100.0</td><td>150.5</td><td>13:00</td></tr>
        # For simplicity, check key elements are present and assume order by visual inspection of a full test run if needed.
        # A more robust check would parse HTML or use very specific regex.
        html_content = response.data.decode('utf-8')
        self.assertIn(b'Vreetvos resultaten', response.data) # Check h1
        self.assertIn(b'Team Alfa DB', response.data)
        self.assertIn(b'<td>1</td>', response.data) # Rank
        self.assertIn(b'<td>50.5</td>', response.data) # calculated_km
        self.assertIn(b'<td>60</td>', response.data)   # duration_minutes
        self.assertIn(b'<td>100.0</td>', response.data) # start_km
        self.assertIn(b'<td>150.5</td>', response.data) # end_km
        self.assertIn(b'<td>13:00</td>', response.data) # arrival_time_last_fox
        self.assertIn(b'class="rank-gold"', response.data) # Should be rank 1, so gold

        # Check DB
        db = get_db()
        cursor = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Alfa DB',))
        entry_from_db = cursor.fetchone()
        self.assertIsNotNone(entry_from_db)
        self.assertEqual(entry_from_db['calculated_km'], 50.5)
        self.assertEqual(entry_from_db['duration_minutes'], 60)

    def test_04_kilometer_calculation_direct_check_db(self):
        self.login() # Log in first
        self.client.post('/add_entry', data={
            'name': 'Team Bravo DB', 'start_km': '200.3', 'end_km': '210.7', 'arrival_time_last_fox': '12:30'
        }) # calc_km = 10.4, duration = 30
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Bravo DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 10.4)
        self.assertEqual(entry['duration_minutes'], 30)

    def test_05_sorting_logic_km_then_duration_check_ui(self):
        self.login() # Log in first
        self.client.post('/add_entry', data={'name': 'Hunter B', 'start_km': '0.0', 'end_km': '30.0', 'arrival_time_last_fox': '13:30'}) # 30km, 90min
        self.client.post('/add_entry', data={'name': 'Hunter A', 'start_km': '0.0', 'end_km': '50.0', 'arrival_time_last_fox': '14:00'}) # 50km, 120min
        self.client.post('/add_entry', data={'name': 'Hunter C', 'start_km': '0.0', 'end_km': '50.0', 'arrival_time_last_fox': '13:00'}) # 50km, 60min

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        # Check for table headers including "Plaats"
        self.assertIn(b'<th>Plaats</th>', response.data)
        self.assertIn(b'<th>Naam</th>', response.data)
        self.assertIn(b'<th>Gereden KM</th>', response.data)
        data_str = response.data.decode('utf-8')

        hunter_b_pos = data_str.find('Hunter B')
        hunter_c_pos = data_str.find('Hunter C')
        hunter_a_pos = data_str.find('Hunter A')

        self.assertTrue(hunter_b_pos != -1 and hunter_c_pos != -1 and hunter_a_pos != -1)
        self.assertTrue(hunter_b_pos < hunter_c_pos < hunter_a_pos, "Sorting error: expected B, C, A")

    def test_06_error_non_numeric_km_redirects_check_db_empty(self):
        self.login() # Log in first
        self.client.post('/add_entry', data={
            'name': 'Error Team Numeric', 'start_km': 'abc', 'end_km': '100.0', 'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_07_total_kilometers_calculation_dutch_ui(self):
        self.login() # Log in first
        self.client.post('/add_entry', data={'name': 'Auto 1', 'start_km': '0.0', 'end_km': '10.5', 'arrival_time_last_fox': '12:10'})
        self.client.post('/add_entry', data={'name': 'Auto 2', 'start_km': '100.0', 'end_km': '120.3', 'arrival_time_last_fox': '12:20'})
        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        self.assertIn(b'<th>Plaats</th>', response.data) # Check for new column header
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 30.8 km', response.data)

    def test_08_empty_results_page_dutch_ui(self):
        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        # On an empty page, the table headers (including "Plaats") are not rendered.
        # self.assertIn(b'<th>Plaats</th>', response.data) # This should not be present
        self.assertNotIn(b'<th>Plaats</th>', response.data) # Verify it's NOT there
        self.assertIn(b'Nog geen ritten ingevoerd.', response.data)
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 0 km', response.data)
        self.assertIn(b'Inloggen om Rit In te Voeren', response.data) # Check for login link
        db = get_db() # Check DB is indeed empty
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)


    def test_09_add_multiple_entries_dutch_ui_duration_check_ui_and_db_count(self):
        self.login() # Log in first
        self.client.post('/add_entry', data={'name': 'Rijder X', 'start_km': '50.0', 'end_km': '60.0', 'arrival_time_last_fox': '14:00'}) # 10km, 120min -> Rank 2
        self.client.post('/add_entry', data={'name': 'Rijder Y', 'start_km': '70.0', 'end_km': '75.5', 'arrival_time_last_fox': '12:30'}) # 5.5km, 30min -> Rank 1
        self.client.post('/add_entry', data={'name': 'Rijder Z', 'start_km': '80.0', 'end_km': '95.0', 'arrival_time_last_fox': '13:00'}) # 15km, 60min -> Rank 3

        db = get_db()
        entries_count = db.execute('SELECT COUNT(id) FROM entries').fetchone()[0]
        self.assertEqual(entries_count, 3)

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        self.assertIn(b'<th>Plaats</th>', response.data) # Check for new column header
        self.assertIn(b'Uitloggen', response.data) # Check for logout link
        self.assertIn(b'Nieuwe Rit Invoeren', response.data) # Check for new entry link

        # Check if ranks and names are present. Order is Rijder Y (1), Rijder X (2), Rijder Z (3)
        html_content = response.data.decode('utf-8')
        self.assertIn(b'<td>1</td>', response.data)
        self.assertIn(b'Rijder Y', response.data) # Rank 1
        self.assertIn(b'<td>2</td>', response.data)
        self.assertIn(b'Rijder X', response.data) # Rank 2
        self.assertIn(b'<td>3</td>', response.data)
        self.assertIn(b'Rijder Z', response.data) # Rank 3

        self.assertIn(b'120', response.data) # duration for X
        self.assertIn(b'Rijder Y', response.data)
        self.assertIn(b'30', response.data)  # duration for Y
        self.assertIn(b'Rijder Z', response.data)
        self.assertIn(b'60', response.data)  # duration for Z
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 30.5 km', response.data)

    def test_10_odometer_rollover_calculation_check_db(self):
        self.login() # Log in first
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
        self.login() # Log in first
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
        self.login() # Log in first
        self.client.post('/add_entry', data={
            'name': 'Time Error Team', 'start_km': '10.0', 'end_km': '20.0', 'arrival_time_last_fox': '99:99'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_13_duration_calculation_various_times_check_db(self):
        self.login() # Log in first
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

    def test_14_rank_highlighting(self):
        """Test rank-based CSS class highlighting for top 3 entries."""
        self.login() # Log in first
        # Entry data: (name, km_start, km_end, time_str, expected_km, expected_duration)
        # Rank 1 (Gold)
        self.client.post('/add_entry', data={'name': 'Gold A', 'start_km': '0', 'end_km': '10', 'arrival_time_last_fox': '13:00'}) # 10km, 60min
        self.client.post('/add_entry', data={'name': 'Gold B', 'start_km': '100', 'end_km': '110', 'arrival_time_last_fox': '13:00'}) # 10km, 60min
        # Rank 2 (Silver)
        self.client.post('/add_entry', data={'name': 'Silver C', 'start_km': '0', 'end_km': '20', 'arrival_time_last_fox': '13:10'}) # 20km, 70min
        # Rank 3 (Bronze)
        self.client.post('/add_entry', data={'name': 'Bronze D', 'start_km': '0', 'end_km': '30', 'arrival_time_last_fox': '13:20'}) # 30km, 80min
        self.client.post('/add_entry', data={'name': 'Bronze E', 'start_km': '50', 'end_km': '80', 'arrival_time_last_fox': '13:20'}) # 30km, 80min
        # Rank 4 (No highlight)
        self.client.post('/add_entry', data={'name': 'NoHighlight F', 'start_km': '0', 'end_km': '40', 'arrival_time_last_fox': '13:30'}) # 40km, 90min

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        html_content = response.data.decode('utf-8')

        # Check for title - Vreetvos resultaten
        self.assertIn("<title>Vreetvos resultaten</title>", html_content)
        self.assertIn(b'<th>Plaats</th>', response.data) # Check for new column header
        self.assertIn(b'Uitloggen', response.data) # Check for logout link
        import re

        def get_row_html_for_entry(entry_name, full_html):
            # Captures the whole <tr> element containing the entry_name
            # Ensures that <td>entry_name</td> is part of the row content.
            # It looks for the opening <tr>, then any characters non-greedily (.*?),
            # as long as it's not another <tr> or </tr> too soon,
            # then the specific <td>entry_name</td>, then any characters non-greedily (.*?),
            # and finally the closing </tr>.
            # (?:(?!</?tr>).)* matches anything that's not an opening or closing tr tag
            pattern = f'(<tr[^>]*>((?:(?!</?tr>).)*?)<td>{re.escape(entry_name)}</td>((?:(?!</?tr>).)*?)</tr>)'
            match = re.search(pattern, full_html, re.DOTALL)
            if match:
                return match.group(1) # Return the whole <tr>...</tr>
            self.fail(f"Row for entry '{entry_name}' not found in HTML content.") # Fail if row not found

        # Check Gold A and Gold B (Rank 1)
        row_gold_a = get_row_html_for_entry('Gold A', html_content)
        self.assertIn('class="rank-gold"', row_gold_a)
        row_gold_b = get_row_html_for_entry('Gold B', html_content)
        self.assertIn('class="rank-gold"', row_gold_b)

        # Check Silver C (Rank 2)
        row_silver_c = get_row_html_for_entry('Silver C', html_content)
        self.assertIn('class="rank-silver"', row_silver_c)

        # Check Bronze D and Bronze E (Rank 3)
        row_bronze_d = get_row_html_for_entry('Bronze D', html_content)
        self.assertIn('class="rank-bronze"', row_bronze_d)
        row_bronze_e = get_row_html_for_entry('Bronze E', html_content)
        self.assertIn('class="rank-bronze"', row_bronze_e)

        # Check NoHighlight F (Rank 4)
        row_no_highlight_f = get_row_html_for_entry('NoHighlight F', html_content)
        # Rank 4 should have class="" because of how the Jinja template is structured
        self.assertIn('class=""', row_no_highlight_f)
        self.assertNotIn('rank-gold', row_no_highlight_f)
        self.assertNotIn('rank-silver', row_no_highlight_f)
        self.assertNotIn('rank-bronze', row_no_highlight_f)

    # New Authentication Tests
    def test_15_auth_input_page_requires_login(self):
        """Test that accessing /input without login redirects to /login."""
        response = self.client.get('/input', follow_redirects=False) # Don't follow, check redirect location
        self.assertEqual(response.status_code, 302)
        # Flask's test client with SERVER_NAME often results in location like '/login?next=http://servername/protected_route'
        expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}/input"
        self.assertEqual(response.location, expected_redirect_url)

        # After login, should be accessible
        self.login()
        response = self.client.get('/input')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data)

    def test_16_auth_add_entry_requires_login(self):
        """Test that POST to /add_entry without login redirects and does not add data."""
        # Attempt to add entry without login
        response = self.client.post('/add_entry', data={
            'name': 'Sneaky Entry', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:01'
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}/add_entry"
        self.assertEqual(response.location, expected_redirect_url)

        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Sneaky Entry',)).fetchone()
        self.assertIsNone(entry, "Entry should not have been added without login")

        # Log in and add entry
        self.login()
        response = self.client.post('/add_entry', data={
            'name': 'Legit Entry', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:01'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to results
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Legit Entry',)).fetchone()
        self.assertIsNotNone(entry, "Entry should have been added after login")

    def test_17_auth_login_logout_flow(self):
        """Test the full login and logout flow."""
        # Access login page
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Inloggen voor Rit Invoer', response.data)

        # Attempt incorrect login
        response = self.login(password="wrong_password")
        self.assertEqual(response.status_code, 200) # Stays on login page
        self.assertIn(b'Ongeldig wachtwoord. Probeer opnieuw.', response.data)
        self.assertIn(b'Inloggen voor Rit Invoer', response.data) # Still on login page

        # Correct login
        response = self.login(password="test_password") # Uses default correct password from setUp
        self.assertEqual(response.status_code, 200) # Redirects to input_form by default
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data) # Check we are on input page
        self.assertIn(b'Uitloggen', response.data) # Logout link should be on input page

        # Access results page while logged in
        response = self.client.get('/results')
        self.assertIn(b'Uitloggen', response.data) # Logout link on results page
        self.assertIn(b'Nieuwe Rit Invoeren', response.data) # New entry link on results page

        # Logout
        response = self.logout()
        self.assertEqual(response.status_code, 200) # Redirects to results
        self.assertIn(b'Vreetvos resultaten', response.data) # Back on results page
        self.assertIn(b'Inloggen om Rit In te Voeren', response.data) # Login link is back
        self.assertNotIn(b'Uitloggen', response.data) # Logout link is gone

        # Verify /input is protected again
        response = self.client.get('/input', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}/input"
        self.assertEqual(response.location, expected_redirect_url)


if __name__ == '__main__':
    unittest.main()
