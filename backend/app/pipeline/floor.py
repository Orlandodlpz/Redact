"""Floor rules: Luhn, key/password patterns, entropy, class rules. Owner: Victor. Phase 2.

Floor hits are always masked and the model cannot override them. They run beside the
judge, not after it, so a judge failure never costs a floor hit (docs/CLAUDE.md,
Hard constraints).

Four rules, in the order they are checked per candidate:
  1. Luhn valid card numbers in an OCR line, anchored to a real card prefix.
  2. Known API key and token formats in an OCR line.
  3. A secret next to a password or key label in an OCR line.
  4. Long high entropy strings in an OCR line.
  5. SAM classes that are sensitive by what they are: ID card, credit card, QR code, barcode.

Two things this module never does. It never puts matched text in a reason, because
reasons are shown in the UI, go into the response, and would re export the secret we
just masked. And it never treats OCR text as anything but data: every reason is a
fixed string, so nothing from the image reaches the user as our own words.

One candidate produces at most one finding. OCR gives whole lines, so masking the line
covers every secret on it, and one finding per line keeps the review editor readable.
"""

import math
import re

from app.schemas import Candidate, Category, Finding

# SAM classes that are a floor hit by themselves. Narrower than
# config.HIGH_RISK_SAM_CLASSES, which is the fail closed set for a missing judge:
# a whiteboard is worth masking when the judge is down, but it is not sensitive
# by definition the way an ID card is. Kept here rather than in the shared
# config.py because only this module uses it.
FLOOR_SAM_CLASSES: dict[str, tuple[Category, str]] = {
    "id card": (
        "government_id",
        "An ID card is in this region, so it is masked for every destination",
    ),
    "credit card": (
        "payment",
        "A payment card is in this region, so it is masked for every destination",
    ),
    "qr code": (
        "other_sensitive",
        "A QR code can carry a link, a network password or a payment handle, so it is masked",
    ),
    "barcode": (
        "other_sensitive",
        "A barcode can carry an account or document number, so it is masked",
    ),
}

_CARD_REASON = "A number on this line passes the card checksum, so it is masked for every destination"
_KEY_REASON = "This line matches a known API key or token format, so it is masked for every destination"
_LABEL_REASON = "This line puts a value next to a password or key label, so it is masked for every destination"
_ENTROPY_REASON = "This line holds a long random looking string of the shape keys and tokens take, so it is masked"

# Card prefixes and the lengths each brand actually issues. Luhn alone passes one in
# ten random digit strings, so a long serial or tracking number would hit it by chance.
# Requiring a real prefix at a length that brand issues cuts those without losing cards.
_CARD_BRANDS: tuple[tuple[str, tuple[int, ...]], ...] = (
    (r"4", (13, 16, 19)),
    (r"5[1-5]", (16,)),
    (r"2[2-7]", (16,)),
    (r"3[47]", (15,)),
    (r"6011", (16, 19)),
    (r"65", (16,)),
    (r"64[4-9]", (16,)),
    (r"30[0-5]", (14,)),
    (r"3[68]", (14,)),
    (r"35", (16,)),
)
_BRAND_RES = tuple((re.compile(p), lengths) for p, lengths in _CARD_BRANDS)

# A run of digits that may be grouped by single spaces or hyphens, the way cards are
# printed. Anything else ends the run, so two phone numbers in a sentence stay apart.
_DIGIT_RUN_RE = re.compile(r"\d(?:[ \-]?\d)*")

# Formats that identify themselves. No entropy check needed: the prefix is the evidence.
_KEY_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bASIA[0-9A-Z]{16}\b",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{16,}\b",
        r"\bAIza[0-9A-Za-z_\-]{35}\b",
        r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b",
        r"\bxapp-\d-[A-Za-z0-9\-]{10,}\b",
        r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{10,}\b",
        r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )
)

# Labels that introduce a secret. "pin" is handled apart from the rest because it is a
# common English word and only a short digit run after it counts.
_LABEL_WORDS = (
    r"wi[\- ]?fi\s*(?:password|pass|key|code)",
    r"network\s*(?:password|key)",
    r"passwords?",
    r"passwd",
    r"passphrase",
    r"pwd",
    r"api[\s_\-]?keys?",
    r"access[\s_\-]?keys?",
    r"secret[\s_\-]?keys?",
    r"client[\s_\-]?secret",
    r"auth[\s_\-]?token",
    r"bearer",
    r"secrets?",
    r"tokens?",
    r"credentials?",
    r"psk",
    r"otp",
    r"one[\s\-]?time[\s\-]?code",
)
_LABEL_RE = re.compile(
    r"(?:^|[^A-Za-z])(?:" + "|".join(_LABEL_WORDS) + r")\s*(?::|=|\bis\b)\s*(.+)$",
    re.IGNORECASE,
)
_PIN_RE = re.compile(r"(?:^|[^A-Za-z])pins?\s*(?::|=|\bis\b)\s*(\d{4,8})(?!\d)", re.IGNORECASE)

# Words that mean the label was talked about, not used. "Password: must be 8 characters"
# is a rule on a sign, not a secret on a whiteboard.
_NOT_A_SECRET = frozenset(
    """
    must should shall will would can cannot is are was were be been being
    required require requires needed needs field box input form reset change changed
    changing expired expires expiry invalid incorrect wrong correct strength policy
    policies hint manager managers protected protection enabled disabled empty blank
    none null unknown unset tbd todo n/a na yes no ok okay here there below above same
    and or the your my our their a an not never please enter type use used set create
    created forgot forgotten update updated confirm verify remember save saved copy
    copied hidden redacted masked removed rotate rotated rotation shared share sharing
    found missing error failed success valid expires_in only all every
    """.split()
)
_PLACEHOLDER_CHARS = frozenset("*•·.#xX_-?")

_MIN_LABEL_VALUE = 4
# Entropy thresholds for the no label case. Base64 and hex alphabets have very different
# per character ceilings (6 bits vs 4), so they get their own floor.
_B64_MIN_LEN, _B64_MIN_ENTROPY = 20, 4.0
_HEX_MIN_LEN, _HEX_MIN_ENTROPY = 32, 3.2
_GENERIC_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{20,}")
_HEX_TOKEN_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def find_floor_hits(candidates: list[Candidate]) -> list[Finding]:
    """Returns findings with locked=True.

    Takes the numbered candidate list, so each finding carries its mark and the review
    editor can tie it back to a region. Candidates without a mark still produce a
    finding, with an empty mark list, so the rules can be run on their own.
    """
    findings: list[Finding] = []
    for candidate in candidates:
        hit = _check(candidate)
        if hit is None:
            continue
        category, reason = hit
        findings.append(
            Finding(
                id=f"f_{len(findings) + 1:02d}",
                marks=[] if candidate.mark is None else [candidate.mark],
                category=category,
                reason=reason,
                source="floor",
                masked=True,
                locked=True,
                box=candidate.box,
                mask_rle=candidate.mask_rle,
            )
        )
    return findings


def _check(candidate: Candidate) -> tuple[Category, str] | None:
    """The first rule that fires wins, strongest evidence first."""
    if candidate.source == "sam":
        return FLOOR_SAM_CLASSES.get((candidate.sam_label or "").strip().lower())

    text = candidate.text or ""
    if not text.strip():
        return None
    if has_card_number(text):
        return "payment", _CARD_REASON
    if has_known_key(text):
        return "credential", _KEY_REASON
    if has_labelled_secret(text):
        return "credential", _LABEL_REASON
    if has_high_entropy_token(text):
        return "credential", _ENTROPY_REASON
    return None


def luhn_valid(digits: str) -> bool:
    """Standard mod 10 checksum. Expects digits only."""
    total, parity = 0, len(digits) % 2
    for i, char in enumerate(digits):
        n = int(char)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def has_card_number(text: str) -> bool:
    """A card prefix at a length that brand issues, with a valid Luhn checksum.

    A printed card line usually carries the expiry too ("4532 0151 1283 0366 12/26"),
    so the number is often a part of the digit run rather than the whole of it. The part
    we test has to begin and end on the run's own grouping, which is what stops a bad
    16 digit number from passing on its first 13 digits. The cost is that a card whose
    groups OCR ran together with the expiry is missed; the groups are what SAM's
    "credit card" class and the judge are there for.
    """
    for run in _DIGIT_RUN_RE.finditer(text):
        raw = run.group()
        digits = [c for c in raw if c.isdigit()]
        if len(digits) < 13:
            continue
        # Where each digit sits in the run, so a window can be held to the grouping.
        at = [i for i, c in enumerate(raw) if c.isdigit()]
        starts = [d for d, i in enumerate(at) if i == 0 or not raw[i - 1].isdigit()]
        for start in starts:
            window = "".join(digits[start:])
            for brand, lengths in _BRAND_RES:
                if not brand.match(window):
                    continue
                for length in lengths:
                    end = start + length
                    if end > len(digits):
                        continue
                    if end < len(digits) and raw[at[end] - 1].isdigit():
                        continue  # the number runs on into more digits, so it is not a card
                    if luhn_valid(window[:length]):
                        return True
    return False


def has_known_key(text: str) -> bool:
    return any(pattern.search(text) for pattern in _KEY_RES)


def has_labelled_secret(text: str) -> bool:
    """A password or key label, a separator, then something that looks like a value."""
    if _PIN_RE.search(text):
        return True
    match = _LABEL_RE.search(text)
    if match is None:
        return False
    value = match.group(1).strip().strip("\"'`()[]<>")
    if not value:
        return False
    first = value.split()[0].strip("\"'`,;.()[]<>")
    if len(first) < _MIN_LABEL_VALUE:
        return False
    if first.lower().strip(".") in _NOT_A_SECRET:
        return False
    if set(first) <= _PLACEHOLDER_CHARS:
        return False
    return True


def shannon_entropy(text: str) -> float:
    """Bits per character. A key is near the ceiling of its alphabet, prose is not."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _char_classes(token: str) -> int:
    return sum(
        (
            any(c.islower() for c in token),
            any(c.isupper() for c in token),
            any(c.isdigit() for c in token),
            any(c in "+/=_-" for c in token),
        )
    )


def has_high_entropy_token(text: str) -> bool:
    """A long random looking string with no label and no known prefix.

    Tokens inside a URL are skipped: a repo path is long and mixed case without being a
    secret, and a key that really does sit in a query string is caught by has_known_key.
    """
    for word in text.split():
        if "://" in word or "/" in word or word.lower().startswith("www."):
            continue
        for match in _HEX_TOKEN_RE.finditer(word):
            if shannon_entropy(match.group()) >= _HEX_MIN_ENTROPY:
                return True
        for match in _GENERIC_TOKEN_RE.finditer(word):
            token = match.group()
            if len(token) < _B64_MIN_LEN or _char_classes(token) < 3:
                continue
            if shannon_entropy(token) >= _B64_MIN_ENTROPY:
                return True
    return False
