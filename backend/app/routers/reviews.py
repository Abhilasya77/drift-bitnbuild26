"""Exception-only human review (schema section 11). Reviewers see only cases the engine couldn't clear,
with the exact field difference, so they check one thing instead of re-reading the whole identity."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import workflow as wf
from ..auth import CurrentUser, require_role
from ..db import get_db
from ..models import ReviewCase, ReviewAction, IdentityProfile, IdentityDocument, BiometricVerification, \
    PermanentCredentialLink, Credential
from ..services import storage
from ..services.events import audit, notify

router = APIRouter(prefix="/reviews", tags=["Human review"])
reviewer_only = require_role("reviewer")


def _case_summary(db: Session, c: ReviewCase) -> dict:
    p = db.get(IdentityProfile, c.profile_id)
    return {"id": c.id, "kind": c.kind, "status": c.status, "reason": c.reason,
            "profile_name": p.name_as_used if p else None, "created_at": c.created_at,
            "assigned_reviewer_id": c.assigned_reviewer_id}


@router.get("")
def queue(status: str | None = None, reviewer: CurrentUser = Depends(reviewer_only), db: Session = Depends(get_db)):
    q = db.query(ReviewCase)
    q = q.filter(ReviewCase.status == status) if status else q.filter(ReviewCase.status != "resolved")
    return [_case_summary(db, c) for c in q.order_by(ReviewCase.created_at).all()]


@router.get("/stats")
def stats(reviewer: CurrentUser = Depends(reviewer_only), db: Session = Depends(get_db)):
    """How much work the engine saved: profiles checked vs cases that needed a human."""
    from ..models import ConsistencyEvaluation
    total_profiles = db.query(IdentityProfile).count()
    evaluated = db.query(ConsistencyEvaluation.profile_id).distinct().count()
    cases = db.query(ReviewCase).count()
    open_cases = db.query(ReviewCase).filter(ReviewCase.status != "resolved").count()
    return {"profiles": total_profiles, "profiles_checked": evaluated, "review_cases_total": cases,
            "open_cases": open_cases,
            "auto_cleared_share": round(1 - cases / evaluated, 2) if evaluated else None}


@router.get("/{case_id}")
def open_case(case_id: str, reviewer: CurrentUser = Depends(reviewer_only), db: Session = Depends(get_db)):
    c = db.get(ReviewCase, case_id)
    if not c:
        raise HTTPException(404, "Case not found.")
    if c.status == "open":
        c.status, c.assigned_reviewer_id = "under_review", reviewer.id
        db.add(ReviewAction(review_case_id=c.id, reviewer_id=reviewer.id, action_type="opened"))
    out = _case_summary(db, c)

    if c.kind == "consistency" and c.evaluation_id:
        from ..models import ConsistencyEvaluation
        ev = wf.evaluation_json(db, db.get(ConsistencyEvaluation, c.evaluation_id))
        out["flagged_fields"] = [x for x in ev["comparisons"] if x["classification"] in ("uncertain", "conflict")]
        out["already_explained"] = [x for x in ev["comparisons"] if x["classification"] in ("match", "explainable_variant")]
    if c.kind == "biometric":
        bio = wf.latest_biometric(db, c.profile_id)
        out["biometric"] = {"status": bio.status, "provider": bio.provider,
                            "similarity": (bio.similarity_metadata or {}).get("similarity")} if bio else None
    if c.kind == "permanent_credential":
        link = (db.query(PermanentCredentialLink).filter_by(profile_id=c.profile_id)
                .order_by(PermanentCredentialLink.created_at.desc()).first())
        out["permanent_link"] = {"id": link.id, "status": link.consistency_status} if link else None

    # evidence the reviewer may open: short-lived links (Supabase) or the reviewer file route (local)
    docs = wf.active_documents(db, c.profile_id)
    out["evidence"] = [{"document_id": d.id, "document_type": d.document_type, "evidence_class": d.evidence_class,
                        "confirmed_fields": {k: v for k, v in wf.confirmed_fields(db, d.id).items()
                                             if k != "mrz_failed_parts"},
                        "view_url": storage.signed_url(d.storage_path) or f"/reviews/{c.id}/documents/{d.id}/file"}
                       for d in docs]
    out["history"] = [{"action": a.action_type, "note": a.note, "at": a.created_at}
                      for a in db.query(ReviewAction).filter_by(review_case_id=c.id).order_by(ReviewAction.created_at)]
    audit(db, reviewer.id, "review_opened", "review", c.id)
    db.commit()
    return out


@router.get("/{case_id}/documents/{doc_id}/file")
def case_file(case_id: str, doc_id: str, reviewer: CurrentUser = Depends(reviewer_only), db: Session = Depends(get_db)):
    from fastapi.responses import Response
    c = db.get(ReviewCase, case_id)
    d = db.get(IdentityDocument, doc_id)
    if not c or not d or d.profile_id != c.profile_id:
        raise HTTPException(404, "File not found.")
    return Response(storage.load(d.storage_path), media_type=d.mime_type or "application/octet-stream",
                    headers={"Cache-Control": "no-store"})


class EvidenceRequest(BaseModel):
    document_type: str = Field(description="What to upload, e.g. grade10, national_id, other")
    message: str = Field(min_length=5, max_length=500, description="Plain-language reason shown to the user")


@router.post("/{case_id}/request-evidence")
def request_evidence(case_id: str, body: EvidenceRequest, reviewer: CurrentUser = Depends(reviewer_only),
                     db: Session = Depends(get_db)):
    c = db.get(ReviewCase, case_id)
    if not c or c.status == "resolved":
        raise HTTPException(404, "Open case not found.")
    c.status = "awaiting_evidence"
    db.add(ReviewAction(review_case_id=c.id, reviewer_id=reviewer.id, action_type="requested_evidence",
                        note=f"{body.document_type}: {body.message}"))
    p = db.get(IdentityProfile, c.profile_id)
    notify(db, p.user_id, "evidence_request", "One more document needed", body.message, "/app/documents")
    audit(db, reviewer.id, "evidence_requested", "review", c.id, {"document_type": body.document_type})
    db.commit()
    return _case_summary(db, c)


class Resolution(BaseModel):
    decision: str = Field(description="cleared (identity consistent) or not_cleared")
    note: str | None = Field(default=None, max_length=1000)


@router.post("/{case_id}/resolve")
def resolve(case_id: str, body: Resolution, reviewer: CurrentUser = Depends(reviewer_only),
            db: Session = Depends(get_db)):
    if body.decision not in ("cleared", "not_cleared"):
        raise HTTPException(422, "decision must be 'cleared' or 'not_cleared'.")
    c = db.get(ReviewCase, case_id)
    if not c or c.status == "resolved":
        raise HTTPException(404, "Open case not found.")
    c.status, c.resolution, c.reviewer_note, c.resolved_at = "resolved", body.decision, body.note, wf.utcnow()
    db.add(ReviewAction(review_case_id=c.id, reviewer_id=reviewer.id, action_type="resolved", note=body.note))
    p = db.get(IdentityProfile, c.profile_id)
    cleared = body.decision == "cleared"

    if c.kind == "consistency":
        p.evidence_status = "evidence_backed" if cleared else "action_required"
    elif c.kind == "biometric":
        bio = wf.latest_biometric(db, p.id)
        if bio:
            bio.status = "passed" if cleared else "failed"
            bio.completed_at = wf.utcnow()
    elif c.kind == "permanent_credential":
        link = (db.query(PermanentCredentialLink).filter_by(profile_id=p.id)
                .order_by(PermanentCredentialLink.created_at.desc()).first())
        if link and cleared:
            from .permanent import complete_link
            complete_link(db, p, link, reviewer.id)
        elif link:
            link.consistency_status = "conflict"
            cred = wf.current_credential(db, p.id)
            if cred and cred.state == "in_transition":
                cred.state = "active"

    notify(db, p.user_id, "review", "Review completed" if cleared else "Action needed",
           "A reviewer confirmed your details. You can continue." if cleared else
           "A reviewer couldn't confirm your details. Check the report for what to do next.",
           "/app/consistency")
    audit(db, reviewer.id, "review_resolved", "review", c.id, {"decision": body.decision, "kind": c.kind})
    db.commit()
    return _case_summary(db, c)
