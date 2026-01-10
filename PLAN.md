# Project: NotebookLM PDF to Editable PPTX Rebuilder

## Goal
Convert flattened NotebookLM PDFs into fully editable PowerPoint files. The core logic is to **infer the layout intent** (e.g., "Two Column", "Title Only") using Vision AI, extract text into native editable placeholders, and crop visuals (charts/diagrams) as separate images.

## Safety & Compliance (UK/GDPR)
* **Ephemeral Processing:** Files are processed in RAM and deleted immediately after the request closes. No disk storage.
* **Data Minimization:** No content (text or extracted JSON) is logged to the console.
* **Transience:** The service acts as a technical conduit only.

## Core Tech Stack
* **Backend:** Python 3.11+, FastAPI
* **AI/Vision:** Google Gemini 3.0 Flash (Preview)
* **Image Processing:** `pdf2image` (requires Poppler), `Pillow` (PIL)
* **PPTX:** `python-pptx`

---

## FOLDER STRUCTURE

notebook-to-pptx/
├── .gitignore               # Standard Python gitignore
├── .env                     # Local secrets (API Keys) - DO NOT COMMIT
├── PLAN.md                  # Your Execution Plan
├── requirements.txt         # Python dependencies
├── main.py                  # Entry point (FastAPI application & Routes)
├── services/                # Business Logic Layer
│   ├── __init__.py          # Makes this a Python package
│   ├── pdf_processor.py     # Handles PDF -> Image conversion (Poppler)
│   ├── vision_processor.py  # Handles Gemini AI calls & Image Cropping
│   └── ppt_builder.py       # Handles .pptx file generation
└── static/                  # Frontend Layer
    └── index.html           # Simple UI for drag-and-drop

---

## EXECUTION STEPS

### [ ] Step 1: PDF Ingestion & Image Conversion
**Objective:** Convert a NotebookLM PDF into high-resolution images, one page at a time, without loading the entire document into memory.
**Instructions for AI:**
1.  Open `services/pdf_processor.py`.
2.  Import `pdf2image.convert_from_bytes`, `PIL.Image`, and `typing.Iterator`.
3.  Implement a function: `convert_pdf_to_images(pdf_bytes: bytes) -> Iterator[Image.Image]`.
4.  **Critical Implementation Details:**
    * Use `convert_from_bytes`.
    * Set `dpi=300` (High Res is needed for cropping charts later).
    * **Yield** each page as a `PIL.Image` (do not return a list, to save RAM).
    * **Strict Rule:** Do not save images to disk.
5.  *Note:* Remind me that `poppler` must be installed on the OS (e.g., `sudo apt-get install poppler-utils` in Codespaces).

### [ ] Step 2: Vision Analysis & Layout Inference
**Objective:** Send a slide image to Gemini and receive structured, validated semantic data.
**Instructions for AI:**
1.  Open `services/vision_processor.py`.
2.  Setup `google-generativeai` with `GEMINI_API_KEY` from environment variables.
3.  Configure the model to use **Gemini 3.0 Flash**.
4.  Implement `analyze_slide_image(image: Image.Image) -> dict`.
5.  **The Prompt:** Construct a strict prompt asking for this JSON schema:
    ```json
    {
      "layout_type": "title_only | title_and_content | two_column | image_left_text_right | image_right_text_left | full_image | diagram_heavy | mixed_freeform",
      "title": "Slide title text",
      "body_text": ["Bullet 1", "Bullet 2"],
      "speaker_notes": "Inferred notes...",
      "figures": [
        {
          "description": "Chart description",
          "box_2d": [ymin, xmin, ymax, xmax] // Scale 0-1000
        }
      ]
    }
    ```
6.  **Constraints:**
    * "Identify charts, diagrams, and photos as `figures`. Do NOT include the Title or Body Text in the bounding box."
    * "Coordinates must be integers 0-1000."
    * "If a chart has text labels inside it, treat the whole thing as a Figure."
7.  **Safety Rule:** Do not log the raw JSON response to the console.

### [ ] Step 3: Image Cropping Utility
**Objective:** Crop visual elements from the slide image using AI-provided coordinates.
**Instructions for AI:**
1.  Stay in `services/vision_processor.py`.
2.  Implement `crop_figures_from_slide(original_image: Image.Image, figures: list[dict]) -> list[dict]`.
3.  **Logic:**
    * Iterate through `figures`.
    * Convert 0-1000 `box_2d` coordinates to pixel coordinates (`y/1000 * height`).
    * Use `PIL.Image.crop((left, top, right, bottom))`.
    * Save the cropped image to a `BytesIO` buffer.
    * Add the buffer to the dictionary key `image_bytes`.
    * Return the updated figures list.

### [ ] Step 4: PPTX Builder & Layout Reconstruction
**Objective:** Rebuild each slide in PPTX format using layout intent, editable text boxes, and positioned images.
**Instructions for AI:**
1.  Open `services/ppt_builder.py`.
2.  Import `Presentation` from `python-pptx` and `BytesIO`.
3.  Implement `generate_pptx(slides_data: list[dict]) -> BytesIO`.
4.  **Logic:**
    * Initialize `Presentation()`.
    * Loop through `slides_data`.
    * **Layout Switching:** Use `layout_type` to determine placement.
        * *If "title_and_content":* Use standard placeholders.
        * *If "two_column":* Create two text boxes side-by-side.
    * **Text:** Insert `title` and `body_text` into **editable** text frames.
    * **Images:** Iterate through `figures`. Use `slide.shapes.add_picture(figure['image_bytes'], ...)` positioning them based on their approximate coordinates.
    * **Notes:** Add `speaker_notes` to the notes slide.
5.  Save to `BytesIO` and return.

### [ ] Step 5: API Endpoint & Pipeline Integration
**Objective:** Connect all services into a single `/convert` endpoint with **Adaptive Rate Limiting** for Gemini Preview.
**Instructions for AI:**
1.  Open `main.py`.
2.  Add `POST /convert`.
3.  **Implement Adaptive Timer Logic:**
    * Initialize `current_delay = 5` (seconds).
    * Loop `page_image` in `pdf_processor.convert_pdf_to_images(file.read())`:
        * **Try:**
            * Sleep for `current_delay`.
            * Call `vision_processor.analyze_slide_image(page_image)`.
        * **Except (429 Too Many Requests):**
            * Log "Rate limit hit. Increasing delay."
            * Increase `current_delay` (e.g., `current_delay += 5`).
            * Sleep `current_delay` and **Retry** the same slide.
        * **On Success:**
            * Proceed to crop figures and append data.
    * `pptx_file = ppt_builder.generate_pptx(slides_data)`
    * Return `StreamingResponse` (media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation").

### [ ] Step 6: Frontend Drag-and-Drop UI
**Objective:** Provide a minimal browser interface.
**Instructions for AI:**
1.  Open `static/index.html`.
2.  Create a clean UI:
    * File drop zone (accepts `.pdf`).
    * "Convert" Button.
    * **Disclaimer:** Add a text: *"Files are processed in memory and deleted immediately. No data is stored."*
    * **Status Log:** A simple `div` to show messages like "Analyzing Slide 3...".
3.  **JS:** Use `fetch` to POST the file. Handle the binary blob response and trigger a download of `converted.pptx`.