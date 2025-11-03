import json
import pandas as pd
from PyPDF2 import PdfReader
from docx import Document
import pdfplumber
import easyocr
import io
import numpy as np
import cv2
from PIL import Image

import torch

import warnings

# -----------------------------
# Extract text from uploaded file object
# -----------------------------
def extract_text_from_file(file_obj, file_name):
    ext = file_name.lower().split('.')[-1]
    text = ""

    if ext == "txt":
        text = file_obj.read().decode("utf-8", errors="ignore")

    elif ext == "pdf":
        try:
            # Prefer pdfplumber for better text extraction
            with pdfplumber.open(file_obj) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n".join(pages)
        except:
            # fallback to PyPDF2
            pdf = PdfReader(file_obj)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    elif ext in ["doc", "docx"]:
        document = Document(file_obj)
        text = "\n".join(p.text for p in document.paragraphs)

    elif ext == "json":
        data = json.load(file_obj)
        text = json.dumps(data, indent=2)

    elif ext == "csv":
        df = pd.read_csv(file_obj)
        # combine all columns into text
        text = "\n".join(df[col].astype(str).str.cat(sep="\n") for col in df.columns)

    elif ext in ["jpg", "jpeg", "png", "bmp", "tiff", "webp"]:
                
        # -----------------------------
        # Suppress GPU/pin_memory warnings
        # -----------------------------
        warnings.filterwarnings("ignore", message=".*pin_memory.*")
        warnings.filterwarnings("ignore", category=UserWarning, module="easyocr")
        torch.backends.cudnn.enabled = False  # Disable CUDA backend
        # -----------------------------
        # Initialize EasyOCR reader (English only for speed)
        # -----------------------------
        reader = easyocr.Reader(['en'], gpu=False, download_enabled=True, model_storage_directory="./models")

        try:
            # ✅ Convert uploaded image to NumPy array (no temp file, no URL)
            file_bytes = np.asarray(bytearray(file_obj.read()), dtype=np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if image is None:
                raise ValueError("Could not decode image from upload.")

            # Run OCR directly on the in-memory image
            result = reader.readtext(image, detail=0)
            text = "\n".join(result)
        except Exception as e:
            text = f"[Error reading image text: {e}]"

    else:
        # fallback: try reading as text
        text = file_obj.read().decode("utf-8", errors="ignore")

    return text
