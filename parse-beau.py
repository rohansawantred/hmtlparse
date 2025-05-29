#!/usr/bin/env python3
"""
login_and_parse_noselenium.py

Logs into a website (no Selenium) using provided CSS selectors for
username, password, and login button, then fetches and parses the
home page listing navigation links and form fields.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from getpass import getpass


def login(session, login_url, username, password, user_sel, pass_sel, button_sel):
    # Fetch login page
    resp = session.get(login_url)
    resp.raise_for_status()
    print(resp.text)
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Locate fields/buttons by CSS selector
    user_input = soup.select_one(user_sel)
    pass_input = soup.select_one(pass_sel)
    submit_btn = soup.select_one(button_sel)

    if not user_input or not pass_input or not submit_btn:
        raise RuntimeError("Could not find login elements with provided selectors")

    # Find enclosing <form>
    form = submit_btn.find_parent('form')
    if not form:
        raise RuntimeError("Login button not inside a form")

    action = form.get('action') or login_url
    post_url = urljoin(login_url, action)

    # Build payload
    payload = {}
    for inp in form.find_all('input'):
        name = inp.get('name')
        if not name:
            continue
        if inp is user_input:
            payload[name] = username
        elif inp is pass_input:
            payload[name] = password
        else:
            payload[name] = inp.get('value', '')

    # Submit login
    headers = {'Referer': login_url}
    post = session.post(post_url, data=payload, headers=headers)
    post.raise_for_status()
    if post.url == login_url:
        raise RuntimeError("Login may have failed; still on login page")


def parse_home(session, home_url):
    resp = session.get(home_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    print("\n=== Navigation Links ===")
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True) or "[no text]"
        href = urljoin(home_url, a['href'])
        print(f"- {text}: {href}")

    print("\n=== Form Fields ===")
    for form in soup.find_all('form'):
        action = form.get('action') or home_url
        print(f"\nForm action: {urljoin(home_url, action)}")
        for fld in form.find_all(['input', 'select', 'textarea']):
            tag = fld.name
            name = fld.get('name', '[no name]')
            typ = fld.get('type', tag)
            print(f"  - <{tag} type='{typ}' name='{name}'>")


def main():
    base = input("Base URL (e.g. https://example.com): ").strip().rstrip('/')
    login_path = input("Login URL or path (e.g. /login): ").strip()
    login_url = urljoin(base + '/', login_path.lstrip('/'))

    username = input("Username: ").strip()
    password = getpass("Password: ")

    user_sel = input("CSS selector for username field: ").strip()
    pass_sel = input("CSS selector for password field: ").strip()
    button_sel = input("CSS selector for login button: ").strip()

    session = requests.Session()
    try:
        print(f"\nLogging in to {login_url}...")
        login(session, login_url, username, password, user_sel, pass_sel, button_sel)
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return

    home_path = input("\nHome page URL or path (e.g. /home): ").strip() or '/'
    home_url = urljoin(base + '/', home_path.lstrip('/'))

    print(f"\nParsing home page at {home_url}...")
    try:
        parse_home(session, home_url)
    except Exception as e:
        print(f"❌ Error parsing home page: {e}")


if __name__ == "__main__":
    import sys
    try:
        from urllib.parse import urljoin
    except ImportError:
        print("Error: urllib.parse.urljoin not available", file=sys.stderr)
        sys.exit(1)

    main()
