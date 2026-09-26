# modules/ocr_module.py
# This module extracts text from PDF identity documents

import pdfplumber
import subprocess
import re
from datetime import datetime

def extract_fields_from_pdf(pdf_path, document_type):
    """
    Extract identity fields from a PDF document.
    
    Args:
        pdf_path (str): Path to the PDF file
        document_type (str): Type of document (passport, national_id, visa, etc.)
    
    Returns:
        dict: Extracted fields with normalized values
    """
    
    try:
        # Read PDF and extract text
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        
        # Extract identity fields
        fields = extract_identity_fields(text)
        
        return {
            "status": "success",
            "document_type": document_type,
            "extracted_fields": fields,
            "overall_confidence": calculate_confidence(fields)
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "document_type": document_type
        }


def extract_identity_fields(text):
    """
    Extract specific identity fields from extracted text.
    
    Returns list of field dictionaries with original and normalized values.
    """
    
    fields = []
    
    # Find NAME (usually after "Name:" label)
    name_match = re.search(r"Name:\s*([A-Za-z\s\.\-]+?)(?:\n|$)", text, re.IGNORECASE)
    if name_match:
        original = name_match.group(1).strip()
        fields.append({
            "field_name": "name",
            "original_value": original,
            "normalized_value": normalize_name(original),
            "confidence": 0.95
        })
    
    # Find DOB (looks for DD/MM/YYYY pattern)
    dob_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
    if dob_match:
        original = dob_match.group(1)
        fields.append({
            "field_name": "dob",
            "original_value": original,
            "normalized_value": normalize_dob(original),
            "confidence": 0.98
        })
    
    # Find NATIONALITY
    nationality_match = re.search(r"Nationality:\s*([A-Za-z\s]+?)(?:\n|$)", text, re.IGNORECASE)
    if nationality_match:
        original = nationality_match.group(1).strip()
        fields.append({
            "field_name": "nationality",
            "original_value": original,
            "normalized_value": original.lower(),
            "confidence": 1.0
        })
    
    # Find DOCUMENT NUMBER (alphanumeric)
    number_match = re.search(r"Number:\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    if number_match:
        original = number_match.group(1).strip()
        fields.append({
            "field_name": "number",
            "original_value": original,
            "normalized_value": original.lower(),
            "confidence": 0.92
        })
    
    # Find EXPIRY DATE
    expiry_match = re.search(r"Expiry.*?(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    if expiry_match:
        original = expiry_match.group(1)
        fields.append({
            "field_name": "expiry",
            "original_value": original,
            "normalized_value": normalize_dob(original),
            "confidence": 0.96
        })
    
    return fields


def normalize_name(name):
    """
    Clean and normalize a name.
    - Lowercase
    - Remove extra spaces
    - Keep special characters (hyphens, apostrophes)
    """
    name = name.lower()
    name = re.sub(r'\s+', ' ', name)  # Replace multiple spaces with single space
    return name.strip()


def normalize_dob(dob):
    """
    Convert date format DD/MM/YYYY to YYYY-MM-DD
    """
    try:
        parsed = datetime.strptime(dob, "%d/%m/%Y")
        return parsed.strftime("%Y-%m-%d")
    except:
        return dob


def calculate_confidence(fields):
    """
    Calculate overall confidence by averaging field confidences.
    """
    if not fields:
        return 0.0
    
    total = sum(f["confidence"] for f in fields)
    return round(total / len(fields), 2)