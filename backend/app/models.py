"""Database tables — follows 'Identity Continuity Platform – Backend Schema' section 4.

Small additions (marked ADDED) are nullable, so the schema doc still holds.
IDs are UUID strings so the same code runs on SQLite (local) and Supabase Postgres.
Enum-like columns are plain text; allowed values are listed in comments and in app/enums.py.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Date, DateTime, Boolean, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class IdentityProfile(Base):                      # 4.1
    __tablename__ = "identity_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)   # auth.users.id
    email: Mapped[str | None] = mapped_column(Text)                             # ADDED: convenience for notifications
    name_as_used: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[datetime | None] = mapped_column(Date)
    nationality: Mapped[str] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(Text)
    current_country: Mapped[str] = mapped_column(Text)
    father_name: Mapped[str | None] = mapped_column(Text)   # ADDED: optional; explains "father's name appended" variants
    mother_name: Mapped[str | None] = mapped_column(Text)   # ADDED: optional supporting info
    evidence_status: Mapped[str] = mapped_column(String(32), default="self_declared")
    # self_declared / evidence_backed / action_required / under_review
    setup_status: Mapped[str] = mapped_column(String(32), default="in_progress")
    # not_completed / in_progress / completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IdentityDocument(Base):                     # 4.2
    __tablename__ = "identity_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("identity_profiles.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(32))
    # passport / national_id / gcc_id / visa_residence / grade10 / grade12 / other
    evidence_class: Mapped[str] = mapped_column(String(16))          # primary / supporting
    storage_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    document_number: Mapped[str | None] = mapped_column(Text)
    expiry_date: Mapped[datetime | None] = mapped_column(Date)
    processing_status: Mapped[str] = mapped_column(String(32), default="uploaded")
    # uploaded / processing / processed / action_required / failed
    renewal_status: Mapped[str] = mapped_column(String(32), default="current")
    # current / renewal_in_progress / replaced / expired
    replaces_document_id: Mapped[str | None] = mapped_column(ForeignKey("identity_documents.id"))
    is_permanent_credential: Mapped[bool] = mapped_column(Boolean, default=False)  # ADDED: marks the final local ID
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentField(Base):                        # 4.3
    __tablename__ = "document_fields"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("identity_documents.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    # name / dob / nationality / document_number / expiry_date / father_name / mrz_check ...
    original_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="ocr")   # ocr / user_confirmed / manual_demo
    confidence: Mapped[float | None] = mapped_column(Float)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConsistencyEvaluation(Base):                # 4.4
    __tablename__ = "consistency_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("identity_profiles.id"), index=True)
    overall_status: Mapped[str] = mapped_column(String(32))   # match / explainable_variant / uncertain / conflict
    engine_version: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FieldComparison(Base):                      # 4.5
    __tablename__ = "field_comparisons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("consistency_evaluations.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    source_a_document_id: Mapped[str | None] = mapped_column(ForeignKey("identity_documents.id"))  # null = profile
    source_b_document_id: Mapped[str | None] = mapped_column(ForeignKey("identity_documents.id"))
    value_a: Mapped[str | None] = mapped_column(Text)
    value_b: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(32))
    similarity_score: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewCase(Base):                           # 4.6
    __tablename__ = "review_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("identity_profiles.id"), index=True)
    evaluation_id: Mapped[str | None] = mapped_column(ForeignKey("consistency_evaluations.id"))
    status: Mapped[str] = mapped_column(String(32), default="open")   # open / under_review / awaiting_evidence / resolved
    assigned_reviewer_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)   # cleared / not_cleared
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default="consistency")  # ADDED: consistency / biometric / permanent_credential
    signature: Mapped[str | None] = mapped_column(Text)  # ADDED: fingerprint of the flagged differences (no re-review of the same thing)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewAction(Base):                         # 4.7
    __tablename__ = "review_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    review_case_id: Mapped[str] = mapped_column(ForeignKey("review_cases.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(36))
    action_type: Mapped[str] = mapped_column(String(32))   # opened / requested_evidence / resolved / reopened
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BiometricVerification(Base):                # 4.8 — no raw biometric data stored
    __tablename__ = "biometric_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("identity_profiles.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))   # compreface / simulated
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    # not_started / processing / passed / retry / failed / requires_review
    verification_reference: Mapped[str | None] = mapped_column(Text)
    similarity_metadata: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Credential(Base):                           # 4.9
    __tablename__ = "credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("identity_profiles.id"), index=True)
    public_credential_id: Mapped[str] = mapped_column(String(32), unique=True)
    verification_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    evidence_status: Mapped[str] = mapped_column(String(32))
    biometric_status: Mapped[str] = mapped_column(String(32))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(32), default="active")   # active / in_transition / expired / revoked
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PermanentCredentialLink(Base):              # 4.10
    __tablename__ = "permanent_credential_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(ForeignKey("identity_profiles.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("identity_documents.id"))
    consistency_status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending / consistent / uncertain / conflict
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):                         # 4.11
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(32))   # expiry / review / evidence_request / credential / permanent_id / general
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    action_route: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text, index=True)   # ADDED: avoids duplicate expiry reminders
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):                           # 4.12
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(36))
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)   # non-sensitive only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Attestation(Base):                          # 4.13 (optional Web3)
    __tablename__ = "attestations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    credential_id: Mapped[str] = mapped_column(ForeignKey("credentials.id"), index=True)
    network: Mapped[str] = mapped_column(String(32), default="polygon-amoy")
    attestation_hash: Mapped[str] = mapped_column(String(80))
    transaction_hash: Mapped[str | None] = mapped_column(String(80))
    contract_address: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")   # pending / confirmed / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
