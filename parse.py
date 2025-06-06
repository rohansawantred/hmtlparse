#!/usr/bin/env python3
"""
selenium_login_parse.py

Uses Selenium to log into a website with provided credentials,
then navigates to the home page and prints out all headings,
paragraphs, and links.
"""
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from getpass import getpass
import sys
import time 

def setup_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    #service = Service(ChromeDriverManager().install())
    #driver  = webdriver.Chrome(service=service)
    return driver

def login(driver, login_url, username, password,
          user_selector, pass_selector, submit_selector):
    driver.get(login_url)
    # wait for username field to be present
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, user_selector))
    )
    driver.find_element(By.CSS_SELECTOR, user_selector).send_keys(username)
    driver.find_element(By.CSS_SELECTOR, pass_selector).send_keys(password)
    driver.find_element(By.CSS_SELECTOR, submit_selector).click()
    time.sleep(2)
    # wait for URL to change or some element on home page
    #WebDriverWait(driver, 10).until(
    #    EC.url_changes(login_url)
    #)

def parse_homepage(driver, home_url):
    driver.get(home_url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    print("\n=== Headings ===")
    for level in ("h1","h2","h3","h4","h5","h6"):
        elems = driver.find_elements(By.TAG_NAME, level)
        for e in elems:
            text = e.text.strip()
            if text:
                print(f"{level.upper()}: {text}")

    print("\n=== Paragraphs ===")
    for p in driver.find_elements(By.TAG_NAME, "p"):
        text = p.text.strip()
        if text:
            print(f"- {text}")

    print("\n=== Links ===")
    for a in driver.find_elements(By.TAG_NAME, "a"):
        href = a.get_attribute("href")
        text = a.text.strip() or "[no text]"
        print(f"{text}: {href}")

def main():
    base_url = input("Base URL (e.g. https://example.com): ").strip().rstrip('/')
    login_path = input("Login path (e.g. /login): ").strip()
    username = input("Username: ").strip()
    password = getpass("Password: ")

    login_url = base_url + login_path
    home_path = input("Home page path (e.g. /dashboard): ").strip() or "/"
    home_url = base_url + home_path

    print("\nEnter CSS selectors for the login form fields:")
    user_sel = input("Username field selector (e.g. input#user, input[name='username']): ").strip()
    pass_sel = input("Password field selector (e.g. input#pass, input[name='password']): ").strip()
    submit_sel = input("Submit button selector (e.g. button[type='submit']): ").strip()

    driver = setup_driver(headless=True)
    try:
        print(f"\nLogging in to {login_url}...")
        login(driver, login_url, username, password, user_sel, pass_sel, submit_sel)
        print("✅ Login successful")
        time.sleep(2)
        print(f"\nParsing home page at {home_url}...")
        parse_homepage(driver, home_url)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
