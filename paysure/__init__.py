import os

# Windows: set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe if tesseract is not on PATH
if os.environ.get("TESSERACT_CMD"):
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
