import unittest
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class IndigoInputTests(unittest.TestCase):
    BASE_URL = "https://6epartner-preprod.goindigo.in/"  # Replace with actual URL

    @classmethod
    def setUpClass(cls):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        cls.driver = webdriver.Chrome(options=options)
        cls.wait = WebDriverWait(cls.driver, 15)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def setUp(self):
        self.driver.get(self.BASE_URL)
        # Wait for the booking form to render
        self.wait.until(EC.presence_of_element_located(
            (By.XPATH, "//*[@id='radio-input-triptype-oneWay']"))
        )
        time.sleep(1)  # brief pause for any remaining React rendering

    def test_select_trip_type_radio_buttons(self):
        """Verify that each trip-type radio button can be selected."""
        # One Way
        oneway = self.driver.find_element(By.XPATH, "//*[@id='radio-input-triptype-oneWay']")
        oneway.click()
        self.assertTrue(oneway.is_selected(), "One-way radio button should be selected.")

        # Round Trip
        roundtrip = self.driver.find_element(By.XPATH, "//*[@id='radio-input-triptype-roundTrip']")
        roundtrip.click()
        self.assertTrue(roundtrip.is_selected(), "Round-trip radio button should be selected.")
        self.assertFalse(oneway.is_selected(), "One-way should be deselected when Round-trip is selected.")

        # Multi City
        multicity = self.driver.find_element(By.XPATH, "//*[@id='radio-input-triptype-multiCity']")
        multicity.click()
        self.assertTrue(multicity.is_selected(), "Multi-city radio button should be selected.")
        self.assertFalse(roundtrip.is_selected(), "Round-trip should be deselected when Multi-city is selected.")

    def test_fill_source_and_destination_iata(self):
        """Fill Source and Destination inputs using IATA codes and verify correctness."""
        # Source (IATA)
        src_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[1]/div[1]/input[1]"
        )
        self.assertEqual(src_input.get_attribute("aria-label"), "sourceCity")
        src_input.clear()
        src_input.send_keys("DEL")  # New Delhi IATA
        src_input.send_keys(Keys.ENTER)
        time.sleep(1)
        self.assertIn("DEL", src_input.get_attribute("value"))

        # Destination (IATA)
        dest_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[2]/div[1]/input[1]"
        )
        self.assertEqual(dest_input.get_attribute("aria-label"), "destinationCity")
        dest_input.clear()
        dest_input.send_keys("BOM")  # Mumbai IATA
        dest_input.send_keys(Keys.ENTER)
        time.sleep(1)
        self.assertIn("BOM", dest_input.get_attribute("value"))

    def test_fill_departure_and_arrival_dates(self):
        """Fill Departure and Arrival date inputs and verify the entered values."""
        # Departure Date
        dep_date_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[3]/div[1]/input[1]"
        )
        self.assertEqual(dep_date_input.get_attribute("aria-label"), "departureDate")
        dep_date_input.click()
        dep_date_input.clear()
        dep_date_input.send_keys("30 Jun 2025")  # YYYY or DD MMM YYYY as required
        dep_date_input.send_keys(Keys.ENTER)
        time.sleep(1)
        self.assertTrue(dep_date_input.get_attribute("value").strip() != "", "Departure date should be populated.")

        # Arrival Date
        arr_date_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[4]/div[1]/input[1]"
        )
        self.assertEqual(arr_date_input.get_attribute("aria-label"), "arrivalDate")
        arr_date_input.click()
        arr_date_input.clear()
        arr_date_input.send_keys("05 Jul 2025")
        arr_date_input.send_keys(Keys.ENTER)
        time.sleep(1)
        self.assertTrue(arr_date_input.get_attribute("value").strip() != "", "Arrival date should be populated.")

    def test_pax_selection_input(self):
        """Fill the Pax Selection input and verify."""
        pax_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[5]/div[1]/input[1]"
        )
        self.assertEqual(pax_input.get_attribute("aria-label"), "Pax Selection")
        pax_input.click()
        # Example: select "1 Adult" or type a numeric value if allowed
        # If it's an autocomplete, send "1" then ENTER
        pax_input.clear()
        pax_input.send_keys("1")
        pax_input.send_keys(Keys.ENTER)
        time.sleep(1)
        # Verify it populated (value might be "1 Adult" or similar)
        self.assertTrue(pax_input.get_attribute("value").strip() != "", "Pax selection should be populated.")

    def test_click_search_button(self):
        """Click the Search button after filling mandatory fields."""
        # (Fill mandatory fields first: one-way, source, dest, dep date, pax.)
        # Select One-Way
        oneway_radio = self.driver.find_element(By.XPATH, "//*[@id='radio-input-triptype-oneWay']")
        oneway_radio.click()
        # Source
        src_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[1]/div[1]/input[1]"
        )
        src_input.clear()
        src_input.send_keys("DEL")
        src_input.send_keys(Keys.ENTER)
        # Destination
        dest_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[2]/div[1]/input[1]"
        )
        dest_input.clear()
        dest_input.send_keys("BOM")
        dest_input.send_keys(Keys.ENTER)
        # Departure
        dep_date_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[3]/div[1]/input[1]"
        )
        dep_date_input.click()
        dep_date_input.clear()
        dep_date_input.send_keys("30 Jun 2025")
        dep_date_input.send_keys(Keys.ENTER)
        # Pax
        pax_input = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[2]/div[2]/div[5]/div[1]/input[1]"
        )
        pax_input.click()
        pax_input.clear()
        pax_input.send_keys("1")
        pax_input.send_keys(Keys.ENTER)

        # Click Search (button)
        search_button = self.driver.find_element(By.XPATH,
            "/html[1]/body[1]/main[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[4]/div[1]/div[2]/button[1]"
        )
        self.assertEqual(search_button.get_attribute("type"), "button")
        search_button.click()

        # After click, validate that results page or a search-results container appears
        self.wait.until(EC.url_contains("/flight-search"))
        self.assertIn("/flight-search", self.driver.current_url)

if __name__ == "__main__":
    unittest.main()
