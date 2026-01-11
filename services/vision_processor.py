import os
import io
import json
import base64
import logging
from openai import OpenAI
from PIL import Image
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found!")

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_NAME = "gpt-4o"


def encode_image(image: Image.Image) -> str:
    """Encode image to base64, resizing for API efficiency."""
    buffered = io.BytesIO()
    img_copy = image.copy()
    img_copy.thumbnail((1536, 1536))  # Larger for better text recognition
    img_copy.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def analyze_slide_image(image: Image.Image) -> dict:
    """
    Analyze a slide image and extract structured content.
    Focus: Complete text extraction with minimal image cropping.
    """
    try:
        base64_image = encode_image(image)

        prompt = """You are a slide content extractor. Analyze this slide image and extract ALL text content.

CRITICAL RULES:
1. Extract EVERY piece of readable text from the slide into either "title" or "body_text"
2. The title is usually the largest text at the top
3. body_text should be an array of strings - each bullet point or paragraph as a separate item
4. Extract text COMPLETELY - do not summarize or truncate
5. For figures: ONLY create a figure entry for actual images/charts/diagrams/icons - NOT for text boxes
6. Figure bounding boxes should EXCLUDE any text labels near them

OUTPUT JSON SCHEMA:
{
  "layout_type": "title_only | title_and_content | two_column | diagram_heavy",
  "title": "The exact title text from the slide",
  "body_text": [
    "First bullet point or paragraph - complete text",
    "Second bullet point or paragraph - complete text",
    "Third point..."
  ],
  "speaker_notes": "Brief summary for speaker notes",
  "figures": [
    {
      "description": "what the image shows",
      "box_2d": [ymin, xmin, ymax, xmax]
    }
  ]
}

LAYOUT TYPE GUIDE:
- "title_only": Slide with just a title and maybe one large image
- "title_and_content": Title with bullet points/text (most common)
- "two_column": Two distinct sections side by side
- "diagram_heavy": Dominated by a large diagram/chart with minimal text

COORDINATE FORMAT for figures:
- box_2d: [ymin, xmin, ymax, xmax] where values are 0-1000 scale
- ymin/ymax: vertical position (0=top, 1000=bottom)
- xmin/xmax: horizontal position (0=left, 1000=right)

Return ONLY valid JSON."""

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=4096,
        )

        content = response.choices[0].message.content
        data = json.loads(content)
        
        # Log what we got
        logger.info(f"Extracted: title='{data.get('title', '')[:50]}...', "
                   f"body_items={len(data.get('body_text', []))}, "
                   f"figures={len(data.get('figures', []))}")
        
        return data

    except Exception as e:
        logger.error(f"Error analyzing slide: {e}", exc_info=True)
        return {
            "layout_type": "title_and_content",
            "title": "Error Processing Slide",
            "body_text": ["Could not analyze this slide. Check logs for details."],
            "speaker_notes": "",
            "figures": []
        }


def crop_figures_from_slide(original_image: Image.Image, figures: list[dict]) -> list[dict]:
    """Crop figures from the slide using AI-provided coordinates (0-1000 scale)."""
    width, height = original_image.size
    processed_figures = []
    
    for fig in figures:
        box = fig.get("box_2d")
        if not box or len(box) != 4:
            continue
        
        ymin, xmin, ymax, xmax = box
        
        # Validate coordinates
        if ymin >= ymax or xmin >= xmax:
            logger.warning(f"Invalid box coordinates: {box}")
            continue
        
        # Convert to pixel coordinates
        left = int((xmin / 1000) * width)
        top = int((ymin / 1000) * height)
        right = int((xmax / 1000) * width)
        bottom = int((ymax / 1000) * height)
        
        # Clamp to image bounds
        left = max(0, min(left, width))
        right = max(0, min(right, width))
        top = max(0, min(top, height))
        bottom = max(0, min(bottom, height))
        
        # Minimum size check
        if (right - left) < 50 or (bottom - top) < 50:
            logger.warning(f"Figure too small, skipping: {right-left}x{bottom-top}")
            continue
        
        try:
            cropped = original_image.crop((left, top, right, bottom))
            
            img_bytes = io.BytesIO()
            cropped.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            fig_copy = fig.copy()
            fig_copy["image_bytes"] = img_bytes.read()
            processed_figures.append(fig_copy)
            
        except Exception as e:
            logger.error(f"Error cropping figure: {e}")
            continue
    
    return processed_figures
