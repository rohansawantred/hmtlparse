from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# === Configuration ===
LOGIN_URL = "https://6epartner-preprod.goindigo.in/"  # Replace with the actual login URL
WAIT_AFTER_LOGIN = 30
WAIT_REACT_RENDER = 10

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
    driver.execute_script("arguments[0].parentElement.style.border='2px solid red'; arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", elem)
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
        included_elements.append({
            'tag': tag,
            'type': elem_type,
            'name': name,
            'id': id_,
            'placeholder': placeholder,
            'innerHTML': inner_html
        })

    # Optionally clear the highlight after prompt (optional)
    driver.execute_script("arguments[0].style.border='';", elem)

# === Summary ===
print("\n=== Included Elements ===")
for idx, item in enumerate(included_elements, 1):
    print(f"{idx}. <{item['tag']}> name='{item['name']}', id='{item['id']}', type='{item['type']}'")

input("\nPress Enter to close the browser...")
driver.quit()


