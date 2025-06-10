import asyncio
import os
import json
import base64
import argparse
import zipfile
from io import BytesIO
from datetime import datetime

import yaml
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import textwrap
from pyobjtojson import obj_to_json

# Browser-Use & LangChain
from browser_use import Agent
from langchain_openai import ChatOpenAI

# Azure OpenAI SDK (for final script generation)
import openai

# ─── CLI Argument Parsing ───────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    description="Record browser agent activity and generate a Selenium script"
)
parser.add_argument(
    '--task', '-t',
    action='append',
    required=True,
    help='One browser automation task step; can be specified multiple times'
)
parser.add_argument(
    '--prompt-file', '-p',
    required=True,
    help='YAML file path with system_prompt and user_prompt templates'
)
parser.add_argument(
    '--screenshot-dir', '-s',
    default='screenshots',
    help='Directory to save step screenshots'
)
parser.add_argument(
    '--selenium-script', '-o',
    default='generated_selenium_script.py',
    help='Output path for generated Selenium script'
)
parser.add_argument(
    '--zip-output', '-z',
    default='output_bundle.zip',
    help='Output ZIP file name'
)
args = parser.parse_args()

# ─── Load Prompt Templates ───────────────────────────────────────────────────
with open(args.prompt_file, 'r') as f:
    prompts = yaml.safe_load(f)

SYSTEM_PROMPT = prompts.get('system_prompt', 'You generate Python Selenium scripts.')
USER_PROMPT_TEMPLATE = prompts.get(
    'user_prompt',
    "Generate a complete Selenium Python method named `{method_name}` that performs the following browser actions in order:\n\n{actions_list}"
)

# ─── Configuration ────────────────────────────────────────────────────────────
SCREENSHOT_DIR  = args.screenshot_dir
PDF_OUTPUT_PATH = "step_by_step.pdf"
SELENIUM_SCRIPT = args.selenium_script
ZIP_OUTPUT      = args.zip_output

# Ensure screenshot directory exists
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Azure OpenAI settings from env
load_dotenv()
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
    website_screenshot: str = await agent_obj.browser_context.take_screenshot()
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    file_name = f"{timestamp}.png"
    file_path = os.path.join(SCREENSHOT_DIR, file_name)
    img_bytes = base64.b64decode(website_screenshot)

    #with open(file_path, "wb") as f:
    #    f.write(img_bytes)

    print(f"Saved image to {file_path}")
    """Hook function that captures and records agent activity at each step"""
    model_thoughts_last_elem = None
    model_outputs_json_last_elem = None
    model_actions_json_last_elem = None

    print('--- ON_STEP_START HOOK ---')
    

    # Make sure we have state history
    if hasattr(agent_obj, "state"):
        history = agent_obj.state.history
    else:
        history = None
        print("Warning: Agent has no state history")
        return

    # Process model thoughts
    model_thoughts = obj_to_json(
        obj=history.model_thoughts(),
        check_circular=False
    )
    if len(model_thoughts) > 0:
        model_thoughts_last_elem = model_thoughts[-1]
    print(model_thoughts_last_elem)
    #model_thoughts_last_elem.evaluation_previous_goal
    annotated = annotate_pil_image(
        bytes_to_image(img_bytes),
        text=model_thoughts_last_elem["evaluation_previous_goal"],
        position=(50, 50),
        font_path=None,
        font_size=48,
        fill=(255, 255, 0),
        outline_fill=(0, 0, 0),
        outline_width=2,
        max_height_ratio=0.8
    )
    
    annotated.save(file_path)
    #with open(file_path, "wb") as f:
    #    f.write(img_bytes)
    # Process model outputs
    model_outputs = agent_obj.state.history.model_outputs()
    model_outputs_json = obj_to_json(
        obj=model_outputs,
        check_circular=False
    )
    if len(model_outputs_json) > 0:
        model_outputs_json_last_elem = model_outputs_json[-1]
    lastentry=int(len(model_outputs_json_last_elem["action"]))
    # Process model actions
    model_actions = agent_obj.state.history.model_actions()
    model_actions_json = obj_to_json(
        obj=model_actions,
        check_circular=False
    )
    #lastentry=int(len(model_actions_json["action"]))
    if len(model_actions_json) > 0:
        model_actions_json_last_elem = model_actions_json[-abs(lastentry):]  
    prev_result=model_outputs_json_last_elem["current_state"]["evaluation_previous_goal"]
    prev_memory=model_outputs_json_last_elem["current_state"]["memory"]
    if "Success" not in prev_result:
        if "error message" not in prev_memory:
            if actionslist:
                actionslist.pop()
    actionslist.append(model_actions_json_last_elem)
    screenshots.append(file_path)

# ─── Agent Setup & Execution ─────────────────────────────────────────────────
task_description = "\n".join(args.task)
agent = Agent(task=task_description, llm=llm)

async def run_agent():
    await agent.run(on_step_end=record_activity, max_steps=30)

    if screenshots:
        images = [Image.open(p).convert("RGB") for p in screenshots]
        images[0].save(PDF_OUTPUT_PATH, save_all=True, append_images=images[1:])
        print("Saved PDF:", PDF_OUTPUT_PATH)

    print("Captured actions:", json.dumps(actionslist, indent=2))

    if actionslist:
        resp = openai.ChatCompletion.create(
            engine=AZURE_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Convert the following task description into a concise Python snake_case method name."},
                {"role": "user", "content": task_description}
            ]
        )
        method_name = resp.choices[0].message.content.strip().replace(' ', '_')

        actions_list_str = "\n".join(f"{i+1}. {json.dumps(a)}" for i, a in enumerate(actionslist))
        user_prompt = USER_PROMPT_TEMPLATE.format(method_name=method_name, actions_list=actions_list_str)

        response = openai.ChatCompletion.create(
            engine=AZURE_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt}
            ]
        )
        selenium_code = response.choices[0].message.content
        with open(SELENIUM_SCRIPT, "w") as f:
            f.write(selenium_code)
        print("Generated Selenium script:", SELENIUM_SCRIPT)



if __name__ == "__main__":
    asyncio.run(run_agent())
