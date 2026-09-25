from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import config
from .. import workflow as wf
from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..models import IdentityDocument, DocumentField, FieldComparison
from ..services import ocr, storage
from ..services.events import audit, notify

router = APIRouter(prefix="/documents", tags=["Documents"])

EDITABLE_FIELDS = {"name", "dob", "nationality", "document_number", "expiry_date", "father_name"}


def _doc_out(db: Session, d: IdentityDocument, with_fields: bool = False) -> dict:
    out = {"id": d.id, "document_type": d.document_type, "evidence_class": d.evidence_class,
           "original_filename": d.original_filename, "processing_status": d.processing_status,
           "renewal_status": d.renewal_status, "expiry_date": d.expiry_date,
           "days_left": wf.days_until(d.expiry_date), "replaces_document_id": d.replaces_document_id,
           "is_permanent_credential": d.is_permanent_credential, "created_at": d.created_at,
           "fields_confirmed": bool(wf.confirmed_fields(db, d.id))}
    if with_fields:
        rows = db.query(DocumentField).filter_by(document_id=d.id).order_by(DocumentField.created_at).all()
        latest = {}
        for r in rows:                                   # latest value per field wins
            latest[r.field_name] = r
        out["fields"] = [{"field_name": r.field_name, "value": r.original_value, "source": r.source,
                          "confidence": r.confidence, "confirmed": r.confirmed} for r in latest.values()]
    return out


@router.post("", status_code=201)
async def upload_document(
    document_type: str = Form(..., description="passport / national_id / gcc_id / visa_residence / grade10 / grade12 / other"),
    file: UploadFile = File(...),
    replaces_document_id: str | None = Form(default=None, description="Set when uploading a renewed document"),
    is_permanent_credential: bool = Form(default=False, description="True for the final Emirates ID / local ID"),
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    p = wf.profile_or_404(db, user)
    if document_type not in wf.DOC_TYPES:
        raise HTTPException(422, f"Unknown document type. Use one of: {', '.join(sorted(wf.DOC_TYPES))}")
    if file.content_type not in config.ALLOWED_MIME:
        raise HTTPException(415, "Please upload a JPG, PNG or PDF file.")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is too large (max {config.MAX_UPLOAD_MB} MB).")
    if not data:
        raise HTTPException(422, "The file is empty.")
    old = None
    if replaces_document_id:
        old = wf.document_or_404(db, p, replaces_document_id)

    d = IdentityDocument(profile_id=p.id, document_type=document_type,
                         evidence_class="primary" if document_type in wf.PRIMARY_TYPES else "supporting",
                         storage_path="", original_filename=(file.filename or "")[:120], mime_type=file.content_type,
                         replaces_document_id=old.id if old else None,
                         is_permanent_credential=is_permanent_credential)
    db.add(d)
    db.flush()
    d.storage_path = f"{user.id}/{p.id}/{d.id}/{storage.safe_filename(file.filename, file.content_type)}"
    storage.save(d.storage_path, data, file.content_type)
    audit(db, user.id, "document_uploaded", "document", d.id,
          {"type": document_type, "renewal": bool(old), "permanent": is_permanent_credential})
    db.commit()
    return _doc_out(db, d)


@router.get("")
def list_documents(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    docs = db.query(IdentityDocument).filter_by(profile_id=p.id).order_by(IdentityDocument.created_at).all()
    return [_doc_out(db, d) for d in docs]


@router.get("/{doc_id}")
def get_document(doc_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    return _doc_out(db, wf.document_or_404(db, p, doc_id), with_fields=True)


@router.get("/{doc_id}/file")
def get_document_file(doc_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """The owner can preview their own upload. Never public."""
    p = wf.profile_or_404(db, user)
    d = wf.document_or_404(db, p, doc_id)
    return Response(storage.load(d.storage_path), media_type=d.mime_type or "application/octet-stream",
                    headers={"Cache-Control": "no-store"})


@router.post("/{doc_id}/process")
def process_document(doc_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run OCR (Tesseract + passport MRZ). Results are saved UNCONFIRMED; the user confirms them next."""
    p = wf.profile_or_404(db, user)
    d = wf.document_or_404(db, p, doc_id)
    d.processing_status = "processing"
    fields, confidence, note = ocr.extract(storage.load(d.storage_path), d.mime_type or "")
    for name, value in fields.items():
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = ",".join(value)
        db.add(DocumentField(document_id=d.id, field_name=name, original_value=str(value),
                             normalized_value=str(value).strip().upper(), source="ocr",
                             confidence=confidence, confirmed=False))
    d.processing_status = "processed" if fields else "action_required"
    audit(db, user.id, "document_processed", "document", d.id,
          {"fields_found": len(fields), "status": d.processing_status})
    db.commit()
    out = _doc_out(db, d, with_fields=True)
    out["note"] = note
    return out


class ConfirmFields(BaseModel):
    """Values exactly as printed on the document. Dates as YYYY-MM-DD."""
    name: str | None = None
    dob: date | None = None
    nationality: str | None = None
    document_number: str | None = None
    expiry_date: date | None = None
    father_name: str | None = None


@router.post("/{doc_id}/confirm-fields")
def confirm_fields(doc_id: str, body: ConfirmFields, user: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """User checks/corrects what OCR read (or types it if OCR found nothing). Only confirmed values are compared.
    MRZ integrity results from OCR (mrz_check) are kept as-is and cannot be edited by the user."""
    p = wf.profile_or_404(db, user)
    d = wf.document_or_404(db, p, doc_id)
    values = {k: (v.isoformat() if isinstance(v, date) else v)
              for k, v in body.model_dump(exclude_unset=True).items() if v not in (None, "")}
    if not values.get("name"):
        raise HTTPException(422, "Please enter the name exactly as it is printed on this document.")

    ocr_rows = {r.field_name: r for r in db.query(DocumentField).filter_by(document_id=d.id, source="ocr").all()}
    # previous confirmations are replaced
    db.query(DocumentField).filter(DocumentField.document_id == d.id, DocumentField.source != "ocr").delete()
    db.query(DocumentField).filter_by(document_id=d.id, source="ocr").update({"confirmed": False})
    for name, value in values.items():
        o = ocr_rows.get(name)
        if o and o.original_value == str(value):
            o.confirmed = True                                   # OCR value accepted as read
        else:
            db.add(DocumentField(document_id=d.id, field_name=name, original_value=str(value),
                                 normalized_value=str(value).strip().upper(), source="user_confirmed",
                                 confidence=None, confirmed=True))
    for integrity in ("mrz_check", "mrz_failed_parts"):         # tamper signal: always carried over
        if integrity in ocr_rows:
            ocr_rows[integrity].confirmed = True

    if values.get("document_number"):
        d.document_number = values["document_number"]
    if values.get("expiry_date"):
        d.expiry_date = date.fromisoformat(values["expiry_date"])
    d.processing_status = "processed"

    # a renewed document replaces the old one once its fields are confirmed
    if d.replaces_document_id:
        old = db.get(IdentityDocument, d.replaces_document_id)
        if old and old.renewal_status != "replaced":
            old.renewal_status = "replaced"
            audit(db, user.id, "document_replaced", "document", old.id, {"by": d.id})
            notify(db, user.id, "expiry", "Renewed document added",
                   f"Your new {d.document_type.replace('_', ' ')} replaced the old one. Your identity history is kept.",
                   "/app/documents")
    audit(db, user.id, "document_fields_confirmed", "document", d.id, {"fields": sorted(values)})
    db.commit()
    return _doc_out(db, d, with_fields=True)


@router.get("/{doc_id}/compare-previous")
def compare_previous(doc_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Renewal view: what changed between the old and the new document (number, expiry) vs what stayed (name, DOB)."""
    p = wf.profile_or_404(db, user)
    new = wf.document_or_404(db, p, doc_id)
    if not new.replaces_document_id:
        raise HTTPException(400, "This document does not replace an earlier one.")
    a, b = wf.confirmed_fields(db, new.replaces_document_id), wf.confirmed_fields(db, new.id)
    rows = []
    for f in ("name", "dob", "nationality", "document_number", "expiry_date"):
        if f in a or f in b:
            changed = (a.get(f) or "").strip().upper() != (b.get(f) or "").strip().upper()
            stable = f in ("name", "dob", "nationality")
            rows.append({"field": f, "old": a.get(f), "new": b.get(f), "changed": changed,
                         "expected_to_change": not stable,
                         "note": ("Needs attention: identity field changed" if changed and stable else
                                  "Updated as expected" if changed else "Unchanged")})
    return {"old_document_id": new.replaces_document_id, "new_document_id": new.id, "fields": rows}


@router.post("/{doc_id}/renewal")
def mark_renewal(doc_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark 'Renewal in Progress'. The established identity is kept; the credential is not cut short by
    this document's old expiry date while the renewal is pending."""
    p = wf.profile_or_404(db, user)
    d = wf.document_or_404(db, p, doc_id)
    d.renewal_status = "renewal_in_progress"
    audit(db, user.id, "renewal_started", "document", d.id, {"type": d.document_type})
    notify(db, user.id, "expiry", "Renewal in progress",
           f"We've noted that your {d.document_type.replace('_', ' ')} is being renewed. "
           "Upload the new one when you have it.", "/app/documents")
    db.commit()
    return _doc_out(db, d)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove an upload that hasn't been used for a credential yet (e.g. wrong file)."""
    p = wf.profile_or_404(db, user)
    d = wf.document_or_404(db, p, doc_id)
    if wf.current_credential(db, p.id):
        raise HTTPException(409, "This document supports an issued credential. Mark it for renewal instead.")
    storage.delete(d.storage_path)
    db.query(DocumentField).filter_by(document_id=d.id).delete()
    db.query(FieldComparison).filter_by(source_a_document_id=d.id).update({"source_a_document_id": None})
    db.query(FieldComparison).filter_by(source_b_document_id=d.id).update({"source_b_document_id": None})
    db.query(IdentityDocument).filter_by(replaces_document_id=d.id).update({"replaces_document_id": None})
    db.delete(d)
    audit(db, user.id, "document_deleted", "document", doc_id)
    db.commit()
