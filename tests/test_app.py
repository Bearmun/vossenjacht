import unittest
import sys
import os

# Add the parent directory to the Python path to allow module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, hunt_entries # MAX_ODOMETER_READING removed

class FoxHuntTrackerTests(unittest.TestCase):

    def setUp(self):
        """Set up test client and clear hunt_entries before each test."""
        self.app = app.test_client()
        self.app.testing = True
        hunt_entries.clear()
        # Ensure MAX_ODOMETER_READING is consistent for tests, can be overridden per test if needed
        self.app.application.config['MAX_ODOMETER_READING'] = 1000.0


    def test_01_index_redirects_to_results(self):
        """Test that the index route '/' redirects to '/results'."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/results', response.location)

    def test_02_input_route_loads_dutch(self):
        """Test that the '/input' route loads successfully with Dutch text."""
        response = self.app.get('/input')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data)
        self.assertIn(b'Naam:', response.data)
        self.assertIn(b'Begin Kilometerstand:', response.data)
        self.assertIn(b'Eind Kilometerstand:', response.data)
        self.assertIn(b'Aankomsttijd Laatste Vos (UU:MM):', response.data)
        self.assertIn(b'Rit Opslaan', response.data)
        self.assertIn(b'Bekijk Resultaten', response.data)

    def test_03_add_valid_entry_dutch_ui_and_duration(self):
        """Test adding a single valid entry and check Dutch UI, data, and duration."""
        response = self.app.post('/add_entry', data={
            'name': 'Team Alfa',
            'start_km': '100.0',
            'end_km': '150.5',
            'arrival_time_last_fox': '13:00' # 60 minutes from 12:00
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        # Check for Dutch text on results page
        self.assertIn(b'Vossenjacht Resultaten', response.data)
        self.assertIn(b'Team Alfa', response.data)
        self.assertIn(b'100.0', response.data)
        self.assertIn(b'150.5', response.data)
        self.assertIn(b'50.5', response.data) # calculated_km
        self.assertIn(b'13:00', response.data) # arrival_time_last_fox
        self.assertIn(b'Duur (minuten)', response.data) # Duration column header
        self.assertIn(b'60', response.data) # duration_minutes

        self.assertEqual(len(hunt_entries), 1)
        entry = hunt_entries[0]
        self.assertEqual(entry['name'], 'Team Alfa')
        self.assertEqual(entry['calculated_km'], 50.5)
        self.assertEqual(entry['duration_minutes'], 60)
        self.assertEqual(entry['arrival_time_last_fox'], '13:00')


    def test_04_kilometer_calculation_direct(self): # Renamed for clarity
        """Test the calculated_km is correct (no rollover)."""
        self.app.post('/add_entry', data={
            'name': 'Team Bravo', 'start_km': '200.3', 'end_km': '210.7', 'arrival_time_last_fox': '12:30'
        })
        self.assertEqual(len(hunt_entries), 1)
        self.assertEqual(hunt_entries[0]['calculated_km'], 10.4)
        self.assertEqual(hunt_entries[0]['duration_minutes'], 30)

    def test_05_sorting_logic_km_then_duration(self):
        """Test sorting: 1st by KM (asc), 2nd by Duration (asc)."""
        # Hunter B (30km, 90min)
        self.app.post('/add_entry', data={'name': 'Hunter B', 'start_km': '0.0', 'end_km': '30.0', 'arrival_time_last_fox': '13:30'})
        # Hunter A (50km, 120min)
        self.app.post('/add_entry', data={'name': 'Hunter A', 'start_km': '0.0', 'end_km': '50.0', 'arrival_time_last_fox': '14:00'})
        # Hunter C (50km, 60min)
        self.app.post('/add_entry', data={'name': 'Hunter C', 'start_km': '0.0', 'end_km': '50.0', 'arrival_time_last_fox': '13:00'})

        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)
        data_str = response.data.decode('utf-8')

        hunter_b_pos = data_str.find('Hunter B') # 30km, 90min
        hunter_c_pos = data_str.find('Hunter C') # 50km, 60min
        hunter_a_pos = data_str.find('Hunter A') # 50km, 120min

        self.assertTrue(hunter_b_pos != -1 and hunter_c_pos != -1 and hunter_a_pos != -1, "All hunters should be present")
        self.assertTrue(hunter_b_pos < hunter_c_pos < hunter_a_pos, "Entries are not sorted correctly (B, C, A)")

    def test_06_error_non_numeric_km_redirects_to_input(self): # Was test_07
        """Test error handling for non-numeric kilometer input."""
        response = self.app.post('/add_entry', data={
            'name': 'Error Team Numeric', 'start_km': 'abc', 'end_km': '100.0', 'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data) # Check redirect to input page (Dutch)
        self.assertEqual(len(hunt_entries), 0)

    def test_07_total_kilometers_calculation_dutch_ui(self): # Was test_08
        """Test total kilometers calculation with Dutch UI."""
        self.app.post('/add_entry', data={'name': 'Auto 1', 'start_km': '0.0', 'end_km': '10.5', 'arrival_time_last_fox': '12:10'}) # 10.5 km
        self.app.post('/add_entry', data={'name': 'Auto 2', 'start_km': '100.0', 'end_km': '120.3', 'arrival_time_last_fox': '12:20'}) # 20.3 km

        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 30.8 km', response.data) # Dutch text

    def test_08_empty_results_page_dutch_ui(self): # Was test_09
        """Test the results page when no entries are submitted with Dutch UI."""
        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nog geen ritten ingevoerd.', response.data) # Dutch text
        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 0 km', response.data) # Dutch text, 0 km

    def test_09_add_multiple_entries_dutch_ui_duration(self): # Was test_10
        """Test adding multiple entries, check Dutch UI, display, total KM, duration."""
        self.app.post('/add_entry', data={'name': 'Rijder X', 'start_km': '50.0', 'end_km': '60.0', 'arrival_time_last_fox': '14:00'}) # 10km, 120min
        self.app.post('/add_entry', data={'name': 'Rijder Y', 'start_km': '70.0', 'end_km': '75.5', 'arrival_time_last_fox': '12:30'}) # 5.5km, 30min
        self.app.post('/add_entry', data={'name': 'Rijder Z', 'start_km': '80.0', 'end_km': '95.0', 'arrival_time_last_fox': '13:00'}) # 15km, 60min

        self.assertEqual(len(hunt_entries), 3)
        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)

        self.assertIn(b'Rijder X', response.data)
        self.assertIn(b'10.0', response.data) # calculated_km for X
        self.assertIn(b'120', response.data) # duration_minutes for X (14:00)

        self.assertIn(b'Rijder Y', response.data)
        self.assertIn(b'5.5', response.data) # calculated_km for Y
        self.assertIn(b'30', response.data)  # duration_minutes for Y (12:30)

        self.assertIn(b'Rijder Z', response.data)
        self.assertIn(b'15.0', response.data) # calculated_km for Z
        self.assertIn(b'60', response.data)  # duration_minutes for Z (13:00)

        self.assertIn(b'Totaal Aantal Gereden Kilometers (iedereen): 30.5 km', response.data) # Dutch

    def test_10_odometer_rollover_calculation(self):
        """Test kilometer calculation with odometer rollover."""
        # MAX_ODOMETER_READING is 1000.0 by default from setUp
        self.app.post('/add_entry', data={
            'name': 'Rollover Car', 'start_km': '950.0', 'end_km': '50.0', 'arrival_time_last_fox': '13:00'
        }) # Expected: (50.0 + 1000.0) - 950.0 = 100.0 km
        self.assertEqual(len(hunt_entries), 1)
        self.assertEqual(hunt_entries[0]['calculated_km'], 100.0)
        self.assertEqual(hunt_entries[0]['name'], 'Rollover Car')
        self.assertEqual(hunt_entries[0]['start_km'], 950.0) # Original start_km stored
        self.assertEqual(hunt_entries[0]['end_km'], 50.0)   # Original end_km stored

    def test_11_negative_calculated_km_after_rollover_redirects(self):
        """Test redirect if calculated_km is negative after rollover adjustment."""
        # This happens if MAX_ODOMETER_READING is too small for the jump or data is inconsistent.
        # Example: start=100, end=10. MAX_ODOMETER_READING=50. actual_end = 10+50=60. calculated = 60-100 = -40.
        original_max_odom = self.app.application.config['MAX_ODOMETER_READING']
        self.app.application.config['MAX_ODOMETER_READING'] = 50.0 # Temporarily set for this test

        response = self.app.post('/add_entry', data={
            'name': 'Negative KM Team', 'start_km': '100.0', 'end_km': '10.0', 'arrival_time_last_fox': '13:00'
        }, follow_redirects=True)

        self.app.application.config['MAX_ODOMETER_READING'] = original_max_odom # Reset

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data) # Should redirect to input
        self.assertEqual(len(hunt_entries), 0) # No entry should be added

    def test_12_invalid_time_format_redirects_to_input(self):
        """Test that invalid time format for arrival_time_last_fox redirects to input."""
        response = self.app.post('/add_entry', data={
            'name': 'Time Error Team', 'start_km': '10.0', 'end_km': '20.0', 'arrival_time_last_fox': '99:99' # Invalid time
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Nieuwe Vossenjacht Rit Invoeren', response.data) # Check redirect to input page
        self.assertEqual(len(hunt_entries), 0) # No entry should be added

    def test_13_duration_calculation_various_times(self):
        """Test duration calculation for various arrival times."""
        # 12:00 arrival -> 0 minutes
        self.app.post('/add_entry', data={'name': 'Team Noon', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:00'})
        self.assertEqual(hunt_entries[-1]['duration_minutes'], 0)
        # 12:01 arrival -> 1 minute
        self.app.post('/add_entry', data={'name': 'Team Noon Plus One', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '12:01'})
        self.assertEqual(hunt_entries[-1]['duration_minutes'], 1)
        # 23:59 arrival -> (23-12)*60 + 59 = 11*60 + 59 = 660 + 59 = 719 minutes
        self.app.post('/add_entry', data={'name': 'Team Late', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '23:59'})
        self.assertEqual(hunt_entries[-1]['duration_minutes'], 719)
        # Test with time that would be negative if not handled (e.g. 11:00, currently allowed by app.py logic, results in negative duration)
        # The problem description implies start is 12:00, so arrival before is unlikely/error.
        # Current app.py logic: duration_delta = arrival_dt - start_dt. If arrival_dt < start_dt, duration_minutes is negative.
        self.app.post('/add_entry', data={'name': 'Team Early', 'start_km': '0', 'end_km': '1', 'arrival_time_last_fox': '11:00'})
        self.assertEqual(hunt_entries[-1]['duration_minutes'], -60) # 11:00 is 60 mins before 12:00


if __name__ == '__main__':
    unittest.main()
