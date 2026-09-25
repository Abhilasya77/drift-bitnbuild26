from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import sqlite3, json, uuid, hashlib

app = FastAPI(title="VeriMove API")

# Lets the frontend (running on another port) call this API
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

DB_FILE = "verimove.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS signups (id TEXT PRIMARY KEY, data TEXT)")
    return conn

# ---------- What the signup form sends ----------
class Address(BaseModel):
    line1: str
    landmark: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None   # optional on purpose: many UAE addresses have none

class SignupIn(BaseModel):
    full_name: str                   # one field, any language: no first/last split
    preferred_name: Optional[str] = None
    country: str
    address: Address
    phone: str
    email: Optional[str] = None
    nationality: Optional[str] = None
    document_type: Optional[str] = None
    visa_expiry: Optional[str] = None

class Decision(BaseModel):
    decision: str                    # "approved" or "rejected"

# ---------- Plug-in points for teammates ----------
def score_risk(signup: dict):
    """TEMPORARY. The ML teammate replaces this with the real model."""
    return 0.10, ["Placeholder score (ML model not connected yet)"]

def make_credential_hash(signup: dict):
    """Fingerprint of the verified identity. The blockchain teammate stores this on-chain."""
    core = {k: signup[k] for k in ("id", "full_name", "nationality", "created_at")}
    return "0x" + hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()

# ---------- Helpers ----------
def save(signup: dict):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO signups VALUES (?, ?)",
                     (signup["id"], json.dumps(signup)))

def load(signup_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT data FROM signups WHERE id = ?", (signup_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Signup not found")
    return json.loads(row[0])

# ---------- API endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/signups")
def create_signup(data: SignupIn):
    signup = data.model_dump()
    signup["id"] = "u_" + uuid.uuid4().hex[:8]
    signup["created_at"] = datetime.now(timezone.utc).isoformat()

    score, reasons = score_risk(signup)
    signup["risk_score"] = score
    signup["risk_reasons"] = reasons

    if score < 0.5:
        signup["status"] = "auto_approved"
        signup["credential_hash"] = make_credential_hash(signup)
    else:
        signup["status"] = "needs_review"
        signup["credential_hash"] = None

    save(signup)
    return signup

@app.get("/signups")
def list_signups(status: Optional[str] = None):
    with get_db() as conn:
        rows = conn.execute("SELECT data FROM signups").fetchall()
    signups = [json.loads(r[0]) for r in rows]
    if status:
        signups = [s for s in signups if s["status"] == status]
    return signups

@app.get("/signups/{signup_id}")
def get_signup(signup_id: str):
    return load(signup_id)

@app.post("/signups/{signup_id}/decision")
def decide(signup_id: str, body: Decision):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be 'approved' or 'rejected'")
    signup = load(signup_id)
    signup["status"] = body.decision
    if body.decision == "approved":
        signup["credential_hash"] = make_credential_hash(signup)
    save(signup)
    return signup