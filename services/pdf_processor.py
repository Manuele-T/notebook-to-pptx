from pdf2image import convert_from_bytes
from PIL import Image
from typing import Iterator

def convert_pdf_to_images(pdf_bytes: bytes) -> Iterator[Image.Image]:
    """
    Converts a PDF (from bytes) into high-resolution PIL images, yielding one page at a time.
    
    Args:
        pdf_bytes: The byte content of the PDF file.
        
    Yields:
        A PIL Image object for each page of the PDF.
    """
    # convert_from_bytes takes the PDF data and returns a list of PIL Images.
    # We yield them to keep memory usage lower if we were processing many pages.
    # Note: dpi=300 is used for high-quality extraction of charts later.
    images = convert_from_bytes(pdf_bytes, dpi=300)
    for image in images:
        yield image
