from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import io
import os
from services.pdf_processor import convert_pdf_to_images
from services.vision_processor import analyze_slide_image, crop_figures_from_slide
from services.ppt_builder import generate_pptx

app = FastAPI()

# Mount static files for the UI
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("static/index.html", "r") as f:
        return f.read()

@app.post("/rebuild")
async def rebuild_pptx(file: UploadFile = File(...)):
    """
    Main endpoint to convert a PDF into an editable PPTX.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF.")

    try:
        # Read PDF bytes
        pdf_bytes = await file.read()
        
        # 1. Convert PDF to Images
        images = convert_pdf_to_images(pdf_bytes)
        
        slides_data = []
        
        # 2 & 3. Analyze each page and crop figures
        for img in images:
            # Analyze Layout
            slide_analysis = analyze_slide_image(img)
            
            # Crop Figures if any
            if slide_analysis.get("figures"):
                slide_analysis["figures"] = crop_figures_from_slide(img, slide_analysis["figures"])
            
            slides_data.append(slide_analysis)
            
        # 4. Generate PPTX
        if not slides_data:
             raise HTTPException(status_code=422, detail="No slides could be processed from the PDF.")
             
        pptx_buffer = generate_pptx(slides_data)
        
        # Return as downloadable file
        return StreamingResponse(
            pptx_buffer,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f"attachment; filename=rebuilt_{file.filename.split('.')[0]}.pptx"}
        )

    except Exception as e:
        # In a real app, you'd log this properly
        print(f"Error during processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
