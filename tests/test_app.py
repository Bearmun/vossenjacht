import unittest
import sys
import os

import re # Added re
from datetime import datetime # Ensure datetime is imported

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
            "MAX_ODOMETER_READING": 1000, # Ensure integer
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
            'name': 'Team Alfa DB', 'start_km': '100', 'end_km': '150', 'arrival_time_last_fox': '13:00' # KM as int
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)

        html_content = response.data.decode('utf-8')
        self.assertIn(b'Vreetvos resultaten', response.data) # Check h1
        self.assertIn(b'Team Alfa DB', response.data)
        self.assertIn(b'<td>1</td>', response.data) # Rank
        self.assertIn(b'<td>50</td>', response.data) # calculated_km (150-100 = 50)
        self.assertIn(b'<td>60</td>', response.data)   # duration_minutes
        self.assertIn(b'<td>100</td>', response.data) # start_km
        self.assertIn(b'<td>150</td>', response.data) # end_km
        self.assertIn(b'<td>13:00</td>', response.data) # arrival_time_last_fox
        self.assertIn(b'class="rank-gold"', response.data) # Should be rank 1, so gold

        db = get_db()
        cursor = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Alfa DB',))
        entry_from_db = cursor.fetchone()
        self.assertIsNotNone(entry_from_db)
        self.assertEqual(entry_from_db['calculated_km'], 50)
        self.assertEqual(entry_from_db['start_km'], 100)
        self.assertEqual(entry_from_db['end_km'], 150)
        self.assertEqual(entry_from_db['duration_minutes'], 60)

    def test_04_kilometer_calculation_direct_check_db(self):
        self.login()
        self.client.post('/add_entry', data={
            'name': 'Team Bravo DB', 'start_km': '200', 'end_km': '210', 'arrival_time_last_fox': '12:30'
        })
        db = get_db()
        entry = db.execute('SELECT * FROM entries WHERE name = ?', ('Team Bravo DB',)).fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['calculated_km'], 10)
        self.assertEqual(entry['start_km'], 200)
        self.assertEqual(entry['end_km'], 210)
        self.assertEqual(entry['duration_minutes'], 30)

    def test_05_sorting_logic_km_then_duration_check_ui(self):
        self.login()
        self.client.post('/add_entry', data={'name': 'Hunter B', 'start_km': '0', 'end_km': '30', 'arrival_time_last_fox': '13:30'})
        self.client.post('/add_entry', data={'name': 'Hunter A', 'start_km': '0', 'end_km': '50', 'arrival_time_last_fox': '14:00'})
        self.client.post('/add_entry', data={'name': 'Hunter C', 'start_km': '0', 'end_km': '50', 'arrival_time_last_fox': '13:00'})

        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
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
        self.login()
        self.client.post('/add_entry', data={
            'name': 'Error Team Numeric', 'start_km': 'abc', 'end_km': '100.0', 'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        db = get_db()
        entries = db.execute('SELECT * FROM entries').fetchall()
        self.assertEqual(len(entries), 0)

    def test_07_total_kilometers_calculation_dutch_ui(self):
        self.login()
        self.client.post('/add_entry', data={'name': 'Auto 1', 'start_km': '0', 'end_km': '11', 'arrival_time_last_fox': '12:10'})
        self.client.post('/add_entry', data={'name': 'Auto 2', 'start_km': '100', 'end_km': '120', 'arrival_time_last_fox': '12:20'})
        response = self.client.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<title>Vreetvos resultaten</title>', response.data)
        self.assertIn(b'<th>Plaats</th>', response.data)
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 31 km', response.data)

    def test_08_empty_results_page_dutch_ui(self):
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

    def test_17_auth_login_logout_flow(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Inloggen voor Rit Invoer', response.data)

        response = self.login(password="wrong_password")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ongeldig wachtwoord. Probeer opnieuw.', response.data)
        self.assertIn(b'Inloggen voor Rit Invoer', response.data)

        response = self.login(password="test_password")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data)
        self.assertIn(b'Uitloggen', response.data)

        response = self.client.get('/results')
        self.assertIn(b'Uitloggen', response.data)
        self.assertIn(b'Nieuwe Rit Invoeren', response.data)

        response = self.logout()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vreetvos resultaten', response.data)
        self.assertIn(b'Inloggen om Rit In te Voeren', response.data)
        self.assertNotIn(b'Uitloggen', response.data)

        response = self.client.get('/input', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        expected_redirect_url = f"/login?next=http://{app.config['SERVER_NAME']}/input"
        self.assertEqual(response.location, expected_redirect_url)

    # New tests for Settings Page Functionalities start from test_18
    def test_18_settings_page_access_and_content(self):
        """Test access to /settings page and basic content listing."""
        self.login()
        # Add some entries
        self.client.post('/add_entry', data={'name': 'Entry One', 'start_km': '10', 'end_km': '20', 'arrival_time_last_fox': '12:30'}) # 10km, 30min
        self.client.post('/add_entry', data={'name': 'Entry Two', 'start_km': '20', 'end_km': '40', 'arrival_time_last_fox': '13:00'}) # 20km, 60min

        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        html_content = response.data.decode('utf-8')

        self.assertIn('<h1>Instellingen</h1>', html_content)
        self.assertIn('Entry One', html_content)
        self.assertIn('Entry Two', html_content)
        self.assertIn('<td>10</td>', html_content) # Calc KM for Entry One
        self.assertIn('<td>20</td>', html_content) # Calc KM for Entry Two

        # Check for Edit and Delete actions (presence of forms/links)
        self.assertTrue(re.search(fr"href=\"[^\"]*/edit_entry/\d+\".*?>Bewerk</a>", html_content))
        self.assertTrue(re.search(fr"<form method=\"POST\" action=\"[^\"]*/delete_entry/\d+\".*?>", html_content))
        self.assertIn('Verwijder Alle Ritten Definitief', html_content) # Button for clear all

    def test_19_delete_entry_functionality(self):
        """Test deleting an entry from the settings page."""
        self.login()
        # Add an entry
        self.client.post('/add_entry', data={'name': 'ToDelete', 'start_km': '100', 'end_km': '110', 'arrival_time_last_fox': '12:05'})

        db = get_db()
        entry_to_delete = db.execute("SELECT id FROM entries WHERE name = 'ToDelete'").fetchone()
        self.assertIsNotNone(entry_to_delete, "Entry to delete was not added.")
        entry_id = entry_to_delete['id']

        # Delete the entry
        response = self.client.post(f'/delete_entry/{entry_id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to /settings
        self.assertIn(b'<h1>Instellingen</h1>', response.data) # Check we are on settings page

        # Verify entry is gone from DB and UI
        self.assertIsNone(db.execute("SELECT id FROM entries WHERE id = ?", (entry_id,)).fetchone(), "Entry was not deleted from DB.")
        self.assertNotIn(b'ToDelete', response.data, "Deleted entry name still found on settings page.")

        # Test deleting non-existent entry
        response_non_existent = self.client.post('/delete_entry/99999', follow_redirects=True)
        self.assertEqual(response_non_existent.status_code, 200) # Should redirect to settings
        self.assertIn(b'<h1>Instellingen</h1>', response_non_existent.data) # Stays on settings

    def test_20_edit_entry_display_and_update(self):
        """Test displaying the edit form and submitting updates."""
        self.login()
        # Add an entry to edit
        self.client.post('/add_entry', data={'name': 'Original Name', 'start_km': '10', 'end_km': '20', 'arrival_time_last_fox': '12:30'}) # 10km, 30min
        db = get_db()
        original_entry = db.execute("SELECT * FROM entries WHERE name = 'Original Name'").fetchone()
        self.assertIsNotNone(original_entry)
        entry_id = original_entry['id']

        # Test GET /edit_entry/<id>
        response_get_edit = self.client.get(f'/edit_entry/{entry_id}')
        self.assertEqual(response_get_edit.status_code, 200)
        html_get = response_get_edit.data.decode('utf-8')
        self.assertIn('<h1>Bewerk Rit</h1>', html_get)
        self.assertIn('value="Original Name"', html_get)
        self.assertIn('value="10"', html_get) # start_km
        self.assertIn('value="20"', html_get) # end_km
        self.assertIn('value="12:30"', html_get) # arrival_time

        # Test POST /edit_entry/<id> (Successful Update)
        updated_data = {
            'name': 'Updated Name', 'start_km': '15', 'end_km': '30', # 15km
            'arrival_time_last_fox': '13:00' # 60min
        }
        response_post_edit = self.client.post(f'/edit_entry/{entry_id}', data=updated_data, follow_redirects=True)
        self.assertEqual(response_post_edit.status_code, 200) # Redirects to settings
        self.assertIn(b'<h1>Instellingen</h1>', response_post_edit.data)

        updated_entry_db = db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        self.assertEqual(updated_entry_db['name'], 'Updated Name')
        self.assertEqual(updated_entry_db['start_km'], 15)
        self.assertEqual(updated_entry_db['end_km'], 30)
        self.assertEqual(updated_entry_db['calculated_km'], 15) # (30-15)
        self.assertEqual(updated_entry_db['duration_minutes'], 60) # 13:00 from 12:00
        self.assertIn(b'Updated Name', response_post_edit.data) # Check if new name is on settings page

        # Test POST with data causing negative calculated_km (should redirect back to edit page)
        # We need to adjust MAX_ODOMETER_READING for this specific sub-test to reliably cause negative calculated_km
        original_max_odom = app.config['MAX_ODOMETER_READING']
        app.config['MAX_ODOMETER_READING'] = 50 # e.g. start 100, end 10. (10+50)-100 = -40
        invalid_data_neg_km = {'name': 'Negative Test', 'start_km': '100', 'end_km': '10', 'arrival_time_last_fox': '12:10'}
        response_neg_km = self.client.post(f'/edit_entry/{entry_id}', data=invalid_data_neg_km, follow_redirects=False)
        app.config['MAX_ODOMETER_READING'] = original_max_odom # Reset
        self.assertEqual(response_neg_km.status_code, 302) # Should redirect
        self.assertTrue(response_neg_km.location.endswith(f'/edit_entry/{entry_id}')) # Back to edit page

        # Test GET /edit_entry for non-existent ID
        response_non_existent_get = self.client.get('/edit_entry/99999', follow_redirects=True)
        # For a non-existent entry, edit_entry route redirects to settings
        self.assertEqual(response_non_existent_get.status_code, 200)
        self.assertTrue(response_non_existent_get.request.path.endswith('/settings')) # Check actual path after redirect
        self.assertIn(b'<h1>Instellingen</h1>', response_non_existent_get.data)


    def test_21_clear_database_functionality(self):
        """Test clearing the entire database from the settings page."""
        self.login()
        # Add some entries
        self.client.post('/add_entry', data={'name': 'Entry A', 'start_km': '1', 'end_km': '2', 'arrival_time_last_fox': '12:01'})
        self.client.post('/add_entry', data={'name': 'Entry B', 'start_km': '1', 'end_km': '3', 'arrival_time_last_fox': '12:02'})

        db = get_db()
        self.assertEqual(len(db.execute("SELECT * FROM entries").fetchall()), 2)

        # Test Clear Attempt (Incorrect Confirmation)
        response_fail_clear = self.client.post('/clear_database', data={'confirm_text': 'WRONG TEXT'}, follow_redirects=True)
        self.assertEqual(response_fail_clear.status_code, 200) # Redirects to settings
        self.assertEqual(len(db.execute("SELECT * FROM entries").fetchall()), 2, "DB should not be cleared with wrong confirm text.")

        # Test Clear Attempt (Correct Confirmation)
        response_clear = self.client.post('/clear_database', data={'confirm_text': 'VERWIJDER ALLES'}, follow_redirects=True)
        self.assertEqual(response_clear.status_code, 200) # Redirects to settings
        self.assertIn(b'Geen ritten in de database.', response_clear.data)
        self.assertEqual(len(db.execute("SELECT * FROM entries").fetchall()), 0, "DB should be empty after correct clear.")


if __name__ == '__main__':
    unittest.main()
