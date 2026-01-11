import os
import io
import json
import base64
from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv

import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- CRITICAL CONFIG ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found in environment variables")
    raise ValueError("❌ OPENAI_API_KEY not found! Please Reload Window (Ctrl+Shift+P > Reload Window) or check Secrets.")

# Initialize OpenAI Client
client = OpenAI(api_key=OPENAI_API_KEY)

# Use GPT-4o Mini (Cost-effective Vision model)
MODEL_NAME = "gpt-4o-mini"

def encode_image(image: Image.Image) -> str:
    """Encodes a PIL Image to a base64 string for OpenAI."""
    buffered = io.BytesIO()
    # Resize if too massive to save tokens/bandwidth (optional but recommended)
    # image.thumbnail((2048, 2048)) 
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def analyze_slide_image(image: Image.Image) -> dict:
    """
    Sends a slide image to GPT-4o-mini and receives structured JSON data.
    """
    try:
        logger.info("Encoding image for analysis...")
        # Convert image to base64
        base64_image = encode_image(image)

        prompt = """
        Analyze this slide image and return a JSON object that strictly follows this schema:
        {
          "layout_type": "title_only | title_and_content | two_column | image_left_text_right | image_right_text_left | full_image | diagram_heavy | mixed_freeform",
          "title": "Slide title text",
          "body_text": ["Bullet 1", "Bullet 2"],
          "speaker_notes": "Inferred notes...",
          "figures": [
            {
              "description": "Chart description",
              "box_2d": [ymin, xmin, ymax, xmax] 
            }
          ]
        }
        
        Constraints:
        - Identify charts, diagrams, and photos as `figures`.
        - Do NOT include the Title or Body Text in the bounding box for figures.
        - Coordinates in `box_2d` must be integers scaled from 0-1000.
        - If a chart has text labels inside it, treat the whole thing as a Figure.
        - Return ONLY the JSON object.
        """

        logger.info(f"Sending request to OpenAI model: {MODEL_NAME}")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"}, # Forces valid JSON
            max_tokens=4096,
        )

        # Parse the JSON response
        content = response.choices[0].message.content
        logger.info(f"Raw OpenAI response content: {content[:500]}...")
        data = json.loads(content)
        logger.info(f"Parsed data keys: {list(data.keys())}")
        logger.info(f"Parsed title: {data.get('title', 'NO TITLE')}")
        logger.info(f"Parsed body_text: {data.get('body_text', [])}")
        return data

    except Exception as e:
        logger.error(f"Error analyzing slide: {e}", exc_info=True)
        # print(f"Error analyzing slide: {e}") # removed duplicate print
        return {
            "layout_type": "mixed_freeform",
            "title": "Error Processing Slide",
            "body_text": ["Could not analyze this slide."],
            "speaker_notes": "",
            "figures": []
        }

def crop_figures_from_slide(original_image: Image.Image, figures: list[dict]) -> list[dict]:
    """
    Crops visual elements from the slide image using AI-provided coordinates (0-1000 scaled).
    """
    width, height = original_image.size
    processed_figures = []
    
    for fig in figures:
        box = fig.get("box_2d")
        if not box or len(box) != 4:
            continue
            
        # Coordinates are [ymin, xmin, ymax, xmax] scaled 0-1000
        ymin, xmin, ymax, xmax = box
        
        # Convert to pixel coordinates
        left = (xmin / 1000) * width
        top = (ymin / 1000) * height
        right = (xmax / 1000) * width
        bottom = (ymax / 1000) * height
        
        # Crop the image
        try:
            cropped_img = original_image.crop((left, top, right, bottom))
            
            # Save to BytesIO buffer
            img_byte_arr = io.BytesIO()
            cropped_img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            # Add the image bytes to the figure data
            fig_copy = fig.copy()
            fig_copy["image_bytes"] = img_byte_arr.read()
            processed_figures.append(fig_copy)
        except Exception as e:
            logger.error(f"Error cropping figure: {e}", exc_info=True)
            continue
        
    return processed_figures