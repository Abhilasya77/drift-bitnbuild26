"""End-to-end test of the whole demo story.   Run:  pytest -q   (from the backend folder)"""
import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["AUTH_MODE"] = "dev"
os.environ["STORAGE_MODE"] = "local"
os.environ["LOCAL_UPLOAD_DIR"] = "test_uploads"
os.environ["REVIEWER_EMAILS"] = "reviewer@drift.demo"
os.environ["COMPREFACE_URL"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "demo" / "docs"
RAVI = {"X-Demo-User": "ravi@drift.demo"}
PRIYA = {"X-Demo-User": "priya@drift.demo"}
REVIEWER = {"X-Demo-User": "reviewer@drift.demo"}


@pytest.fixture(scope="module")
def client():
    if Path("test.db").exists():
        Path("test.db").unlink()
    if not DOCS.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(DOCS.parent / "make_demo_docs.py")], check=True)
    from app.main import app
    with TestClient(app) as c:
        yield c
    Path("test.db").unlink(missing_ok=True)


def upload(c, who, doc_type, filename, **extra):
    with open(DOCS / filename, "rb") as f:
        r = c.post("/documents", headers=who, data={"document_type": doc_type, **extra},
                   files={"file": (filename, f, "image/png")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def confirm(c, who, doc_id, **fields):
    r = c.post(f"/documents/{doc_id}/confirm-fields", headers=who, json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def test_happy_path_ravi(client):
    c = client
    r = c.post("/profiles", headers=RAVI, json={
        "name_as_used": "Ravi Kumar Venkatesh", "date_of_birth": "1994-03-12", "nationality": "India",
        "phone_number": "+971501234567", "current_country": "United Arab Emirates", "father_name": "Srinivasa Rao"})
    assert r.status_code == 201, r.text
    assert c.get("/profiles/me", headers=RAVI).json()["next_action"]["step"] == "upload_documents"

    passport = upload(c, RAVI, "passport", "ravi_passport.png")
    visa = upload(c, RAVI, "visa_residence", "ravi_visa.png")
    grade10 = upload(c, RAVI, "grade10", "ravi_grade10.png")

    # OCR + confirm what was read (the user would correct anything wrong)
    for doc in (passport, visa, grade10):
        out = c.post(f"/documents/{doc}/process", headers=RAVI).json()
        read = {f["field_name"]: f["value"] for f in out["fields"]}
        keep = {k: read[k] for k in ("name", "dob", "nationality", "document_number", "expiry_date", "father_name")
                if k in read}
        confirm(c, RAVI, doc, **keep)

    ev = c.post("/consistency/evaluate", headers=RAVI).json()
    print(ev["summary"])
    for x in ev["comparisons"]:
        print(" ", x["field"], x["source_a"], "vs", x["source_b"], "->", x["classification"], "|", x["explanation"])
    assert ev["overall_status"] in ("match", "explainable_variant"), ev
    assert not ev["requires_review"]
    assert c.get("/reviews", headers=REVIEWER).json() == []          # no approval task for routine cases

    assert c.post("/credentials", headers=RAVI).status_code == 409   # biometric not done yet
    with open(DOCS / "ravi_passport.png", "rb") as f:
        bio = c.post("/biometric/start", headers=RAVI, files={"selfie": ("me.png", f, "image/png")}).json()
    assert bio["status"] == "passed" and bio["provider"] == "simulated"

    elig = c.get("/eligibility", headers=RAVI).json()
    assert elig["eligible"], elig
    cred = c.post("/credentials", headers=RAVI).json()
    assert cred["state"] == "active"
    assert c.get("/credentials/current/qr", headers=RAVI).headers["content-type"] == "image/png"

    token = cred["verification_url"].rsplit("/", 1)[1]
    v = c.get(f"/verify/{token}").json()
    assert v["is_valid"] and v["biometric_completed"] and not v["unresolved_conflicts"]
    assert "document_number" not in str(v)

    # the Gulf News case: the service has the longer visa-style name on file
    n = c.post(f"/verify/{token}/name", json={"name": "Ravi Kumar Venkatesh Srinivasa Rao"}).json()
    assert n["supported"], n
    n2 = c.post(f"/verify/{token}/name", json={"name": "Suresh Babu"}).json()
    assert not n2["supported"]

    # optional web3 attestation
    payload = c.get("/credentials/current/attestation-payload", headers=RAVI).json()
    assert payload["attestation_hash"].startswith("0x")
    r = c.post("/credentials/current/attestation", headers=RAVI,
               json={"transaction_hash": "0x" + "ab" * 32, "network": "polygon-amoy"})
    assert r.status_code == 201

    # renewal: visa expires soon -> reminder, then renewal in progress
    c.post("/notifications/run-expiry-check", headers=RAVI)
    c.post(f"/documents/{visa}/renewal", headers=RAVI)
    titles = [x["title"] for x in c.get("/notifications", headers=RAVI).json()]
    assert "Renewal in progress" in titles

    # permanent ID arrives -> consistent -> linked, temporary credential expires
    perm = upload(c, RAVI, "national_id", "ravi_permanent_id.png", is_permanent_credential="true")
    out = c.post(f"/documents/{perm}/process", headers=RAVI).json()
    read = {f["field_name"]: f["value"] for f in out["fields"]}
    confirm(c, RAVI, perm, **{k: read[k] for k in ("name", "dob", "nationality", "document_number", "expiry_date")
                              if k in read})
    res = c.post("/permanent-credential", headers=RAVI, json={"document_id": perm}).json()
    assert res["outcome"] == "linked", res
    assert c.get(f"/verify/{token}").json()["credential_state"] == "expired"
    me = c.get("/profiles/me", headers=RAVI).json()
    assert me["status"]["permanent_credential"] == "linked"


def test_exception_path_priya(client):
    c = client
    c.post("/profiles", headers=PRIYA, json={"name_as_used": "Priya Sharma", "date_of_birth": "1996-08-05",
                                             "nationality": "India", "current_country": "UAE"})
    passport = upload(c, PRIYA, "passport", "priya_passport_tampered.png")
    visa = upload(c, PRIYA, "visa_residence", "priya_visa.png")
    for doc in (passport, visa):
        out = c.post(f"/documents/{doc}/process", headers=PRIYA).json()
        read = {f["field_name"]: f["value"] for f in out["fields"]}
        confirm(c, PRIYA, doc, **{k: read[k] for k in ("name", "dob", "nationality", "document_number",
                                                       "expiry_date") if k in read})
    ev = c.post("/consistency/evaluate", headers=PRIYA).json()
    assert ev["overall_status"] == "conflict"
    assert any(x["field"] == "mrz_check" for x in ev["comparisons"])

    # blocked until reviewed
    with open(DOCS / "priya_visa.png", "rb") as f:
        assert c.post("/biometric/start", headers=PRIYA, files={"selfie": ("s.png", f, "image/png")}).status_code == 409

    # users can't see the queue; reviewer sees only this exception case
    assert c.get("/reviews", headers=PRIYA).status_code == 403
    queue = c.get("/reviews", headers=REVIEWER).json()
    assert len(queue) == 1
    case = c.get(f"/reviews/{queue[0]['id']}", headers=REVIEWER).json()
    assert case["flagged_fields"] and case["evidence"]
    stats = c.get("/reviews/stats", headers=REVIEWER).json()
    assert stats["review_cases_total"] == 1

    c.post(f"/reviews/{case['id']}/resolve", headers=REVIEWER, json={"decision": "not_cleared",
                                                                     "note": "Printed DOB doesn't match MRZ."})
    assert c.get("/profiles/me", headers=PRIYA).json()["profile"]["evidence_status"] == "action_required"
    assert not c.get("/eligibility", headers=PRIYA).json()["eligible"]


def test_name_playground(client):
    r = client.post("/consistency/compare-names", json={"name_a": "MOHAMMED ABDUL RAHMAN ALI",
                                                         "name_b": "MOHAMMED ABDULRAHMAN ALI"}).json()
    assert r["classification"] == "explainable_variant"
    r = client.post("/consistency/compare-names", json={"name_a": "MOHAMMED ABDUL RAHMAN",
                                                         "name_b": "MOHAMMED ABDUL HAMEED"}).json()
    assert r["classification"] in ("uncertain", "conflict")


def test_web3_attestation_on_local_chain(client):
    """Deploys CredentialAttestation to an in-memory Ethereum test chain and runs issue -> verify -> revoke."""
    import json
    build = Path(__file__).resolve().parents[2] / "blockchain" / "build" / "CredentialAttestation.json"
    try:
        from web3 import Web3, EthereumTesterProvider
    except ImportError:
        pytest.skip("web3 / eth-tester not installed")
    if not build.exists():
        pytest.skip("contract not compiled (run: cd blockchain && node compile.js)")
    from app import config
    from app.services import web3_attest

    art = json.loads(build.read_text())
    w3 = Web3(EthereumTesterProvider())
    owner, stranger = w3.eth.accounts[0], w3.eth.accounts[1]
    tx = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor().transact({"from": owner})
    address = w3.eth.get_transaction_receipt(tx)["contractAddress"]
    contract = w3.eth.contract(address=address, abi=art["abi"])

    # only approved issuers can attest; no double attestation
    with pytest.raises(Exception):
        contract.functions.attest(b"\x01" * 32, 2**40).transact({"from": stranger})

    web3_attest.set_web3(w3, owner)
    config.WEB3_CONTRACT_ADDRESS = address
    try:
        c, who = client, {"X-Demo-User": "sam@drift.demo"}
        c.post("/profiles", headers=who, json={"name_as_used": "Ravi Kumar Venkatesh", "date_of_birth": "1994-03-12",
                                               "nationality": "India", "current_country": "UAE",
                                               "father_name": "Srinivasa Rao"})
        for doc_type, fname in (("passport", "ravi_passport.png"), ("visa_residence", "ravi_visa.png")):
            d = upload(c, who, doc_type, fname)
            out = c.post(f"/documents/{d}/process", headers=who).json()
            read = {f["field_name"]: f["value"] for f in out["fields"]}
            confirm(c, who, d, **{k: read[k] for k in ("name", "dob", "nationality", "father_name") if k in read})
        c.post("/consistency/evaluate", headers=who)
        with open(DOCS / "ravi_passport.png", "rb") as f:
            c.post("/biometric/start", headers=who, files={"selfie": ("me.png", f, "image/png")})
        cred = c.post("/credentials", headers=who).json()
        assert cred["attestation"]["transaction_hash"].startswith("0x"), cred

        cred = c.get("/credentials/current", headers=who).json()
        assert cred["attestation"]["status"] == "confirmed", cred
        token = cred["verification_url"].rsplit("/", 1)[1]
        chain = c.get(f"/verify/{token}").json()["on_chain_attestation"]
        assert chain["exists"] and chain["valid_on_chain"] and not chain["revoked_on_chain"], chain

        # permanent ID linked -> credential expired in DB and revoked on-chain
        d = upload(c, who, "national_id", "ravi_permanent_id.png", is_permanent_credential="true")
        out = c.post(f"/documents/{d}/process", headers=who).json()
        read = {f["field_name"]: f["value"] for f in out["fields"]}
        confirm(c, who, d, **{k: read[k] for k in ("name", "dob", "nationality") if k in read})
        assert c.post("/permanent-credential", headers=who, json={"document_id": d}).json()["outcome"] == "linked"
        chain = c.get(f"/verify/{token}").json()["on_chain_attestation"]
        assert chain["revoked_on_chain"] and not chain["valid_on_chain"], chain
    finally:
        web3_attest.set_web3(None)
        config.WEB3_CONTRACT_ADDRESS = ""
