"""Runs Ravi's happy path against your real setup (your .env), end to end, and prints the
credential, verify link and the Polygon Amoy transaction.

    cd backend && python demo/run_demo_flow.py

Uses AUTH_MODE=dev style login (header X-Demo-User). Each run creates a new demo user.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402

DOCS = Path(__file__).parent / "docs"
if config.AUTH_MODE != "dev":
    sys.exit("This script needs AUTH_MODE=dev in .env (it logs in with the X-Demo-User header).")
if not DOCS.exists():
    sys.exit("Run python demo/make_demo_docs.py first.")

who = {"X-Demo-User": f"ravi.demo{int(time.time())}@drift.demo"}


def step(label, r):
    ok = r.status_code < 300
    print(("  OK  " if ok else "  !!  ") + label + ("" if ok else f"  -> {r.status_code} {r.text[:300]}"))
    if not ok:
        sys.exit(1)
    return r.json() if r.content else None


with TestClient(app) as c:
    print("Demo user:", who["X-Demo-User"])
    step("create profile", c.post("/profiles", headers=who, json={
        "name_as_used": "Ravi Kumar Venkatesh", "date_of_birth": "1994-03-12", "nationality": "India",
        "phone_number": "+971501234567", "current_country": "United Arab Emirates", "father_name": "Srinivasa Rao"}))
    for doc_type, fname in (("passport", "ravi_passport.png"), ("visa_residence", "ravi_visa.png"),
                            ("grade10", "ravi_grade10.png")):
        with open(DOCS / fname, "rb") as f:
            d = step(f"upload {doc_type}", c.post("/documents", headers=who, data={"document_type": doc_type},
                                                   files={"file": (fname, f, "image/png")}))
        out = step(f"OCR {doc_type}", c.post(f"/documents/{d['id']}/process", headers=who))
        read = {x["field_name"]: x["value"] for x in out["fields"]}
        if not read.get("name"):
            sys.exit("OCR found nothing: install Tesseract (brew install tesseract) and try again.")
        keep = {k: read[k] for k in ("name", "dob", "nationality", "document_number", "expiry_date", "father_name")
                if k in read}
        step(f"confirm {doc_type}", c.post(f"/documents/{d['id']}/confirm-fields", headers=who, json=keep))

    ev = step("consistency check", c.post("/consistency/evaluate", headers=who))
    print("       ->", ev["overall_status"], "|", ev["summary"])
    with open(DOCS / "ravi_passport.png", "rb") as f:
        bio = step("biometric", c.post("/biometric/start", headers=who, files={"selfie": ("me.png", f, "image/png")}))
    print("       ->", bio["status"], f"({bio['provider']})")
    cred = step("issue credential", c.post("/credentials", headers=who))
    print("\nCredential:", cred["public_credential_id"], "| state:", cred["state"], "| expires:", cred["expires_at"])
    print("Verify link:", cred["verification_url"])

    att = cred.get("attestation")
    if not att:
        print("\nWeb3 is OFF (WEB3_* not set in .env), so there's no on-chain attestation.")
    else:
        print("On-chain tx:", att["transaction_hash"], "| status:", att["status"])
        if att.get("explorer_url"):
            print("Explorer:  ", att["explorer_url"])
        for _ in range(12):                      # wait up to ~60 s for confirmation
            if att["status"] != "pending":
                break
            time.sleep(5)
            att = c.get("/credentials/current", headers=who).json()["attestation"]
        print("Final attestation status:", att["status"])
        token = cred["verification_url"].rsplit("/", 1)[1]
        print("Verifier sees on-chain:", c.get(f"/verify/{token}").json()["on_chain_attestation"])
