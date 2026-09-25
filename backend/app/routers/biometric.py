from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import workflow as wf
from ..auth import CurrentUser, get_current_user, require_role
from ..db import get_db
from ..models import BiometricVerification, ReviewCase
from ..services import biometric, storage
from ..services.events import audit, notify

router = APIRouter(prefix="/biometric", tags=["Biometric verification"])

DISCLAIMER = ("Prototype biometric step using an existing face-verification service (or a labelled simulation). "
              "It is not an official UAE government biometric check.")


def _out(b: BiometricVerification | None) -> dict:
    if not b:
        return {"status": "not_started", "provider": biometric.provider_name(), "disclaimer": DISCLAIMER}
    return {"id": b.id, "status": b.status, "provider": b.provider, "reference": b.verification_reference,
            "message": (b.similarity_metadata or {}).get("message"), "completed_at": b.completed_at,
            "disclaimer": DISCLAIMER}


@router.post("/start")
async def start(selfie: UploadFile = File(..., description="Photo from the webcam (JPG/PNG)"),
                user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Entry condition: documentary stage passed. The selfie is compared with the passport/ID photo
    and then discarded — only the result is stored."""
    p = wf.profile_or_404(db, user)
    stage = wf.documentary_stage(db, p)
    if not (stage["primary_evidence"] and stage["consistency"]) or stage["review_open"]:
        raise HTTPException(409, "Finish the document checks first (and any review) before the biometric step.")
    if selfie.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(415, "Please send a JPG or PNG photo.")
    selfie_bytes = await selfie.read()

    # reference photo = passport first, else another primary photo ID (images only)
    reference = None
    for d in sorted(wf.active_documents(db, p.id), key=lambda d: d.document_type != "passport"):
        if d.evidence_class == "primary" and d.mime_type in ("image/jpeg", "image/png") \
                and d.document_type in ("passport", "national_id", "gcc_id"):
            reference = storage.load(d.storage_path)
            break

    b = BiometricVerification(profile_id=p.id, provider=biometric.provider_name(), status="processing")
    db.add(b)
    db.flush()
    audit(db, user.id, "biometric_started", "biometric", b.id, {"provider": b.provider})
    result = biometric.verify(selfie_bytes, reference)
    del selfie_bytes                                  # never stored

    b.status = result["status"]
    b.verification_reference = result["reference"]
    b.similarity_metadata = {"similarity": result["similarity"], "threshold_used": biometric.config.BIOMETRIC_THRESHOLD
                             if result["similarity"] is not None else None, "message": result["message"]}
    if b.status in ("passed", "failed", "requires_review"):
        b.completed_at = wf.utcnow()
    if b.status == "requires_review":
        db.add(ReviewCase(profile_id=p.id, kind="biometric", reason=result["message"]))
        notify(db, user.id, "review", "Biometric check needs a reviewer", result["message"], "/app/biometric")
    audit(db, user.id, "biometric_completed", "biometric", b.id, {"status": b.status})
    db.commit()
    return _out(b)


@router.get("/status")
def status(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    return _out(wf.latest_biometric(db, p.id))


@router.post("/complete")
def complete_manually(profile_id: str, passed: bool = True,
                      reviewer: CurrentUser = Depends(require_role("reviewer")), db: Session = Depends(get_db)):
    """Controlled fallback (schema: 'configured demo fallback') when CompreFace is unavailable.
    Only a reviewer can call it; it is recorded in the audit log."""
    b = BiometricVerification(profile_id=profile_id, provider="simulated", status="passed" if passed else "failed",
                              verification_reference="manual_reviewer_check", completed_at=wf.utcnow(),
                              similarity_metadata={"message": "Recorded by a reviewer (demo fallback)."})
    db.add(b)
    audit(db, reviewer.id, "biometric_completed", "biometric", None, {"status": b.status, "manual": True})
    db.commit()
    return _out(b)
