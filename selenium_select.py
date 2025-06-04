#!/usr/bin/env python3
"""
Modified Script: highlight_and_generate_selectors_with_aria.py

This script:
1. Loads a page (e.g., Indigo login).
2. Waits for React-rendered DOM.
3. Finds all <input> and <button> elements.
4. For each element, prompts the user to include it.
   - If included, identifies the nearest ancestor (including itself) with an `aria-*` attribute.
   - Generates the element’s XPath.
5. Highlights the ancestor (or element) with a red border and scrolls it into view.
6. Prints detailed logs at each step, and in the summary prints the `aria-*` values (not selectors).

Usage:
    python3 highlight_and_generate_selectors_with_aria.py
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === Configuration ===
PAGE_URL = "https://6epartner-preprod.goindigo.in/"  # Replace with the actual URL
WAIT_AFTER_LOAD = 30      # seconds to wait for manual login or initial interaction
WAIT_RENDER = 10          # seconds to wait for React rendering

# === Helper Functions ===

def find_aria_ancestor(driver, element):
    """
    Returns the closest ancestor (including the element itself) WebElement that has any attribute
    starting with 'aria-'. If none is found, returns None.
    """
    script = """
    return (function(el) {
      while (el) {
        for (let attr of el.attributes) {
          if (attr.name.startsWith('aria-')) {
            return el;
          }
        }
        el = el.parentElement;
      }
      return null;
    })(arguments[0]);
    """
    return driver.execute_script(script, element)

def get_aria_attributes(driver, element):
    """
    Returns a dict of all aria-* attributes on the given element.
    """
    script = """
    var el = arguments[0];
    var items = {};
    for (var i = 0; i < el.attributes.length; i++) {
      var attr = el.attributes[i];
      if (attr.name.startsWith('aria-')) {
        items[attr.name] = attr.value;
      }
    }
    return items;
    """
    return driver.execute_script(script, element) or {}

def build_css_selector(element):
    """
    Build a CSS selector string for the given WebElement:
      1) If it has an ID -> 'tag#id'
      2) Else if it has classes -> 'tag.class1.class2...'
      3) Else use its tag name alone.
    """
    tag = element.tag_name.lower()
    elem_id = element.get_attribute("id")
    if elem_id:
        safe_id = elem_id.replace('"', '\\"')
        return f"{tag}#{safe_id}"

    class_attr = element.get_attribute("class") or ""
    classes = [cls for cls in class_attr.split() if cls]
    if classes:
        safe_classes = [cls.replace('"', '\\"') for cls in classes]
        return f"{tag}." + ".".join(safe_classes)

    return tag

def get_xpath(driver, element):
    """
    Returns the absolute XPath of the given WebElement.
    """
    script = """
    return (function(el) {
      if (el.id) {
        return '//*[@id=\"' + el.id + '\"]';
      }
      var segs = [];
      while (el && el.nodeType === 1) {
        var idx = 1;
        var sib = el.previousSibling;
        while (sib) {
          if (sib.nodeType === 1 && sib.tagName === el.tagName) {
            idx++;
          }
          sib = sib.previousSibling;
        }
        var tag = el.tagName.toLowerCase();
        var seg = tag + '[' + idx + ']';
        segs.unshift(seg);
        el = el.parentNode;
      }
      return '/' + segs.join('/');
    })(arguments[0]);
    """
    return driver.execute_script(script, element)

# === Main Script ===

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-gpu")
# Disable HTTP/2 to avoid protocol errors on some endpoints
chrome_options.add_argument("--disable-http2")
chrome_options.add_argument("--disable-quic")

print("[LOG] Initializing Chrome WebDriver...")
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)

try:
    print(f"[LOG] Navigating to {PAGE_URL}")
    driver.get(PAGE_URL)

    print(f"[LOG] Waiting {WAIT_AFTER_LOAD} seconds for manual login or initial interactions...")
    time.sleep(WAIT_AFTER_LOAD)

    print(f"[LOG] Waiting up to {WAIT_RENDER} seconds for React-rendered <form> to appear...")
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "form")))
        print("[LOG] <form> detected.")
    except:
        print("[WARN] No <form> found after waiting. Proceeding anyway.")

    time.sleep(WAIT_RENDER)
    print("[LOG] Proceeding to collect form elements.")

    # Collect all <input>, <textarea>, <select>, and <button> elements
    form_elements = driver.find_elements(By.XPATH, "//input | //textarea | //select | //button")
    print(f"[LOG] Found {len(form_elements)} <input>, <textarea>, <select>, or <button> elements.")

    included_elements = []

    print("\n=== Processing Form Components ===")
    for i, elem in enumerate(form_elements, 1):
        tag = elem.tag_name.lower()
        elem_type = elem.get_attribute("type") or ""
        name = elem.get_attribute("name") or ""
        id_ = elem.get_attribute("id") or ""
        placeholder = elem.get_attribute("placeholder") or ""
        inner_html = driver.execute_script("return arguments[0].innerHTML;", elem).strip()
        xpath = get_xpath(driver, elem)

        print(f"\n[LOG] Element {i}/{len(form_elements)}: <{tag}>")
        print(f"      - type: '{elem_type}', name: '{name}', id: '{id_}', placeholder: '{placeholder}'")
        print(f"      - XPath: '{xpath}'")
        print(f"      - innerHTML snippet: \"{inner_html[:100]}\"{'...' if len(inner_html) > 100 else ''}")

        # Highlight with red border
        driver.execute_script(
            "arguments[0].parentElement.style.border='2px solid red';"
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            elem
        )
        time.sleep(1)  # Give time to view the element

        # Prompt user for inclusion
        choice = input("Include this element? (y/n): ").strip().lower()
        if choice == 'y':
            print(f"[LOG] User chose to include element {i}. Attempting to find aria-* ancestor...")
            aria_ancestor = find_aria_ancestor(driver, elem)
            if aria_ancestor:
                a_tag = aria_ancestor.tag_name.lower()
                a_id = aria_ancestor.get_attribute("id") or ""
                a_class = aria_ancestor.get_attribute("class") or ""
                aria_attrs = get_aria_attributes(driver, aria_ancestor)
                print(f"[LOG] Aria-* ancestor found: <{a_tag}>")
                print(f"      - ancestor id: '{a_id}', class: '{a_class}'")
                print(f"      - aria-* attributes: {aria_attrs}")
                ancestor_label = aria_attrs.get("aria-label", "")
                print(f"[LOG] Using aria-label from ancestor: '{ancestor_label}'")
            else:
                # No ancestor with aria-*, try element itself
                aria_attrs_elem = get_aria_attributes(driver, elem)
                ancestor_label = aria_attrs_elem.get("aria-label", "")
                if ancestor_label:
                    print(f"[LOG] Element itself has aria-label: '{ancestor_label}'")
                else:
                    print("[LOG] No aria-* attribute found on element or ancestor.")
                    ancestor_label = ""

            included_elements.append({
                'tag': tag,
                'type': elem_type,
                'name': name,
                'id': id_,
                'placeholder': placeholder,
                'innerHTML': inner_html,
                'element_xpath': xpath,
                'aria_label': ancestor_label
            })

        # Clear the highlight
        driver.execute_script("arguments[0].style.border='';", elem)

    # === Summary ===
    print("\n=== Included Elements with Aria-Label ===")
    for idx, item in enumerate(included_elements, 1):
        print(f"[LOG] {idx}. <{item['tag']}> name='{item['name']}', id='{item['id']}', type='{item['type']}'")
        print(f"      - original XPath: {item['element_xpath']}")
        print(f"      - aria-label: '{item['aria_label']}'")
        print("-" * 80)

    input("\nPress Enter to close the browser...")
    print("[LOG] Closing browser.")

finally:
    driver.quit()
