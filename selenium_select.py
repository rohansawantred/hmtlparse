from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# === Configuration ===
LOGIN_URL = "https://6epartner-preprod.goindigo.in/"  # Replace with the actual login URL
WAIT_AFTER_LOGIN = 30
WAIT_REACT_RENDER = 10

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
        return '//*[@id="' + el.id + '"]';
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

# === Start Browser ===
print("[LOG] Initializing Chrome WebDriver...")
driver = webdriver.Chrome()
print(f"[LOG] Navigating to {LOGIN_URL}")
driver.get(LOGIN_URL)

print(f"[LOG] Waiting {WAIT_AFTER_LOGIN} seconds for manual login or initial interactions...")
time.sleep(WAIT_AFTER_LOGIN)

# === Wait for React-rendered DOM ===
print(f"[LOG] Waiting up to {WAIT_REACT_RENDER} seconds for React-rendered <form> to appear...")
try:
    WebDriverWait(driver, WAIT_REACT_RENDER).until(
        EC.presence_of_element_located((By.TAG_NAME, "form"))
    )
    print("[LOG] <form> detected.")
except:
    print("[WARN] No <form> found after waiting. Proceeding anyway.")

time.sleep(WAIT_REACT_RENDER)
print("[LOG] Proceeding to collect form elements.")

# === Collect Form Elements ===
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
            a_selector = build_css_selector(aria_ancestor)
            a_xpath = get_xpath(driver, aria_ancestor)
            print(f"[LOG] Aria-* ancestor found: <{a_tag}>")
            print(f"      - ancestor id: '{a_id}', class: '{a_class}'")
            print(f"      - ancestor XPath: '{a_xpath}'")
            print(f"      - generated CSS selector for ancestor: '{a_selector}'")
        else:
            a_selector = build_css_selector(elem)
            print("[LOG] No ancestor with aria-* found. Using element itself for selector.")
            print(f"      - generated CSS selector for element: '{a_selector}'")

        included_elements.append({
            'tag': tag,
            'type': elem_type,
            'name': name,
            'id': id_,
            'placeholder': placeholder,
            'innerHTML': inner_html,
            'element_xpath': xpath,
            'aria_ancestor_selector': a_selector
        })

    # Clear the highlight
    driver.execute_script("arguments[0].style.border='';", elem)

# === Summary ===
print("\n=== Included Elements with Aria-Ancestor Selectors ===")
for idx, item in enumerate(included_elements, 1):
    print(f"[LOG] {idx}. <{item['tag']}> name='{item['name']}', id='{item['id']}', type='{item['type']}'")
    print(f"      - original XPath: {item['element_xpath']}")
    print(f"      - aria-level selector: {item['aria_ancestor_selector']}")
    print("-" * 80)

input("\nPress Enter to close the browser...")
print("[LOG] Closing browser.")
driver.quit()
