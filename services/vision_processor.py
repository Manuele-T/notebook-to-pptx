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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found")
    raise ValueError("❌ OPENAI_API_KEY not found! Reload Window (Ctrl+Shift+P > Reload Window)")

client = OpenAI(api_key=OPENAI_API_KEY)

MODEL_NAME = "gpt-4o" 

def encode_image(image: Image.Image) -> str:
    """Encodes a PIL Image to a base64 string, resizing it for speed."""
    buffered = io.BytesIO()
    analysis_img = image.copy()
    # Resize to max 1024px to prevent 504 Timeouts
    analysis_img.thumbnail((1024, 1024)) 
    analysis_img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def analyze_slide_image(image: Image.Image) -> dict:
    """
    Sends a slide image to GPT-4o and receives structured JSON data.
    """
    try:
        base64_image = encode_image(image)

        # --- "DECONSTRUCTIVE CROPPING" PROMPT ---
        system_prompt = """
        You are a Slide Decomposition Engine. Your ONLY job is to separate PIXELS (Images) from TEXT (Strings).
        
        ### CRITICAL INSTRUCTION: THE "NO TEXT IN IMAGE" RULE
        You must NEVER include readable bullet points, paragraphs, or sentences inside a `figure` bounding box.
        If you see an image next to text, you must SURGICALLY CROP only the visual element.
        
        ### SCENARIO 1: COMPARISON SLIDES (e.g., "The Past vs The Future")
        - **Visual:** You see an icon (e.g., a Hammer) and an icon (e.g., a Blueprint).
        - **ACTION:** Create TWO separate figures.
          - Figure 1: [box_2d around ONLY the Hammer]
          - Figure 2: [box_2d around ONLY the Blueprint]
        - **Text:** Extract the text below the icons into `body_text`.
        - **ERROR TRAP:** Do NOT draw a box around the "Hammer AND the Text". That is a failure.
        
        ### SCENARIO 2: NETWORK/HUB DIAGRAMS (e.g., "Mission Control")
        - **Visual:** A central node connected by lines to outer nodes.
        - **ACTION:** This is a single complex diagram.
          - Figure 1: [box_2d around the Central Node + Lines + Outer Icons]
        - **Text:** There is usually explanatory text on the side (e.g., "Manager View: The primary interface...").
        - **ACTION:** Extract that text into `body_text`. Do NOT include it in the figure box.
        
        ### SCENARIO 3: TEXT LABELS INSIDE DIAGRAMS
        - If a word is INSIDE a blue box (e.g., "Manager View"), it is part of the image. Leave it alone. 
        - If a word is a paragraph NEXT TO the blue box, it is `body_text`. Extract it.
        
        ### OUTPUT FORMAT
        Return ONLY valid JSON.
        """

        user_prompt = """
        Analyze this slide. Deconstruct it strictly according to the rules.
        
        Schema:
        {
          "layout_type": "title_only | title_and_content | two_column | diagram_heavy | mixed_freeform",
          "title": "Clean Title",
          "body_text": ["Bullet 1", "Bullet 2"],
          "figures": [
            {
              "description": "hammer_icon",
              "box_2d": [ymin, xmin, ymax, xmax] 
            }
          ]
        }
        """

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
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
        return data

    except Exception as e:
        logger.error(f"Error analyzing slide: {e}", exc_info=True)
        return {
            "layout_type": "title_and_content",
            "title": "Error Processing Slide",
            "body_text": ["Analysis failed. Check logs."],
            "figures": []
        }

def crop_figures_from_slide(original_image: Image.Image, figures: list[dict]) -> list[dict]:
    """Crops visual elements from the slide image using AI-provided coordinates (0-1000 scaled)."""
    width, height = original_image.size
    processed_figures = []
    
    for fig in figures:
        box = fig.get("box_2d")
        if not box or len(box) != 4:
            continue
            
        ymin, xmin, ymax, xmax = box
        
        # Convert to pixel coordinates
        left = (xmin / 1000) * width
        top = (ymin / 1000) * height
        right = (xmax / 1000) * width
        bottom = (ymax / 1000) * height
        
        try:
            cropped_img = original_image.crop((left, top, right, bottom))
            
            img_byte_arr = io.BytesIO()
            cropped_img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            fig_copy = fig.copy()
            fig_copy["image_bytes"] = img_byte_arr.read()
            processed_figures.append(fig_copy)
        except Exception as e:
            logger.error(f"Error cropping figure: {e}", exc_info=True)
            continue
        
    return processed_figures