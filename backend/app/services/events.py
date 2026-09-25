"""Audit events (schema section 18) and in-app notifications (4.11)."""
from sqlalchemy.orm import Session

from ..models import AuditEvent, Notification


def audit(db: Session, actor: str | None, event_type: str, target_type: str,
          target_id: str | None, metadata: dict | None = None) -> None:
    # metadata must stay non-sensitive: statuses, types, counts. Never names, numbers or files.
    db.add(AuditEvent(actor_user_id=actor, event_type=event_type, target_type=target_type,
                      target_id=target_id, event_metadata=metadata or {}))


def notify(db: Session, user_id: str, type_: str, title: str, message: str,
           action_route: str | None = None, dedupe_key: str | None = None) -> None:
    if dedupe_key and db.query(Notification).filter_by(user_id=user_id, dedupe_key=dedupe_key).first():
        return
    db.add(Notification(user_id=user_id, type=type_, title=title, message=message,
                        action_route=action_route, dedupe_key=dedupe_key))
