#!/usr/bin/env python3
"""
Agent: Infinite‐scroll + link traversal (return to home) + clickable clicks with highlight + annotated PDF screenshots.

Dependencies:
    pip install pyppeteer pillow

Usage:
    python crawler_agent.py \
        --url "https://react-travel-website-chi.vercel.app/" \
        --output "actions_record.pdf" \
        --max-scrolls 30 \
        --delay 1.5
"""

import os
import asyncio
import time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pyppeteer import launch
from pyppeteer.errors import BrowserError

async def annotate_image(img_bytes: bytes, label: str) -> Image.Image:
    """
    Given raw screenshot bytes and a label, return a PIL Image
    with the label drawn in the top-left corner.
    """
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Choose a font size relative to image width
    font_size = max(16, img.width // 50)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    text_pos = (10, 10)
    # Measure text bounding box
    bbox = draw.textbbox(text_pos, label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding = 6
    rect_end = (text_pos[0] + text_width + padding, text_pos[1] + text_height + (padding // 2))
    draw.rectangle([text_pos, rect_end], fill=(0, 0, 0, 180))
    draw.text((text_pos[0] + 2, text_pos[1] + 2), label, font=font, fill=(255, 255, 255))

    return img

async def crawl_and_record(
    home_url: str,
    output_pdf: str = "actions_record.pdf",
    max_scrolls: int = 50,
    scroll_delay: float = 1.0,
):
    """
    1. Launch headless Chrome.
    2. Navigate to home_url.
    3. Perform infinite scroll up to max_scrolls, capturing annotated screenshots.
    4. Extract unique <a href> links; for each link:
       a. Navigate, capture screenshot labeled "Navigated to [link]".
       b. For each <button> on that page:
          i. Highlight the button, take a screenshot labeled "Highlighting button '[text]' on [link]".
         ii. Click the button, wait, take a screenshot labeled "Clicked button '[text]' on [link] – result".
         iii. Remove highlight if possible, go back to the link’s page.
       c. Return to home_url.
    5. Compile all annotated screenshots into a single PDF.
    """
    # Locate a local Chrome/Chromium executable
    chrome_paths = [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]
    executable_path = next((p for p in chrome_paths if os.path.exists(p)), None)

    launch_opts = {
        "headless": False,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"],
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
    screenshots = []

    # 1) Navigate to home_url
    print(f"[INFO] Navigating to {home_url} …")
    try:
        await page.goto(home_url, {"waitUntil": "load"})
        time.sleep(3)
    except Exception as e:
        print(f"[ERROR] Failed to load {home_url}: {e}")
        await browser.close()
        return

    # 2) Infinite scroll with annotated screenshots
    print("[INFO] Starting infinite scroll …")
    last_height = await page.evaluate("() => document.body.scrollHeight")
    for i in range(1, max_scrolls + 1):
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(scroll_delay)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        print(f"  ➡️ Scroll {i}: {last_height} → {new_height}")
        img_bytes = await page.screenshot({"fullPage": True})
        screenshots.append(await annotate_image(img_bytes, f"Scrolled step {i}"))
        if new_height == last_height:
            print("  ● No more content; stopping scroll.")
            break
        last_height = new_height

    # 3) Extract unique links from the home page
    print("[INFO] Extracting links from home …")
    anchors = await page.querySelectorAll("a[href]")
    hrefs = set()
    for a in anchors:
        try:
            href = await page.evaluate("(e) => e.href", a)
            if href and href.startswith("http"):
                hrefs.add(href)
        except Exception:
            pass
    hrefs = list(hrefs)
    print(f"  • Found {len(hrefs)} unique links.")

    # 4) Traverse each link and then return to home_url
    for idx, link in enumerate(hrefs, start=1):
        print(f"[INFO] ({idx}/{len(hrefs)}) Navigating to {link}")
        try:
            await page.goto(link, {"waitUntil": "networkidle2"})
            await asyncio.sleep(1)
        except Exception as e:
            print(f"  [WARN] Could not load {link}: {e}")
            continue

        # Screenshot after navigation
        img_bytes = await page.screenshot({"fullPage": True})
        screenshots.append(await annotate_image(img_bytes, f"Navigated to {link}"))

        # 4a) Click and highlight all <button> elements on this page
        buttons = await page.querySelectorAll("button")
        for b_idx, btn in enumerate(buttons, start=1):
            try:
                btn_text = await page.evaluate("(e) => e.innerText", btn) or "<no-text>"
            except Exception:
                btn_text = "<no-text>"

            # Highlight the button by adding red outline
            highlight_js = "(el) => el.style.outline = '3px solid red'"
            remove_highlight_js = "(el) => el.style.outline = ''"
            highlight_label = f"Highlighting button '{btn_text}' on {link}"
            click_label = f"Clicked button '{btn_text}' on {link} – result"

            print(f"  • {highlight_label}")
            try:
                await page.evaluate(highlight_js, btn)
            except Exception:
                pass

            # Screenshot the highlighted button
            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(await annotate_image(img_bytes, highlight_label))

            # Click the button
            try:
                await btn.click()
                await asyncio.sleep(1)
            except Exception as e:
                print(f"    [WARN] Could not click '{btn_text}': {e}")

            # Screenshot the result after click
            img_bytes = await page.screenshot({"fullPage": True})
            screenshots.append(await annotate_image(img_bytes, click_label))

            # Remove highlight
            try:
                await page.evaluate(remove_highlight_js, btn)
            except Exception:
                pass

            # Return to link page (in case click navigated away)
            try:
                await page.goBack({"waitUntil": "networkidle2"})
                await asyncio.sleep(1)
            except Exception:
                pass

        # Return to home_url after processing this link
        print(f"[INFO] Returning to home {home_url}")
        try:
            await page.goto(home_url, {"waitUntil": "networkidle2"})
            await asyncio.sleep(1)
        except Exception as e:
            print(f"  [WARN] Could not return to home: {e}")

    # 5) Compile annotated screenshots into a single PDF
    print(f"[INFO] Saving {len(screenshots)} screenshots to '{output_pdf}' …")
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
    print("[INFO] Browser closed; complete.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Puppeteer agent: infinite scroll, link traversal, highlight+click, annotated screenshots to PDF"
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
        help="Maximum number of scroll iterations (default: 50)."
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to wait after each scroll (default: 1.0)."
    )

    args = parser.parse_args()

    asyncio.get_event_loop().run_until_complete(
        crawl_and_record(
            home_url=args.url,
            output_pdf=args.output,
            max_scrolls=args.max_scrolls,
            scroll_delay=args.delay
        )
    )

