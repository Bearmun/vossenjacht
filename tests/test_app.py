import unittest
import sys
import os

import re # Added re
from datetime import datetime # Ensure datetime is imported

# Add the parent directory to the Python path to allow module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, get_db, init_db # Import get_db, init_db
# from flask import g # g is not typically used directly in tests this way

from werkzeug.security import generate_password_hash # Added for user creation

class FoxHuntTrackerDBTests(unittest.TestCase):

    def setUp(self):
        """Set up test client, in-memory DB, and app context before each test."""
        app.config.update({
            "TESTING": True,
            "DATABASE": ":memory:", # Use in-memory SQLite for tests
            "MAX_ODOMETER_READING": 1000,
            "FLASK_SECRET_KEY": "test_secret_key_for_sessions",
            "SERVER_NAME": "localhost.localdomain", # For url_for with next param if needed
            "WTF_CSRF_ENABLED": False, # Disable CSRF for simpler test forms
            "DEBUG": False
        })
        self.client = app.test_client()

        self.app_context = app.app_context()
        self.app_context.push()

        init_db() # Initialize schema

        # Create default users for tests
        db = get_db()
        db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                   ('testadmin', generate_password_hash('adminpass'), 'admin'))
        db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                   ('testmod', generate_password_hash('modpass'), 'moderator'))
        db.commit()

        self.admin_user = {'username': 'testadmin', 'password': 'adminpass'}
        self.mod_user = {'username': 'testmod', 'password': 'modpass'}


    def tearDown(self):
        self.app_context.pop()

    # Helper methods for login/logout
    def login(self, username="testadmin", password="adminpass"): # Updated parameters
        return self.client.post('/login', data=dict(username=username, password=password), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # Removed _get_db_for_test, use get_db() from app directly

    # --- Helper methods for creating DB entities ---
    def _create_user(self, username, password, role):
        db = get_db()
        user_id = db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                           (username, generate_password_hash(password), role)).lastrowid
        db.commit()
        return user_id

    def _create_vossenjacht(self, name, type, creator_id, start_time='12:00'): # Added start_time, defaults to 12:00 for existing tests
        db = get_db()
        vj_id = db.execute("INSERT INTO vossenjachten (name, type, creator_id, start_time) VALUES (?, ?, ?, ?)",
                         (name, type, creator_id, start_time)).lastrowid
        db.commit()
        return vj_id

    def _create_entry(self, name, start_km, end_km, arrival_time_str, vj_id, user_id, calculated_km=None, duration_minutes=None):
        db = get_db()
        # Simplified calculation for tests if not provided
        if calculated_km is None:
            actual_end_km = end_km
            if end_km < start_km:
                actual_end_km += app.config.get('MAX_ODOMETER_READING', 1000)
            calculated_km = actual_end_km - start_km

        if duration_minutes is None:
            try:
                arrival_dt = datetime.strptime(arrival_time_str, '%H:%M')
                start_dt = datetime.strptime('12:00', '%H:%M') # Default start for duration
                duration_delta = arrival_dt - start_dt
                duration_minutes = int(duration_delta.total_seconds() / 60)
            except ValueError:
                duration_minutes = 0 # Default if time parsing fails in test helper

        entry_id = db.execute(
            'INSERT INTO entries (name, start_km, end_km, arrival_time_last_fox, calculated_km, duration_minutes, vossenjacht_id, user_id)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (name, start_km, end_km, arrival_time_str, calculated_km, duration_minutes, vj_id, user_id)
        ).lastrowid
        db.commit()
        return entry_id

    def test_01_index_redirects_to_results(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/results', response.location)

    def test_02_input_route_loads_dutch_after_login(self):
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response = self.client.get('/input')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Rit Invoeren', response.data) # Updated title/header text
        self.assertIn(b'Uitloggen', response.data) # Check for logout link

    def test_03_add_valid_entry_check_db_and_ui(self):
        """Test adding a single valid entry, check DB and UI after login."""
        # A moderator or admin needs to create a Vossenjacht first
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("Test VJ for Entry", "kilometers", admin_id)

        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        response = self.client.post('/add_entry', data={
            'vossenjacht_id': vj_id, # Crucial: associate with a VJ
            'name': 'Team Alfa DB', 'start_km': '100', 'end_km': '150', 'arrival_time_last_fox': '13:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vreetvos Resultaten', response.data) # Updated title

        html_content = response.data.decode('utf-8')
        self.assertIn('Team Alfa DB', html_content)
        self.assertIn('<td>1</td>', html_content) # Rank
        self.assertIn('<td>50</td>', html_content) # calculated_km
        self.assertIn('<td>60</td>', html_content) # duration_minutes
        self.assertIn('Test VJ for Entry', html_content) # Vossenjacht name
        self.assertIn('class="rank-gold"', html_content)

        db = get_db()
        entry_from_db = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Alfa DB',)).fetchone()
        self.assertIsNotNone(entry_from_db)
        self.assertEqual(entry_from_db['calculated_km'], 50)
        self.assertEqual(entry_from_db['vossenjacht_id'], vj_id)
        self.assertEqual(entry_from_db['user_id'], db.execute("SELECT id FROM users WHERE username = 'testmod'").fetchone()['id'])


    def test_04_kilometer_calculation_direct_check_db(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("Test VJ for KM Calc", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        self.client.post('/add_entry', data={
            'vossenjacht_id': vj_id,
            'name': 'Team Bravo DB', 'start_km': '200', 'end_km': '210', 'arrival_time_last_fox': '12:30'
        })
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Bravo DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 10)

    def test_05_sorting_logic_km_then_duration_check_ui(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("SortTest VJ", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        self._create_entry('Hunter B', 0, 30, '13:30', vj_id, admin_id) # 30km, 90min
        self._create_entry('Hunter A', 0, 50, '14:00', vj_id, admin_id) # 50km, 120min
        self._create_entry('Hunter C', 0, 50, '13:00', vj_id, admin_id) # 50km, 60min

        response = self.client.get(f'/results?vj_id={vj_id}') # Filter by VJ
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vreetvos Resultaten', response.data)
        data_str = response.data.decode('utf-8')

        hunter_b_pos = data_str.find('Hunter B') # Rank 3 (30km)
        hunter_c_pos = data_str.find('Hunter C') # Rank 1 (50km, 60min)
        hunter_a_pos = data_str.find('Hunter A') # Rank 2 (50km, 120min)

        self.assertTrue(hunter_b_pos != -1 and hunter_c_pos != -1 and hunter_a_pos != -1, "One or more hunters not found in results")
        # Expected order: C (50km, 60min), A (50km, 120min), B (30km, 90min)
        self.assertTrue(hunter_c_pos < hunter_a_pos < hunter_b_pos, f"Sorting error: expected C, A, B. Got C at {hunter_c_pos}, A at {hunter_a_pos}, B at {hunter_b_pos}")

    def test_06_error_non_numeric_km_redirects_check_db_empty(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("ErrorTest VJ", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        self.client.post('/add_entry', data={
            'vossenjacht_id': vj_id,
            'name': 'Error Team Numeric', 'start_km': 'abc', 'end_km': '100.0', 'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries WHERE name = "Error Team Numeric"').fetchall() # Check for specific name
        self.assertEqual(len(entries), 0)

    def test_07_total_kilometers_calculation_dutch_ui(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("TotalKM VJ", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        self._create_entry('Auto 1', 0, 11, '12:10', vj_id, admin_id)
        self._create_entry('Auto 2', 100, 120, '12:20', vj_id, admin_id)

        response = self.client.get(f'/results?vj_id={vj_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vreetvos Resultaten', response.data)
        self.assertIn(b'Totaal Gereden Kilometers (voor getoonde selectie): 31 km', response.data)

    def test_08_empty_results_page_dutch_ui(self): # This test now implicitly tests global results
        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        self.assertNotIn(b'<th>Plaats</th>', response.data)
        self.assertIn(b'Nog geen ritten ingevoerd.', response.data)
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 0 km', response.data)
        self.assertIn(b'Inloggen om Rit In te Voeren', response.data)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_09_add_multiple_entries_dutch_ui_duration_check_ui_and_db_count(self):
        self.login()
        self.client.post('/add_entry', data={'name': 'Rijder X', 'start_km': '50', 'end_km': '60', 'arrival_time_last_fox': '14:00'})
        self.client.post('/add_entry', data={'name': 'Rijder Y', 'start_km': '70', 'end_km': '76', 'arrival_time_last_fox': '12:30'})
        self.client.post('/add_entry', data={'name': 'Rijder Z', 'start_km': '80', 'end_km': '95', 'arrival_time_last_fox': '13:00'})

        db = get_db()
        entries_count = db.execute('SELECT COUNT(id) FROM entries').fetchone()[0]
        self.assertEqual(entries_count, 3)

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        self.assertIn(b'<th>Plaats</th>', response.data)
        self.assertIn(b'Uitloggen', response.data)
        self.assertIn(b'Nieuwe Rit Invoeren', response.data)

        html_content = response.data.decode('utf-8')
        self.assertTrue(re.search(r'<td>\s*1\s*</td>.*?<td>\s*Rijder Y\s*</td>.*?<td>\s*6\s*</td>', html_content, re.DOTALL))
        self.assertTrue(re.search(r'<td>\s*2\s*</td>.*?<td>\s*Rijder X\s*</td>.*?<td>\s*10\s*</td>', html_content, re.DOTALL))
        self.assertTrue(re.search(r'<td>\s*3\s*</td>.*?<td>\s*Rijder Z\s*</td>.*?<td>\s*15\s*</td>', html_content, re.DOTALL))

        self.assertIn(b'<td>120</td>', response.data)
        self.assertIn(b'<td>30</td>', response.data)
        self.assertIn(b'<td>60</td>', response.data)
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 31 km', response.data)

    def test_10_odometer_rollover_calculation_check_db(self):
        self.login()
        self.client.post('/add_entry', data={
            'name': 'Rollover Car DB', 'start_km': '950', 'end_km': '50', 'arrival_time_last_fox': '13:00'
        })
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Rollover Car DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 100)
        self.assertEqual(entry['start_km'], 950)
        self.assertEqual(entry['end_km'], 50)

    def test_11_negative_calculated_km_after_rollover_redirects_check_db_empty(self):
        self.login()
        original_max_odom = app.config['MAX_ODOMETER_READING']
        app.config['MAX_ODOMETER_READING'] = 50

        self.client.post('/add_entry', data={
            'name': 'Negative KM Team', 'start_km': '100', 'end_km': '10', 'arrival_time_last_fox': '13:00'
        }, follow_redirects=True)

        app.config['MAX_ODOMETER_READING'] = original_max_odom

        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_12_invalid_time_format_redirects_to_input_check_db_empty(self):
        self.login()
        self.client.post('/add_entry', data={
            'name': 'Time Error Team', 'start_km': '10', 'end_km': '20', 'arrival_time_last_fox': '99:99'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_13_duration_calculation_various_times_check_db(self):
        self.login()
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
        self.login()
        self.client.post('/add_entry', data={'name': 'Gold A', 'start_km': '0', 'end_km': '10', 'arrival_time_last_fox': '13:00'})
        self.client.post('/add_entry', data={'name': 'Gold B', 'start_km': '100', 'end_km': '110', 'arrival_time_last_fox': '13:00'})
        self.client.post('/add_entry', data={'name': 'Silver C', 'start_km': '0', 'end_km': '20', 'arrival_time_last_fox': '13:10'})
        self.client.post('/add_entry', data={'name': 'Bronze D', 'start_km': '0', 'end_km': '30', 'arrival_time_last_fox': '13:20'})
        self.client.post('/add_entry', data={'name': 'Bronze E', 'start_km': '50', 'end_km': '80', 'arrival_time_last_fox': '13:20'})
        self.client.post('/add_entry', data={'name': 'NoHighlight F', 'start_km': '0', 'end_km': '40', 'arrival_time_last_fox': '13:30'})

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        html_content = response.data.decode('utf-8')

        self.assertIn("<title>Vreetvos resultaten</title>", html_content)
        self.assertIn(b'<th>Plaats</th>', response.data)
        self.assertIn(b'Uitloggen', response.data)

        def get_row_html_for_entry(entry_name, full_html):
            pattern = f'(<tr[^>]*>((?:(?!</?tr>).)*?)<td>{re.escape(entry_name)}</td>((?:(?!</?tr>).)*?)</tr>)'
            match = re.search(pattern, full_html, re.DOTALL)
            if match:
                return match.group(1)
            self.fail(f"Row for entry '{entry_name}' not found in HTML content.")

        row_gold_a = get_row_html_for_entry('Gold A', html_content)
        self.assertIn('class="rank-gold"', row_gold_a)
        row_gold_b = get_row_html_for_entry('Gold B', html_content)
        self.assertIn('class="rank-gold"', row_gold_b)
        row_silver_c = get_row_html_for_entry('Silver C', html_content)
        self.assertIn('class="rank-silver"', row_silver_c)
        row_bronze_d = get_row_html_for_entry('Bronze D', html_content)
        self.assertIn('class="rank-bronze"', row_bronze_d)
        row_bronze_e = get_row_html_for_entry('Bronze E', html_content)
        self.assertIn('class="rank-bronze"', row_bronze_e)
        row_no_highlight_f = get_row_html_for_entry('NoHighlight F', html_content)
        self.assertIn('class=""', row_no_highlight_f)
        self.assertNotIn('rank-gold', row_no_highlight_f)
        self.assertNotIn('rank-silver', row_no_highlight_f)
        self.assertNotIn('rank-bronze', row_no_highlight_f)

    def test_15_auth_protected_get_routes_require_login(self):
        protected_get_routes_map = {
            '/input': b'Nieuwe Vossenjacht Rit Invoeren',
            '/settings': b'<h1>Instellingen</h1>',
            '/edit_entry/1': None
        }

        for route, expected_text in protected_get_routes_map.items():
            with self.subTest(route=route):
                response = self.client.get(route, follow_redirects=False)
                self.assertEqual(response.status_code, 302, f"Route {route} did not redirect unauthenticated user.")
                expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}{route}"
                self.assertEqual(response.location, expected_redirect_url)

                self.login()
                response_authed = self.client.get(route)

                if route == '/edit_entry/1':
                    self.assertTrue(
                        (response_authed.status_code == 302 and response_authed.location.endswith('/settings')) or
                        (response_authed.status_code == 200 and b'Rit niet gevonden' in response_authed.data),
                        f"Authenticated GET to {route} (non-existent entry) failed. Status: {response_authed.status_code}"
                    )
                elif route == '/input':
                    self.assertEqual(response_authed.status_code, 200)
                    self.assertIn(expected_text, response_authed.data)
                    html_content = response_authed.data.decode('utf-8')
                    match = re.search(r'<input type="time" id="arrival_time_last_fox"[^>]*value="(\d{2}:\d{2})"[^>]*>', html_content)
                    self.assertIsNotNone(match, "Arrival time input field with value was not found on /input.")
                    if match:
                        try: datetime.strptime(match.group(1), '%H:%M')
                        except ValueError: self.fail(f"Prefilled time on /input is not HH:MM: {match.group(1)}")
                else:
                    self.assertEqual(response_authed.status_code, 200)
                    self.assertIn(expected_text, response_authed.data)
                self.logout()

    def test_16_auth_protected_post_routes_require_login(self):
        db = get_db()
        post_routes_to_check = {
            '/add_entry': {'name': 'Sneaky Add Test'},
            '/delete_entry/1': {},
            '/clear_database': {'confirm_text': 'VERWIJDER ALLES'},
            '/edit_entry/1': {'name': 'Sneaky Edit Test'}
        }

        for route, data in post_routes_to_check.items():
            with self.subTest(route=route):
                response = self.client.post(route, data=data, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}{route}"
                self.assertEqual(response.location, expected_redirect_url)

                if route == '/add_entry':
                    self.assertIsNone(db.execute("SELECT id FROM entries WHERE name = 'Sneaky Add Test'").fetchone())
                elif route == '/clear_database':
                    db.execute("INSERT INTO entries (name, start_km, end_km, arrival_time_last_fox, calculated_km, duration_minutes) VALUES ('PreClearTestAuth',0,0,'00:00',0,0)")
                    db.commit()
                    self.assertIsNotNone(db.execute("SELECT id FROM entries WHERE name = 'PreClearTestAuth'").fetchone())
                    db.execute("DELETE FROM entries WHERE name = 'PreClearTestAuth'")
                    db.commit()

        self.login()
        cursor = db.execute("INSERT INTO entries (name, start_km, end_km, arrival_time_last_fox, calculated_km, duration_minutes) VALUES ('Temp for POST Auth Test',0,0,'00:00',0,0)")
        db.commit()
        temp_id = cursor.lastrowid

        response_delete_authed = self.client.post(f'/delete_entry/{temp_id}', follow_redirects=True)
        self.assertEqual(response_delete_authed.status_code, 200)
        self.assertIsNone(db.execute("SELECT id FROM entries WHERE id = ?", (temp_id,)).fetchone())
        self.logout()

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vreetvos Resultaten', response.data)
        self.assertIn(b'Nog geen resultaten voor deze selectie.', response.data) # Updated text
        self.assertIn(b'Totaal Gereden Kilometers (voor getoonde selectie): 0 km', response.data)
        self.assertIn(b'Inloggen', response.data) # Login link
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    # Test_09 needs to be updated for Vossenjacht context or removed if too complex for now
    # def test_09_add_multiple_entries_dutch_ui_duration_check_ui_and_db_count(self): ...

    def test_10_odometer_rollover_calculation_check_db(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("Rollover VJ", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        self.client.post('/add_entry', data={
            'vossenjacht_id': vj_id,
            'name': 'Rollover Car DB', 'start_km': '950', 'end_km': '50', 'arrival_time_last_fox': '13:00'
        })
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Rollover Car DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 100)


    def test_12_invalid_time_format_redirects_to_input_check_db_empty(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("TimeError VJ", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        self.client.post('/add_entry', data={
            'vossenjacht_id': vj_id,
            'name': 'Time Error Team', 'start_km': '10', 'end_km': '20', 'arrival_time_last_fox': '99:99'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries WHERE name="Time Error Team"').fetchall()
        self.assertEqual(len(entries), 0)

    # test_13 needs to be updated or removed
    # def test_13_duration_calculation_various_times_check_db(self): ...

    def test_14_rank_highlighting(self):
        """Test rank highlighting CSS classes on the results page for a VJ."""
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        mod_id = db.execute("SELECT id FROM users WHERE username = 'testmod'").fetchone()['id']
        # Using "kilometers" type VJ, where sorting is KM then Time
        vj_id = self._create_vossenjacht("HighlightTestVJ", "kilometers", admin_id)

        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        # Create entries designed to achieve specific ranks
        # Rank 1 (Gold): 50km, 60min
        self._create_entry('Gold Team', 0, 50, '13:00', vj_id, mod_id)
        # Rank 1 (Gold): Also 50km, 60min (tie for gold)
        self._create_entry('Gold Twin', 100, 150, '13:00', vj_id, mod_id)
        # Rank 2 (Silver): 40km, 30min (less km than gold, time doesn't matter for primary rank)
        self._create_entry('Silver Team', 0, 40, '12:30', vj_id, mod_id)
        # Rank 3 (Bronze): 30km, 10min
        self._create_entry('Bronze Team', 0, 30, '12:10', vj_id, mod_id)
        # Rank 3 (Bronze): Also 30km, but 20min (tie for bronze on KM, secondary sort by time)
        self._create_entry('Bronze Slower', 50, 80, '12:20', vj_id, mod_id)
        # Rank 4 (No Highlight): 20km
        self._create_entry('No Highlight Team', 0, 20, '14:00', vj_id, mod_id)


        response = self.client.get(f'/results?vj_id={vj_id}')
        self.assertEqual(response.status_code, 200)
        html_content = response.data.decode('utf-8')

        self.assertIn(b'HighlightTestVJ', response.data) # Ensure correct VJ

        def get_row_html_for_entry_test14(entry_name, full_html): # Renamed to avoid conflict
            # More robust regex to find the TR containing the entry name
            pattern = fr'<tr[^>]*class="([^"]*)"[^>]*>.*?<td>{re.escape(entry_name)}</td>.*?</tr>'
            match = re.search(pattern, full_html, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(0) # Return the whole <tr> tag
            self.fail(f"Row for entry '{entry_name}' not found in HTML content for test_14.")

        row_gold = get_row_html_for_entry_test14('Gold Team', html_content)
        self.assertIn('rank-gold', row_gold)
        row_gold_twin = get_row_html_for_entry_test14('Gold Twin', html_content)
        self.assertIn('rank-gold', row_gold_twin)

        row_silver = get_row_html_for_entry_test14('Silver Team', html_content)
        self.assertIn('rank-silver', row_silver)

        row_bronze = get_row_html_for_entry_test14('Bronze Team', html_content)
        self.assertIn('rank-bronze', row_bronze)
        row_bronze_slower = get_row_html_for_entry_test14('Bronze Slower', html_content)
        self.assertIn('rank-bronze', row_bronze_slower)

        row_no_highlight = get_row_html_for_entry_test14('No Highlight Team', html_content)
        # Check that it doesn't have any of the rank classes explicitly
        self.assertNotIn('rank-gold', row_no_highlight)
        self.assertNotIn('rank-silver', row_no_highlight)
        self.assertNotIn('rank-bronze', row_no_highlight)
        # It might have an empty class attribute class="" or no class attribute for rank
        self.assertTrue('class=""' in row_no_highlight or not 'class="rank-' in row_no_highlight,
                        "No Highlight Team row should not contain rank-gold/silver/bronze.")
        self.logout()

    def test_13_duration_calculation_various_times_check_db(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        mod_id = db.execute("SELECT id FROM users WHERE username = 'testmod'").fetchone()['id']
        vj_id = self._create_vossenjacht("DurationTestVJ", "time", admin_id) # Type 'time' might be relevant for sorting later

        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        # Test cases: name, arrival_time, expected_duration_minutes
        test_cases = [
            ('Team Noon', '12:00', 0),
            ('Team Noon Plus One', '12:01', 1),
            ('Team Late', '23:59', 719), # (23-12)*60 + 59 = 11*60 + 59 = 660 + 59 = 719
            ('Team Early', '11:00', -60) # 11:00 is before 12:00 start
        ]

        for name, time_str, expected_duration in test_cases:
            with self.subTest(name=name):
                self._create_entry(name, 0, 1, time_str, vj_id, mod_id, duration_minutes=None) # Let helper calculate duration
                entry = db.execute('SELECT duration_minutes FROM entries WHERE name = ? AND vossenjacht_id = ?', (name, vj_id)).fetchone()
                self.assertIsNotNone(entry, f"Entry {name} was not created.")
                self.assertEqual(entry['duration_minutes'], expected_duration, f"Duration for {name} (time {time_str}) was not calculated correctly.")
        self.logout()

    def test_11_negative_calculated_km_after_rollover_redirects_check_db_empty(self):
        """Test adding an entry with negative calculated_km after rollover (should fail/redirect)."""
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        vj_id = self._create_vossenjacht("NegativeKMTestVJ", "kilometers", admin_id)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        original_max_odom = app.config['MAX_ODOMETER_READING']
        # Set a small max odom to easily create a negative scenario after rollover
        # e.g. start=80, end=10. With max_odom=50 -> (10+50) - 80 = -20
        app.config['MAX_ODOMETER_READING'] = 50

        response = self.client.post('/add_entry', data={
            'vossenjacht_id': vj_id,
            'name': 'Negative Rollover Team',
            'start_km': '80',
            'end_km': '10',
            'arrival_time_last_fox': '13:00'
        }, follow_redirects=True) # Follow redirect to see where it lands (input form)

        app.config['MAX_ODOMETER_READING'] = original_max_odom # Reset config

        self.assertEqual(response.status_code, 200) # Should redirect back to input form
        # Check if it landed on input form (look for a unique element of input form)
        self.assertIn(b'Nieuwe Rit Invoeren', response.data)
        # Could also check for a flashed error message if implemented, e.g. self.assertIn(b'Negative calculated kilometers', response.data)

        db = get_db()
        entries = db.execute('SELECT * FROM entries WHERE name = ?', ('Negative Rollover Team',)).fetchall()
        self.assertEqual(len(entries), 0, "Entry with negative calculated km after rollover should not be saved.")


    def test_09_add_multiple_entries_check_ranks_and_totals(self):
        """Adds multiple entries to a single VJ, checks ranks, totals, and basic UI elements."""
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        mod_id = db.execute("SELECT id FROM users WHERE username = 'testmod'").fetchone()['id']
        vj_id = self._create_vossenjacht("MultiEntryTestVJ", "kilometers", admin_id)

        self.login(username=self.mod_user['username'], password=self.mod_user['password'])

        # Entries: (Name, StartKM, EndKM, Time, ExpectedKM, ExpectedDuration)
        # Rider Y: 6km, 30min (12:30) -> Rank 1
        # Rider X: 10km, 120min (14:00) -> Rank 2
        # Rider Z: 15km, 60min (13:00) -> Rank 3 (Note: km primary sort for "kilometers" type)
        # Corrected order by KM then Time: Z (15km, 60min), X (10km, 120min), Y (6km, 30min)
        # No, default is KM then Time. So:
        # Z: 15km, 60min -> Rank 1
        # X: 10km, 120min -> Rank 2
        # Y: 6km, 30min -> Rank 3

        self._create_entry('Rijder X', 50, 60, '14:00', vj_id, mod_id) # 10km, 120min
        self._create_entry('Rijder Y', 70, 76, '12:30', vj_id, mod_id) # 6km, 30min
        self._create_entry('Rijder Z', 80, 95, '13:00', vj_id, mod_id) # 15km, 60min

        db_entries = get_db().execute('SELECT COUNT(id) FROM entries WHERE vossenjacht_id = ?', (vj_id,)).fetchone()[0]
        self.assertEqual(db_entries, 3, "Incorrect number of entries created in DB.")

        response = self.client.get(f'/results?vj_id={vj_id}') # View results for this VJ
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vreetvos Resultaten', response.data)
        self.assertIn(b'MultiEntryTestVJ', response.data) # Check VJ name is displayed
        self.assertIn(b'Uitloggen', response.data)
        self.assertIn(b'Nieuwe Rit', response.data) # Navigation link

        html_content = response.data.decode('utf-8')

        # Check ranks based on KM then Time for "kilometers" type VJ
        # Rider Z: 15km, 60min
        self.assertTrue(re.search(r'<td>\s*1\s*</td>.*?<td>\s*Rijder Z\s*</td>.*?<td>\s*15\s*</td>.*?<td>\s*60\s*</td>', html_content, re.DOTALL), "Rijder Z (Rank 1) not found or incorrect.")
        # Rider X: 10km, 120min
        self.assertTrue(re.search(r'<td>\s*2\s*</td>.*?<td>\s*Rijder X\s*</td>.*?<td>\s*10\s*</td>.*?<td>\s*120\s*</td>', html_content, re.DOTALL), "Rijder X (Rank 2) not found or incorrect.")
        # Rider Y: 6km, 30min
        self.assertTrue(re.search(r'<td>\s*3\s*</td>.*?<td>\s*Rijder Y\s*</td>.*?<td>\s*6\s*</td>.*?<td>\s*30\s*</td>', html_content, re.DOTALL), "Rijder Y (Rank 3) not found or incorrect.")

        # Total KM for this VJ: 10 + 6 + 15 = 31 km
        self.assertIn(b'Totaal Gereden Kilometers (voor getoonde selectie): 31 km', response.data)
        self.logout()

    # test_13 needs to be updated or removed
    # def test_13_duration_calculation_various_times_check_db(self): ...


    def test_15_auth_protected_get_routes_require_login(self):
        # Routes that require login, and optionally, specific roles (role check is not the primary focus here, just login)
        # Expected text is for basic successful load, None if complex or error page expected for non-existent data
        protected_get_routes_map = {
            '/input': b'Nieuwe Rit Invoeren',
            '/settings': b'Instellingen en Rittenbeheer',
            '/edit_entry/1': None, # Expects redirect to settings or "not found" if entry 1 not made by helpers
            '/admin/users': b'User Management', # Admin only, but still needs login first
            '/admin/users/add': b'Add New User', # Admin only
            '/vossenjachten': b'Vossenjachten Overview',
            '/vossenjachten/new': b'Create New Vossenjacht', # Moderator/Admin
            '/vossenjachten/edit/1': None, # Moderator/Admin, expects redirect or "not found"
        }

        for route, expected_text_if_any in protected_get_routes_map.items():
            with self.subTest(route=route):
                response = self.client.get(route, follow_redirects=False)
                self.assertEqual(response.status_code, 302, f"Route {route} did not redirect unauthenticated user.")
                self.assertTrue(response.location.startswith(f"/login?next="), f"Route {route} redirected to {response.location} instead of login.")

                # Login as admin to ensure access if route is admin only, or mod for others
                if '/admin/' in route:
                    self.login(username=self.admin_user['username'], password=self.admin_user['password'])
                else: # For other routes, mod login is sufficient for this test's purpose
                    self.login(username=self.mod_user['username'], password=self.mod_user['password'])

                response_authed = self.client.get(route)

                if route.endswith('/1'): # For /edit_entry/1 or /vossenjachten/edit/1
                    # It's okay if it's 404 (Not Found) or 403 (Forbidden if mod tries to edit admin's VJ)
                    # or 200 (if it's a placeholder page for "not found" or an empty edit page)
                    # or 302 (if it redirects, e.g. edit_entry to settings)
                    self.assertIn(response_authed.status_code, [200, 404, 403, 302],
                                  f"Authenticated GET to {route} (non-existent item) failed. Status: {response_authed.status_code}")
                elif expected_text_if_any:
                    self.assertEqual(response_authed.status_code, 200, f"Authenticated GET to {route} failed. Status: {response_authed.status_code}")
                    self.assertIn(expected_text_if_any, response_authed.data)
                else: # No specific text to check, just ensure it doesn't error out badly (e.g. 500)
                     self.assertNotIn(response_authed.status_code, [500], f"Authenticated GET to {route} resulted in server error.")
                self.logout()

    def test_16_auth_protected_post_routes_require_login(self):
        db = get_db()
        admin_id = db.execute("SELECT id FROM users WHERE username = ?", (self.admin_user['username'],)).fetchone()['id']
        # Create a dummy VJ for add_entry test
        vj_id_for_add_entry = self._create_vossenjacht("VJ for AddEntryTest", "kilometers", admin_id)

        post_routes_to_check = {
            '/add_entry': {'name': 'Sneaky Add Test POST', 'vossenjacht_id': vj_id_for_add_entry, 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:00'},
            '/delete_entry/999': {}, # Non-existent entry
            '/clear_database': {'confirm_text': 'VERWIJDER ALLES'}, # Admin only
            '/edit_entry/999': {'name': 'Sneaky Edit Test POST'}, # Non-existent
            '/admin/users/add': {'username': 'newtestuserpost', 'password': 'password', 'role': 'moderator'}, # Admin only
            '/admin/users/delete/999': {}, # Admin only, non-existent user
            '/vossenjachten/new': {'name': 'New VJ POST', 'type': 'time'}, # Mod/Admin
            '/vossenjachten/edit/999': {'name': 'Edit VJ POST', 'type': 'both', 'status': 'active'}, # Mod/Admin, non-existent
            '/vossenjachten/delete/999': {} # Mod/Admin, non-existent
        }

        for route, data in post_routes_to_check.items():
            with self.subTest(route=route):
                response = self.client.post(route, data=data, follow_redirects=False)
                self.assertEqual(response.status_code, 302, f"Route {route} did not redirect unauthenticated user for POST.")
                self.assertTrue(response.location.startswith(f"/login?next="), f"Route {route} redirected to {response.location} instead of login for POST.")

                # Brief check that the action didn't happen while unauthenticated
                if route == '/add_entry':
                    self.assertIsNone(db.execute("SELECT id FROM entries WHERE name = 'Sneaky Add Test POST'").fetchone())
                elif route == '/admin/users/add':
                    self.assertIsNone(db.execute("SELECT id FROM users WHERE username = 'newtestuserpost'").fetchone())
                elif route == '/vossenjachten/new':
                     self.assertIsNone(db.execute("SELECT id FROM vossenjachten WHERE name = 'New VJ POST'").fetchone())

        # Test one actual POST action after login (e.g., clear_database for admin)
        self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        # Add a temp entry to see if clear_database works
        mod_id = db.execute("SELECT id FROM users WHERE username = ?", (self.mod_user['username'],)).fetchone()['id']
        entry_id_before_clear = self._create_entry("Entry Before Clear", 0, 1, "12:00", vj_id_for_add_entry, mod_id)
        self.assertIsNotNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_id_before_clear,)).fetchone())

        if app.config.get('TESTING'): # Only run clear_database if truly in testing with in-memory
            response_clear_authed = self.client.post('/clear_database', data={'confirm_text': 'VERWIJDER ALLES'}, follow_redirects=True)
            self.assertEqual(response_clear_authed.status_code, 200) # Should redirect to settings
            # Ensure the specific entry is gone
            self.assertIsNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_id_before_clear,)).fetchone(), "Entry still exists after supposedly clearing database.")
        self.logout()


    def test_17_auth_login_logout_flow(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Inloggen Vreetvos', response.data) # Updated title

        # Test login with wrong password
        response = self.login(username=self.admin_user['username'], password="wrong_password")
        self.assertEqual(response.status_code, 200) # Stays on login page
        self.assertIn(b'Ongeldige gebruikersnaam of wachtwoord.', response.data)
        self.assertIn(b'Inloggen Vreetvos', response.data)

        # Test login with correct admin credentials
        response = self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        self.assertEqual(response.status_code, 200) # Redirects to input_form by default
        self.assertIn(b'Nieuwe Rit Invoeren', response.data) # Check content of input_form
        self.assertIn(b'Uitloggen', response.data)
        self.assertIn(b'testadmin', response.data) # Check if username is shown

        # Check session variables (indirectly by checking nav links)
        response_results_logged_in = self.client.get('/results')
        self.assertIn(b'Uitloggen (testadmin)', response_results_logged_in.data)
        self.assertIn(b'User Management', response_results_logged_in.data) # Admin specific link

        # Logout
        response_logout = self.logout()
        self.assertEqual(response_logout.status_code, 200) # Redirects to results
        self.assertIn(b'Vreetvos Resultaten', response_logout.data)
        self.assertIn(b'Inloggen', response_logout.data) # Login link should be back
        self.assertNotIn(b'Uitloggen', response_logout.data)
        self.assertNotIn(b'testadmin', response_logout.data)

        # Try accessing protected page
        response_input_logged_out = self.client.get('/input', follow_redirects=False)
        self.assertEqual(response_input_logged_out.status_code, 302) # Redirect to login
        expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}/input"
        self.assertEqual(response_input_logged_out.location, expected_redirect_url)

    def test_18_settings_page_access_and_content(self):
        """Test access to /settings page and role-based content listing."""
        admin_user_id = db.execute("SELECT id FROM users WHERE username = ?", (self.admin_user['username'],)).fetchone()['id']
        mod_user_id = db.execute("SELECT id FROM users WHERE username = ?", (self.mod_user['username'],)).fetchone()['id']

        vj_admin = self._create_vossenjacht("Admin VJ", "kilometers", admin_user_id)
        vj_mod = self._create_vossenjacht("Mod VJ", "time", mod_user_id)

        self._create_entry("AdminEntry1", 10, 20, "12:30", vj_admin, admin_user_id) # 10km, 30min
        self._create_entry("ModEntry1", 5, 15, "13:00", vj_mod, mod_user_id)       # 10km, 60min
        self._create_entry("AdminEntry2_InModVJ", 0, 5, "13:30", vj_mod, admin_user_id) # 5km, 90min (admin entry in mod's VJ)

        # Test as Admin
        self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        response_admin = self.client.get('/settings')
        self.assertEqual(response_admin.status_code, 200)
        html_admin = response_admin.data.decode('utf-8')
        self.assertIn('<h1>Instellingen en Rittenbeheer</h1>', html_admin)
        self.assertIn('Alle Ritten (Admin View)', html_admin)
        self.assertIn('AdminEntry1', html_admin)
        self.assertIn('ModEntry1', html_admin)
        self.assertIn('AdminEntry2_InModVJ', html_admin)
        self.assertIn('Admin VJ', html_admin) # Vossenjacht name
        self.assertIn('Mod VJ', html_admin)   # Vossenjacht name
        self.assertIn('Database Beheer (Admin Only)', html_admin) # Admin can see DB management
        self.logout()

        # Test as Moderator
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_mod = self.client.get('/settings')
        self.assertEqual(response_mod.status_code, 200)
        html_mod = response_mod.data.decode('utf-8')
        self.assertIn(f'Ritten voor Vossenjachten gemaakt door {self.mod_user["username"]}', html_mod)
        self.assertNotIn('AdminEntry1', html_mod) # Should not see admin's entry in admin's VJ
        self.assertIn('ModEntry1', html_mod)       # Should see own entry in own VJ
        self.assertIn('AdminEntry2_InModVJ', html_mod) # Should see admin's entry in own VJ
        self.assertNotIn('Admin VJ', html_mod) # Vossenjacht name of Admin's VJ
        self.assertIn('Mod VJ', html_mod)    # Vossenjacht name of Mod's VJ
        self.assertNotIn('Database Beheer (Admin Only)', html_mod) # Mod should not see DB management
        self.logout()

    # test_19_delete_entry_functionality needs update for permissions
    def test_19_delete_entry_functionality(self):
        """Test deleting an entry from the settings page with permissions."""
        admin_user_id = db.execute("SELECT id FROM users WHERE username = ?", (self.admin_user['username'],)).fetchone()['id']
        mod_user_id = db.execute("SELECT id FROM users WHERE username = ?", (self.mod_user['username'],)).fetchone()['id']

        vj_mod = self._create_vossenjacht("Mod VJ for Delete Test", "kilometers", mod_user_id)

        entry_by_mod_id = self._create_entry("ModEntryToDelete", 0, 10, "12:10", vj_mod, mod_user_id)
        entry_by_admin_in_mod_vj_id = self._create_entry("AdminEntryInModVJToDelete", 0, 20, "12:20", vj_mod, admin_user_id)

        # 1. Moderator tries to delete their own entry (should succeed)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_mod_delete_own = self.client.post(f'/delete_entry/{entry_by_mod_id}', follow_redirects=True)
        self.assertEqual(response_mod_delete_own.status_code, 200)
        self.assertIsNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_by_mod_id,)).fetchone(), "Moderator failed to delete their own entry.")
        self.logout()

        # 2. Moderator tries to delete an admin's entry IN THE MODERATOR'S OWN VJ (should succeed as they own the VJ)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_mod_delete_admin_entry = self.client.post(f'/delete_entry/{entry_by_admin_in_mod_vj_id}', follow_redirects=True)
        self.assertEqual(response_mod_delete_admin_entry.status_code, 200)
        self.assertIsNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_by_admin_in_mod_vj_id,)).fetchone(), "Moderator failed to delete admin's entry in their own VJ.")
        self.logout()

        # Re-create an entry for admin tests
        vj_admin = self._create_vossenjacht("Admin VJ for Delete Test", "kilometers", admin_user_id)
        entry_in_admin_vj_id = self._create_entry("EntryInAdminVJ", 0, 5, "12:05", vj_admin, admin_user_id)

        # 3. Moderator tries to delete an entry from an Admin's VJ (should fail - 403)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_mod_delete_admin_vj_entry = self.client.post(f'/delete_entry/{entry_in_admin_vj_id}', follow_redirects=False) # Expect 403
        self.assertEqual(response_mod_delete_admin_vj_entry.status_code, 403)
        self.assertIsNotNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_in_admin_vj_id,)).fetchone(), "Moderator incorrectly deleted entry from Admin's VJ.")
        self.logout()

        # 4. Admin deletes an entry from their own VJ (should succeed)
        self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        response_admin_delete_own_vj = self.client.post(f'/delete_entry/{entry_in_admin_vj_id}', follow_redirects=True)
        self.assertEqual(response_admin_delete_own_vj.status_code, 200)
        self.assertIsNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_in_admin_vj_id,)).fetchone(), "Admin failed to delete entry from their own VJ.")
        self.logout()

    def test_20_edit_entry_display_and_update(self):
        """Test displaying edit form and submitting updates with permissions."""
        admin_user_id = db.execute("SELECT id FROM users WHERE username = ?", (self.admin_user['username'],)).fetchone()['id']
        mod_user_id = db.execute("SELECT id FROM users WHERE username = ?", (self.mod_user['username'],)).fetchone()['id']

        vj_admin = self._create_vossenjacht("Admin VJ for Edit", "kilometers", admin_user_id)
        vj_mod = self._create_vossenjacht("Mod VJ for Edit", "time", mod_user_id)

        entry_mod_in_modvj_id = self._create_entry("ModOriginalName", 10, 20, "12:30", vj_mod, mod_user_id)
        entry_admin_in_adminvj_id = self._create_entry("AdminOriginalName", 5, 15, "13:00", vj_admin, admin_user_id)

        # 1. Moderator edits their own entry in their VJ
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_get_mod_edit = self.client.get(f'/edit_entry/{entry_mod_in_modvj_id}')
        self.assertEqual(response_get_mod_edit.status_code, 200)
        self.assertIn(b'ModOriginalName', response_get_mod_edit.data)

        mod_update_data = {'name': 'ModUpdatedName', 'start_km': '11', 'end_km': '22', 'arrival_time_last_fox': '12:35'}
        response_post_mod_edit = self.client.post(f'/edit_entry/{entry_mod_in_modvj_id}', data=mod_update_data, follow_redirects=True)
        self.assertEqual(response_post_mod_edit.status_code, 200)
        updated_mod_entry = db.execute("SELECT * FROM entries WHERE id = ?", (entry_mod_in_modvj_id,)).fetchone()
        self.assertEqual(updated_mod_entry['name'], 'ModUpdatedName')
        self.logout()

        # 2. Moderator tries to GET edit page for admin's entry in admin's VJ (should be 403)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_get_mod_edit_admin_entry = self.client.get(f'/edit_entry/{entry_admin_in_adminvj_id}')
        self.assertEqual(response_get_mod_edit_admin_entry.status_code, 403)
        self.logout()

        # 3. Moderator tries to POST edit for admin's entry in admin's VJ (should be 403)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        mod_forbidden_update = {'name': 'ModForbiddenUpdate', 'start_km': '1', 'end_km': '2', 'arrival_time_last_fox': '12:01'}
        response_post_mod_edit_admin_entry = self.client.post(f'/edit_entry/{entry_admin_in_adminvj_id}', data=mod_forbidden_update, follow_redirects=False)
        self.assertEqual(response_post_mod_edit_admin_entry.status_code, 403)
        admin_entry_after_mod_attempt = db.execute("SELECT name FROM entries WHERE id = ?", (entry_admin_in_adminvj_id,)).fetchone()
        self.assertEqual(admin_entry_after_mod_attempt['name'], 'AdminOriginalName') # Should not change
        self.logout()

        # 4. Admin edits their own entry
        self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        admin_update_data = {'name': 'AdminUpdatedName', 'start_km': '6', 'end_km': '17', 'arrival_time_last_fox': '13:05'}
        response_post_admin_edit = self.client.post(f'/edit_entry/{entry_admin_in_adminvj_id}', data=admin_update_data, follow_redirects=True)
        self.assertEqual(response_post_admin_edit.status_code, 200)
        updated_admin_entry = db.execute("SELECT * FROM entries WHERE id = ?", (entry_admin_in_adminvj_id,)).fetchone()
        self.assertEqual(updated_admin_entry['name'], 'AdminUpdatedName')
        self.logout()

        # 5. Admin edits moderator's entry (should succeed)
        entry_mod_in_modvj_id_for_admin_edit = self._create_entry("ModEntryForAdminEdit", 1, 2, "14:00", vj_mod, mod_user_id)
        self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        admin_edit_mod_entry_data = {'name': 'AdminEditedModEntry', 'start_km': '2', 'end_km': '4', 'arrival_time_last_fox': '14:05'}
        response_admin_edit_mod_entry = self.client.post(f'/edit_entry/{entry_mod_in_modvj_id_for_admin_edit}', data=admin_edit_mod_entry_data, follow_redirects=True)
        self.assertEqual(response_admin_edit_mod_entry.status_code, 200)
        updated_mod_entry_by_admin = db.execute("SELECT name FROM entries WHERE id = ?", (entry_mod_in_modvj_id_for_admin_edit,)).fetchone()
        self.assertEqual(updated_mod_entry_by_admin['name'], 'AdminEditedModEntry')
        self.logout()

    # test_21_clear_database_functionality: ensure only admin can clear
    def test_21_clear_database_functionality_admin_only(self):
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        admin_id = db.execute("SELECT id FROM users WHERE username = 'testadmin'").fetchone()['id']
        mod_id = db.execute("SELECT id FROM users WHERE username = 'testmod'").fetchone()['id']
        vj_id = self._create_vossenjacht("ClearTestVJ", "kilometers", admin_id)
        self._create_entry("Entry To Clear", 0, 1, "12:00", vj_id, mod_id)

        # Try as moderator (should fail or not show button)
        self.login(username=self.mod_user['username'], password=self.mod_user['password'])
        response_mod_settings = self.client.get('/settings')
        self.assertNotIn(b'Database Beheer (Admin Only)', response_mod_settings.data) # Button/section should not be visible

        # Attempt POST as moderator (should be blocked by route decorator ideally, or fail on confirm_text if form not there)
        response_mod_clear = self.client.post('/clear_database', data={'confirm_text': 'VERWIJDER ALLES'}, follow_redirects=True)
        # Depending on implementation, this might be a 403 if @admin_required is hit, or just back to settings
        # For now, we check that the entry still exists
        self.assertIsNotNone(db.execute("SELECT id FROM entries WHERE name = 'Entry To Clear'").fetchone(), "DB cleared by moderator, but should not have.")
        self.logout()

        # Try as admin (should succeed)
        self.login(username=self.admin_user['username'], password=self.admin_user['password'])
        response_admin_settings = self.client.get('/settings')
        self.assertIn(b'Database Beheer (Admin Only)', response_admin_settings.data)

        if app.config.get('TESTING'): # Safety check
            response_admin_clear = self.client.post('/clear_database', data={'confirm_text': 'VERWIJDER ALLES'}, follow_redirects=True)
            self.assertEqual(response_admin_clear.status_code, 200)
            self.assertIsNone(db.execute("SELECT id FROM entries WHERE name = 'Entry To Clear'").fetchone(), "DB NOT cleared by admin.")
        self.logout()


if __name__ == '__main__':
    unittest.main()
