import os
import io
import json
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

# Load environment variables from .env (if present)
load_dotenv()

# --- CRITICAL FIX: Explicitly fetch and configure the key ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    # This raises a clear error in your logs if the key is missing
    raise ValueError("❌ GEMINI_API_KEY not found in environment variables! Please add it to your Codespace Secrets.")

# Configure the Gemini API with the specific key
genai.configure(api_key=GEMINI_API_KEY)
# ------------------------------------------------------------

# Use Gemini 3.0 Flash (Preview)
MODEL_NAME = "gemini-3.0-flash"

def analyze_slide_image(image: Image.Image) -> dict:
    """
    Sends a slide image to Gemini and receives structured, validated semantic data.
    """
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        
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
        
        # Send the image and prompt to Gemini
        response = model.generate_content([prompt, image])
        
        # Extract JSON from the response text
        text = response.text.strip()
        
        # Clean up Markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
            
        data = json.loads(text)
        return data

    except Exception as e:
        print(f"Error analyzing slide: {e}")
        # Fail gracefully with a default structure if the AI output is malformed or API fails
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
            print(f"Error cropping figure: {e}")
            continue
        
    return processed_figures