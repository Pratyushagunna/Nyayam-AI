"""core/case_builder.py - turns a chat into a structured case.

Flow for each user message (process_user_message):
  1. AI extracts ONLY new facts from the message  -> "updates"
  2. Python cleans the updates (unknown fields / bad values are dropped)
  3. Python merges them into the case (never silently overwrites a fact)
  4. Python tidies dates/timeline and works out what is still missing
  5. AI writes a short, kind follow-up message asking for what is missing

Documents other than the agreement and payment proof are set by the user
(through the evidence checklist), never guessed by the AI.
"""
import copy
import json
import re
import sys
from pathlib import Path

from core.llm import LLMError, generate_json, generate_response

BASE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"

DOC_LABELS = {
    "rental_agreement": "a written rental agreement",
    "deposit_payment_proof": "proof of paying the deposit (bank or UPI record)",
    "handover_evidence": "proof of handing over the property",
    "property_photos_videos": "photos or videos of the property",
    "whatsapp_messages": "WhatsApp or SMS messages with the landlord",
    "emails": "emails with the landlord",
    "written_refund_request": "a written request for your deposit back",
    "landlord_replies": "any written replies from the landlord",
}

# Only these two documents may be set from the chat by the AI.
DOC_AI_SETTABLE = {"rental_agreement", "deposit_payment_proof"}

EMPTY_CASE = {
    "case_title": None,
    "category": "rental_security_deposit",
    "in_scope": None,
    "location": {"state": None, "city": None},
    "parties": {"tenant_name": None, "landlord_name": None},
    "property_address": None,
    "deposit_amount_inr": None,
    "monthly_rent_inr": None,
    "rental_start_date": None,
    "vacating_date": None,
    "landlord_responses": [],
    "user_claims": [],
    "landlord_claims": [],
    "timeline": [],
    "facts_established": [],
    "issues_to_verify": [],
    "documents": {key: "unknown" for key in DOC_LABELS},
    "risk_flags": [],
}

# (path in the case, plain-English label) - the case is "ready" when all are known
REQUIRED = [
    ("location.state", "the state where the property is"),
    ("location.city", "the city or town"),
    ("deposit_amount_inr", "the security deposit amount"),
    ("rental_start_date", "when the tenancy started (approximately is fine)"),
    ("vacating_date", "when you moved out (approximately is fine)"),
    ("landlord_responses", "what the landlord has said or done about returning the deposit"),
    ("documents.rental_agreement", "whether you have a written rental agreement"),
    ("documents.deposit_payment_proof", "whether you have proof of paying the deposit"),
]

LOCKED_PATHS = {"risk_flags"}  # the AI is never allowed to set these
AMOUNT_PATHS = {"deposit_amount_inr", "monthly_rent_inr"}

MOVE_IN = re.compile(r"(?i)\b(moved? in|moving in|move-in|tenancy (started|began|start)|started renting)")
MOVE_OUT = re.compile(r"(?i)\b(moved? out|move-out|vacat\w*)")

EXTRACT_TASK = """
TASK: You receive JSON with "current_case", "assistant_previous_message" and "user_latest_message".
Extract ONLY new information from "user_latest_message" (the previous assistant message is given only so you understand short answers like "yes").
Return a JSON object: {"updates": {...}, "corrections": [...]}

Rules:
- Use exactly the field names from current_case. Never add new fields. Include only fields the latest message gives information about.
- Record only what the user actually said. Never guess, infer or calculate. Do NOT infer the state from the city; set location.state only if the user states it or clearly confirms it.
- Amounts: a plain number in rupees, for example 20000. If unclear, leave it out.
- Dates: copy the user's own wording exactly (for example "about two months ago", "March 2023"). Never convert or compute dates.
- rental_start_date: whenever the user says when they moved in or the tenancy started, put it here. vacating_date: whenever the user says when they moved out or vacated, put it here.
- documents: ONLY rental_agreement and deposit_payment_proof may be set. "available" only if the user says they have it; "unavailable" only if they say they do not. Do not set any other document field.
- landlord_responses: a list of short factual statements about what the landlord said or did, as reported by the user. Only NEW statements from this message.
- landlord_claims / user_claims: lists of short strings describing what each side claims (include amounts if stated).
- timeline: list of {"date": "<user's wording or null>", "event": "<short event>"} for events OTHER than moving in and moving out (those belong in rental_start_date and vacating_date). Examples: deposit paid, refund requested, landlord replied, notice received.
- facts_established: list of short statements the user made (these are user-supplied, not verified).
- issues_to_verify: list of things that are unclear or contradictory.
- in_scope: true if this is about a residential rental security deposit in India; false if clearly about something else; leave out if unclear.
- corrections: list of dotted field paths (for example "deposit_amount_inr", "location.city") ONLY where the user explicitly corrects something they said earlier.
- If the message has no case information, return {"updates": {}, "corrections": []}.
"""

FOLLOWUP_TASK = """
TASK: Write the assistant's next chat message. Plain text only: no JSON, no headings, no bullet lists. Under 80 words.
You receive JSON with the case so far, "still_missing_required" (labels), "conflicts_to_clarify" and "user_latest_message".

Rules:
1. Start with one short, kind sentence acknowledging what the user said. No legal advice.
2. If "conflicts_to_clarify" is not empty, ask the user to clarify the first conflict.
3. Otherwise ask at most TWO questions, taken in order from "still_missing_required".
4. If the state is missing, simply ask which state the property is in. Do not guess the state and do not explain why you are asking.
5. If "still_missing_required" is empty, say you now have enough to build the case summary, invite the user to open the Evidence checklist to tick which documents they have, and say they can add more details anytime.
6. If in_scope is false, politely say Nyayam AI currently only helps with residential rental security deposit disputes in India and suggest speaking with a qualified lawyer or the local legal services authority. Do not ask intake questions.
7. If the message had no case information, gently steer back to the rental deposit problem.
8. Never cite laws, sections or deadlines, and never promise outcomes.
"""


def new_case():
    return copy.deepcopy(EMPTY_CASE)


def _base_prompt():
    return BASE_PROMPT_PATH.read_text(encoding="utf-8")


def format_inr(amount):
    """20000 -> ₹20,000 ; 100000 -> ₹1,00,000 (Indian digit grouping)."""
    s = str(int(amount))
    if len(s) <= 3:
        return "₹" + s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "₹" + ",".join(parts + [tail])


def get_path(case, path):
    value = case
    for part in path.split("."):
        value = value[part]
    return value


def missing_required(case):
    """Plain-English labels of required facts we still do not have."""
    result = []
    for path, label in REQUIRED:
        value = get_path(case, path)
        if value is None or value == "unknown" or value == []:
            result.append(label)
    return result


def set_document_status(case, key, status):
    """Used by the evidence checklist: the USER decides what they have."""
    if key not in DOC_LABELS or status not in ("available", "unavailable", "unknown"):
        raise ValueError(f"Invalid document update: {key!r} -> {status!r}")
    case["documents"][key] = status


def get_timeline(case):
    """Timeline for display: start date, other events (in the order reported), move-out."""
    items = []
    if case["rental_start_date"]:
        items.append({"date": case["rental_start_date"], "event": "Tenancy started / moved in"})
    items.extend(case["timeline"])
    if case["vacating_date"]:
        items.append({"date": case["vacating_date"], "event": "Moved out of the property"})
    return items


# ---------- cleaning what the AI returned ----------

def _clean_scalar(path, value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if path in AMOUNT_PATHS:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value) if value > 0 else None
        text = re.sub(r"(?i)₹|rs\.?|inr|rupees|/-|,|\s", "", str(value))
        return int(float(text)) if re.fullmatch(r"\d+(\.\d+)?", text) and float(text) > 0 else None
    if path.startswith("documents."):
        return value if value in ("available", "unavailable") else None
    if path == "in_scope":
        return value if isinstance(value, bool) else None
    return str(value).strip()


def _clean_list(path, value):
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if path == "timeline":
            if isinstance(item, dict) and isinstance(item.get("event"), str) and item["event"].strip():
                date = item.get("date")
                cleaned.append({
                    "date": date.strip() if isinstance(date, str) and date.strip() else None,
                    "event": item["event"].strip(),
                })
        elif isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned


def _filter(updates, template, path=""):
    """Keep only fields that exist in our case template, with valid values."""
    out = {}
    if not isinstance(updates, dict):
        return out
    for key, tmpl in template.items():
        full = f"{path}.{key}" if path else key
        if full in LOCKED_PATHS or key not in updates:
            continue
        if path == "documents" and key not in DOC_AI_SETTABLE:
            continue  # only the user may mark these (checklist)
        value = updates[key]
        if isinstance(tmpl, dict):
            sub = _filter(value, tmpl, full)
            if sub:
                out[key] = sub
        elif isinstance(tmpl, list):
            items = _clean_list(full, value)
            if items:
                out[key] = items
        else:
            clean = _clean_scalar(full, value)
            if clean is not None:
                out[key] = clean
    return out


# ---------- merging ----------

def _list_has(existing, item):
    if isinstance(item, dict):
        return any(isinstance(e, dict) and e["event"].lower() == item["event"].lower() for e in existing)
    return any(isinstance(e, str) and e.lower() == item.lower() for e in existing)


def _merge(target, updates, path, corrections, conflicts, replaced):
    for key, value in updates.items():
        full = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            _merge(target[key], value, full, corrections, conflicts, replaced)
        elif isinstance(value, list):
            for item in value:
                if not _list_has(target[key], item):
                    target[key].append(item)
        else:
            current = target.get(key)
            is_empty = current == "unknown" if path == "documents" else current is None
            if is_empty:
                target[key] = value
            elif current == value:
                continue
            elif full in corrections:
                replaced.append((full, current))
                target[key] = value
            else:
                conflicts.append(f"{full}: you said '{current}' earlier, but now '{value}'")


def _remove_stale(case, path, old_value):
    """After the user corrects a value, remove things that still mention the old one."""
    prefix = f"Conflicting statements - {path}:"
    case["issues_to_verify"] = [i for i in case["issues_to_verify"] if not i.startswith(prefix)]
    if path in AMOUNT_PATHS and isinstance(old_value, int):
        pattern = re.compile(rf"(?<!\d){old_value}(?!\d)")
        case["facts_established"] = [
            f for f in case["facts_established"] if not pattern.search(re.sub(r"[,\s]", "", f))
        ]


def _add_issue(case, note):
    if not _list_has(case["issues_to_verify"], note):
        case["issues_to_verify"].append(note)


def merge_updates(case, updates, corrections=()):
    """Merge cleaned updates into the case. Returns a list of conflicts."""
    conflicts, replaced = [], []
    _merge(case, updates, "", set(corrections or []), conflicts, replaced)
    for path, old_value in replaced:
        _remove_stale(case, path, old_value)
    for text in conflicts:
        _add_issue(case, "Conflicting statements - " + text)
    return conflicts


def _tidy_timeline(case):
    """Move-in / move-out events belong in the date fields, not the timeline.
    If the AI put a date only in the timeline, promote it (the user's own wording)."""
    kept = []
    for entry in case["timeline"]:
        for pattern, field, label in ((MOVE_IN, "rental_start_date", "move-in"),
                                      (MOVE_OUT, "vacating_date", "move-out")):
            if entry["date"] and pattern.search(entry["event"]):
                if case[field] is None:
                    case[field] = entry["date"]
                elif case[field].lower() != entry["date"].lower():
                    _add_issue(case, f"Two different {label} dates were mentioned: "
                                     f"'{case[field]}' and '{entry['date']}'")
                break
        else:
            kept.append(entry)
            continue
    case["timeline"] = kept


def _set_title(case):
    """The title is always generated by us, so we refresh it every time."""
    if case["location"]["city"] and case["deposit_amount_inr"]:
        case["case_title"] = (
            f"Security deposit refund dispute - {case['location']['city']} "
            f"({format_inr(case['deposit_amount_inr'])})"
        )


# ---------- the main function the app will call ----------

def process_user_message(case, history, user_text):
    """Update `case` (in place) from one user message and write the reply.

    history: earlier messages [{"role": "user"|"assistant", "content": "..."}]
    Returns a dict: reply, conflicts, applied_updates, raw_extraction.
    If the AI extraction fails, LLMError is raised and the case is left untouched."""
    last_assistant = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)

    payload = {
        "current_case": case,
        "assistant_previous_message": last_assistant,
        "user_latest_message": user_text,
    }
    extraction = generate_json(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        _base_prompt() + "\n" + EXTRACT_TASK,
        required_keys=["updates"],
    )

    applied = _filter(extraction.get("updates", {}), EMPTY_CASE)
    corrections = [c for c in extraction.get("corrections", []) if isinstance(c, str)]
    conflicts = merge_updates(case, applied, corrections)
    _tidy_timeline(case)
    _set_title(case)

    missing = missing_required(case)
    followup_payload = {
        "case": case,
        "still_missing_required": missing,
        "conflicts_to_clarify": conflicts,
        "user_latest_message": user_text,
    }
    try:
        reply = generate_response(
            [{"role": "user", "content": json.dumps(followup_payload, ensure_ascii=False)}],
            _base_prompt() + "\n" + FOLLOWUP_TASK,
        )
    except LLMError:
        # The case was saved; fall back to a plain message instead of failing.
        reply = "I have noted what you shared."
        if missing:
            reply += f" Next, could you tell me {missing[0]}?"

    return {
        "reply": reply,
        "conflicts": conflicts,
        "applied_updates": applied,
        "raw_extraction": extraction,
    }


if __name__ == "__main__":
    # Self-test with FICTIONAL data. Run with:  python -m core.case_builder
    sys.stdout.reconfigure(encoding="utf-8")  # so ₹ prints correctly on Windows

    script = [
        "I rented a flat in Hyderabad. I paid Rs 20,000 as security deposit. I vacated about two "
        "months ago but my landlord is not returning it and not picking up my calls. "
        "I have the rental agreement and payment screenshots.",
        "Yes, it is in Telangana. I moved in March 2023.",
        "Sorry, I made a mistake, the deposit was actually 25,000. He said on WhatsApp that he will see.",
    ]

    case = new_case()
    history = []
    for number, text in enumerate(script, start=1):
        print("=" * 70)
        print(f"USER (message {number}):", text)
        result = process_user_message(case, history, text)
        print("\nAPPLIED UPDATES:", json.dumps(result["applied_updates"], ensure_ascii=False))
        print("CONFLICTS:", result["conflicts"])
        print("STATE AFTER THIS MESSAGE:", case["location"]["state"])
        print("STILL MISSING:", missing_required(case))
        print("\nNyayam AI:", result["reply"])
        history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": result["reply"]},
        ]

    print("=" * 70)
    print("DISPLAY TIMELINE:", json.dumps(get_timeline(case), ensure_ascii=False))
    print("FINAL CASE JSON:")
    print(json.dumps(case, indent=2, ensure_ascii=False))