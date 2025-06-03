#!/usr/bin/env python3
"""
Agent: BFS crawl + in-domain filtering + infinite-scroll + link/button highlight + LLM form filling + annotated PDF screenshots,
never revisiting the same normalized URL.

Dependencies:
    pip install pyppeteer pillow openai

Usage:
    export OPENAI_API_KEY="sk-..."
    python crawler_agent.py \
        --url "https://react-travel-website-chi.vercel.app/" \
        --output "actions_record.pdf" \
        --max-scrolls 30 \
        --delay 1.5 \
        --max-pages 20
"""

import os
import asyncio
import time
from io import BytesIO
from collections import defaultdict, deque
from urllib.parse import urlparse, urlunparse
from PIL import Image, ImageDraw, ImageFont
from pyppeteer import launch
from pyppeteer.errors import BrowserError
import openai

# Make sure your OpenAI API key is set
openai.api_key = os.getenv("OPENAI_API_KEY")


def normalize_url(raw_url: str) -> str:
    """
    Normalize a URL by removing any fragment and trimming trailing slashes
    (except if the path is just "/").
    """
    parsed = urlparse(raw_url)
    # Drop the fragment
    no_frag = parsed._replace(fragment="")
    # Normalize path: remove trailing slash unless it's the root "/"
    path = no_frag.path
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    normalized = urlunparse((no_frag.scheme, no_frag.netloc, path, no_frag.params, no_frag.query, ""))
    return normalized


async def generate_mock_value(field_info: dict) -> str:
    """
    Use OpenAI ChatCompletion to generate realistic mock data for a form field
    based on its attributes. Falls back to "test" on error.
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
        f"Generate a realistic mock input value for a form field with {prompt_desc}. "
        "Keep it concise (e.g. 'john_doe', 'test@example.com', 'password123')."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant for generating test data."},
                {"role": "user",   "content": user_prompt}
            ],
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
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


def in_domain(link: str, home_netloc: str) -> bool:
    """
    Returns True if 'link' is same-domain (or relative) relative to home_netloc.
    """
    parsed = urlparse(link)
    return (parsed.netloc == "" or parsed.netloc == home_netloc)


async def crawl_and_record(
    home_url: str,
    output_pdf: str = "actions_record.pdf",
    max_scrolls: int = 50,
    scroll_delay: float = 1.0,
    max_pages: int = 20
):
    """
    1. Launch Chrome (headed).
    2. BFS‐crawl up to max_pages, never revisiting the same normalized URL:
       a. Navigate to URL.
       b. Infinite scroll (max_scrolls), screenshot each step.
       c. Extract all <a href> (in‐domain) and <button> elements:
          i. Build link_freq; after first FREQ_LIMIT pages, compute global_links.
          ii. Enqueue any new in-domain, non-global, normalized <a> for BFS.
          iii. For each <a> on this page:
                • Highlight in red, screenshot "Highlight link '[text]' on [page]".
                • Click/navigate, wait, screenshot "Navigated to [link]".
                • Return to original page.
          iv. For each <button> on this page:
                • Highlight in red, screenshot "Highlight button '[text]' on [page]".
                • Fill all <input> fields with LLM‐generated data, screenshot “Filled inputs for button '[text]'”.
                • Click, wait, screenshot "Clicked button '[text]' on [page]".
                • Return to original page.
    3. Compile screenshots into a single PDF.
    """

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

    # --------------- Data Structures for BFS ---------------
    visited = set()
    frontier = deque([normalize_url(home_url)])
    link_freq = defaultdict(int)
    global_links = set()
    screenshots = []

    home_netloc = urlparse(home_url).netloc
    pages_visited = 0
    FREQ_LIMIT = 5  # first N pages to detect global links

    # --------------- BFS Crawl ---------------
    while frontier and pages_visited < max_pages:
        raw_url = frontier.popleft()
        if raw_url in visited:
            continue

        visited.add(raw_url)
        pages_visited += 1

        print(f"[INFO] ({pages_visited}/{max_pages}) Visiting: {raw_url}")
        try:
            await page.goto(raw_url, {"waitUntil": "networkidle2"})
            await asyncio.sleep(1)
        except Exception as e:
            print(f"  [WARN] Failed to load {raw_url}: {e}")
            continue

        # --- 1) Infinite Scroll on this page ---
        last_height = await page.evaluate("() => document.body.scrollHeight")
        for i in range(1, max_scrolls + 1):
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(scroll_delay)
            new_height = await page.evaluate("() => document.body.scrollHeight")
            print(f"    ↪︎ Scroll {i}: {last_height} → {new_height}")
            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(annotate_image(img_bytes, f"Scrolled '{raw_url}' step {i}"))
            if new_height == last_height:
                break
            last_height = new_height

        # --- 2) Extract all <a href> in-domain on this page ---
        anchors = await page.querySelectorAll("a[href]")
        extracted_hrefs = []
        for a_elem in anchors:
            try:
                href = await page.evaluate("(e) => e.href", a_elem)
                if href and in_domain(href, home_netloc):
                    normalized = normalize_url(href)
                    extracted_hrefs.append(normalized)
            except Exception:
                pass

        # Update frequency counts for first FREQ_LIMIT pages
        if pages_visited <= FREQ_LIMIT:
            for href in extracted_hrefs:
                link_freq[href] += 1
            if pages_visited == FREQ_LIMIT:
                for link, freq in link_freq.items():
                    if freq >= FREQ_LIMIT - 1:
                        global_links.add(link)

        # Enqueue new in-domain, non-global, normalized links
        for href in extracted_hrefs:
            if href not in visited and href not in frontier and href not in global_links:
                frontier.append(href)

        # --- 3) Highlight & click each <a> on this page ---
        for href in extracted_hrefs:
            selector = f"a[href='{href}']"
            try:
                a_elem = await page.querySelector(selector)
                link_text = await page.evaluate("(e) => e.innerText.trim()", a_elem) or "<no-text>"
            except Exception:
                a_elem = None
                link_text = "<no-text>"

            hl_js = "(el) => el.style.outline = '3px solid red'"
            rm_js = "(el) => el.style.outline = ''"
            highlight_label = f"Highlight link '{link_text}' on {raw_url}"

            if a_elem:
                print(f"    • {highlight_label}")
                try:
                    await page.evaluate(hl_js, a_elem)
                except Exception:
                    pass
                img_bytes = await page.screenshot({"fullPage": True})
                screenshots.append(annotate_image(img_bytes, highlight_label))
            else:
                print(f"    [WARN] Could not find link '{href}' to highlight on {raw_url}")

            click_label = f"Clicked link '{link_text}' on {raw_url}"
            print(f"    • {click_label}")
            if a_elem:
                try:
                    await a_elem.click()
                    await asyncio.sleep(1)
                except Exception:
                    await page.goto(href, {"waitUntil": "networkidle2"})
                    await asyncio.sleep(1)
            else:
                await page.goto(href, {"waitUntil": "networkidle2"})
                await asyncio.sleep(1)

            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(annotate_image(img_bytes, f"Navigated to {href}"))

            if a_elem:
                try:
                    await page.evaluate(rm_js, a_elem)
                except Exception:
                    pass

            # Return to original page
            try:
                await page.goto(raw_url, {"waitUntil": "networkidle2"})
                await asyncio.sleep(1)
            except Exception:
                pass

        # --- 4) Extract all <button> on this page ---
        button_elems = await page.querySelectorAll("button")
        for btn_elem in button_elems:
            try:
                btn_text = await page.evaluate("(e) => e.innerText.trim()", btn_elem) or "<no-text>"
            except Exception:
                btn_text = "<no-text>"

            hl_btn_js = "(el) => el.style.outline = '3px solid red'"
            rm_btn_js = "(el) => el.style.outline = ''"
            highlight_btn_label = f"Highlight button '{btn_text}' on {raw_url}"

            print(f"    • {highlight_btn_label}")
            try:
                await page.evaluate(hl_btn_js, btn_elem)
            except Exception:
                pass
            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(annotate_image(img_bytes, highlight_btn_label))

            # Fill any <input> fields on this page with LLM data
            inputs = await page.querySelectorAll("input")
            for inp in inputs:
                field_info = {}
                for attr in ["name", "id", "placeholder", "type"]:
                    try:
                        val = await page.evaluate(f"(e) => e.getAttribute('{attr}')", inp)
                        if val:
                            field_info[attr] = val
                    except Exception:
                        pass
                mock_val = await generate_mock_value(field_info)
                try:
                    await inp.click({"clickCount": 3})
                    await inp.type(mock_val, {"delay": 50})
                except Exception:
                    pass

            fill_label = f"Filled inputs for button '{btn_text}' on {raw_url}"
            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(annotate_image(img_bytes, fill_label))

            click_btn_label = f"Clicked button '{btn_text}' on {raw_url}"
            print(f"    • {click_btn_label}")
            try:
                await btn_elem.click()
                await asyncio.sleep(1)
            except Exception as e:
                print(f"      [WARN] Could not click '{btn_text}': {e}")

            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(annotate_image(img_bytes, click_btn_label))

            try:
                await page.evaluate(rm_btn_js, btn_elem)
            except Exception:
                pass

            # Return to original page
            try:
                await page.goto(raw_url, {"waitUntil": "networkidle2"})
                await asyncio.sleep(1)
            except Exception:
                pass

    # --------------- Save All Screenshots to a PDF ---------------
    if screenshots:
        try:
            screenshots[0].save(
                output_pdf,
                save_all=True,
                append_images=screenshots[1:]
            )
            print(f"[INFO] PDF saved: {output_pdf}")
        except Exception as e:
            print(f"[ERROR] Could not save PDF: {e}")
    else:
        print("[WARN] No screenshots captured; PDF not created.")

    await browser.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Puppeteer agent: BFS crawl, in-domain filtering, infinite scroll, highlight+LLM fill, annotated PDF"
    )
    parser.add_argument(
        "--url", type=str, required=True,
        help="Home URL to crawl (with infinite scroll)."
    )
    parser.add_argument(
        "--output", type=str, default="actions_record.pdf",
        help="Output PDF filename (default: actions_record.pdf)."
    )
    parser.add_argument(
        "--max-scrolls", type=int, default=50,
        help="Max scroll iterations per page (default: 50)."
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to wait after each scroll (default: 1.0)."
    )
    parser.add_argument(
        "--max-pages", type=int, default=20,
        help="Max pages to crawl (default: 20)."
    )

    args = parser.parse_args()
    asyncio.get_event_loop().run_until_complete(
        crawl_and_record(
            home_url=args.url,
            output_pdf=args.output,
            max_scrolls=args.max_scrolls,
            scroll_delay=args.delay,
            max_pages=args.max_pages
        )
    )
