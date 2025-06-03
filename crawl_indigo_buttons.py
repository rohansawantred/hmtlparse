#!/usr/bin/env python3
"""
crawl_indigo_buttons.py

A Pyppeteer-based script that:
  1. Navigates to https://www.goindigo.in/
  2. Finds every <button> on the homepage.
  3. For each button:
     a. Determines related <input> fields using several heuristics:
        i.   Parse inline onclick for quoted IDs.
        ii.  data-target="<button_id>" on inputs.
        iii. Proximity: inputs in button.closest('div,section').
     b. Uses OpenAI to generate mock data for each related input.
     c. Fills those inputs.
     d. Highlights the button in red, clicks it, waits for “networkidle2.”
     e. Takes a full‐page screenshot and annotates it with the action (e.g. “Clicked button '…'”).
     f. Reloads the homepage to reset state before processing the next button.
  4. Compiles all annotated screenshots into a single PDF.

Dependencies:
    pip install pyppeteer openai pillow

Usage:
    export OPENAI_API_KEY="sk-..."
    python crawl_indigo_buttons.py
"""

import os
import asyncio
import re
from io import BytesIO
from urllib.parse import urlparse, urljoin
from pyppeteer import launch
import openai
import time
from PIL import Image, ImageDraw, ImageFont

openai.api_key = os.getenv("OPENAI_API_KEY")
HOME_URL = "https://www.goindigo.in/"

async def generate_mock_value(field_info: dict) -> str:
    """
    Use OpenAI to generate a realistic mock value for a form field.
    """
    print(f"[LOG] Generating mock value for field: {field_info}")
    prompt_parts = []
    for key in ("name", "id", "placeholder", "type"):
        if field_info.get(key):
            prompt_parts.append(f"{key}='{field_info[key]}'")
    desc = ", ".join(prompt_parts) or "no attributes"
    user_prompt = (
        f"Generate a realistic mock input for a form field with {desc}. "
        "Keep it concise (e.g. 'john_doe', 'test@example.com', 'Password123')."
    )
    try:
        resp = await openai.ChatCompletion.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a test data generator."},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        mock_value = resp.choices[0].message.content.strip()
        print(f"[LOG] Received mock value: {mock_value}")
        return mock_value
    except Exception as e:
        print(f"[WARN] OpenAI call failed: {e}. Using default 'test'.")
        return "test"


async def collect_related_input_ids(page, button_js_handle) -> list[str]:
    """
    Given a Button element handle, return a list of IDs for related <input> fields,
    using heuristics in this order:
      1) Parse inline onclick='…' for quoted IDs.
      2) Look for inputs with data‐target='<button_id>'.
      3) Proximity: inputs inside button.closest('div,section').
    """
    print("[LOG] Collecting related input IDs for button")
    # 1) inline onclick → parse quoted IDs
    onclick_attr = await page.evaluate(
        "(btn) => btn.getAttribute('onclick') || ''", button_js_handle
    )
    ids = []
    if onclick_attr:
        print(f"[LOG] Found onclick attribute: {onclick_attr}")
        raw_ids = re.findall(r"['\"]([^'\"]+)['\"]", onclick_attr)
        for rid in raw_ids:
            exists = await page.evaluate("(id) => !!document.getElementById(id)", rid)
            if exists:
                print(f"[LOG] Input ID '{rid}' exists in DOM")
                ids.append(rid)
        if ids:
            print(f"[LOG] Using inline onclick IDs: {ids}")
            return ids

    # 2) data‐target="<button_id>"
    btn_id = await page.evaluate("(btn) => btn.id || ''", button_js_handle)
    if btn_id:
        print(f"[LOG] Button has ID: {btn_id}, looking for inputs with data-target")
        ids_via_data = await page.evaluate(
            """
            (buttonId) => {
              const out = [];
              document
                .querySelectorAll(`input[data-target="${buttonId}"]`)
                .forEach(el => { if (el.id) out.push(el.id); });
              return out;
            }
            """,
            btn_id
        )
        if ids_via_data:
            print(f"[LOG] Found inputs via data-target: {ids_via_data}")
            return ids_via_data

    # 3) proximity: inputs inside button.closest('div,section')
    print("[LOG] Looking for inputs in the same container as the button")
    ids_in_container = await page.evaluate(
        """
        (btn) => {
          const out = [];
          const container = btn.closest('div, section');
          if (!container) return out;
          container.querySelectorAll("input[id]").forEach(inp => {
            out.push(inp.id);
          });
          return out;
        }
        """,
        button_js_handle
    )
    print(f"[LOG] Found inputs in container: {ids_in_container}")
    return ids_in_container


def annotate_image(img_bytes: bytes, label: str) -> Image.Image:
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
    bbox = draw.textbbox(text_pos, label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding = 6
    rect_end = (
        text_pos[0] + text_width + padding,
        text_pos[1] + text_height + (padding // 2)
    )
    # Draw semi-transparent background
    draw.rectangle([text_pos, rect_end], fill=(0, 0, 0, 180))
    # Draw the label text in white
    draw.text((text_pos[0] + 2, text_pos[1] + 2), label, font=font, fill=(255, 255, 255))

    return img


async def highlight_and_click(page, button_handle):
    """
    Highlights the given button in red (outline), clicks it,
    waits for “networkidle2” or a short timeout if no navigation,
    then removes the highlight.
    """
    print("[LOG] Highlighting button and attempting click")
    # Add a red outline
    await page.evaluate("(btn) => btn.style.outline = '3px solid red'", button_handle)

    try:
        # Try to click and wait for either navigation or network idle
        await asyncio.gather(
            page.waitForNavigation({"waitUntil": "networkidle2", "timeout": 10000}).catch(lambda _: None),
            button_handle.click()
        )
        print("[LOG] Click successful, waited for navigation/network idle")
    except Exception as e:
        print(f"[WARN] Click or navigation wait failed: {e}")

    # Remove the red outline
    await page.evaluate("(btn) => btn.style.outline = ''", button_handle)
    print("[LOG] Removed button highlight")


async def process_button(index: int, browser) -> Image.Image | None:
    """
    Opens a fresh page, navigates to HOME_URL, finds the index-th button,
    fills related inputs, clicks it, and returns a PIL Image screenshot
    annotated with the action “Clicked button '…'”.
    If the index is out of range, returns None.
    """
    print(f"[LOG] process_button: Opening new page for button index {index}")
    page = await browser.newPage()
    await page.setViewport({"width": 1280, "height": 800})
    page.setDefaultNavigationTimeout(60000)

    # 1) Navigate to HOME_URL and wait for full load
    print(f"[LOG] Navigating to {HOME_URL}")
    try:
        await page.goto(HOME_URL, {"waitUntil": "networkidle2"})
        print("[LOG] Page loaded (networkidle2)")
        await asyncio.sleep(2)
    except Exception:
        print("[WARN] networkidle2 not reached, falling back to load event")
        await page.goto(HOME_URL, {"waitUntil": "load", "timeout": 60000})
        await asyncio.sleep(2)

    # 2) Query all buttons on the fully loaded page
    time.sleep(120)
    buttons = await page.querySelectorAll("button")
    print(f"[LOG] Found {len(buttons)} buttons on homepage")
    if index >= len(buttons):
        print(f"[WARN] Index {index} out of range (only {len(buttons)} buttons)")
        await page.close()
        return None

    btn = buttons[index]
    btn_text_init = await page.evaluate("(btn) => btn.outerText.trim()", btn) or "<no-text>"
    print(f"[LOG] Processing button {index}: '{btn_text_init}'")

    # 3) Collect IDs of related inputs
    input_ids = await collect_related_input_ids(page, btn)
    print(f"[LOG] Related input IDs for button '{btn_text_init}': {input_ids}")

    # 4) Fill each input with LLM-generated mock data
    for inp_id in input_ids:
        try:
            print(f"[LOG] Retrieving attributes for input ID '{inp_id}'")
            field_info = await page.evaluate(
                """
                (id) => {
                  const el = document.getElementById(id);
                  return {
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    type: el.getAttribute('type') || 'text'
                  };
                }
                """,
                inp_id
            )
            mock = await generate_mock_value(field_info)
            print(f"[LOG] Filling input '{inp_id}' with mock value '{mock}'")
            inp_handle = await page.querySelector(f"#{inp_id}")
            await inp_handle.click({"clickCount": 3})
            await inp_handle.type(mock, {"delay": 50})
        except Exception as e:
            print(f"[WARN] Failed to fill input '{inp_id}': {e}")

    # 5) Highlight and click
    btn_text = await page.evaluate("(btn) => btn.outerText.trim()", btn) or "<no-text>"
    print(f"[LOG] About to highlight and click button '{btn_text}'")
    await highlight_and_click(page, btn)
    await asyncio.sleep(2)

    # 6) Take full‐page screenshot as bytes
    print(f"[LOG] Taking screenshot after clicking button '{btn_text}'")
    img_bytes = await page.screenshot({"fullPage": True})

    # 7) Annotate the image with the action label
    label = f"Clicked button '{btn_text}' (index {index})"
    annotated_img = annotate_image(img_bytes, label)
    print(f"[LOG] Annotated screenshot for button '{btn_text}'")

    await page.close()
    print(f"[LOG] Closed page for button index {index}")
    return annotated_img


async def main():
    # --------------- Launch browser ---------------
    print("[LOG] Launching browser")
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

    browser = await launch(launch_opts)
    print("[LOG] Browser launched")

    # --------------- Count buttons on homepage ---------------
    print(f"[LOG] Opening a temporary page to count buttons on {HOME_URL}")
    temp_page = await browser.newPage()
    temp_page.setDefaultNavigationTimeout(60000)
    try:
        await temp_page.goto(HOME_URL, {"waitUntil": "networkidle2"})
        print("[LOG] temp_page networkidle2 complete")
        await asyncio.sleep(2)
    except Exception:
        print("[WARN] temp_page networkidle2 failed, using load event")
        await temp_page.goto(HOME_URL, {"waitUntil": "load", "timeout": 60000})
        await asyncio.sleep(2)
    
    time.sleep(120)
    all_buttons = await temp_page.querySelectorAll("button")
    total_buttons = len(all_buttons)
    print(f"[LOG] Found {total_buttons} buttons on homepage")
    await temp_page.close()

    # --------------- Process each button and collect screenshots ---------------
    screenshots = []
    for i in range(total_buttons):
        print(f"[LOG] Starting process for button index {i}/{total_buttons-1}")
        img = await process_button(i, browser)
        if img is None:
            print(f"[WARN] Button index {i} out of range or failed; stopping loop.")
            break
        screenshots.append(img)
        print(f"[LOG] Completed processing button index {i}")

    print("[LOG] All button processing complete, closing browser")
    await browser.close()

    # --------------- Compile screenshots into a single PDF ---------------
    if screenshots:
        pdf_path = "results.pdf"
        print(f"[LOG] Compiling {len(screenshots)} screenshots into PDF '{pdf_path}'")
        try:
            screenshots[0].save(
                pdf_path,
                save_all=True,
                append_images=screenshots[1:],
                format="PDF"
            )
            print(f"[INFO] Saved all annotated screenshots into '{pdf_path}'")
        except Exception as e:
            print(f"[ERROR] Could not save PDF: {e}")
    else:
        print("[WARN] No screenshots captured; PDF not created.")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
