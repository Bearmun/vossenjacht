import unittest
import sys
import os

# Add the parent directory to the Python path to allow module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, hunt_entries

class FoxHuntTrackerTests(unittest.TestCase):

    def setUp(self):
        """Set up test client and clear hunt_entries before each test."""
        self.app = app.test_client()
        self.app.testing = True
        # Clear the global list before each test
        hunt_entries.clear()

    def test_01_index_redirects_to_results(self):
        """Test that the index route '/' redirects to '/results'."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/results', response.location)

    def test_02_input_route_loads(self):
        """Test that the '/input' route loads successfully."""
        response = self.app.get('/input')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Add New Fox Hunt Entry', response.data)

    def test_03_add_valid_entry(self):
        """Test adding a single valid entry."""
        response = self.app.post('/add_entry', data={
            'name': 'Team A',
            'start_km': '100.0',
            'end_km': '150.5',
            'arrival_time_last_fox': '10:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Team A', response.data)
        self.assertIn(b'100.0', response.data)
        self.assertIn(b'150.5', response.data)
        self.assertIn(b'50.5', response.data) # calculated_km
        self.assertIn(b'10:00', response.data)
        self.assertEqual(len(hunt_entries), 1)
        self.assertEqual(hunt_entries[0]['name'], 'Team A')
        self.assertEqual(hunt_entries[0]['calculated_km'], 50.5)

    def test_04_kilometer_calculation(self):
        """Test the calculated_km is correct."""
        self.app.post('/add_entry', data={
            'name': 'Team B',
            'start_km': '200.3',
            'end_km': '210.7', # Difference = 10.4
            'arrival_time_last_fox': '11:00'
        })
        self.assertEqual(len(hunt_entries), 1)
        self.assertEqual(hunt_entries[0]['calculated_km'], 10.4)

    def test_05_sorting_logic(self):
        """Test that entries are sorted correctly on the results page."""
        # Entry 1: Lower KM, Earlier Time
        self.app.post('/add_entry', data={
            'name': 'Team Alpha', 'start_km': '10.0', 'end_km': '20.0', 'arrival_time_last_fox': '09:00' # 10km
        })
        # Entry 2: Higher KM
        self.app.post('/add_entry', data={
            'name': 'Team Beta', 'start_km': '10.0', 'end_km': '30.0', 'arrival_time_last_fox': '10:00' # 20km
        })
        # Entry 3: Lower KM, Later Time
        self.app.post('/add_entry', data={
            'name': 'Team Gamma', 'start_km': '10.0', 'end_km': '20.0', 'arrival_time_last_fox': '09:30' # 10km
        })

        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)

        # Expected order: Team Alpha (10km, 09:00), Team Gamma (10km, 09:30), Team Beta (20km, 10:00)
        # The names appear in the response data in the order they are rendered.
        data_str = response.data.decode('utf-8')

        # Find indices of team names
        alpha_pos = data_str.find('Team Alpha')
        gamma_pos = data_str.find('Team Gamma')
        beta_pos = data_str.find('Team Beta')

        self.assertTrue(alpha_pos != -1 and gamma_pos != -1 and beta_pos != -1, "All team names should be present")
        self.assertTrue(alpha_pos < gamma_pos < beta_pos, "Entries are not sorted correctly by KM then time")

    def test_06_error_end_km_less_than_start_km(self):
        """Test error handling when end_km is less than start_km."""
        response = self.app.post('/add_entry', data={
            'name': 'Error Team',
            'start_km': '150.0',
            'end_km': '100.0', # Invalid
            'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to input form
        self.assertIn(b'Add New Fox Hunt Entry', response.data) # Check if it's the input page
        self.assertEqual(len(hunt_entries), 0) # No entry should be added

    def test_07_error_non_numeric_km(self):
        """Test error handling for non-numeric kilometer input."""
        response = self.app.post('/add_entry', data={
            'name': 'Error Team Numeric',
            'start_km': 'abc', # Invalid
            'end_km': '100.0',
            'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to input form
        self.assertIn(b'Add New Fox Hunt Entry', response.data) # Check if it's the input page
        self.assertEqual(len(hunt_entries), 0) # No entry should be added

        response = self.app.post('/add_entry', data={
            'name': 'Error Team Numeric 2',
            'start_km': '10.0',
            'end_km': 'xyz', # Invalid
            'arrival_time_last_fox': '12:00'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Add New Fox Hunt Entry', response.data)
        self.assertEqual(len(hunt_entries), 0)

    def test_08_total_kilometers_calculation(self):
        """Test the total kilometers calculation on the results page."""
        self.app.post('/add_entry', data={'name': 'Car 1', 'start_km': '0.0', 'end_km': '10.5', 'arrival_time_last_fox': '08:00'}) # 10.5 km
        self.app.post('/add_entry', data={'name': 'Car 2', 'start_km': '100.0', 'end_km': '120.3', 'arrival_time_last_fox': '08:30'}) # 20.3 km

        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)
        # Total = 10.5 + 20.3 = 30.8
        self.assertIn(b'Total Kilometers Driven by All: 30.8 km', response.data)

    def test_09_empty_results_page(self):
        """Test the results page when no entries are submitted."""
        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No entries submitted yet.', response.data)
        self.assertIn(b'Total Kilometers Driven by All: 0 km', response.data)

    def test_10_add_multiple_entries_and_check_display_and_total_km(self):
        """Test adding multiple entries and verify they are all displayed and total KM is correct."""
        self.app.post('/add_entry', data={'name': 'Driver X', 'start_km': '50.0', 'end_km': '60.0', 'arrival_time_last_fox': '14:00'}) # 10km
        self.app.post('/add_entry', data={'name': 'Driver Y', 'start_km': '70.0', 'end_km': '75.5', 'arrival_time_last_fox': '14:30'}) # 5.5km
        self.app.post('/add_entry', data={'name': 'Driver Z', 'start_km': '80.0', 'end_km': '95.0', 'arrival_time_last_fox': '13:00'}) # 15km

        self.assertEqual(len(hunt_entries), 3)

        response = self.app.get('/results')
        self.assertEqual(response.status_code, 200)

        # Check for all entries' data
        self.assertIn(b'Driver X', response.data)
        self.assertIn(b'60.0', response.data) # end_km for X
        self.assertIn(b'10.0', response.data) # calculated_km for X

        self.assertIn(b'Driver Y', response.data)
        self.assertIn(b'75.5', response.data) # end_km for Y
        self.assertIn(b'5.5', response.data) # calculated_km for Y

        self.assertIn(b'Driver Z', response.data)
        self.assertIn(b'95.0', response.data) # end_km for Z
        self.assertIn(b'15.0', response.data) # calculated_km for Z

        # Total KM = 10 + 5.5 + 15 = 30.5
        self.assertIn(b'Total Kilometers Driven by All: 30.5 km', response.data)


if __name__ == '__main__':
    unittest.main()
