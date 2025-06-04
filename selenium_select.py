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
    JavaScript snippet to return the closest ancestor (including the element itself)
    that has any attribute starting with 'aria-'. Returns None if none found.
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
        safe_id = elem_id.replace('"', '\\"')
        return f"{tag}#{safe_id}"

    class_attr = element.get_attribute("class") or ""
    classes = [cls for cls in class_attr.split() if cls]
    if classes:
        safe_classes = [cls.replace('"', '\\"') for cls in classes]
        return f"{tag}." + ".".join(safe_classes)

    return tag

# === Start Browser ===
driver = webdriver.Chrome()
driver.get(LOGIN_URL)

print(f"Please login manually in the browser window. Waiting {WAIT_AFTER_LOGIN} seconds...")
time.sleep(WAIT_AFTER_LOGIN)

# === Wait for React-rendered DOM ===
try:
    WebDriverWait(driver, WAIT_REACT_RENDER).until(
        EC.presence_of_element_located((By.TAG_NAME, "form"))
    )
except:
    print("Warning: Form not found after waiting. Proceeding anyway.")

time.sleep(WAIT_REACT_RENDER)

# === Collect Form Elements ===
form_elements = driver.find_elements(By.XPATH, "//input | //textarea | //select | //button")
included_elements = []

print("\n=== Processing Form Components ===")
for i, elem in enumerate(form_elements, 1):
    tag = elem.tag_name
    elem_type = elem.get_attribute("type") or ""
    name = elem.get_attribute("name") or ""
    id_ = elem.get_attribute("id") or ""
    placeholder = elem.get_attribute("placeholder") or ""
    inner_html = driver.execute_script("return arguments[0].innerHTML;", elem)

    # Highlight with red border
    driver.execute_script(
        "arguments[0].parentElement.style.border='2px solid red';"
        "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
        elem
    )
    time.sleep(1)  # Give time to view the element

    print(f"""{i}. <{tag}>
    - type: '{elem_type}'
    - name: '{name}'
    - id: '{id_}'
    - placeholder: '{placeholder}'
    - innerHTML: \"{inner_html.strip()[:100]}\"{'...' if len(inner_html.strip()) > 100 else ''}""")

    # Prompt user for inclusion
    choice = input("Include this element? (y/n): ").strip().lower()
    if choice == 'y':
        # Find nearest ancestor with aria-* (including itself)
        aria_ancestor = find_aria_ancestor(driver, elem)
        if aria_ancestor:
            ancestor_tag = aria_ancestor.tag_name
            ancestor_id = aria_ancestor.get_attribute("id") or ""
            ancestor_class = aria_ancestor.get_attribute("class") or ""
            # Build CSS selector for the ancestor
            ancestor_selector = build_css_selector(aria_ancestor)
            # Collect its aria-* attributes
            aria_attrs = driver.execute_script(
                """
                var el = arguments[0];
                var items = {};
                for (var i = 0; i < el.attributes.length; i++) {
                  var attr = el.attributes[i];
                  if (attr.name.startsWith('aria-')) {
                    items[attr.name] = attr.value;
                  }
                }
                return items;
                """,
                aria_ancestor
            ) or {}
        else:
            ancestor_tag = None
            ancestor_id = ""
            ancestor_class = ""
            ancestor_selector = build_css_selector(elem)
            aria_attrs = {}

        included_elements.append({
            'tag': tag,
            'type': elem_type,
            'name': name,
            'id': id_,
            'placeholder': placeholder,
            'innerHTML': inner_html,
            'aria_ancestor_tag': ancestor_tag,
            'aria_ancestor_id': ancestor_id,
            'aria_ancestor_class': ancestor_class,
            'aria_ancestor_selector': ancestor_selector,
            'aria_attributes': aria_attrs
        })

    # Clear the highlight
    driver.execute_script("arguments[0].style.border='';", elem)

# === Summary ===
print("\n=== Included Elements with Aria-Ancestor Info ===")
for idx, item in enumerate(included_elements, 1):
    print(f"{idx}. <{item['tag']}> name='{item['name']}', id='{item['id']}', type='{item['type']}'")
    if item['aria_ancestor_tag']:
        print(f"   -> Aria Ancestor: <{item['aria_ancestor_tag']}>")
        print(f"      - id: '{item['aria_ancestor_id']}', class: '{item['aria_ancestor_class']}'")
        print(f"      - aria-* attributes: {item['aria_attributes']}")
        print(f"      - generated CSS selector: {item['aria_ancestor_selector']}")
    else:
        print("   -> No ancestor with aria-* found. Using element itself for selector:")
        print(f"      - generated CSS selector: {item['aria_ancestor_selector']}")
    print("-" * 80)

input("\nPress Enter to close the browser...")
driver.quit()
