#!/usr/bin/env python3
"""
Modified Script: highlight_and_generate_selectors.py

This script:
1. Loads a page (e.g., Indigo login).
2. Waits for React-rendered DOM.
3. Finds all <input> and <button> elements.
4. For each element, finds its nearest ancestor (including itself) that has any `aria-*` attribute.
5. Generates a CSS selector for that ancestor (or the element itself if no such ancestor).
6. Highlights the ancestor with a red border and scrolls into view briefly.
7. Prints each element’s tag, attributes, the found aria-* ancestor’s tag/attributes, and the generated CSS selector.

Usage:
    python3 highlight_and_generate_selectors.py
"""

import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === Configuration ===
PAGE_URL = "https://6epartner-preprod.goindigo.in/"  # Replace with the actual URL
WAIT_AFTER_LOAD = 30
WAIT_RENDER = 10

# === Helper Functions ===

def find_aria_ancestor(driver, element):
    """
    JavaScript snippet to return the closest ancestor (including the element itself)
    that has any attribute starting with 'aria-'. Returns null if none found.
    """
    script = """
    (function(el) {
      while (el) {
        for (let i = 0; i < el.attributes.length; i++) {
          if (el.attributes[i].name.startsWith('aria-')) {
            return el;
          }
        }
        el = el.parentElement;
      }
      return null;
    })(arguments[0]);
    """
    return driver.execute_script(script, element)

def build_css_selector(element):
    """
    Build a CSS selector string for the given WebElement:
      1) If it has an ID -> tag#id
      2) Else if it has classes -> tag.class1.class2...
      3) Else use its tag name alone.
    """
    tag = element.tag_name.lower()
    elem_id = element.get_attribute("id")
    if elem_id:
        # sanitize ID for CSS
        safe_id = elem_id.replace('"', '\\"')
        return f"{tag}#{safe_id}"

    class_attr = element.get_attribute("class") or ""
    classes = [cls for cls in class_attr.split() if cls]
    if classes:
        # sanitize class names
        safe_classes = [cls.replace('"', '\\"') for cls in classes]
        return f"{tag}." + ".".join(safe_classes)

    return tag

def get_element_summary(element):
    """
    Return a dictionary with key attributes to help identify the element:
      - tag, type, id, name, placeholder, aria-* attributes (as dict)
    """
    summary = {
        "tag": element.tag_name.lower(),
        "type": element.get_attribute("type") or "",
        "id": element.get_attribute("id") or "",
        "name": element.get_attribute("name") or "",
        "placeholder": element.get_attribute("placeholder") or "",
        "aria_attributes": {}
    }
    # Collect aria-* attributes
    for attr in element.get_property("attributes"):
        name = attr.get_attribute("name")
        value = attr.get_attribute("value")
        if name.startswith("aria-"):
            summary["aria_attributes"][name] = value
    return summary

# === Main Script ===

driver = webdriver.Chrome()
driver.get(PAGE_URL)

print(f"Waiting {WAIT_AFTER_LOAD} seconds for manual login or any initial interaction...")
time.sleep(WAIT_AFTER_LOAD)

# Wait until some form/input appears, indicating React has rendered
try:
    WebDriverWait(driver, WAIT_RENDER).until(
        EC.presence_of_element_located((By.TAG_NAME, "form"))
    )
except:
    print("Warning: No <form> found after waiting. Proceeding anyway.")

time.sleep(WAIT_RENDER)

# Collect all <input> and <button> elements
elements = driver.find_elements(By.XPATH, "//input | //button")
print(f"\nFound {len(elements)} <input> or <button> elements.\n")

for idx, elem in enumerate(elements, start=1):
    # 1) Get basic summary of the element
    elem_summary = get_element_summary(elem)

    # 2) Find the nearest ancestor (or itself) with an aria-* attribute
    aria_ancestor = find_aria_ancestor(driver, elem)

    if aria_ancestor:
        ancestor_summary = get_element_summary(driver.find_element(By.XPATH, "."), )  # placeholder
        # Build a WebElement from the returned element reference
        aria_elem = aria_ancestor
        ancestor_summary = get_element_summary(aria_elem)
        selector = build_css_selector(aria_elem)

        # Highlight the ancestor
        driver.execute_script(
            "arguments[0].style.border='2px solid red'; arguments[0].scrollIntoView({behavior:'smooth', block:'center'});",
            aria_elem
        )
        time.sleep(1)
        # Clear highlight
        driver.execute_script("arguments[0].style.border='';", aria_elem)

    else:
        ancestor_summary = None
        selector = build_css_selector(elem)

        # Highlight the element itself
        driver.execute_script(
            "arguments[0].style.border='2px solid red'; arguments[0].scrollIntoView({behavior:'smooth', block:'center'});",
            elem
        )
        time.sleep(1)
        driver.execute_script("arguments[0].style.border='';", elem)

    # 3) Print results
    print(f"{idx}. Element: <{elem_summary['tag']}>")
    print(f"   - type: '{elem_summary['type']}', id: '{elem_summary['id']}', name: '{elem_summary['name']}', placeholder: '{elem_summary['placeholder']}'")
    if elem_summary["aria_attributes"]:
        print(f"   - aria- attributes: {elem_summary['aria_attributes']}")
    if ancestor_summary:
        print(f"   -> Aria ancestor: <{ancestor_summary['tag']}>")
        print(f"      - type: '{ancestor_summary['type']}', id: '{ancestor_summary['id']}', name: '{ancestor_summary['name']}', placeholder: '{ancestor_summary['placeholder']}'")
        if ancestor_summary["aria_attributes"]:
            print(f"      - aria- attributes: {ancestor_summary['aria_attributes']}")
        print(f"      - generated CSS selector: {selector}")
    else:
        print("   -> No ancestor with aria-* found. Using element itself.")
        print(f"      - generated CSS selector: {selector}")

    print("-" * 80)

print("\nDone. Closing browser in 5 seconds...")
time.sleep(5)
driver.quit()
