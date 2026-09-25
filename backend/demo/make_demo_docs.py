"""Generate SYNTHETIC demo documents (plain cards clearly marked SPECIMEN — not copies of any real
government design). Use these for the demo instead of anyone's real documents.

    python demo/make_demo_docs.py      -> writes PNGs into demo/docs/

Persona 1 — Ravi (happy path): passport, visa (adds father's name), Grade 10 certificate, and later
            the permanent ID. All differences are explainable.
Persona 2 — Priya (exception path): passport whose printed DOB was edited, so the MRZ check digit
            fails -> Conflict -> reviewer queue.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "docs"
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/System/Library/Fonts/Menlo.ttc",
              "/Library/Fonts/Courier New.ttf", "C:/Windows/Fonts/consola.ttf"]


def font(size: int):
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _cd(data: str) -> str:
    w = (7, 3, 1)
    val = lambda c: int(c) if c.isdigit() else (ord(c) - 55 if c.isalpha() else 0)
    return str(sum(val(c) * w[i % 3] for i, c in enumerate(data)) % 10)


def mrz_td3(surname, given, number, nat, dob, sex, expiry, issuer="UTO"):
    names = (surname.replace(" ", "<") + "<<" + given.replace(" ", "<")).upper()
    l1 = ("P<" + issuer + names).ljust(44, "<")[:44]
    num = number.ljust(9, "<")[:9]
    opt = "<" * 14
    body = num + _cd(num) + nat + dob + _cd(dob) + sex + expiry + _cd(expiry) + opt + _cd(opt)
    comp = num + _cd(num) + dob + _cd(dob) + expiry + _cd(expiry) + opt + _cd(opt)
    return l1, body + _cd(comp)


def card(filename, title, lines, mrz=None):
    img = Image.new("RGB", (1400, 900 if mrz else 760), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1380, img.height - 20], outline="black", width=3)
    d.text((50, 45), title, fill="black", font=font(40))
    d.text((50, 100), "SPECIMEN - SYNTHETIC DEMO DOCUMENT - NOT VALID", fill="black", font=font(26))
    y = 170
    for label, value in lines:
        d.text((50, y), f"{label}: {value}", fill="black", font=font(34))
        y += 62
    if mrz:
        d.text((40, img.height - 190), mrz[0], fill="black", font=font(40))
        d.text((40, img.height - 120), mrz[1], fill="black", font=font(40))
    OUT.mkdir(exist_ok=True)
    img.save(OUT / filename)
    print("wrote", OUT / filename)


def main():
    # --- Ravi: happy path -------------------------------------------------------------
    card("ravi_passport.png", "PASSPORT (DEMO)", [
        ("Name", "RAVI KUMAR VENKATESH"), ("Nationality", "INDIA"), ("Date of Birth", "12/03/1994"),
        ("Passport No", "Z1234567"), ("Father's Name", "SRINIVASA RAO"), ("Expiry Date", "15/06/2031"),
    ], mrz_td3("VENKATESH", "RAVI KUMAR", "Z1234567", "IND", "940312", "M", "310615"))

    card("ravi_visa.png", "RESIDENCE VISA (DEMO)", [
        ("Full Name", "RAVI KUMAR VENKATESH SRINIVASA RAO"), ("Nationality", "INDIA"),
        ("Date of Birth", "12/03/1994"), ("Document No", "784-1994-1234567"), ("Expiry Date", "20/11/2026"),
    ])

    card("ravi_grade10.png", "GRADE 10 CERTIFICATE (DEMO)", [
        ("Name", "V RAVI KUMAR"), ("Father's Name", "SRINIVASA RAO"), ("Date of Birth", "12/03/1994"),
    ])

    card("ravi_permanent_id.png", "PERMANENT RESIDENT ID (DEMO)", [
        ("Name", "RAVI KUMAR VENKATESH SRINIVASA RAO"), ("Nationality", "INDIA"),
        ("Date of Birth", "12/03/1994"), ("ID Number", "784-1994-7654321"), ("Expiry Date", "01/10/2028"),
    ])

    # --- Priya: printed DOB edited from 1996 to 1990, MRZ left as original -> check digit fails ------
    l1, l2 = mrz_td3("SHARMA", "PRIYA", "P7654321", "IND", "960805", "F", "300101")
    tampered = l2[:13] + "900805" + l2[19:]          # someone edits DOB digits but not the check digit
    card("priya_passport_tampered.png", "PASSPORT (DEMO)", [
        ("Name", "PRIYA SHARMA"), ("Nationality", "INDIA"), ("Date of Birth", "05/08/1990"),
        ("Passport No", "P7654321"), ("Expiry Date", "01/01/2030"),
    ], (l1, tampered))

    card("priya_visa.png", "RESIDENCE VISA (DEMO)", [
        ("Full Name", "PRIYA SHARMA"), ("Nationality", "INDIA"), ("Date of Birth", "05/08/1996"),
        ("Document No", "784-1996-2223334"), ("Expiry Date", "10/02/2027"),
    ])


if __name__ == "__main__":
    main()
