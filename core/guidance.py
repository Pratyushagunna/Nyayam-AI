def risk_next_steps():
    """For flagged (time-sensitive) cases we give NO procedural advice, only safe basics."""
    return [
        "Because a time-sensitive situation was noted in your chat, speaking to a lawyer or "
        "legal services authority promptly comes before everything else.",
        "Keep every notice, letter, message and paper you have received safe, and note the date you "
        "received each one. Do not ignore any paper that gives a date to reply or appear.",
        "Write down a simple timeline: dates, amounts, and who said what, so you can show it to the "
        "lawyer or legal aid centre.",
        "Call the NALSA helpline 15100 or contact your nearest Legal Services Institution, or consult a "
        "lawyer of your choice. We cannot verify specific procedures or time limits.",
    ]

"""core/guidance.py - practical guidance built from the case and the verified sources.

NO AI is used here. Everything is built by plain Python from the case and
knowledge/legal_sources.json, so it can be tested offline and cannot invent law.
Every item carries a label:
  From you | Practical suggestion | Verified source | Not verified
"""
from core.case_builder import format_inr
from core.evidence import EVIDENCE_ITEMS
from core.legal_guardrails import load_sources

# Set to True in the document-generator step, once the Document tab exists.
DOCUMENT_TAB_READY = True

DOC_STATUS_TEXT = {
    "available": "You say you have it",
    "unavailable": "You say you do not have it",
    "unknown": "Not yet marked",
}

WHEN_TO_GET_HELP = [
    "You have received a court notice, summons or legal notice.",
    "You are being told to leave, or have been locked out or cut off from electricity or water.",
    "Anyone is threatening you, or police are involved.",
    "The landlord is claiming a large amount for damage or other deductions.",
    "Your situation does not fit a simple deposit dispute.",
]


def _state_entry(state_text):
    state = state_text.strip().lower()
    for entry in load_sources().get("states", {}).values():
        if any(alias.lower() in state for alias in entry["aliases"]):
            return entry
    return None


def situation_summary(case):
    loc = ", ".join(x for x in (case["location"]["city"], case["location"]["state"]) if x)
    first = "You describe a dispute about a rental security deposit"
    if case["deposit_amount_inr"]:
        first += f" of {format_inr(case['deposit_amount_inr'])}"
    if loc:
        first += f" for a property in {loc}"
    sentences = [first + "."]
    if case["rental_start_date"]:
        sentences.append(f'You gave the start of the tenancy as "{case["rental_start_date"]}".')
    if case["vacating_date"]:
        sentences.append(f'You gave your move-out time as "{case["vacating_date"]}".')
    if case["landlord_responses"]:
        sentences.append("As you reported it, the landlord's response so far: "
                         + "; ".join(case["landlord_responses"]) + ".")
    if case["landlord_claims"]:
        sentences.append("The landlord has claimed: " + "; ".join(case["landlord_claims"]) + ".")
    return " ".join(sentences)


def facts_that_matter(case):
    docs = case["documents"]
    facts = [
        {"fact": "Deposit amount",
         "value": format_inr(case["deposit_amount_inr"]) if case["deposit_amount_inr"] else "Not provided yet",
         "why": "This is the amount you are asking to get back."},
        {"fact": "Dates (move-in and move-out)",
         "value": f"{case['rental_start_date'] or 'not provided'} to {case['vacating_date'] or 'not provided'}",
         "why": "How long ago you left can matter, so keep any record of dates."},
        {"fact": "Rental agreement", "value": DOC_STATUS_TEXT[docs["rental_agreement"]],
         "why": "It usually records the deposit and the agreed terms."},
        {"fact": "Proof you paid the deposit", "value": DOC_STATUS_TEXT[docs["deposit_payment_proof"]],
         "why": "It shows that the money was paid, how much, and when."},
        {"fact": "What the landlord has said or done",
         "value": "; ".join(case["landlord_responses"]) or "Not provided yet",
         "why": "Written replies are easier to rely on than phone calls."},
    ]
    if case["landlord_claims"]:
        facts.append({"fact": "What the landlord claims", "value": "; ".join(case["landlord_claims"]),
                      "why": "If deductions are claimed, you can ask for them in writing, with reasons and proof."})
    return facts


def next_steps(case):
    steps = []
    if case["risk_flags"]:
        steps.append("Because a time-sensitive situation was noted in your chat, speaking to a lawyer or "
                     "legal services authority promptly comes before everything else below.")
    missing = [i["label"] for i in EVIDENCE_ITEMS
               if i["priority"] == "most" and case["documents"][i["key"]] != "available"]
    if missing:
        steps.append("Gather the useful documents you have not yet marked as 'Have it': "
                     + ", ".join(missing) + ". The Evidence checklist tab suggests where to look.")
    steps.append("Write down a simple timeline: dates, amounts, and who said what. "
                 "The Timeline tab shows what you have told us so far.")
    request = "Ask for your deposit back in writing (message, email or letter), keep a copy, and keep proof that you sent it."
    if DOCUMENT_TAB_READY:
        request += " The Document tab can draft this request for you."
    steps.append(request)
    if case["landlord_claims"]:
        steps.append("If the landlord claims deductions, ask for them in writing, itemised, with reasons "
                     "and any bills or photos. Keep your own photos and handover records.")
    if not case["landlord_responses"]:
        steps.append("Keep a record of every attempt to reach the landlord (dates of calls and messages).")
    steps.append("Stay polite and keep communication in writing where you can.")
    steps.append("If there is still no reply, speak to a lawyer or a legal aid centre about what formal "
                 "options exist for your state. We cannot verify specific procedures or time limits.")
    return steps


def legal_information(case):
    state_text = (case["location"]["state"] or "").strip()
    if not state_text:
        return {"status": "state_unknown", "entry": None,
                "message": "Tell us which state the property is in, and we will show what we have verified for it."}
    entry = _state_entry(state_text)
    if entry:
        return {"status": "verified_state", "entry": entry, "message": None}
    return {"status": "unverified_state", "entry": None,
            "message": (f"We have not verified the rent and tenancy rules for {state_text}. Please contact your "
                        "State Legal Services Authority or a local lawyer, or call the NALSA helpline 15100.")}


def build_guidance(case):
    sources = load_sources()
    legal = legal_information(case)
    links = [{"name": s["name"], "url": s["url"]} for s in sources["sources"]]
    if legal["entry"]:
        links.append({"name": legal["entry"]["act_name"], "url": legal["entry"]["official_url"]})
    return {
        "situation": situation_summary(case),
        "facts": facts_that_matter(case),
        "legal": legal,
        "could_not_verify": sources["could_not_verify_general"],
        "next_steps": risk_next_steps() if case["risk_flags"] else next_steps(case),
        "when_to_get_help": WHEN_TO_GET_HELP,
        "links": links,
    }


if __name__ == "__main__":
    # Offline self-test with FICTIONAL cases. Run:  python -m core.guidance
    import sys
    from core.case_builder import new_case

    sys.stdout.reconfigure(encoding="utf-8")

    def make(state, city, claims=None, responses=None, flags=None):
        c = new_case()
        c["location"].update({"state": state, "city": city})
        c["deposit_amount_inr"] = 20000
        c["rental_start_date"] = "March 2023"
        c["vacating_date"] = "about two months ago"
        c["landlord_claims"] = claims or []
        c["landlord_responses"] = responses or []
        c["risk_flags"] = flags or []
        c["documents"]["rental_agreement"] = "available"
        return c

    cases = {
        "Telangana": make("Telangana", "Hyderabad", responses=["not picking up calls"]),
        "Maharashtra + deduction claim": make("Maharashtra", "Mumbai", claims=["Rs 15,000 for property damage"]),
        "Unverified state (Karnataka)": make("Karnataka", "Bengaluru"),
        "State not given": make(None, "Pune"),
        "High-risk flag": make("Telangana", "Hyderabad", flags=[{"id": "court_notice", "title": "A court notice"}]),
    }
    for name, c in cases.items():
        g = build_guidance(c)
        print("=" * 70)
        print(name)
        print("SITUATION:", g["situation"])
        print("LEGAL STATUS:", g["legal"]["status"])
        if g["legal"]["message"]:
            print("MESSAGE:", g["legal"]["message"])
        if g["legal"]["entry"]:
            for item in g["legal"]["entry"]["what_it_says"]:
                print(f"  [{item['ref']}] {item['text'][:90]}...")
            print("  LIMITS:", len(g["legal"]["entry"]["limits"]), "| NOT FOUND:", len(g["legal"]["entry"]["not_found"]))
        print("NEXT STEPS:")
        for i, s in enumerate(g["next_steps"], 1):
            print(f"  {i}. {s}")