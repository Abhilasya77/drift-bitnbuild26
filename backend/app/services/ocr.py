"""Field extraction: Tesseract OCR + passport MRZ parsing.

OCR is NOT authoritative (TDR section 4). Extracted values are saved unconfirmed;
the user confirms/corrects them via POST /documents/{id}/confirm-fields before they are compared.

The passport MRZ (the two '<<<' lines) has built-in check digits. If someone edits the
passport number, date of birth or expiry, the check digits stop adding up. We record that as
a field called mrz_check = "passed"/"failed", which the consistency engine turns into a Conflict
that goes to a human reviewer with the exact reason.

Tesseract must be installed on the machine for real OCR:  Mac: brew install tesseract
If it isn't, processing returns action_required and the user types the fields (demo still works).
"""
import io
import re
from datetime import date

try:
    import pytesseract
    from PIL import Image
except ImportError:            # pragma: no cover
    pytesseract = None


def tesseract_available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- MRZ (passport, ICAO 9303 TD3)
def _char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if c.isalpha():
        return ord(c.upper()) - 55   # A=10 ... Z=35
    return 0                         # '<'


def check_digit(data: str) -> str:
    weights = (7, 3, 1)
    return str(sum(_char_value(c) * weights[i % 3] for i, c in enumerate(data)) % 10)


def _yymmdd(s: str, future: bool) -> str | None:
    if not re.fullmatch(r"\d{6}", s):
        return None
    yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:])
    this_yy = date.today().year % 100
    year = 2000 + yy if (future or yy <= this_yy) else 1900 + yy
    try:
        return date(year, mm, dd).isoformat()
    except ValueError:
        return None


def _clean_mrz_name(part: str) -> str:
    """OCR often misreads the '<' filler as C/E/K/L. Drop filler-looking runs like 'CCEEEEEC'."""
    tokens = [t for t in part.replace("<", " ").split() if not re.fullmatch(r"[CEKL]{4,}", t)]
    return " ".join(tokens)


def parse_td3(line1: str, line2: str) -> dict | None:
    """Parse the two 44-character passport MRZ lines. Returns fields + which check digits passed."""
    l1, l2 = line1.replace(" ", "").upper(), line2.replace(" ", "").upper()
    if len(l1) < 44 or len(l2) < 44 or not l1.startswith("P"):
        return None
    l1, l2 = l1[:44], l2[:44]
    names = l1[5:].rstrip("<")
    surname, _, given = names.partition("<<")
    surname = _clean_mrz_name(surname)
    given = _clean_mrz_name(given)
    number, cd_number = l2[0:9], l2[9]
    nationality = l2[10:13].replace("<", "")
    dob, cd_dob = l2[13:19], l2[19]
    expiry, cd_expiry = l2[21:27], l2[27]
    optional, cd_optional = l2[28:42], l2[42]
    cd_final = l2[43]
    checks = {
        "document_number": check_digit(number) == cd_number,
        "date_of_birth": check_digit(dob) == cd_dob,
        "expiry_date": check_digit(expiry) == cd_expiry,
        # an empty optional field may use '<' as its check digit
        "optional": cd_optional == check_digit(optional) or (optional.strip("<") == "" and cd_optional == "<"),
        "composite": check_digit(number + cd_number + dob + cd_dob + expiry + cd_expiry + optional + cd_optional) == cd_final,
    }
    full_name = " ".join(p for p in (given, surname) if p)   # given names first, as people usually write it
    return {
        "name": full_name,
        "surname": surname,
        "given_names": given,
        "document_number": number.replace("<", ""),
        "nationality": nationality,
        "dob": _yymmdd(dob, future=False),
        "expiry_date": _yymmdd(expiry, future=True),
        "mrz_check": "passed" if all(checks.values()) else "failed",
        "mrz_failed_parts": [k for k, ok in checks.items() if not ok],
    }


def find_mrz(text: str) -> dict | None:
    lines = [re.sub(r"\s", "", ln).upper() for ln in text.splitlines()]
    lines = [ln for ln in lines if re.fullmatch(r"[A-Z0-9<]{40,48}", ln)]
    for i in range(len(lines) - 1):
        parsed = parse_td3(lines[i], lines[i + 1])
        if parsed:
            return parsed
    return None


# ---------------------------------------------------------------- generic labelled text
_LABELS = {
    "name": r"(?:full\s*name|name)\s*[:\-]\s*(.+)",
    "father_name": r"(?:father'?s?\s*name|name\s*of\s*father)\s*[:\-]\s*(.+)",
    "dob": r"(?:date\s*of\s*birth|dob|birth\s*date)\s*[:\-]\s*([0-9]{1,2}[/.\-][0-9]{1,2}[/.\-][0-9]{2,4})",
    "nationality": r"nationality\s*[:\-]\s*([A-Za-z ]+)",
    "document_number": r"(?:document|passport|id|card)\s*(?:no|number|#)\.?\s*[:\-]\s*([A-Z0-9\-]+)",
    "expiry_date": r"(?:expiry|expiry\s*date|date\s*of\s*expiry|valid\s*until)\s*[:\-]\s*([0-9]{1,2}[/.\-][0-9]{1,2}[/.\-][0-9]{2,4})",
}


def _dmy_to_iso(s: str) -> str | None:
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", s.strip())
    if not m:
        return None
    d, mth, y = int(m[1]), int(m[2]), int(m[3])
    if y < 100:
        y += 2000 if y <= date.today().year % 100 + 20 else 1900
    try:
        return date(y, mth, d).isoformat()
    except ValueError:
        return None


def parse_labelled_text(text: str) -> dict:
    out = {}
    for field, pattern in _LABELS.items():
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if field in ("dob", "expiry_date"):
                val = _dmy_to_iso(val) or val
            out[field] = val
    return out


# ---------------------------------------------------------------- entry point
def extract(data: bytes, mime: str) -> tuple[dict, float | None, str]:
    """Returns (fields, confidence, note). Empty fields -> ask the user to type them."""
    if mime == "application/pdf":
        return {}, None, "PDF uploaded: please confirm the fields manually."
    if not tesseract_available():
        return {}, None, "OCR is not installed on this server: please enter the fields manually."
    try:
        img = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img)
    except Exception:
        return {}, None, "Could not read this image: please enter the fields manually."
    mrz = find_mrz(text)
    fields = parse_labelled_text(text)
    if mrz:
        # MRZ values win; printed labels fill gaps (e.g. father's name is printed, not in the MRZ)
        for k, v in fields.items():
            mrz.setdefault(k, v)
        return mrz, 0.9, "Read from the passport MRZ lines."
    if fields:
        return fields, 0.6, "Read with OCR: please check each value."
    return {}, None, "No fields could be read: please enter them manually."
