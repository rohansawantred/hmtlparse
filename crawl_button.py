#!/usr/bin/env python3
"""
crawler_forms_llm.py

A Pyppeteer-based crawler that:
  1) Starts at a given URL.
  2) BFS-crawls in-domain links, never revisiting the same normalized URL.
  3) On each page:
     a. Repeatedly find any <form> containing at least one <input> and one <button>.
     b. For that form:
        i. Fill every <input> with mock data generated via OpenAI (LLM).
       ii. Highlight the first <button> in red, take a screenshot.
      iii. Click that button, wait for navigation (if any), take another screenshot.
       iv. Repeat until no such form remains on the page.
     c. After forms are exhausted, take a “final” screenshot of the page.
  4) Extract all in-domain <a href> links (via `querySelectorAll` + `evaluate`),
     normalize them, and enqueue any not yet visited.
  5) Stop when there are no more links or when a max-pages limit is reached.
  6) Compile all screenshots into a single PDF.

Dependencies:
    pip install pyppeteer pillow openai

Usage:
    export OPENAI_API_KEY="sk-..."
    python crawler_forms_llm.py \
        --url "https://example.com" \
        --output "actions_record.pdf" \
        --max-pages 20
"""

import os
import asyncio
import time
from io import BytesIO
from collections import deque
from urllib.parse import urlparse, urljoin, urlunparse
from PIL import Image, ImageDraw, ImageFont
from pyppeteer import launch
import openai

# Ensure your OpenAI API key is in the environment
openai.api_key = os.getenv("OPENAI_API_KEY")


def normalize_url(raw_url: str, base_origin: str) -> str | None:
    """
    Normalize a URL by:
      - Resolving relative URLs against base_origin
      - Removing any fragment
      - Stripping trailing slashes unless path is "/"
      - Returning an absolute string, or None if invalid
    """
    try:
        parsed = urlparse(raw_url, allow_fragments=True)
        if not parsed.netloc:
            # relative URL
            abs_url = urljoin(base_origin, raw_url)
            parsed = urlparse(abs_url)
        # Drop fragment
        parsed = parsed._replace(fragment="")
        # Strip trailing slash (unless path == "/")
        path = parsed.path
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")
        normalized = urlunparse((parsed.scheme, parsed.netloc, path,
                                 parsed.params, parsed.query, ""))
        return normalized
    except:
        return None


def in_domain(link: str, base_origin: str) -> bool:
    """
    Return True if link's origin matches base_origin's origin.
    """
    try:
        return urlparse(link).origin == urlparse(base_origin).origin
    except:
        return False


async def generate_mock_value(field_info: dict) -> str:
    """
    Use OpenAI ChatCompletion to generate a realistic mock value for a form field
    based on its attributes. Fall back to "test" on error.
    field_info: { name, id, placeholder, type }
    """
    prompt_parts = []
    if field_info.get("name"):
        prompt_parts.append(f"name='{field_info['name']}'")
    if field_info.get("id"):
        prompt_parts.append(f"id='{field_info['id']}'")
    if field_info.get("placeholder"):
        prompt_parts.append(f"placeholder='{field_info['placeholder']}'")
    if field_info.get("type"):
        prompt_parts.append(f"type='{field_info['type']}'")
    prompt_desc = ", ".join(prompt_parts) or "no attributes"

    user_prompt = (
        f"Generate a realistic mock value for a form field with {prompt_desc}. "
        "Keep it concise (e.g. 'john_doe', 'test@example.com', 'Password123')."
    )
    try:
        resp = await openai.ChatCompletion.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert test data generator."},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except:
        return "test"


def annotate_image(img_bytes: bytes, label: str) -> Image.Image:
    """
    Given raw screenshot bytes and a label, return a PIL Image
    with the label drawn in the top-left corner.
    """
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_size = max(16, img.width // 50)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    text_pos = (10, 10)
    bbox = draw.textbbox(text_pos, label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding = 6
    rect_end = (
        text_pos[0] + text_width + padding,
        text_pos[1] + text_height + (padding // 2)
    )
    draw.rectangle([text_pos, rect_end], fill=(0, 0, 0, 180))
    draw.text((text_pos[0] + 2, text_pos[1] + 2), label, font=font, fill=(255, 255, 255))

    return img


async def process_form_chain(page, screenshots: list[Image.Image], page_label: str):
    """
    Repeatedly:
      - Find the first <form> with at least one <input> and one <button>.
      - Fill inputs via LLM, screenshot.
      - Highlight first button in red, screenshot.
      - Click, wait for navigation, screenshot.
    Loop until no such form remains.
    """
    while True:
        forms = await page.querySelectorAll("form")
        target_form = None
        for form in forms:
            inputs = await form.querySelectorAll("input")
            buttons = await form.querySelectorAll("button")
            if inputs and buttons:
                target_form = form
                break
        if not target_form:
            break

        timestamp = int(time.time() * 1000)

        # Fill inputs
        inputs = await target_form.querySelectorAll("input")
        for inp in inputs:
            field_info = await page.evaluate(
                """el => ({
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    type: el.getAttribute('type') || 'text'
                })""",
                inp
            )
            mock_val = await generate_mock_value(field_info)
            try:
                await inp.click({"clickCount": 3})
                await inp.type(mock_val, {"delay": 50})
            except:
                pass

        # Screenshot after filling inputs
        filled_label = f"Filled inputs on {page_label}"
        img_bytes = await page.screenshot({"fullPage": True})
        screenshots.append(annotate_image(img_bytes, filled_label))

        # Highlight first button
        buttons = await target_form.querySelectorAll("button")
        btn = buttons[0]
        try:
            await page.evaluate("(el) => el.style.outline = '3px solid red'", btn)
        except:
            pass

        highlight_label = f"Highlight button on {page_label}"
        img_bytes = await page.screenshot({"fullPage": True})
        screenshots.append(annotate_image(img_bytes, highlight_label))

        # Click and wait for navigation (if any)
        try:
            await asyncio.gather(
                page.waitForNavigation({"waitUntil": "networkidle2", "timeout": 10000}).catch(lambda _: None),
                btn.click()
            )
        except:
            pass

        afterclick_label = f"After click on {page_label}"
        img_bytes = await page.screenshot({"fullPage": True})
        screenshots.append(annotate_image(img_bytes, afterclick_label))

        # Remove outline
        try:
            await page.evaluate("(el) => el.style.outline = ''", btn)
        except:
            pass

        # Loop continues on new page (if navigated), else same page


async def process_page(page, url: str, home_origin: str, screenshots: list[Image.Image]) -> list[str]:
    """
    Navigate to url, process form chain, final screenshot, extract links.
    Returns a list of in-domain, normalized URLs found on this page.
    """
    try:
        await page.goto(url, {"waitUntil": "networkidle2", "timeout": 60000})
        await asyncio.sleep(1)
    except:
        return []

    parsed = urlparse(url)
    page_label = parsed.path.strip("/").replace("/", "_") or "root"

    # 1) Process form chain
    await process_form_chain(page, screenshots, page_label)

    # 2) Final screenshot when no forms remain
    final_label = f"No forms on {page_label}"
    img_bytes = await page.screenshot({"fullPage": True})
    screenshots.append(annotate_image(img_bytes, final_label))

    # 3) Extract all <a href> links, normalize, filter in-domain
    anchors = await page.querySelectorAll("a[href]")
    new_links = set()
    for a_elem in anchors:
        try:
            raw_href = await page.evaluate("(el) => el.getAttribute('href')", a_elem)
            norm = normalize_url(raw_href, url)
            if norm and in_domain(norm, home_origin):
                new_links.add(norm)
        except:
            pass

    return list(new_links)


async def crawl_and_record(
    home_url: str,
    output_pdf: str = "actions_record.pdf",
    max_pages: int = 20
):
    """
    1) Launch browser.
    2) BFS-crawl up to max_pages, never revisiting URLs.
    3) On each page: process form chain, final screenshot, extract links.
    4) After crawl, compile screenshots into a single PDF.
    """
    # Launch Chrome
    # --------------- Setup Puppeteer ---------------
    chrome_paths = [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    executable_path = next((p for p in chrome_paths if os.path.exists(p)), None)

    launch_opts = {
        "headless": False,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"]
    }
    if executable_path:
        launch_opts["executablePath"] = executable_path

    try:
        browser = await launch(launch_opts)
    except BrowserError as e:
        print(f"[ERROR] Could not launch browser: {e}")
        return
    page = await browser.newPage()
    await page.setViewport({"width": 1280, "height": 800})

    visited = set()
    frontier = deque([normalize_url(home_url, home_url)])
    screenshots: list[Image.Image] = []

    parsed = urlparse(home_url)
    home_origin = f"{parsed.scheme}://{parsed.netloc}"
    pages_visited = 0

    while frontier and pages_visited < max_pages:
        url = frontier.popleft()
        if not url or url in visited:
            continue
        visited.add(url)
        pages_visited += 1

        print(f"[{pages_visited}/{max_pages}] Visiting: {url}")
        new_links = await process_page(page, url, home_origin, screenshots)

        # Enqueue new, unvisited links
        for link in new_links:
            if link not in visited:
                frontier.append(link)

    # Compile screenshots into PDF
    if screenshots:
        try:
            screenshots[0].save(
                output_pdf,
                save_all=True,
                append_images=screenshots[1:]
            )
            print(f"[INFO] Saved PDF: {output_pdf}")
        except Exception as e:
            print(f"[ERROR] Could not save PDF: {e}")
    else:
        print("[WARN] No screenshots captured; PDF not created.")

    await browser.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pyppeteer crawler: BFS, in-domain, form-fill via LLM, screenshots to PDF"
    )
    parser.add_argument(
        "--url", type=str, required=True,
        help="Starting URL to crawl."
    )
    parser.add_argument(
        "--output", type=str, default="actions_record.pdf",
        help="Output PDF filename."
    )
    parser.add_argument(
        "--max-pages", type=int, default=20,
        help="Maximum number of pages to visit."
    )

    args = parser.parse_args()
    asyncio.get_event_loop().run_until_complete(
        crawl_and_record(
            home_url=args.url,
            output_pdf=args.output,
            max_pages=args.max_pages
        )
    )

