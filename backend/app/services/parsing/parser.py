import pymupdf
from typing import List, Dict, Any

def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses a PDF file using PyMuPDF and extracts text per page.
    Returns a list of dictionaries: [{"page_num": 1, "text": "..."}, ...]
    """
    pages_data = []
    try:
        doc = pymupdf.open(file_path)
        for i in range(len(doc)):
            page = doc.load_page(i)
            text = page.get_text()
            # Clean up excessive newlines or weird character sequences if any
            clean_text = text.replace("\x00", "").strip()
            pages_data.append({
                "page_num": i + 1,
                "text": clean_text
            })
        doc.close()
    except Exception as e:
        raise RuntimeError(f"Failed to parse PDF at {file_path}: {str(e)}")
        
    return pages_data
