"""
Script: extract_indigo_buttons_inputs.py

This script demonstrates how to programmatically derive the JSON mapping of
“buttons → associated input fields” on the Indigo homepage (https://www.goindigo.in).
It uses Selenium (headless Chrome) to load the fully rendered page, locates each
<button> element, then finds inputs that each button depends on (either by being
inside the same <form>, sharing data-target attributes, or being in the same container).
Finally, it prints out a JSON object matching the format:

{
  "button_identifier_1": ["input_identifier_A", "input_identifier_B", …],
  "button_identifier_2": ["input_identifier_C", …],
  …
}
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def get_button_identifier(button):
    """
    Choose a clear identifier for the button. Prefer:
     1) Visible text (if non-empty, trimmed)
     2) Unique data-testid or id attribute (if present)
     3) Fallback to “tag + index” if none of the above.
    """
    text = button.text.strip()
    if text:
        return f"{text} ({button.get_attribute('tagName').lower()})"
    # try data-testid
    data_testid = button.get_attribute("data-testid")
    if data_testid:
        return f"{button.tag_name}[data-testid=\"{data_testid}\"]"
    # try id
    btn_id = button.get_attribute("id")
    if btn_id:
        return f"{button.tag_name}#{btn_id}"
    # fallback: use CSS selector via index
    # We'll return tagName with no other info; script ensures uniqueness externally.
    return f"{button.tag_name}(index placeholder)"


def find_associated_inputs(driver, button):
    """
    Given a Selenium WebElement 'button', return a list of CSS selectors (strings)
    for all <input> elements that this button “depends on” or “submits”.
    Heuristics:
      1) If button is inside a <form>, gather all <input> descendants of that form.
      2) Else (form-less button), look for:
        a) <input data-target="<button_id>"> if button has an id attribute.
        b) All <input> elements in the same closest <div> or <section> ancestor.
      3) Filter out duplicates, return list of “input#id” or “input[name=…]” selectors.
    """
    associated = set()

    # 1) Check if button is inside a <form>
    try:
        form = button.find_element(By.XPATH, "./ancestor::form")
    except:
        form = None

    if form:
        # gather all input descendants of the form
        inputs_in_form = form.find_elements(By.TAG_NAME, "input")
        for inp in inputs_in_form:
            sel = build_input_selector(inp)
            if sel:
                associated.add(sel)
        return list(associated)

    # 2) Form-less: a) data-target
    btn_id = button.get_attribute("id")
    if btn_id:
        # find all inputs with data-target attribute equal to this button’s id
        inputs_dt = driver.find_elements(By.CSS_SELECTOR, f"input[data-target=\"{btn_id}\"]")
        for inp in inputs_dt:
            sel = build_input_selector(inp)
            if sel:
                associated.add(sel)

    # 2) Form-less: b) inputs in same container (closest div or section)
    try:
        container = button.find_element(By.XPATH, "./ancestor::div | ./ancestor::section")
    except:
        container = None

    if container:
        inputs_in_container = container.find_elements(By.TAG_NAME, "input")
        for inp in inputs_in_container:
            sel = build_input_selector(inp)
            if sel:
                associated.add(sel)

    return list(associated)


def build_input_selector(input_elem):
    """
    Given a Selenium WebElement 'input_elem', return a unique CSS selector string:
     - Prefer “input#id” if id attribute exists.
     - Else if name attribute exists, “input[name=\"…\"]”.
     - Else if placeholder exists, “input[placeholder=\"…\"]”.
     - Else return None (we skip inputs without any meaningful identifier).
    """
    inp_id = input_elem.get_attribute("id")
    if inp_id:
        return f"input#{inp_id}"
    name = input_elem.get_attribute("name")
    if name:
        return f"input[name=\"{name}\"]"
    placeholder = input_elem.get_attribute("placeholder")
    if placeholder:
        return f"input[placeholder=\"{placeholder}\"]"
    return None


def main():
    # 1) Launch headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    # To avoid HTTP2 issues, optionally disable HTTP/2:
    chrome_options.add_argument("--disable-http2")
    chrome_options.add_argument("--disable-quic")

    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        # 2) Navigate to homepage
        driver.get("https://www.goindigo.in")
        # 3) Wait until a known input is present (ensures the React app has rendered)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#gosuggest_inputSrc")))
        time.sleep(1)  # brief buffer for any remaining dynamic loads

        # 4) Find all <button> elements on the page
        buttons = driver.find_elements(By.TAG_NAME, "button")

        result = {}
        for idx, btn in enumerate(buttons):
            # Build a button identifier
            identifier = get_button_identifier(btn)
            # If fallback “index placeholder” was used, append the index for uniqueness
            if "index placeholder" in identifier:
                identifier = f"{btn.tag_name}[index={idx}]"

            # 5) Find all associated inputs using the heuristics
            inputs = find_associated_inputs(driver, btn)
            # Filter out any empty or None selectors
            inputs = [inp for inp in inputs if inp]

            if inputs:
                result[f"{identifier}"] = inputs

        # 6) Print the JSON mapping
        print(json.dumps(result, indent=2))

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
