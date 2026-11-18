"""core/legal_guardrails.py - safety rules that do NOT depend on the AI.

1. detect_high_risk(text)        plain keyword rules, run before any AI call
2. build_escalation_message()    fixed, careful message (no procedural advice)
3. check_response(text)          replaces sentences that look like invented law
4. load_sources()                the verified-information file
"""
import json
import re
from pathlib import Path

SOURCES_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "legal_sources.json"
CANNOT_VERIFY = "I cannot verify this legal provision from the available sources."


def load_sources():
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


# ---------------- 1. high-risk detection ----------------

_I = re.IGNORECASE
HIGH_RISK_RULES = [
    ("court_notice", "A court notice, summons or hearing",
     re.compile(r"\b(court|tribunal)\b.{0,30}\b(notice|summons|hearing|order)\b"
                r"|\bsummons\b|\bhearing date\b"
                r"|\bcase (has been |was |is )?(filed|registered) against me\b", _I)),
    ("legal_notice", "A legal notice from a lawyer",
     re.compile(r"\b(received|got|get|served)\b.{0,40}\blegal notice\b|\b(lawyer|advocate)'?s? notice\b", _I)),
    ("eviction", "Eviction, a forced move-out or a lock-out",
     re.compile(r"\bevict\w*"
                r"|\bvacate\b.{0,30}\b(immediately|right now|today|tomorrow|within \d+)"
                r"|\b(throw|throwing|threw|thrown|kick\w*)\b.{0,15}\bout\b"
                r"|\b(changed|change|changing)\b.{0,15}\block\w*"
                r"|\blocked (me|us) out\b"
                r"|\bcut (off )?(the )?(electricity|power|water)\b", _I)),
    ("police", "Police or an arrest is involved",
     re.compile(r"\bpolice\b|\bFIR\b|\barrest\w*\b", _I)),
    ("safety", "Threats or violence",
     re.compile(r"\b(beat|beaten|assault\w*|violen\w*|abus\w*|harass\w*|goons?)\b"
                r"|\bhit me\b|\bthreaten\w*\b.{0,15}\b(kill|hurt|harm|beat)\b", _I)),
]


def detect_high_risk(text):
    """Return a list of {"id", "title"} for every high-risk pattern found."""
    found = []
    for rule_id, title, pattern in HIGH_RISK_RULES:
        if pattern.search(text):
            found.append({"id": rule_id, "title": title})
    return found


def build_escalation_message(flags):
    ids = {f["id"] for f in flags}
    parts = []
    if "safety" in ids:
        parts.append("If you feel unsafe right now, please contact your local emergency services first.")
    parts.append(
        "This sounds time-sensitive and possibly serious, and I cannot give reliable "
        "step-by-step legal procedure for it. Please speak to a qualified lawyer or your "
        "nearest legal services authority as soon as you can. Notices and legal papers often "
        "carry dates by which something must be done, so please do not ignore them."
    )
    if ids & {"court_notice", "legal_notice", "police"}:
        parts.append(
            "To help organise your case, could you tell me: (1) the date on the notice or paper "
            "you received, and (2) any date it gives for replying or appearing? If you are not "
            "sure, that is fine. Please keep the original safe."
        )
    elif "eviction" in ids:
        parts.append(
            "To help organise your case, could you tell me exactly what the landlord has said "
            "or done, and on what date? Please keep any messages or papers safe."
        )
    return " ".join(parts)


# ---------------- 3. unsupported-claim checker ----------------

# (pattern, extra pattern that must ALSO appear in the sentence, or None)
UNSUPPORTED_PATTERNS = [
    (re.compile(r"\bsections?\s+\d+[A-Za-z]?\b", _I), None),
    (re.compile(r"\barticles?\s+\d+\b", _I), None),
    (re.compile(r"\bAct,?\s*(of\s*)?(1[89]|20)\d{2}\b"), None),
    (re.compile(r"\b(IPC|BNS|BNSS|CrPC|CPC|BSA)\b"), None),
    (re.compile(r"\b[A-Z][a-z]+\s+v(?:s)?\.?\s+[A-Z][a-z]+"), None),
    (re.compile(r"\b(AIR|SCC|SCR)\s*\d"), None),
    (re.compile(r"\b(Supreme Court|High Court)\b.{0,40}\b(held|ruled|decided|judg(e)?ment)\b", _I), None),
    (re.compile(r"\bwithin\s+\d+\s+(days|weeks|months)\b", _I),
     re.compile(r"\b(law|legal|act|statut\w*|required|must|mandatory|obliged|rule)\b", _I)),
    (re.compile(r"\byou will (definitely |certainly )?(win|succeed|get (your|the) (money|deposit))\b"
                r"|\bguarantee[ds]?\b|\b100% (sure|certain)\b", _I), None),
    (re.compile(r"\b(breaking|violating|violates|against) the law\b|\bpunishable\b"
                r"|\b(is|are) (illegal|unlawful)\b|\bcriminal offen[cs]e\b", _I), None),
]


def _is_unsupported(sentence):
    for pattern, extra in UNSUPPORTED_PATTERNS:
        if pattern.search(sentence) and (extra is None or extra.search(sentence)):
            return True
    return False


def check_response(text):
    """Return (safe_text, blocked_sentences).
    Sentences that look like unverified legal claims are replaced by CANNOT_VERIFY.
    Phrases listed in legal_sources.json 'approved_mentions' are allowed."""
    allowed = sorted(load_sources().get("approved_mentions", []), key=len, reverse=True)
    blocked, out_lines = [], []
    for line in text.split("\n"):
        kept = []
        for sentence in re.split(
            r"(?<=[.!?])(?<!\bv\.)(?<!\bvs\.)(?<!\bRs\.)(?<!\bNo\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bDr\.)\s+(?=[A-Z0-9\"(])",
            line,
        ):
            probe = sentence
            for phrase in allowed:
                probe = re.sub(re.escape(phrase), " ", probe, flags=_I)
            if sentence.strip() and _is_unsupported(probe):
                blocked.append(sentence)
                if CANNOT_VERIFY not in kept:
                    kept.append(CANNOT_VERIFY)
            else:
                kept.append(sentence)
        out_lines.append(" ".join(kept))
    return "\n".join(out_lines), blocked


if __name__ == "__main__":
    # Offline self-test (no AI needed). Run:  python -m core.legal_guardrails
    print("HIGH-RISK DETECTOR")
    risk_tests = [
        ("I received a court notice about eviction from my landlord", {"court_notice", "eviction"}),
        ("My landlord says vacate immediately or he will throw me out", {"eviction"}),
        ("I vacated two months ago and he is not returning my deposit of 20000", set()),
        ("He threatened to call the police on me", {"police"}),
        ("He changed the locks while my belongings were inside", {"eviction"}),
        ("I got a legal notice from his lawyer", {"legal_notice"}),
        ("What is the weather today?", set()),
    ]
    for text, expected in risk_tests:
        got = {f["id"] for f in detect_high_risk(text)}
        print(f"  {'PASS' if got == expected else 'FAIL'}  got={sorted(got)} expected={sorted(expected)} | {text}")

    print("\nUNSUPPORTED-CLAIM CHECKER")
    claim_tests = [
        ("Under Section 12 of the Transfer of Property Act, 1882 your landlord must refund within 15 days.", True),
        ("Free legal aid is available under Section 12 of the Legal Services Authorities Act, 1987 for eligible people.", False),
        ("You will definitely win this case.", True),
        ("The Supreme Court held in Sharma v. Gupta that deposits must be returned.", True),
        ("Please keep your payment screenshots safe.", False),
    ]
    for text, should_block in claim_tests:
        safe, blocked = check_response(text)
        print(f"  {'PASS' if bool(blocked) == should_block else 'FAIL'}  blocked={bool(blocked)} expected={should_block}")
        print(f"        in : {text}\n        out: {safe}")