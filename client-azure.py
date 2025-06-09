import asyncio
import os
import sys
import json
import base64
from io import BytesIO
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from PIL import Image, ImageDraw, ImageFont
import textwrap
from pyobjtojson import obj_to_json

# Browser-Use & LangChain
from browser_use import Agent
from langchain_openai import ChatOpenAI

# Azure OpenAI SDK (for final script generation)
import openai

# ─── Configuration ────────────────────────────────────────────────────────────

# Azure OpenAI settings from env
AZURE_API_BASE        = os.getenv("AZURE_OPENAI_API_BASE")
AZURE_API_KEY         = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION     = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

# Configure the openai python SDK to use Azure
openai.api_type    = "azure"
openai.api_base    = AZURE_API_BASE
openai.api_version = AZURE_API_VERSION
openai.api_key     = AZURE_API_KEY

# Prepare LangChain ChatOpenAI to also use Azure
llm = ChatOpenAI(
    model="gpt-4o",
    openai_api_type="azure",
    openai_api_base=AZURE_API_BASE,
    openai_api_version=AZURE_API_VERSION,
    openai_api_key=AZURE_API_KEY,
    deployment_name=AZURE_DEPLOYMENT_NAME
)

# ─── Globals ─────────────────────────────────────────────────────────────────

SCREENSHOT_DIR  = "screenshots"
PDF_OUTPUT_PATH = "step_by_step.pdf"
SELENIUM_SCRIPT = "generated_selenium_script.py"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
screenshots: list[str] = []
actionslist: list = []

# ─── Helper Functions ─────────────────────────────────────────────────────────

def bytes_to_image(img_bytes: bytes) -> Image.Image:
    buf = BytesIO(img_bytes)
    img = Image.open(buf)
    img.load()
    return img

def annotate_pil_image(
    img: Image.Image,
    text: str,
    position: tuple[int,int],
    font_path: str|None = None,
    font_size: int = 80,
    fill=(255,0,0),
    outline_fill=(0,0,0),
    outline_width: int = 3,
    max_width_ratio: float = 0.95,
    max_height_ratio: float = 0.3,
    box_bg=(0,0,0,128),
    explicit_box: tuple[int,int]|None = None
) -> Image.Image:
    base = img.convert("RGBA")
    txt_layer = Image.new("RGBA", base.size, (0,0,0,0))
    draw = ImageDraw.Draw(txt_layer)
    try:
        font = ImageFont.truetype(font_path or "DejaVuSans.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    w_img, h_img = base.size
    if explicit_box:
        box_w, box_h = explicit_box
    else:
        box_w = int(w_img * max_width_ratio)
        box_h = int(h_img * max_height_ratio)

    lines = []
    for para in text.split("\n"):
        for chunk in textwrap.wrap(para, width=40):
            words = chunk.split()
            if not words:
                continue
            line = words[0]
            for w in words[1:]:
                test = f"{line} {w}"
                bbox = draw.textbbox((0,0), test, font=font)
                if (bbox[2]-bbox[0]) <= box_w:
                    line = test
                else:
                    lines.append(line)
                    line = w
            lines.append(line)
    if not lines:
        lines = [""]

    # measure line height
    bbox = draw.textbbox((0,0), "Ay", font=font)
    line_h = (bbox[3]-bbox[1]) + int(font_size*0.2)
    total_h = line_h * len(lines)

    x0,y0 = position
    x1,y1 = x0+box_w, y0+total_h
    draw.rectangle(
        [x0-outline_width, y0-outline_width, x1+outline_width, y1+outline_width],
        fill=box_bg
    )

    y = y0
    for line in lines:
        for dx in range(-outline_width, outline_width+1):
            for dy in range(-outline_width, outline_width+1):
                if dx==0 and dy==0: continue
                draw.text((x0+dx,y+dy), line, font=font, fill=outline_fill)
        draw.text((x0,y), line, font=font, fill=fill)
        y += line_h

    out = Image.alpha_composite(base, txt_layer)
    return out.convert(img.mode)


async def record_activity(agent_obj):
    """
    on_step_end hook:  
    1. Takes a screenshot  
    2. Annotates it with the LLM’s last evaluation  
    3. Captures and appends the last action to actionslist  
    """
    # 1. Screenshot
    screenshot_b64 = await agent_obj.browser_context.take_screenshot()
    img_bytes = base64.b64decode(screenshot_b64)
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(SCREENSHOT_DIR, f"{now}.png")

    # 2. Annotate with previous goal evaluation
    history = getattr(agent_obj.state, "history", None)
    if history:
        thoughts = obj_to_json(history.model_thoughts(), check_circular=False)
        if thoughts:
            eval_msg = thoughts[-1].get("evaluation_previous_goal", "")
            anno = annotate_pil_image(
                bytes_to_image(img_bytes),
                text=eval_msg,
                position=(20,20),
                font_size=48,
                max_height_ratio=0.5
            )
            anno.save(file_path)
        else:
            with open(file_path, "wb") as f:
                f.write(img_bytes)
    else:
        with open(file_path, "wb") as f:
            f.write(img_bytes)

    screenshots.append(file_path)

    # 3. Capture last action
    actions = obj_to_json(agent_obj.state.history.model_actions(), check_circular=False)
    if actions:
        actionslist.append(actions[-1])


# ─── Agent Setup & Execution ─────────────────────────────────────────────────

agent = Agent(
    task=(
        "1. goto www.goindigo.in\n"
        "2. click the Web Check-in CTA\n"
        "3. enter PNR 'TYIOPER'\n"
        "4. enter Last Name 'Doe'\n"
        "5. click Web Check-in"
    ),
    llm=llm,
)

async def run_agent():
    # run the agent with our hook
    await agent.run(on_step_end=record_activity, max_steps=30)

    # combine screenshots into PDF
    if screenshots:
        images = [Image.open(p).convert("RGB") for p in screenshots]
        images[0].save(PDF_OUTPUT_PATH, save_all=True, append_images=images[1:])
        print("Saved PDF:", PDF_OUTPUT_PATH)

    print("Captured actions:", json.dumps(actionslist, indent=2))

    # ─── Now generate a Selenium script from actionslist ────────────────────────
    if actionslist:
        prompt = (
            "You are a Python expert. Generate a complete Selenium Python script that "
            "performs the following browser actions in order:\n\n"
            + "\n".join(f"{i+1}. {json.dumps(a)}" for i,a in enumerate(actionslist))
        )

        response = openai.ChatCompletion.create(
            engine=AZURE_DEPLOYMENT_NAME,
            messages=[
                {"role":"system","content":"You generate Python Selenium scripts."},
                {"role":"user","content":prompt}
            ]
        )
        selenium_code = response.choices[0].message.content

        with open(SELENIUM_SCRIPT, "w") as f:
            f.write(selenium_code)
        print("Generated Selenium script:", SELENIUM_SCRIPT)

if __name__ == "__main__":
    asyncio.run(run_agent())
