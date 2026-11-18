"""core/evidence.py - what evidence to collect, and how ready the user is.

Priority ("most" / "also") is OUR practical suggestion, not a legal rule.
legal_status stays "Not verified" until a verified source is added to
knowledge/legal_sources.json (Step 11).
"""

EVIDENCE_ITEMS = [
    {
        "key": "rental_agreement",
        "label": "Rental agreement",
        "priority": "most",
        "why": "Usually shows the deposit amount, the rent and the agreed terms.",
        "how": "Look in your email, cloud storage or phone gallery. Ask the landlord or broker for a copy.",
    },
    {
        "key": "deposit_payment_proof",
        "label": "Proof you paid the deposit",
        "priority": "most",
        "why": "Shows that the money was paid, how much, and when.",
        "how": "Download a bank statement or UPI history for that month. Screenshots help, but an official statement is clearer.",
    },
    {
        "key": "whatsapp_messages",
        "label": "WhatsApp or SMS messages with the landlord",
        "priority": "most",
        "why": "Can show your requests and the landlord's replies, with dates.",
        "how": "In WhatsApp use Export Chat on that conversation, and keep screenshots showing the dates.",
    },
    {
        "key": "written_refund_request",
        "label": "A written request for your deposit back",
        "priority": "most",
        "why": "A dated written request shows you asked clearly. The draft letter we generate later can serve this purpose.",
        "how": "If you have not asked in writing yet, the Document section can draft a request for you.",
    },
    {
        "key": "handover_evidence",
        "label": "Proof of handing over the property",
        "priority": "also",
        "why": "Can show when you returned the keys and in what state the property was.",
        "how": "Look for a handover note, key return message, or a message confirming the move-out date.",
    },
    {
        "key": "property_photos_videos",
        "label": "Photos or videos of the property",
        "priority": "also",
        "why": "Can show the condition of the property, which matters if the landlord claims damage.",
        "how": "Check your phone gallery and cloud backups around the move-out date.",
    },
    {
        "key": "emails",
        "label": "Emails with the landlord",
        "priority": "also",
        "why": "Another written record of requests and replies.",
        "how": "Search your mailbox for the landlord's name or email address.",
    },
    {
        "key": "landlord_replies",
        "label": "Any written replies from the landlord",
        "priority": "also",
        "why": "Shows the landlord's own position, such as a promise or a reason for not paying.",
        "how": "Check messages, emails and letters. Keep the originals.",
    },
]

STATUS_TO_OPTION = {"available": "Have it", "unavailable": "Don't have it", "unknown": "Not sure yet"}
OPTION_TO_STATUS = {v: k for k, v in STATUS_TO_OPTION.items()}


def legal_status(key):
    """Whether a document is LEGALLY required. We have not verified this from an
    official source yet, so we never claim it. (Updated in Step 11.)"""
    return "Not verified"


def readiness(case):
    """Counts for the 'most useful' documents (our practical suggestion)."""
    most = [i for i in EVIDENCE_ITEMS if i["priority"] == "most"]
    have = [i for i in most if case["documents"][i["key"]] == "available"]
    not_have = [i for i in most if case["documents"][i["key"]] == "unavailable"]
    unsure = [i for i in most if case["documents"][i["key"]] == "unknown"]
    return {
        "total": len(most),
        "have": len(have),
        "not_have": [i["label"] for i in not_have],
        "unsure": [i["label"] for i in unsure],
    }