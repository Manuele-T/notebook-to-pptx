from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import io
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from services.pdf_processor import convert_pdf_to_images
from services.vision_processor import analyze_slide_image, crop_figures_from_slide
from services.ppt_builder import generate_pptx

import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Thread pool for parallel processing (limit to 3 concurrent API calls to avoid rate limits)
executor = ThreadPoolExecutor(max_workers=3)

# Mount static files for the UI
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("static/index.html", "r") as f:
        return f.read()


def process_single_slide(args: tuple) -> dict:
    """Process a single slide - runs in thread pool"""
    idx, img, total = args
    logger.info(f"Processing slide {idx+1}/{total}...")
    
    # Analyze Layout
    slide_analysis = analyze_slide_image(img)
    logger.info(f"Slide {idx+1} analysis: {slide_analysis.get('layout_type', 'unknown layout')}")
    logger.info(f"Slide {idx+1} title: {slide_analysis.get('title', 'NO TITLE')}")
    
    # Crop Figures if any
    if slide_analysis.get("figures"):
        logger.info(f"Cropping {len(slide_analysis['figures'])} figures for slide {idx+1}")
        slide_analysis["figures"] = crop_figures_from_slide(img, slide_analysis["figures"])
    
    # Store index for ordering later
    slide_analysis["_idx"] = idx
    return slide_analysis


@app.post("/rebuild")
async def rebuild_pptx(file: UploadFile = File(...)):
    """
    Main endpoint to convert a PDF into an editable PPTX.
    """
    logger.info(f"Received file upload: {file.filename}")
    if not file.filename.lower().endswith(".pdf"):
        logger.error("Invalid file type uploaded")
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF.")

    try:
        # Read PDF bytes
        logger.info("Reading PDF bytes...")
        pdf_bytes = await file.read()
        logger.info(f"Read {len(pdf_bytes)} bytes")
        
        # 1. Convert PDF to Images
        logger.info("Converting PDF to images...")
        images = list(convert_pdf_to_images(pdf_bytes))
        logger.info(f"Converted PDF to {len(images)} images")
        
        # 2 & 3. Analyze each page in PARALLEL
        logger.info("Starting parallel slide analysis...")
        loop = asyncio.get_event_loop()
        
        # Create tasks for parallel processing
        tasks = [
            loop.run_in_executor(executor, process_single_slide, (i, img, len(images)))
            for i, img in enumerate(images)
        ]
        
        # Wait for all slides to be processed
        results = await asyncio.gather(*tasks)
        
        # Sort by original index to maintain order
        slides_data = sorted(results, key=lambda x: x.get("_idx", 0))
        
        # Remove the temporary index field
        for slide in slides_data:
            slide.pop("_idx", None)
        
        logger.info(f"All {len(slides_data)} slides processed")
            
        # 4. Generate PPTX
        if not slides_data:
             logger.error("No slides processable")
             raise HTTPException(status_code=422, detail="No slides could be processed from the PDF.")
             
        logger.info("Generating PPTX file...")
        pptx_buffer = generate_pptx(slides_data)
        logger.info("PPTX generation complete")
        
        # Return as downloadable file
        return StreamingResponse(
            pptx_buffer,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f"attachment; filename=rebuilt_{file.filename.split('.')[0]}.pptx"}
        )

    except Exception as e:
        # In a real app, you'd log this properly
        logger.error(f"Error during processing: {str(e)}", exc_info=True)
        # print(f"Error during processing: {str(e)}") # removed duplicate print
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
