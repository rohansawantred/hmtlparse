
import time
import logging
from playwright.sync_api import sync_playwright, Page, ElementHandle, Route, Request


def get_xpath(element: ElementHandle) -> str:
    """
    Generate a unique XPath for a given ElementHandle using JavaScript.
    """
    js = """
    (el) => {
        function getXPath(node) {
            if (node.id) {
                return 'id(\"' + node.id + '\")';
            }
            if (node === document.body) {
                return '/html/body';
            }
            let ix = 0;
            const siblings = node.parentNode.childNodes;
            for (let i = 0; i < siblings.length; i++) {
                const sib = siblings[i];
                if (sib === node) {
                    return getXPath(node.parentNode) + '/' + node.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                }
                if (sib.nodeType === 1 && sib.tagName === node.tagName) {
                    ix++;
                }
            }
        }
        return getXPath(el);
    }
    """
    return element.evaluate(js)


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    URL = "https://www.goindigo.in"  # ← Replace with your actual URL

    # Roles to filter by
    target_roles = {"textbox", "button", "radio", "combobox"}

    with sync_playwright() as p:
        # Launch Chromium in visible (non-headless) mode with args for faster loading
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-extensions",
                "--disable-plugins",
                "--no-sandbox",
                "--disable-http2",
                "--disable-quic"
            ]
        )
        context = browser.new_context()
        context.set_default_navigation_timeout(0)
        context.set_default_timeout(0)

        # Block images, stylesheets, and fonts to speed up page load
        page: Page = context.new_page()

        logging.info("Navigating to %s with Playwright (fast-loading)", URL)
        # Use "domcontentloaded" so we proceed once the DOM is parsed (faster than full load)
        page.goto(URL, wait_until="domcontentloaded")
              
        # Step 1: Wait 30 seconds to allow React (or other frameworks) to render
        logging.info("Waiting for 30 seconds to allow React-rendered DOM...")
        time.sleep(30)
        logging.info("30-second wait complete.")

        # Step 2: Wait until document.readyState == 'complete'
        logging.info("Waiting for document.readyState to be 'complete'...")
        page.wait_for_function("() => document.readyState === 'complete'", timeout=30000)
        logging.info("Page readyState is 'complete'.")

        # Step 3: Find all elements with "aria-" or "data-" attribute AND role in target_roles
        logging.info(
            "Locating elements with role in %s and 'aria-' or 'data-' attributes...", 
            target_roles
        )
        all_elements = page.query_selector_all("*")
        logging.info("Total elements on page: %d", len(all_elements))

        matching_elements = []

        for idx, elem in enumerate(all_elements, start=1):
            try:
                tag_name = elem.evaluate("el => el.tagName.toLowerCase()")
            except Exception:
                logging.warning("Element %d is no longer attached; skipping.", idx)
                continue

            role = (elem.get_attribute("role") or "").lower()
            if role not in target_roles:
                continue

            try:
                attr_names = elem.evaluate(
                    "el => Array.from(el.attributes).map(a => a.name.toLowerCase())"
                )
            except Exception:
                logging.warning("Failed to retrieve attributes for element %d; skipping.", idx)
                continue

            if not any(name.startswith("aria-") or name.startswith("data-") for name in attr_names):
                continue

            try:
                xpath = get_xpath(elem)
            except Exception:
                xpath = "<could not generate xpath>"

            aria_label = elem.get_attribute("aria-label") or "<no aria-label>"

            logging.info(
                "Match %d: <%s> — XPath: %s | aria-label: %s | role: %s",
                idx, tag_name, xpath, aria_label, role
            )

            matching_elements.append({
                "tag": tag_name,
                "aria_label": aria_label,
                "role": role,
                "xpath": xpath
            })

        # Step 5: Print summary of matching elements
        print("\n=== Summary: Elements with role in {textbox, button, radio, combobox} and 'aria-' or 'data-' attributes ===")
        if matching_elements:
            for item in matching_elements:
                print(f"\nTag        : <{item['tag']}>")
                print(f"aria-label : {item['aria_label']}")
                print(f"role       : {item['role']}")
                print(f"XPath      : {item['xpath']}")
        else:
            print("No matching elements found.")

        # Cleanup
        logging.info("Closing browser.")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()

