"""Biometric verification adapter (schema section 12, TDR section 6).

- COMPREFACE_URL set   -> calls CompreFace's face *verification* API (selfie vs document photo).
- COMPREFACE_URL empty -> clearly-labelled SIMULATED provider (for demos without Docker).

Nothing biometric is stored: the selfie is processed in memory and discarded. We keep only
status, provider, a reference id and the similarity number (schema 4.8).
This is a prototype face-verification step, NOT an official UAE biometric check, and it is not
liveness/anti-spoofing detection.
"""
import uuid

import httpx

from .. import config


def provider_name() -> str:
    return "compreface" if config.COMPREFACE_URL else "simulated"


def verify(selfie: bytes, reference: bytes | None) -> dict:
    """Returns {"status": passed/retry/failed/requires_review, "similarity": float|None, "message": str}."""
    ref_id = "bio_" + uuid.uuid4().hex[:12]
    if not selfie:
        return {"status": "retry", "similarity": None, "reference": ref_id, "message": "No image received. Please try again."}

    if not config.COMPREFACE_URL:
        return {"status": "passed", "similarity": None, "reference": ref_id,
                "message": "Simulated biometric verification passed (prototype, not a real face comparison)."}

    if not reference:
        return {"status": "requires_review", "similarity": None, "reference": ref_id,
                "message": "No document photo available to compare with. A reviewer will check."}
    try:
        r = httpx.post(
            f"{config.COMPREFACE_URL}/api/v1/verification/verify",
            headers={"x-api-key": config.COMPREFACE_API_KEY},
            files={"source_image": ("selfie.jpg", selfie, "image/jpeg"),
                   "target_image": ("document.jpg", reference, "image/jpeg")},
            timeout=30,
        )
    except httpx.HTTPError:
        return {"status": "retry", "similarity": None, "reference": ref_id,
                "message": "The biometric service is not reachable right now. Please try again."}

    if r.status_code == 400:   # usually "no face found"
        return {"status": "retry", "similarity": None, "reference": ref_id,
                "message": "We couldn't see a face clearly. Use good light and look at the camera."}
    if r.status_code != 200:
        return {"status": "retry", "similarity": None, "reference": ref_id,
                "message": "The biometric service returned an error. Please try again."}

    try:
        matches = r.json()["result"][0]["face_matches"]
        similarity = max(m["similarity"] for m in matches)
    except (KeyError, IndexError, ValueError):
        return {"status": "retry", "similarity": None, "reference": ref_id,
                "message": "We couldn't find a face on the document photo. A clearer document image may help."}

    if similarity >= config.BIOMETRIC_THRESHOLD:
        return {"status": "passed", "similarity": similarity, "reference": ref_id, "message": "Face verification passed."}
    if similarity >= config.BIOMETRIC_THRESHOLD - 0.15:
        return {"status": "requires_review", "similarity": similarity, "reference": ref_id,
                "message": "The match was close but not certain. A reviewer will take a look."}
    return {"status": "retry", "similarity": similarity, "reference": ref_id,
            "message": "The face didn't match the document photo. Please try again."}
