"""Shared workflow logic: evaluation, review routing, eligibility, credential state, next action."""
from datetime import datetime, timezone, timedelta, date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ml import consistency as engine
from .auth import CurrentUser
from .models import (IdentityProfile, IdentityDocument, DocumentField, ConsistencyEvaluation, FieldComparison,
                     ReviewCase, BiometricVerification, Credential, PermanentCredentialLink)
from .services.events import audit, notify

PRIMARY_TYPES = {"passport", "national_id", "gcc_id", "visa_residence"}
SUPPORTING_TYPES = {"grade10", "grade12", "other"}
DOC_TYPES = PRIMARY_TYPES | SUPPORTING_TYPES


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ------------------------------------------------------------------ lookups
def profile_or_404(db: Session, user: CurrentUser) -> IdentityProfile:
    p = db.query(IdentityProfile).filter_by(user_id=user.id).first()
    if not p:
        raise HTTPException(404, "Create your identity profile first.")
    return p


def document_or_404(db: Session, profile: IdentityProfile, doc_id: str) -> IdentityDocument:
    d = db.query(IdentityDocument).filter_by(id=doc_id, profile_id=profile.id).first()
    if not d:
        raise HTTPException(404, "Document not found.")
    return d


def active_documents(db: Session, profile_id: str) -> list[IdentityDocument]:
    """Documents that count as current evidence (replaced ones are kept for history but not compared)."""
    return (db.query(IdentityDocument)
            .filter(IdentityDocument.profile_id == profile_id, IdentityDocument.renewal_status != "replaced")
            .order_by(IdentityDocument.created_at).all())


def confirmed_fields(db: Session, doc_id: str) -> dict:
    rows = db.query(DocumentField).filter_by(document_id=doc_id, confirmed=True).all()
    out = {r.field_name: r.original_value for r in rows}
    if "mrz_failed_parts" in out and out["mrz_failed_parts"]:
        out["mrz_failed_parts"] = out["mrz_failed_parts"].split(",")
    return out


def profile_dict(p: IdentityProfile) -> dict:
    return {"name_as_used": p.name_as_used, "dob": p.date_of_birth.isoformat() if p.date_of_birth else None,
            "nationality": p.nationality, "father_name": p.father_name, "mother_name": p.mother_name}


# ------------------------------------------------------------------ consistency
def flagged_signature(comps: list[dict]) -> str:
    """Same flagged differences -> same signature. Lets a reviewer's decision stick when the check is re-run."""
    return "|".join(sorted(f"{c['field']}:{(c.get('value_a') or '').upper()}:{(c.get('value_b') or '').upper()}:"
                           f"{c['classification']}" for c in comps if c["classification"] in ("uncertain", "conflict")))


def run_evaluation(db: Session, profile: IdentityProfile, actor: str | None) -> ConsistencyEvaluation:
    docs = [d for d in active_documents(db, profile.id) if not d.is_permanent_credential or _linked(db, d)]
    payload = [{"id": d.id, "document_type": d.document_type, "evidence_class": d.evidence_class,
                "fields": confirmed_fields(db, d.id)} for d in docs]
    payload = [d for d in payload if d["fields"]]
    result = engine.evaluate(profile_dict(profile), payload)

    ev = ConsistencyEvaluation(profile_id=profile.id, overall_status=result["overall_status"],
                               engine_version=engine.ENGINE_VERSION, summary=result["summary"],
                               requires_review=result["requires_review"])
    db.add(ev)
    db.flush()
    for c in result["comparisons"]:
        db.add(FieldComparison(evaluation_id=ev.id, field_name=c["field"],
                               source_a_document_id=c["source_a_document_id"],
                               source_b_document_id=c["source_b_document_id"],
                               value_a=c["value_a"], value_b=c["value_b"], classification=c["classification"],
                               similarity_score=c["similarity_score"], explanation=c["explanation"]))

    open_case = open_review(db, profile.id, kind="consistency")
    sig = flagged_signature(result["comparisons"])
    already_cleared = last_resolved_review(db, profile.id, "consistency")
    if result["requires_review"] and not open_case and already_cleared and already_cleared.signature == sig \
            and (already_cleared.resolution or "").startswith("cleared"):
        profile.evidence_status = "evidence_backed"          # a reviewer already cleared exactly these differences
    elif result["requires_review"]:
        reasons = [f"{c['field'].replace('_', ' ')} ({c['source_a']} vs {c['source_b']}): {c['explanation']}"
                   for c in result["comparisons"] if c["classification"] in ("uncertain", "conflict")]
        reason = " | ".join(reasons)
        if open_case:                       # re-evaluation after new evidence: keep one case, refresh it
            open_case.evaluation_id, open_case.reason, open_case.signature = ev.id, reason, sig
            if open_case.status == "awaiting_evidence":
                open_case.status = "open"
        else:
            case = ReviewCase(profile_id=profile.id, evaluation_id=ev.id, reason=reason, kind="consistency",
                              signature=sig)
            db.add(case)
            db.flush()
            audit(db, actor, "review_case_created", "review", case.id, {"kind": "consistency"})
            notify(db, profile.user_id, "review", "A reviewer will check one detail",
                   "Some details on your documents need a quick human check. We'll tell you when it's done.",
                   "/app/consistency")
        profile.evidence_status = "under_review"
    else:
        if open_case:                       # new evidence resolved the problem automatically
            open_case.status, open_case.resolution = "resolved", "cleared_by_new_evidence"
            open_case.resolved_at = utcnow()
        profile.evidence_status = "evidence_backed" if payload else "self_declared"

    audit(db, actor, "consistency_evaluated", "profile", profile.id,
          {"overall_status": ev.overall_status, "requires_review": ev.requires_review})
    return ev


def latest_evaluation(db: Session, profile_id: str) -> ConsistencyEvaluation | None:
    return (db.query(ConsistencyEvaluation).filter_by(profile_id=profile_id)
            .order_by(ConsistencyEvaluation.created_at.desc()).first())


def evaluation_json(db: Session, ev: ConsistencyEvaluation | None) -> dict | None:
    if not ev:
        return None
    labels = {d.id: d.document_type for d in db.query(IdentityDocument)
              .join(FieldComparison, (FieldComparison.source_a_document_id == IdentityDocument.id) |
                    (FieldComparison.source_b_document_id == IdentityDocument.id))
              .filter(FieldComparison.evaluation_id == ev.id).all()}
    comps = db.query(FieldComparison).filter_by(evaluation_id=ev.id).all()
    return {
        "id": ev.id, "overall_status": ev.overall_status, "requires_review": ev.requires_review,
        "summary": ev.summary, "engine_version": ev.engine_version, "created_at": ev.created_at,
        "comparisons": [{
            "field": c.field_name,
            "source_a": engine.LABELS.get(labels.get(c.source_a_document_id), "Profile")
            if c.source_a_document_id else "Profile",
            "source_b": engine.LABELS.get(labels.get(c.source_b_document_id), "Document")
            if c.source_b_document_id else "-",
            "value_a": c.value_a, "value_b": c.value_b, "classification": c.classification,
            "explanation": c.explanation,
        } for c in comps],
    }


# ------------------------------------------------------------------ review
def open_review(db: Session, profile_id: str, kind: str | None = None) -> ReviewCase | None:
    q = db.query(ReviewCase).filter(ReviewCase.profile_id == profile_id, ReviewCase.status != "resolved")
    if kind:
        q = q.filter(ReviewCase.kind == kind)
    return q.order_by(ReviewCase.created_at.desc()).first()


def last_resolved_review(db: Session, profile_id: str, kind: str) -> ReviewCase | None:
    return (db.query(ReviewCase).filter_by(profile_id=profile_id, kind=kind, status="resolved")
            .order_by(ReviewCase.resolved_at.desc()).first())


# ------------------------------------------------------------------ documentary stage
def documentary_stage(db: Session, profile: IdentityProfile) -> dict:
    docs = active_documents(db, profile.id)
    primary_ok = any(d.evidence_class == "primary" and confirmed_fields(db, d.id) for d in docs)
    ev = latest_evaluation(db, profile.id)
    consistency_ok = bool(ev and ev.overall_status in ("match", "explainable_variant"))
    review_open = open_review(db, profile.id, "consistency")
    if ev and ev.requires_review and not review_open:
        resolved = last_resolved_review(db, profile.id, "consistency")
        comps = [{"field": c.field_name, "value_a": c.value_a, "value_b": c.value_b, "classification": c.classification}
                 for c in db.query(FieldComparison).filter_by(evaluation_id=ev.id)]
        consistency_ok = bool(resolved and (resolved.resolution or "").startswith("cleared")
                              and resolved.signature == flagged_signature(comps))
    return {"primary_evidence": primary_ok, "consistency": consistency_ok, "review_open": bool(review_open),
            "review_required": bool(ev and ev.requires_review)}


def latest_biometric(db: Session, profile_id: str) -> BiometricVerification | None:
    return (db.query(BiometricVerification).filter_by(profile_id=profile_id)
            .order_by(BiometricVerification.created_at.desc()).first())


def _linked(db: Session, doc: IdentityDocument) -> bool:
    return bool(db.query(PermanentCredentialLink).filter_by(document_id=doc.id)
                .filter(PermanentCredentialLink.linked_at.isnot(None)).first())


def permanent_status(db: Session, profile_id: str) -> str:
    link = (db.query(PermanentCredentialLink).filter_by(profile_id=profile_id)
            .order_by(PermanentCredentialLink.created_at.desc()).first())
    if not link:
        return "pending"
    if link.linked_at:
        return "linked"
    return {"uncertain": "under_review", "conflict": "under_review"}.get(link.consistency_status, "processing")


# ------------------------------------------------------------------ eligibility (server-side only)
def eligibility(db: Session, profile: IdentityProfile, user: CurrentUser) -> dict:
    stage = documentary_stage(db, profile)
    bio = latest_biometric(db, profile.id)
    perm = permanent_status(db, profile.id)
    items = [
        {"key": "email", "label": "Account / email verification", "passed": user.email_verified,
         "status": "Passed" if user.email_verified else "Verify your email"},
        {"key": "primary_evidence", "label": "Primary identity evidence", "passed": stage["primary_evidence"],
         "status": "Passed" if stage["primary_evidence"] else "Upload and confirm a passport, ID or visa"},
        {"key": "consistency", "label": "Cross-document consistency", "passed": stage["consistency"],
         "status": "Passed" if stage["consistency"] else ("Under review" if stage["review_open"] else "Not passed yet")},
        {"key": "supporting_evidence", "label": "Required supporting evidence", "passed": True,
         "status": "Not required"},
        {"key": "human_review", "label": "Human review", "passed": not stage["review_open"],
         "status": ("Under review" if stage["review_open"] else
                    ("Completed" if stage["review_required"] else "Not required"))},
        {"key": "biometric", "label": "Biometric check", "passed": bool(bio and bio.status == "passed"),
         "status": (bio.status.replace("_", " ").capitalize() if bio else "Not started")},
        {"key": "permanent_id", "label": "Permanent/local ID", "passed": perm != "linked",
         "status": {"pending": "Pending", "linked": "Already linked (temporary credential not needed)"}
         .get(perm, "Being checked")},
    ]
    return {"eligible": all(i["passed"] for i in items), "items": items}


# ------------------------------------------------------------------ credential state
def refresh_credential_state(db: Session, cred: Credential | None) -> Credential | None:
    if cred and cred.state in ("active", "in_transition") and aware(cred.expires_at) <= utcnow():
        cred.state = "expired"
        audit(db, None, "credential_expired", "credential", cred.id, {"reason": "time"})
    return cred


def current_credential(db: Session, profile_id: str) -> Credential | None:
    cred = (db.query(Credential).filter_by(profile_id=profile_id)
            .order_by(Credential.issued_at.desc()).first())
    return refresh_credential_state(db, cred)


# ------------------------------------------------------------------ dashboard "next action"
def next_action(db: Session, profile: IdentityProfile, user: CurrentUser) -> dict:
    docs = active_documents(db, profile.id)
    if not docs:
        return {"step": "upload_documents", "label": "Upload your passport, ID or visa", "route": "/app/documents"}
    unconfirmed = [d for d in docs if not confirmed_fields(db, d.id)]
    if unconfirmed:
        return {"step": "confirm_fields", "label": "Check the details we read from your documents",
                "route": f"/app/documents/{unconfirmed[0].id}"}
    ev = latest_evaluation(db, profile.id)
    if not ev:
        return {"step": "run_consistency", "label": "Run the identity consistency check", "route": "/app/consistency"}
    case = open_review(db, profile.id)
    if case:
        if case.status == "awaiting_evidence":
            return {"step": "provide_evidence", "label": "A reviewer asked for one more document",
                    "route": "/app/documents"}
        return {"step": "wait_review", "label": "A reviewer is checking one detail", "route": "/app/consistency"}
    stage = documentary_stage(db, profile)
    if not stage["consistency"]:
        return {"step": "run_consistency", "label": "Re-run the consistency check", "route": "/app/consistency"}
    bio = latest_biometric(db, profile.id)
    if not bio or bio.status != "passed":
        return {"step": "biometric", "label": "Complete the biometric check", "route": "/app/biometric"}
    cred = current_credential(db, profile.id)
    if permanent_status(db, profile.id) == "linked":
        return {"step": "done", "label": "Your permanent ID is linked", "route": "/app"}
    if not cred or cred.state in ("expired", "revoked"):
        return {"step": "issue_credential", "label": "Get your temporary credential", "route": "/app/eligibility"}
    return {"step": "manage", "label": "Your credential is active", "route": "/app/credential"}


def days_until(d: date | None) -> int | None:
    if not d:
        return None
    return (d - date.today()).days


def credential_expiry(profile_docs: list[IdentityDocument]) -> datetime:
    """Credential lasts CREDENTIAL_DAYS but never longer than the earliest-expiring primary document
    (unless that document is marked renewal_in_progress)."""
    from . import config
    end = utcnow() + timedelta(days=config.CREDENTIAL_DAYS)
    for d in profile_docs:
        if d.evidence_class == "primary" and d.expiry_date and d.renewal_status == "current":
            doc_end = datetime.combine(d.expiry_date, datetime.min.time(), tzinfo=timezone.utc)
            if utcnow() < doc_end < end:
                end = doc_end
    return end
