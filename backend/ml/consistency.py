"""Identity Consistency Engine (baseline) — RapidFuzz + project rules.

Owned by the AI/ML teammate: this is a working baseline so the backend and demo run end to end.
Improve the rules/tables here; keep the function signatures the same and the backend keeps working.

Classifications (schema doc section 10):
  match               -> identical after normalisation
  explainable_variant -> different, but for a known harmless reason (explained)
  uncertain           -> needs human judgment (goes to review queue)
  conflict            -> material mismatch (goes to review queue, blocks progress)
Similarity is a workflow signal, NOT a fraud probability. Never label a person fraudulent.
"""
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

ENGINE_VERSION = "rules-rapidfuzz-0.1"
SEVERITY = {"match": 0, "explainable_variant": 1, "uncertain": 2, "conflict": 3}

TITLES = {"MR", "MRS", "MS", "MISS", "DR", "SHRI", "SMT", "KUMARI", "SRI", "MISTER"}
PLACEHOLDERS = {"FNU", "LNU", "XXX", "NA", "NIL"}             # FNU = "first name unknown" on single-name passports
CONNECTORS = {"BIN", "BINT", "IBN", "SO", "DO", "WO", "BINTI", "BINTE"}   # S/O = son of, D/O = daughter of

# Spelling/transliteration variants that refer to the same name. First item = canonical form.
VARIANT_GROUPS = [
    ["MOHAMMED", "MOHAMMAD", "MUHAMMAD", "MOHAMED", "MOHAMAD", "MUHAMMED", "MOHD", "MD", "MUHAMAD"],
    ["AHMED", "AHMAD", "AHAMED"],
    ["ABDUL", "ABDEL", "ABDOOL", "ABDUL"],
    ["HUSSAIN", "HUSSEIN", "HUSAIN", "HOSSAIN", "HUSEIN"],
    ["YUSUF", "YOUSUF", "YOUSEF", "YOUSSEF", "YUSOF"],
    ["IBRAHIM", "EBRAHIM", "IBRAHEEM"],
    ["FATIMA", "FATIMAH", "FATHIMA"],
    ["AISHA", "AYESHA", "AISHAH", "AYISHA"],
    ["KHALID", "KHALED"],
    ["OMAR", "UMAR"],
    ["ALI", "ALY"],
    ["RAHMAN", "REHMAN", "RAHMAAN"],
    ["LAKSHMI", "LAXMI"],
    ["SRINIVASA", "SRINIVAS", "SREENIVAS", "SREENIVASA"],
    ["VENKATESHA", "VENKATESH"],
    ["MOHAN", "MOHANA"],
    ["SINGH", "SINGHJI"],
]
_CANON = {v: g[0] for g in VARIANT_GROUPS for v in g}

NATIONALITY_GROUPS = [
    ["INDIA", "IND", "IN", "INDIAN"],
    ["UNITED ARAB EMIRATES", "ARE", "AE", "UAE", "EMIRATI"],
    ["PAKISTAN", "PAK", "PK", "PAKISTANI"],
    ["PHILIPPINES", "PHL", "PH", "FILIPINO", "PHILIPPINE"],
    ["BANGLADESH", "BGD", "BD", "BANGLADESHI"],
    ["NEPAL", "NPL", "NP", "NEPALI"],
    ["SRI LANKA", "LKA", "LK", "SRI LANKAN"],
    ["EGYPT", "EGY", "EG", "EGYPTIAN"],
    ["SAUDI ARABIA", "SAU", "SA", "SAUDI"],
    ["UNITED KINGDOM", "GBR", "GB", "UK", "BRITISH"],
    ["UNITED STATES", "USA", "US", "AMERICAN"],
    ["KUWAIT", "KWT", "KW", "KUWAITI"],
    ["OMAN", "OMN", "OM", "OMANI"],
    ["QATAR", "QAT", "QA", "QATARI"],
    ["BAHRAIN", "BHR", "BH", "BAHRAINI"],
    ["JORDAN", "JOR", "JO", "JORDANIAN"],
    ["SYRIA", "SYR", "SY", "SYRIAN"],
    ["LEBANON", "LBN", "LB", "LEBANESE"],
    ["CHINA", "CHN", "CN", "CHINESE"],
]
_NAT = {v: g[0] for g in NATIONALITY_GROUPS for v in g}


# ------------------------------------------------------------------ helpers
def clean_tokens(name: str | None) -> tuple[list[str], list[str]]:
    """Returns (tokens, notes). Removes punctuation, titles, placeholders, connector words."""
    notes = []
    if not name:
        return [], notes
    s = name.upper().replace("'", "").replace("’", "")
    s = re.sub(r"\b([SDW])\s*/\s*O\b", r"\1O", s)          # S/O -> SO
    s = re.sub(r"[^\w\s]", " ", s)
    raw = [t for t in s.split() if t]
    out = []
    for t in raw:
        if t in TITLES:
            notes.append(f"title '{t.title()}' ignored")
        elif t in PLACEHOLDERS:
            notes.append(f"placeholder '{t}' ignored (used on single-name documents)")
        elif t in CONNECTORS:
            notes.append(f"connector word '{t}' ignored")
        else:
            out.append(t)
    return out, notes


def normalize_name(name: str | None) -> str:
    return " ".join(clean_tokens(name)[0])


def normalize_nationality(value: str | None) -> str:
    v = re.sub(r"\s+", " ", (value or "").upper().strip())
    return _NAT.get(v, v)


def _merge_joined(a: list[str], b: list[str], notes: list[str]) -> list[str]:
    """If b has 'ABDULRAHMAN' where a has 'ABDUL','RAHMAN', merge a's pair so they can match."""
    a = a[:]
    for tok in b:
        if tok in a:
            continue
        for size in (2, 3):
            for i in range(len(a) - size + 1):
                if "".join(a[i:i + size]) == tok:
                    notes.append(f"'{' '.join(a[i:i + size])}' written as one word '{tok}'")
                    a[i:i + size] = [tok]
                    break
    return a


@dataclass
class NameResult:
    classification: str
    score: float
    explanation: str
    reasons: list[str] = field(default_factory=list)


def compare_names(a: str | None, b: str | None, family_names: list[str] | None = None) -> NameResult:
    """Compare two names as printed on two sources. family_names = father's/mother's names we know."""
    ta, notes_a = clean_tokens(a)
    tb, notes_b = clean_tokens(b)
    if not ta or not tb:
        return NameResult("uncertain", 0.0, "A name is missing on one of the sources.")
    reasons = sorted(set(notes_a + notes_b))
    score = float(fuzz.token_sort_ratio(" ".join(ta), " ".join(tb)))

    if ta == tb:
        if reasons:
            return NameResult("explainable_variant", 100.0, "Same name; " + "; ".join(reasons) + ".", reasons)
        return NameResult("match", 100.0, "Names are identical.")

    ta = _merge_joined(ta, tb, reasons)
    tb = _merge_joined(tb, ta, reasons)

    family = set()
    for fam in family_names or []:
        family.update(_CANON.get(t, t) for t in clean_tokens(fam)[0])

    rem_a = [_CANON.get(t, t) for t in ta]
    rem_b = [_CANON.get(t, t) for t in tb]
    raw_a, raw_b = ta[:], tb[:]
    severity = "explainable_variant" if (reasons or raw_a != raw_b) else "match"

    # 1) exact (canonical) matches — records spelling variants
    matched_order_a, matched_order_b = [], []
    for i, ca in enumerate(list(rem_a)):
        if ca in rem_b:
            j = rem_b.index(ca)
            if raw_a[i] != raw_b[j]:
                reasons.append(f"recognised spelling variant '{raw_a[i].title()}' / '{raw_b[j].title()}'")
            matched_order_a.append(ca)
            matched_order_b.append((j, ca))
            rem_b[j] = None
            rem_a[i] = None
    left_a = [(raw_a[i], t) for i, t in enumerate(rem_a) if t]
    left_b = [(raw_b[j], t) for j, t in enumerate(rem_b) if t]

    # word order
    order_b = [c for _, c in sorted(matched_order_b)]
    if matched_order_a and matched_order_a != order_b:
        reasons.append("same name parts in a different order")

    # 2) initials: 'K' on one side matches 'KUMAR' on the other
    for side_from, side_to in ((left_a, left_b), (left_b, left_a)):
        for item in list(side_from):
            raw, canon = item
            if len(canon) == 1:
                hit = next((x for x in side_to if x[1].startswith(canon) and len(x[1]) > 1), None)
                if hit:
                    reasons.append(f"initial '{raw}' used for '{hit[0].title()}'")
                    side_from.remove(item)
                    side_to.remove(hit)

    # 3) close spellings (one or two letters different) -> needs a human
    for item in list(left_a):
        best = max(left_b, key=lambda x: fuzz.ratio(item[1], x[1]), default=None)
        if best and fuzz.ratio(item[1], best[1]) >= 80:
            reasons.append(f"spelling differs: '{item[0].title()}' vs '{best[0].title()}'")
            severity = "uncertain"
            left_a.remove(item)
            left_b.remove(best)

    # 4) leftovers: extra name parts on one or both sides
    extra_a = [x for x in left_a]
    extra_b = [x for x in left_b]
    for extras in (extra_a, extra_b):
        if extras and all(c in family for _, c in extras):
            words = " ".join(r.title() for r, _ in extras)
            reasons.append(f"one document adds the father's/family name '{words}'")
            extras.clear()
    if extra_a and extra_b:
        severity = "conflict"
        reasons.append("different name parts: " + ", ".join(r.title() for r, _ in extra_a)
                       + " vs " + ", ".join(r.title() for r, _ in extra_b))
    elif extra_a or extra_b:
        extra = extra_a or extra_b
        severity = max(severity, "uncertain", key=SEVERITY.get)
        reasons.append("extra name part(s) we can't explain yet: " + ", ".join(r.title() for r, _ in extra))

    if severity == "match" and not reasons:
        return NameResult("match", score, "Names are identical.")
    if severity == "match":
        severity = "explainable_variant"
    lead = {
        "explainable_variant": "Same person, written differently: ",
        "uncertain": "Needs a reviewer to confirm: ",
        "conflict": "Names do not agree: ",
    }[severity]
    return NameResult(severity, score, lead + "; ".join(dict.fromkeys(reasons)) + ".", reasons)


def compare_simple(field_name: str, a: str | None, b: str | None) -> NameResult | None:
    """DOB / nationality / other exact fields. Returns None if either side is missing."""
    if not a or not b:
        return None
    if field_name == "nationality":
        na, nb = normalize_nationality(a), normalize_nationality(b)
        if na == nb:
            same = a.strip().upper() == b.strip().upper()
            return NameResult("match", 100.0, "Nationality matches." if same else
                              f"Nationality matches ('{a}' and '{b}' are the same country).")
        return NameResult("conflict", 0.0, f"Nationality differs: '{a}' vs '{b}'.")
    label = {"dob": "Date of birth"}.get(field_name, field_name.replace("_", " ").capitalize())
    if a.strip() == b.strip():
        return NameResult("match", 100.0, f"{label} matches.")
    return NameResult("conflict", 0.0, f"{label} differs: '{a}' vs '{b}'.")


# ------------------------------------------------------------------ whole-profile evaluation
LABELS = {"passport": "Passport", "national_id": "National ID", "gcc_id": "GCC ID",
          "visa_residence": "Visa / residence", "grade10": "Grade 10 certificate",
          "grade12": "Grade 12 certificate", "other": "Other document", None: "Profile"}


def evaluate(profile: dict, documents: list[dict]) -> dict:
    """
    profile:   {"name_as_used", "dob", "nationality", "father_name", "mother_name"}
    documents: [{"id", "document_type", "evidence_class", "fields": {"name","dob","nationality",
                 "father_name","mrz_check","mrz_failed_parts"}}]  (confirmed fields only)
    returns    {"overall_status","summary","requires_review","comparisons":[...] }
    """
    comparisons = []
    family = [profile.get("father_name"), profile.get("mother_name")]
    family += [d["fields"].get("father_name") for d in documents]
    family = [f for f in family if f]

    def add(field_name, a_doc, b_doc, va, vb, res: NameResult):
        comparisons.append({
            "field": field_name,
            "source_a_document_id": a_doc["id"] if a_doc else None,
            "source_b_document_id": b_doc["id"] if b_doc else None,
            "source_a": LABELS.get(a_doc["document_type"] if a_doc else None, "Document"),
            "source_b": LABELS.get(b_doc["document_type"] if b_doc else None, "Document"),
            "value_a": va, "value_b": vb,
            "classification": res.classification,
            "similarity_score": round(res.score, 1),
            "explanation": res.explanation,
        })

    # anchor = passport if present, else first primary document
    primaries = [d for d in documents if d.get("evidence_class") == "primary"]
    anchor = next((d for d in documents if d["document_type"] == "passport"), primaries[0] if primaries else None)

    # 1) profile vs anchor (name, dob, nationality)
    if anchor:
        f = anchor["fields"]
        add("name", None, anchor, profile.get("name_as_used"), f.get("name"),
            compare_names(profile.get("name_as_used"), f.get("name"), family))
        for fld, pkey in (("dob", "dob"), ("nationality", "nationality")):
            r = compare_simple(fld, profile.get(pkey), f.get(fld))
            if r:
                add(fld, None, anchor, profile.get(pkey), f.get(fld), r)

    # 2) anchor vs every other document
    for d in documents:
        if anchor and d["id"] == anchor["id"]:
            continue
        base = anchor["fields"] if anchor else {"name": profile.get("name_as_used"), "dob": profile.get("dob"),
                                                "nationality": profile.get("nationality")}
        f = d["fields"]
        if f.get("name"):
            add("name", anchor, d, base.get("name"), f.get("name"), compare_names(base.get("name"), f.get("name"), family))
        for fld in ("dob", "nationality"):
            r = compare_simple(fld, base.get(fld), f.get(fld))
            if r:
                add(fld, anchor, d, base.get(fld), f.get(fld), r)

    # 3) MRZ integrity (passport check digits)
    for d in documents:
        if d["fields"].get("mrz_check") == "failed":
            parts = d["fields"].get("mrz_failed_parts") or []
            parts_txt = ", ".join(p.replace("_", " ") for p in parts) if parts else "one or more fields"
            add("mrz_check", d, None, "check digits", "failed",
                NameResult("conflict", 0.0, f"The passport's machine-readable lines don't add up for {parts_txt}. "
                                            "The printed value may have been changed; a reviewer should compare "
                                            "the printed field with the MRZ."))

    if not comparisons:
        return {"overall_status": "uncertain", "requires_review": False, "comparisons": [],
                "summary": "Not enough confirmed document fields to compare yet. Upload and confirm a primary document."}

    overall = max((c["classification"] for c in comparisons), key=SEVERITY.get)
    counts = {k: sum(1 for c in comparisons if c["classification"] == k) for k in SEVERITY}
    summary = {
        "match": "All documents agree with each other.",
        "explainable_variant": f"Your documents agree. {counts['explainable_variant']} difference(s) were explained "
                               "automatically (e.g. spacing, word order, father's name).",
        "uncertain": f"{counts['uncertain']} difference(s) need a reviewer to confirm. Only those fields will be checked.",
        "conflict": f"{counts['conflict']} field(s) don't agree across documents. A reviewer will look at exactly those fields.",
    }[overall]
    return {"overall_status": overall, "summary": summary, "requires_review": overall in ("uncertain", "conflict"),
            "comparisons": comparisons}


def name_supported(candidate: str, document_names: list[tuple[str, str]], family_names: list[str]) -> dict:
    """Is `candidate` a supported representation of any confirmed document name?
    document_names: [(label, name)]. Used by service verification (e.g. a bank checking a beneficiary name)."""
    best = None
    for label, n in document_names:
        r = compare_names(candidate, n, family_names)
        if best is None or SEVERITY[r.classification] < SEVERITY[best[1].classification] or (
                r.classification == best[1].classification and r.score > best[1].score):
            best = (label, r)
    if not best:
        return {"supported": False, "explanation": "No confirmed document names on record."}
    label, r = best
    return {"supported": r.classification in ("match", "explainable_variant"),
            "classification": r.classification, "closest_document": label, "explanation": r.explanation}
