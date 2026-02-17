import os
from typing import List, Dict, Any
import logging
from docx import Document as DocxDocument
from pptx import Presentation
import openpyxl
import pandas as pd
from PIL import Image
import io

logger = logging.getLogger(__name__)

class UploadService:
    @staticmethod
    def parse_docx(file_content: bytes) -> str:
        doc = DocxDocument(io.BytesIO(file_content))
        return "\n".join([para.text for para in doc.paragraphs])

    @staticmethod
    def parse_pptx(file_content: bytes) -> str:
        prs = Presentation(io.BytesIO(file_content))
        text_runs = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text_runs.append(shape.text)
        return "\n".join(text_runs)

    @staticmethod
    def parse_excel(file_content: bytes) -> str:
        # Using pandas for easier excel to text conversion
        df_dict = pd.read_excel(io.BytesIO(file_content), sheet_name=None)
        output = []
        for sheet_name, df in df_dict.items():
            output.append(f"Sheet: {sheet_name}")
            output.append(df.to_string())
        return "\n\n".join(output)

    @staticmethod
    def parse_image(file_content: bytes) -> str:
        # Basic parsing - placeholder for actual OCR
        try:
            img = Image.open(io.BytesIO(file_content))
            return f"Image file: {img.format}, {img.size}, {img.mode}. (OCR not fully implemented, but metadata captured)"
        except Exception as e:
            logger.error(f"Image parsing failed: {e}")
            return "Failed to parse image content."

    def parse_file(self, file_content: bytes, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        try:
            if ext in ['.docx']:
                return self.parse_docx(file_content)
            elif ext in ['.pptx']:
                return self.parse_pptx(file_content)
            elif ext in ['.xlsx', '.xls']:
                return self.parse_excel(file_content)
            elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
                return self.parse_image(file_content)
            elif ext in ['.txt', '.md', '.csv']:
                return file_content.decode('utf-8', errors='ignore')
            else:
                return f"Unsupported file format: {ext}"
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            return f"Error parsing {filename}: {str(e)}"
