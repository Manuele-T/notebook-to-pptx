from pptx import Presentation
from pptx.util import Inches, Pt
from io import BytesIO

def generate_pptx(slides_data: list[dict]) -> BytesIO:
    """
    Rebuilds each slide in PPTX format using layout intent, editable text boxes, and positioned images.
    """
    prs = Presentation()
    
    # Mapping our layout_type to python-pptx standard layouts
    # 0: Title Slide, 1: Title and Content, 3: Two Content, 5: Title Only, 6: Blank
    layout_mapping = {
        "title_only": 5,
        "title_and_content": 1,
        "two_column": 3,
        "image_left_text_right": 3,
        "image_right_text_left": 3,
        "full_image": 6,
        "diagram_heavy": 1,
        "mixed_freeform": 6
    }

    for slide_data in slides_data:
        layout_idx = layout_mapping.get(slide_data.get("layout_type"), 6)
        slide_layout = prs.slide_layouts[layout_idx]
        slide = prs.slides.add_slide(slide_layout)
        
        # Set Title
        if slide.shapes.title:
            slide.shapes.title.text = slide_data.get("title", "")
            
        # Set Body Text
        body_text = "\n".join(slide_data.get("body_text", []))
        
        # Determine where to put the body text based on layout
        if layout_idx == 1: # Title and Content
            if len(slide.placeholders) > 1:
                slide.placeholders[1].text = body_text
        elif layout_idx == 3: # Two Content
            # For image/text splits, we might need more logic, but for now simple:
            if slide_data.get("layout_type") == "image_left_text_right":
                 if len(slide.placeholders) > 2:
                     slide.placeholders[2].text = body_text
            else:
                 if len(slide.placeholders) > 1:
                     slide.placeholders[1].text = body_text
        elif layout_idx == 6: # Blank
            # Add a text box for mixed/blank layouts
            if body_text:
                left = Inches(1)
                top = Inches(1.5)
                width = Inches(8)
                height = Inches(5)
                txBox = slide.shapes.add_textbox(left, top, width, height)
                tf = txBox.text_frame
                tf.text = body_text

        # Add Figures
        for figure in slide_data.get("figures", []):
            if "image_bytes" in figure:
                image_stream = BytesIO(figure["image_bytes"])
                
                # Default position if not specified or for full image
                left = Inches(1)
                top = Inches(2)
                width = Inches(4) # Default width
                
                # If we have box_2d, we can try to position it more accurately
                # Coordinates are [ymin, xmin, ymax, xmax] 0-1000
                box = figure.get("box_2d")
                if box and len(box) == 4:
                    # PPT default slide size is 10 x 7.5 inches
                    ymin, xmin, ymax, xmax = box
                    left = Inches(xmin * 10 / 1000)
                    top = Inches(ymin * 7.5 / 1000)
                    width = Inches((xmax - xmin) * 10 / 1000)
                    # Note: height is scaled automatically by add_picture if not provided
                    slide.shapes.add_picture(image_stream, left, top, width=width)
                else:
                    slide.shapes.add_picture(image_stream, left, top, width=width)

        # Add Speaker Notes
        if slide_data.get("speaker_notes"):
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = slide_data.get("speaker_notes")

    # Save to buffer
    pptx_buffer = BytesIO()
    prs.save(pptx_buffer)
    pptx_buffer.seek(0)
    return pptx_buffer
