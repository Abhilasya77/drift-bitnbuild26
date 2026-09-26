# modules/biometric_module.py
# Mock biometric verification module (for hackathon testing)
# Person 4 can swap this with real CompreFace later

import re
from datetime import datetime

def verify_faces(reference_face_path, current_face_path):
    """
    Mock face verification module.
    
    For hackathon testing, we use a simple rule:
    - If both faces are from the same identity ID → PASSED
    - If faces are from different identity IDs → FAILED
    
    Args:
        reference_face_path (str): Path to reference face (from document)
        current_face_path (str): Path to current face (user submission)
    
    Returns:
        dict: Verification result with status and metadata
    """
    
    try:
        # Extract identity IDs from file paths
        # Example: "synthetic_data/ID001_passport_face.jpg" → "ID001"
        ref_id = extract_identity_id(reference_face_path)
        curr_id = extract_identity_id(current_face_path)
        
        # Determine if same person
        if ref_id and curr_id:
            is_same_person = (ref_id == curr_id)
        else:
            # If we can't extract IDs, return uncertain
            is_same_person = False
        
        # Generate status
        if is_same_person:
            status = "passed"
            similarity_score = 0.92  # Mock high similarity
            message = "Face verification successful."
        else:
            status = "failed"
            similarity_score = 0.35  # Mock low similarity
            message = "Face verification failed. Faces do not match."
        
        return {
            "status": status,
            "similarity_score": similarity_score,
            "verification_reference": f"mock_verification_{generate_mock_id()}",
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "is_mock": True  # Important: flag this as mock for testing
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "is_mock": True
        }


def extract_identity_id(file_path):
    """
    Extract identity ID from file path.
    Example: "synthetic_data/ID001_passport_face.jpg" → "ID001"
    """
    
    match = re.search(r'(ID\d{3})', file_path)
    if match:
        return match.group(1)
    return None


def generate_mock_id():
    """
    Generate a mock verification reference ID.
    """
    import time
    return str(int(time.time() * 1000) % 1000000)