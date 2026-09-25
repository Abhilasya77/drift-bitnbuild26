"""Permanent credential arrival (schema section 15): the final Emirates ID / local ID is uploaded,
cross-checked against the established identity, then linked — and the temporary credential expires.
Uncertain/conflicting results go to a reviewer instead of being linked silently."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ml import consistency as engine
from .. import workflow as wf
from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..models import PermanentCredentialLink, ReviewCase, IdentityProfile
from ..services.events import audit, notify

router = APIRouter(tags=["Permanent credential"])


def complete_link(db: Session, p: IdentityProfile, link: PermanentCredentialLink, actor: str | None) -> None:
    link.consistency_status = "consistent"
    link.linked_at = wf.utcnow()
    cred = wf.current_credential(db, p.id)
    if cred and cred.state in ("active", "in_transition"):
        cred.state = "expired"
        cred.revocation_reason = "Permanent credential linked"
        audit(db, actor, "credential_expired", "credential", cred.id, {"reason": "permanent_linked"})
        from .credentials import revoke_on_chain
        revoke_on_chain(db, cred, "permanent credential linked", actor)
    audit(db, actor, "permanent_credential_linked", "profile", p.id)
    notify(db, p.user_id, "permanent_id", "Your permanent ID is linked",
           "Your permanent ID has been added to your identity record. Your temporary credential is no longer needed "
           "and has expired. Services you signed up for with it stay; update them to your new ID number.",
           "/app")


class PermanentIn(BaseModel):
    document_id: str


@router.post("/permanent-credential")
def submit_permanent(body: PermanentIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Call after uploading the new ID (POST /documents with is_permanent_credential=true) and confirming its fields."""
    p = wf.profile_or_404(db, user)
    d = wf.document_or_404(db, p, body.document_id)
    new_fields = wf.confirmed_fields(db, d.id)
    if not new_fields.get("name"):
        raise HTTPException(409, "Confirm the fields on the new ID first.")
    d.is_permanent_credential = True
    audit(db, user.id, "permanent_credential_submitted", "document", d.id, {"type": d.document_type})

    # compare the new ID with every established document + the profile
    established = [x for x in wf.active_documents(db, p.id) if x.id != d.id and not x.is_permanent_credential]
    payload = [{"id": x.id, "document_type": x.document_type, "evidence_class": x.evidence_class,
                "fields": wf.confirmed_fields(db, x.id)} for x in established]
    payload = [x for x in payload if x["fields"]]
    new_doc = {"id": d.id, "document_type": d.document_type, "evidence_class": "primary", "fields": new_fields}
    result = engine.evaluate(wf.profile_dict(p), payload + [new_doc])
    relevant = [c for c in result["comparisons"] if d.id in (c["source_a_document_id"], c["source_b_document_id"])]
    status = max((c["classification"] for c in relevant), key=engine.SEVERITY.get, default="uncertain")
    link_status = {"match": "consistent", "explainable_variant": "consistent"}.get(status, status)

    link = PermanentCredentialLink(profile_id=p.id, document_id=d.id, consistency_status=link_status)
    db.add(link)
    db.flush()
    if link_status == "consistent":
        complete_link(db, p, link, user.id)
        outcome = "linked"
    else:
        reason = " | ".join(f"{c['field']}: {c['explanation']}" for c in relevant
                            if c["classification"] in ("uncertain", "conflict"))
        db.add(ReviewCase(profile_id=p.id, kind="permanent_credential", reason=reason or "Needs a check."))
        cred = wf.current_credential(db, p.id)
        if cred and cred.state == "active":
            cred.state = "in_transition"            # still usable while the reviewer checks
        notify(db, user.id, "permanent_id", "Your new ID needs a quick check",
               "Some details on your new ID differ from your earlier documents. A reviewer will check. "
               "Your temporary credential stays usable meanwhile.", "/app")
        outcome = "under_review"
    db.commit()
    return {"outcome": outcome, "consistency_status": link_status,
            "comparisons": [{k: c[k] for k in ("field", "source_a", "source_b", "classification", "explanation")}
                            for c in relevant]}
