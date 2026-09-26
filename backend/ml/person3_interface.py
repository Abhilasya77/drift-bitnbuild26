# modules/biometric_module.py
# Biometric verification using real CompreFace API

import requests
from datetime import datetime

COMPREFACE_API_URL = "http://localhost:3000/api/v1"

def verify_faces(reference_face_path, current_face_path):
    """
    Real face verification using CompreFace API.
    
    Args:
        reference_face_path (str): Path to reference face image
        current_face_path (str): Path to current face image
    
    Returns:
        dict: Verification result with status and similarity score
    """
    
    try:
        # Read the face images
        with open(reference_face_path, 'rb') as f:
            ref_image = f.read()
        with open(current_face_path, 'rb') as f:
            curr_image = f.read()
        
        # Call CompreFace verify endpoint
        files = {
            'source_image': ref_image,
            'target_image': curr_image
        }
        
        response = requests.post(
            f"{COMPREFACE_API_URL}/verify",
            files=files
        )
        
        if response.status_code == 200:
            data = response.json()
            result = data.get('result', {})
            similarity = result.get('similarity', 0)
            
            # Threshold: >0.80 = passed
            status = "passed" if similarity > 0.80 else "failed"
            
            return {
                "status": status,
                "similarity_score": round(similarity, 2),
                "verification_reference": f"compreface_{datetime.now().isoformat()}",
                "timestamp": datetime.now().isoformat(),
                "message": f"Face verification {'successful' if status == 'passed' else 'failed'}. Similarity: {similarity:.2f}",
                "is_mock": False
            }
        else:
            return {
                "status": "error",
                "message": f"CompreFace error: {response.status_code}",
                "is_mock": False
            }
    
    except FileNotFoundError as e:
        # Fallback for missing face images (for testing)
        return {
            "status": "failed",
            "similarity_score": 0.0,
            "message": f"Face image not found: {str(e)}",
            "is_mock": False
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "is_mock": False
        }