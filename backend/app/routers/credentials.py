from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ml import consistency as engine
from .. import workflow as wf
from .. import config
from ..auth import CurrentUser, get_current_user
from ..db import get_db
from ..models import Credential, Attestation, IdentityProfile, IdentityDocument
from ..services import credentials as creds
from ..services import web3_attest
from ..services.events import audit, notify

router = APIRouter(tags=["Eligibility & credential"])


def cred_hash(c: Credential) -> str:
    """Non-sensitive fingerprint written on-chain. Same inputs every time -> same hash."""
    return creds.attestation_hash(c.public_credential_id, wf.aware(c.issued_at).isoformat(),
                                  wf.aware(c.expires_at).isoformat(), "issued")


def attest_on_chain(db: Session, c: Credential, actor: str | None) -> None:
    """Called automatically after issuing. Never blocks issuance if the chain is unavailable."""
    if not web3_attest.enabled():
        return
    h = cred_hash(c)
    a = Attestation(credential_id=c.id, network=config.WEB3_NETWORK, attestation_hash=h,
                    contract_address=config.WEB3_CONTRACT_ADDRESS)
    try:
        a.transaction_hash = web3_attest.attest(h, int(wf.aware(c.expires_at).timestamp()))
        a.status = "pending"
        audit(db, actor, "attestation_submitted", "credential", c.id, {"network": a.network})
    except Exception as exc:                      # chain down / no gas / wrong key: credential still works
        a.status = "failed"
        audit(db, actor, "attestation_failed", "credential", c.id, {"error": type(exc).__name__})
    db.add(a)


def revoke_on_chain(db: Session, c: Credential, reason: str, actor: str | None) -> None:
    att = db.query(Attestation).filter_by(credential_id=c.id, status="confirmed").first() or \
        db.query(Attestation).filter_by(credential_id=c.id, status="pending").first()
    if not att or not web3_attest.enabled():
        return
    try:
        tx = web3_attest.revoke(att.attestation_hash, reason)
        audit(db, actor, "attestation_revoked", "credential", c.id, {"tx": tx})
    except Exception as exc:
        audit(db, actor, "attestation_revoke_failed", "credential", c.id, {"error": type(exc).__name__})


def _refresh_attestation(att: Attestation | None) -> None:
    if att and att.status == "pending" and att.transaction_hash and web3_attest.enabled():
        try:
            att.status = web3_attest.tx_status(att.transaction_hash)
        except Exception:
            pass


def _cred_out(db: Session, c: Credential) -> dict:
    token = creds.token_for(c.id)
    att = db.query(Attestation).filter_by(credential_id=c.id).order_by(Attestation.created_at.desc()).first()
    _refresh_attestation(att)
    return {
        "label": "Temporary Platform Credential",
        "disclaimer": "Issued by this platform. Not a government ID and not a replacement for Emirates ID or a passport.",
        "public_credential_id": c.public_credential_id,
        "state": c.state, "evidence_status": c.evidence_status, "biometric_status": c.biometric_status,
        "issued_at": c.issued_at, "expires_at": c.expires_at,
        "days_left": max(0, (wf.aware(c.expires_at) - wf.utcnow()).days),
        "verification_url": creds.verify_url(token),
        "qr_png_url": "/credentials/current/qr",
        "attestation": {"network": att.network, "transaction_hash": att.transaction_hash, "status": att.status,
                        "attestation_hash": att.attestation_hash,
                        "explorer_url": web3_attest.explorer_tx_url(att.transaction_hash)} if att else None,
    }


@router.get("/eligibility")
def get_eligibility(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    return wf.eligibility(db, p, user)


@router.post("/credentials", status_code=201)
def issue(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Issued ONLY if the server-side eligibility check passes (the frontend can't fake it)."""
    p = wf.profile_or_404(db, user)
    elig = wf.eligibility(db, p, user)
    if not elig["eligible"]:
        missing = [i["label"] for i in elig["items"] if not i["passed"]]
        raise HTTPException(409, {"message": "Not eligible yet.", "missing": missing})
    existing = wf.current_credential(db, p.id)
    if existing and existing.state in ("active", "in_transition"):
        return _cred_out(db, existing)
    c = Credential(profile_id=p.id, public_credential_id=creds.new_public_id(), verification_token_hash="pending",
                   evidence_status=p.evidence_status, biometric_status="passed",
                   expires_at=wf.credential_expiry(wf.active_documents(db, p.id)), state="active")
    db.add(c)
    db.flush()
    c.verification_token_hash = creds.hash_token(creds.token_for(c.id))
    audit(db, user.id, "credential_issued", "credential", c.id, {"expires_at": c.expires_at.isoformat()})
    attest_on_chain(db, c, user.id)
    notify(db, user.id, "credential", "Your temporary credential is ready",
           f"Credential {c.public_credential_id} is active until {c.expires_at:%d %b %Y}.", "/app/credential")
    db.commit()
    return _cred_out(db, c)


@router.get("/credentials/current")
def current(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    c = wf.current_credential(db, p.id)
    db.commit()
    if not c:
        raise HTTPException(404, "No credential issued yet.")
    return _cred_out(db, c)


@router.get("/credentials/current/qr", responses={200: {"content": {"image/png": {}}}})
def current_qr(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """QR image. It contains only an opaque verification link — no personal data."""
    p = wf.profile_or_404(db, user)
    c = wf.current_credential(db, p.id)
    if not c:
        raise HTTPException(404, "No credential issued yet.")
    return Response(creds.qr_png(creds.verify_url(creds.token_for(c.id))), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ optional Web3 attestation
@router.get("/credentials/current/attestation-payload")
def attestation_payload(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """The hash the blockchain teammate writes to Polygon Amoy (e.g. from MetaMask in the frontend).
    Contains no names, DOB, document numbers or biometrics."""
    p = wf.profile_or_404(db, user)
    c = wf.current_credential(db, p.id)
    if not c:
        raise HTTPException(404, "No credential issued yet.")
    return {"credential_id": c.public_credential_id, "attestation_hash": cred_hash(c),
            "expires_at_unix": int(wf.aware(c.expires_at).timestamp()),
            "contract_address": config.WEB3_CONTRACT_ADDRESS or None, "chain_id": config.WEB3_CHAIN_ID}


class AttestationIn(BaseModel):
    transaction_hash: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")
    contract_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")
    network: str = "polygon-amoy"
    # Use this only if the frontend sends the transaction itself (MetaMask). If WEB3_* is configured,
    # the backend attests automatically at issuance and you don't need this endpoint.


@router.post("/credentials/current/attestation", status_code=201)
def record_attestation(body: AttestationIn, user: CurrentUser = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    c = wf.current_credential(db, p.id)
    if not c:
        raise HTTPException(404, "No credential issued yet.")
    h = attestation_payload(user, db)["attestation_hash"]
    a = Attestation(credential_id=c.id, network=body.network, attestation_hash=h,
                    transaction_hash=body.transaction_hash, contract_address=body.contract_address, status="confirmed")
    db.add(a)
    audit(db, user.id, "attestation_confirmed", "credential", c.id, {"network": body.network})
    db.commit()
    return {"attestation_hash": h, "transaction_hash": a.transaction_hash, "network": a.network}


# ------------------------------------------------------------------ participating service verification
def _by_token(db: Session, token: str) -> Credential:
    c = db.query(Credential).filter_by(verification_token_hash=creds.hash_token(token)).first()
    if not c:
        raise HTTPException(404, "Credential not found or invalid.")   # no identity data leaked
    return wf.refresh_credential_state(db, c)


@router.get("/verify/{token}", tags=["Service verification"])
def verify(token: str, db: Session = Depends(get_db)):
    """What a participating service (fictional bank/telecom) sees after scanning the QR.
    Minimal result only: no document images, biometrics or document numbers."""
    c = _by_token(db, token)
    p = db.get(IdentityProfile, c.profile_id)
    unresolved = wf.open_review(db, p.id) is not None
    att = db.query(Attestation).filter_by(credential_id=c.id).order_by(Attestation.created_at.desc()).first()
    _refresh_attestation(att)
    on_chain = None
    if att:
        on_chain = {"network": att.network, "transaction_hash": att.transaction_hash, "status": att.status,
                    "explorer_url": web3_attest.explorer_tx_url(att.transaction_hash)}
        if web3_attest.enabled() and att.status == "confirmed":
            try:
                chain = web3_attest.verify(att.attestation_hash)
                on_chain.update({"exists": chain["exists"], "valid_on_chain": chain["valid"],
                                 "revoked_on_chain": bool(chain["revoked_at"])})
            except Exception:
                on_chain["note"] = "Blockchain not reachable right now; database status shown."
    audit(db, None, "credential_verified", "credential", c.id, {"state": c.state})
    db.commit()
    return {
        "credential_id": c.public_credential_id,
        "credential_state": c.state,
        "is_valid": c.state in ("active", "in_transition"),
        "identity_evidence_established": c.evidence_status in ("evidence_backed",),
        "biometric_completed": c.biometric_status == "passed",
        "unresolved_conflicts": unresolved,
        "issued_at": c.issued_at,
        "expires_at": c.expires_at,
        "supported_name_representation": p.name_as_used,
        "issuer": "Identity Continuity Platform (prototype)",
        "note": "Platform-issued credential. Each service applies its own acceptance policy.",
        "on_chain_attestation": on_chain,
    }


class NameCheck(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="The name the service has on file, e.g. a beneficiary name")


@router.post("/verify/{token}/name", tags=["Service verification"])
def verify_name(token: str, body: NameCheck, db: Session = Depends(get_db)):
    """Is this name supported by one of the person's confirmed documents? (e.g. the exchange-house case where
    the visa adds the father's name). Answers yes/no + which document type, never the document values."""
    c = _by_token(db, token)
    if c.state not in ("active", "in_transition"):
        return {"supported": False, "explanation": f"Credential is {c.state}."}
    p = db.get(IdentityProfile, c.profile_id)
    names = [(engine.LABELS.get(d.document_type, "Document"), wf.confirmed_fields(db, d.id).get("name"))
             for d in wf.active_documents(db, p.id)]
    names = [(label, n) for label, n in names if n] + [("Profile", p.name_as_used)]
    family = [p.father_name, p.mother_name] + [wf.confirmed_fields(db, d.id).get("father_name")
                                               for d in wf.active_documents(db, p.id)]
    result = engine.name_supported(body.name, names, [f for f in family if f])
    audit(db, None, "name_verified", "credential", c.id, {"supported": result["supported"]})
    db.commit()
    # don't echo document name parts back to the service: only the verdict and which document type supports it
    doc = result.get("closest_document", "a document")
    message = {
        "match": f"This name matches the person's {doc}.",
        "explainable_variant": f"This name is an accepted variation of the name on the person's {doc} "
                               "(e.g. added father's name, spacing, word order or spelling variant).",
        "uncertain": "This name is close to, but not clearly supported by, the person's documents. "
                     "Ask the person to confirm or use another name form.",
        "conflict": "This name is not supported by the person's verified documents.",
    }.get(result.get("classification"), result.get("explanation"))
    return {"supported": result["supported"], "classification": result.get("classification"),
            "supported_by": doc if result["supported"] else None, "explanation": message}
