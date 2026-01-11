import logging
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from io import BytesIO

logger = logging.getLogger(__name__)

def generate_pptx(slides_data: list[dict]) -> BytesIO:
    """
    Rebuilds each slide in PPTX format using layout intent, editable text boxes, and positioned images.
    """
    logger.info(f"Starting PPTX generation with {len(slides_data)} slides")
    prs = Presentation()
    
    # Standard PPTX Slide Dimensions: 10 inches x 7.5 inches
    SLIDE_WIDTH = Inches(10)
    SLIDE_HEIGHT = Inches(7.5)

    # Layout Mapping (0: Title, 1: Title/Content, 5: Title Only, 6: Blank)
    layout_mapping = {
        "title_only": 5,
        "title_and_content": 1,
        "two_column": 3, # Two Content
        "diagram_heavy": 6, # Blank (We will build manually)
        "mixed_freeform": 6
    }

    for idx, slide_data in enumerate(slides_data):
        l_type = slide_data.get("layout_type", "title_and_content")
        logger.info(f"Building slide {idx+1}: {l_type}")
        
        layout_idx = layout_mapping.get(l_type, 1)
        slide_layout = prs.slide_layouts[layout_idx]
        slide = prs.slides.add_slide(slide_layout)
        
        # --- TITLE HANDLING ---
        title_text = slide_data.get("title", "")
        if slide.shapes.title:
            slide.shapes.title.text = title_text
        elif l_type in ["diagram_heavy", "mixed_freeform"] and title_text:
            # Manually add title if Blank layout
            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(1))
            tf = title_box.text_frame
            tf.text = title_text
            tf.paragraphs[0].font.size = Pt(32)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER

        # --- BODY TEXT HANDLING ---
        body_text_list = slide_data.get("body_text", [])
        body_text = "\n".join(body_text_list)
        
        # If standard layout, use placeholder
        if layout_idx == 1 and body_text: # Title and Content
            if len(slide.placeholders) > 1:
                slide.placeholders[1].text = body_text
                
        # If Two Column (Layout 3)
        elif layout_idx == 3:
             # Put text on left, leave right for image (usually)
             if len(slide.placeholders) > 1:
                 slide.placeholders[1].text = body_text

        # If Manual Layout (Diagram Heavy / Freeform)
        elif layout_idx == 6 and body_text:
            # Add a small text box at the bottom or side if text exists
            txBox = slide.shapes.add_textbox(Inches(0.5), Inches(6.5), Inches(9), Inches(1))
            tf = txBox.text_frame
            tf.text = body_text
            tf.paragraphs[0].font.size = Pt(12)

# --- IMAGE HANDLING ---
        figures = slide_data.get("figures", [])
        num_figures = len(figures)
        
        for i, figure in enumerate(figures):
            if "image_bytes" in figure:
                image_stream = BytesIO(figure["image_bytes"])
                
                # Dynamic Positioning
                left = Inches(1)
                top = Inches(2)
                width = Inches(8) 

                # Special Logic: 2 Figures in Two Column Mode (The "Hammer vs Blueprint" Fix)
                if l_type == "two_column" and num_figures == 2:
                    width = Inches(3.5)
                    top = Inches(2)
                    if i == 0:
                        left = Inches(1) # Left side
                    else:
                        left = Inches(5.5) # Right side
                    slide.shapes.add_picture(image_stream, left, top, width=width)

                # Special Logic: Diagram Heavy
                elif l_type == "diagram_heavy":
                    left = Inches(0.5)
                    top = Inches(1.5)
                    width = Inches(9)
                    slide.shapes.add_picture(image_stream, left, top, width=width)
                
                # Standard: Use AI coordinates if available
                else:
                    box = figure.get("box_2d")
                    if box and len(box) == 4:
                        ymin, xmin, ymax, xmax = box
                        left = Inches(xmin * 10 / 1000)
                        top = Inches(ymin * 7.5 / 1000)
                        width = Inches((xmax - xmin) * 10 / 1000)
                        slide.shapes.add_picture(image_stream, left, top, width=width)
                    else:
                        # Fallback
                        slide.shapes.add_picture(image_stream, left, top, width=width)

        # --- SPEAKER NOTES ---
        if slide_data.get("speaker_notes"):
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = slide_data.get("speaker_notes")

    # Save to buffer
    pptx_buffer = BytesIO()
    prs.save(pptx_buffer)
    pptx_buffer.seek(0)
    return pptx_buffer