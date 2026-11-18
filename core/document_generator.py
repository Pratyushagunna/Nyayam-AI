"""core/document_generator.py - builds the refund-request draft.

NO AI is used. Everything comes from the case and the user's optional details.
Unknown information becomes a [placeholder]. No legal citations, no invented
deadlines, nothing is sent anywhere.
"""
import io
import re

from core.case_builder import format_inr
from core.evidence import EVIDENCE_ITEMS

DRAFT_NOTICE = (
    "[DRAFT - Review and edit everything before using it. This is a draft request written from the "
    "details you gave Nyayam AI. It is not a lawyer-verified legal notice. Delete this line before sending.]"
)

LETTER_DOC_TEXT = {
    "rental_agreement": "Copy of the rental agreement",
    "deposit_payment_proof": "Proof of payment of the security deposit (bank or UPI record)",
    "whatsapp_messages": "Copies of WhatsApp or SMS messages between us",
    "written_refund_request": "Copy of my earlier written request for the deposit",
    "handover_evidence": "Records of handing over the property",
    "property_photos_videos": "Photographs or videos of the property",
    "emails": "Copies of emails between us",
    "landlord_replies": "Copies of your written replies",
}

EXACT_DATE = re.compile(
    r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b"
    r"|\b\d{1,2}(st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}\b"
    r"|\b[A-Za-z]{3,9}\.?\s+\d{1,2}(st|nd|rd|th)?,?\s+\d{4}\b"
)


def _pick(value, placeholder):
    if isinstance(value, str):
        value = value.strip()
    return value if value else placeholder


def _date_line(label, value, placeholder):
    if not value:
        return f"- {label}: {placeholder}"
    if EXACT_DATE.search(value):
        return f"- {label}: {value}"
    return f"- {label}: {value} [replace with the exact date if you have it]"


def generate_draft(case, details=None):
    """Return the draft letter as plain text. `details` holds optional fields:
    sender_name, sender_address, sender_contact, landlord_name, landlord_address,
    property_address, letter_date, response_by."""
    d = details or {}
    sender_name = _pick(d.get("sender_name") or case["parties"]["tenant_name"], "[Your name]")
    sender_address = _pick(d.get("sender_address"), "[Your address]")
    sender_contact = _pick(d.get("sender_contact"), "[Your phone or email]")
    landlord_name = _pick(d.get("landlord_name") or case["parties"]["landlord_name"], "[Landlord's name]")
    landlord_address = _pick(d.get("landlord_address"), "[Landlord's address]")
    property_address = _pick(d.get("property_address") or case["property_address"], "[Property address]")
    letter_date = _pick(d.get("letter_date"), "[Date]")
    response_by = _pick(d.get("response_by"), "[DATE - choose a reasonable date for your reply]")
    amount = format_inr(case["deposit_amount_inr"]) if case["deposit_amount_inr"] else "[deposit amount]"

    lines = [
        DRAFT_NOTICE, "",
        "From:", sender_name, sender_address, sender_contact, "",
        f"Date: {letter_date}", "",
        "To:", landlord_name, landlord_address, "",
        f"Subject: Request for refund of security deposit - {property_address}", "",
        f"Dear {landlord_name},", "",
        "I am writing about the security deposit for the property I rented from you. "
        "The details are:", "",
        f"- Property: {property_address}",
        _date_line("Tenancy started", case["rental_start_date"], "[start date]"),
        _date_line("Moved out", case["vacating_date"], "[move-out date]"),
        f"- Security deposit paid: {amount}",
    ]
    if case["monthly_rent_inr"]:
        lines.append(f"- Monthly rent: {format_inr(case['monthly_rent_inr'])}")
    lines += [
        "",
        f"I paid a security deposit of {amount} for this property. I have moved out, and as of the "
        "date of this letter I have not received the deposit back.", "",
    ]
    if case["landlord_claims"]:
        lines.append("I understand you have mentioned the following: " + "; ".join(case["landlord_claims"]) + ".")
        lines.append("")
    lines += [
        f"I would be grateful if you would please do one of the following by {response_by}:", "",
        f"1. Refund the full security deposit of {amount}; or",
        "2. If you believe any amount can be deducted, send me a written, itemised statement of each "
        "deduction, with the reason and supporting proof (such as bills or photographs), and refund the "
        "balance you agree is due to me.", "",
    ]
    available = [LETTER_DOC_TEXT[i["key"]] for i in EVIDENCE_ITEMS
                 if case["documents"].get(i["key"]) == "available"]
    if available:
        lines.append("Supporting documents I have:")
        lines += [f"- {text}" for text in available]
    else:
        lines.append("Supporting documents I have: [list the documents you will attach, if any]")
    lines += [
        "",
        "I would prefer to settle this directly and politely, and I look forward to your reply.", "",
        "Yours sincerely,", "",
        "[Signature]",
        sender_name,
    ]
    return "\n".join(lines)


def count_placeholders(text):
    """How many [placeholders] are left (the draft-notice line is not counted)."""
    body = "\n".join(text.split("\n")[1:]) if text.startswith("[DRAFT") else text
    return len(re.findall(r"\[[^\]\n]+\]", body))


def text_to_docx_bytes(text):
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for line in text.split("\n"):
        paragraph = doc.add_paragraph(line)
        paragraph.paragraph_format.space_after = Pt(0)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


if __name__ == "__main__":
    # Offline self-test with FICTIONAL data. Run:  python -m core.document_generator
    import sys
    from pathlib import Path

    from core.case_builder import new_case
    from core.legal_guardrails import check_response

    sys.stdout.reconfigure(encoding="utf-8")
    out_dir = Path(__file__).resolve().parent.parent / "tests" / "raw_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    full = new_case()
    full["location"].update({"state": "Telangana", "city": "Hyderabad"})
    full["deposit_amount_inr"] = 25000
    full["rental_start_date"] = "March 2023"
    full["vacating_date"] = "14 September 2026"
    full["landlord_claims"] = ["Rs 15,000 for property damage"]
    full["documents"]["rental_agreement"] = "available"
    full["documents"]["deposit_payment_proof"] = "available"
    full["documents"]["whatsapp_messages"] = "available"
    details = {"sender_name": "Asha Rao (fictional)", "landlord_name": "Mr Kumar (fictional)",
               "property_address": "Flat 4B, Example Residency, Hyderabad"}

    draft_full = generate_draft(full, details)
    draft_empty = generate_draft(new_case())

    print("=" * 70, "\nDRAFT FROM A FILLED CASE\n" + "=" * 70)
    print(draft_full)
    print("=" * 70, "\nDRAFT FROM AN EMPTY CASE (placeholders expected)\n" + "=" * 70)
    print(draft_empty)

    (out_dir / "step12_sample_draft.txt").write_text(draft_full, encoding="utf-8")
    docx_bytes = text_to_docx_bytes(draft_full)
    (out_dir / "step12_sample_draft.docx").write_bytes(docx_bytes)

    from docx import Document
    roundtrip = "\n".join(p.text for p in Document(io.BytesIO(docx_bytes)).paragraphs)

    print("=" * 70, "\nCHECKS")
    checks = [
        ("filled draft contains the deposit amount", "₹25,000" in draft_full),
        ("filled draft keeps the claim as reported by the user", "Rs 15,000 for property damage" in draft_full),
        ("exact move-out date has no replace-hint", "14 September 2026 [replace" not in draft_full),
        ("approximate start date gets a replace-hint", "March 2023 [replace" in draft_full),
        ("only available documents are listed", "photographs or videos" not in draft_full.lower()),
        ("empty draft shows placeholders instead of facts", "[deposit amount]" in draft_empty and "[Your name]" in draft_empty),
        ("no 'None' text anywhere", "None" not in draft_full and "None" not in draft_empty),
        ("draft contains no legal-claim patterns", check_response(draft_full)[1] == [] and check_response(draft_empty)[1] == []),
        ("draft notice is the first line", draft_full.startswith("[DRAFT")),
        ("DOCX round-trip matches the text", roundtrip == draft_full),
    ]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print("\nPlaceholders left: filled =", count_placeholders(draft_full), "| empty =", count_placeholders(draft_empty))
    print("Files written to tests/raw_outputs/: step12_sample_draft.txt and step12_sample_draft.docx")