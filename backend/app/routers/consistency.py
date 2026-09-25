from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ml import consistency as engine
from .. import workflow as wf
from ..auth import CurrentUser, get_current_user
from ..db import get_db

router = APIRouter(prefix="/consistency", tags=["Identity consistency"])


@router.post("/evaluate")
def evaluate(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compare the profile and all confirmed document fields. Routine matches never create review tasks;
    only Uncertain/Conflict open a review case (exception-only review = the approval-fatigue fix)."""
    p = wf.profile_or_404(db, user)
    ev = wf.run_evaluation(db, p, user.id)
    db.commit()
    return wf.evaluation_json(db, ev)


@router.get("/latest")
def latest(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    p = wf.profile_or_404(db, user)
    ev = wf.latest_evaluation(db, p.id)
    if not ev:
        raise HTTPException(404, "No consistency check yet. Confirm your document fields, then run it.")
    out = wf.evaluation_json(db, ev)
    case = wf.open_review(db, p.id, "consistency")
    out["review"] = {"status": case.status} if case else None     # user sees status only, not reviewer notes
    return out


class NamePair(BaseModel):
    name_a: str
    name_b: str
    family_names: list[str] = []


@router.post("/compare-names", tags=["Identity consistency"])
def compare_names(body: NamePair):
    """Playground for the ML teammate / demo: compare any two names. No personal data is stored."""
    r = engine.compare_names(body.name_a, body.name_b, body.family_names)
    return {"classification": r.classification, "similarity_score": round(r.score, 1), "explanation": r.explanation}
