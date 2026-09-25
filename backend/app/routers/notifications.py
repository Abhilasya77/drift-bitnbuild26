from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from .. import workflow as wf
from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..models import Notification, IdentityProfile, IdentityDocument, Credential
from ..services.events import notify

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return [{"id": n.id, "type": n.type, "title": n.title, "message": n.message, "action_route": n.action_route,
             "read": n.read_at is not None, "created_at": n.created_at} for n in rows]


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter_by(id=notification_id, user_id=user.id).first()
    if not n:
        raise HTTPException(404, "Notification not found.")
    n.read_at = wf.utcnow()
    db.commit()
    return {"ok": True}


def run_expiry_check(db: Session) -> int:
    """Creates reminders REMINDER_DAYS (default 30 and 7) before a document or credential expires.
    Safe to run repeatedly (deduplicated). Called on a schedule or from the demo endpoint."""
    before = db.query(Notification).count()
    today = date.today()
    for p in db.query(IdentityProfile).all():
        for d in wf.active_documents(db, p.id):
            if not d.expiry_date or d.renewal_status != "current":
                continue
            left = (d.expiry_date - today).days
            label = d.document_type.replace("_", " ")
            if left < 0:
                d.renewal_status = "expired"
                notify(db, p.user_id, "expiry", f"Your {label} has expired",
                       f"Your {label} expired on {d.expiry_date:%d %b %Y}. Mark it as 'renewal in progress' "
                       "or upload the new one.", "/app/documents", dedupe_key=f"exp:{d.id}:expired")
                continue
            for days in sorted(config.REMINDER_DAYS):
                if left <= days:
                    notify(db, p.user_id, "expiry", f"Your {label} expires in {left} days",
                           f"Your {label} expires on {d.expiry_date:%d %b %Y}. Start the renewal early; "
                           "you can mark it as 'renewal in progress' here.", "/app/documents",
                           dedupe_key=f"exp:{d.id}:{days}")
                    break
        cred = wf.current_credential(db, p.id)
        if cred and cred.state in ("active", "in_transition"):
            left = (wf.aware(cred.expires_at) - wf.utcnow()).days
            for days in sorted(config.REMINDER_DAYS):
                if left <= days:
                    notify(db, p.user_id, "credential", f"Your temporary credential expires in {left} days",
                           "Got your Emirates ID or permanent ID? Add it to switch over. "
                           "If it's still pending, check your eligibility to get a new temporary credential.",
                           "/app/credential", dedupe_key=f"cred:{cred.id}:{days}")
                    break
    db.commit()
    return db.query(Notification).count() - before


@router.post("/run-expiry-check")
def trigger_expiry_check(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Demo trigger for the reminder job (in production this runs on a schedule)."""
    return {"created": run_expiry_check(db)}
