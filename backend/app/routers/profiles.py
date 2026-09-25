from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..models import IdentityProfile, Notification
from ..services.events import audit
from .. import workflow as wf

router = APIRouter(prefix="/profiles", tags=["Identity profile"])


class ProfileIn(BaseModel):
    name_as_used: str = Field(min_length=1, max_length=200,
                              description="The name as the person uses it. Any script, any number of parts.")
    date_of_birth: date
    nationality: str = Field(min_length=2, max_length=60)
    phone_number: str | None = Field(default=None, max_length=30, description="With country code, e.g. +971501234567")
    current_country: str = Field(min_length=2, max_length=60)
    father_name: str | None = Field(default=None, max_length=200)
    mother_name: str | None = Field(default=None, max_length=200)


class ProfilePatch(BaseModel):
    name_as_used: str | None = Field(default=None, min_length=1, max_length=200)
    date_of_birth: date | None = None
    nationality: str | None = None
    phone_number: str | None = None
    current_country: str | None = None
    father_name: str | None = None
    mother_name: str | None = None


def _out(p: IdentityProfile) -> dict:
    return {"id": p.id, "name_as_used": p.name_as_used, "date_of_birth": p.date_of_birth,
            "nationality": p.nationality, "phone_number": p.phone_number, "current_country": p.current_country,
            "father_name": p.father_name, "mother_name": p.mother_name,
            "evidence_status": p.evidence_status, "setup_status": p.setup_status}


@router.post("", status_code=201)
def create_profile(body: ProfileIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(IdentityProfile).filter_by(user_id=user.id).first():
        raise HTTPException(409, "You already have a profile. Use PATCH /profiles/me to update it.")
    p = IdentityProfile(user_id=user.id, email=user.email, **body.model_dump())
    db.add(p)
    db.flush()
    audit(db, user.id, "profile_created", "profile", p.id)
    db.commit()
    return _out(p)


@router.get("/me")
def my_profile(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Dashboard data: profile + status of every stage + the one next action to show."""
    p = wf.profile_or_404(db, user)
    docs = wf.active_documents(db, p.id)
    ev = wf.latest_evaluation(db, p.id)
    bio = wf.latest_biometric(db, p.id)
    cred = wf.current_credential(db, p.id)
    case = wf.open_review(db, p.id)
    unread = db.query(Notification).filter_by(user_id=user.id, read_at=None).count()
    action = wf.next_action(db, p, user)
    if action["step"] in ("manage", "done") and p.setup_status != "completed":
        p.setup_status = "completed"
    db.commit()
    return {
        "profile": _out(p),
        "role": user.role,
        "status": {
            "identity": p.evidence_status,
            "documents": len(docs),
            "consistency": ev.overall_status if ev else "not_run",
            "review": case.status if case else "none",
            "biometric": bio.status if bio else "not_started",
            "temporary_credential": cred.state if cred else "not_issued",
            "permanent_credential": wf.permanent_status(db, p.id),
        },
        "document_health": [
            {"id": d.id, "document_type": d.document_type, "expiry_date": d.expiry_date,
             "days_left": wf.days_until(d.expiry_date), "renewal_status": d.renewal_status}
            for d in docs if d.expiry_date
        ],
        "unread_notifications": unread,
        "next_action": action,
    }


@router.patch("/me")
def update_profile(body: ProfilePatch, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    audit(db, user.id, "profile_updated", "profile", p.id, {"fields": sorted(changes)})
    # identity fields changed -> the old comparison no longer applies
    if set(changes) & {"name_as_used", "date_of_birth", "nationality", "father_name", "mother_name"} and wf.latest_evaluation(db, p.id):
        wf.run_evaluation(db, p, user.id)
    db.commit()
    return _out(p)
