"""app.py - Nyayam AI Streamlit interface.
Stage 5: chat, summary, timeline, evidence, guidance, document draft, legal help, safety layer.
"""
import streamlit as st

from core.case_builder import (
    REQUIRED,
    format_inr,
    get_timeline,
    missing_required,
    new_case,
    process_user_message,
    set_document_status,
)
from core.document_generator import count_placeholders, generate_draft, text_to_docx_bytes
from core.evidence import (
    EVIDENCE_ITEMS,
    OPTION_TO_STATUS,
    STATUS_TO_OPTION,
    legal_status,
    readiness,
)
from core.guidance import WHEN_TO_GET_HELP, build_guidance
from core.legal_guardrails import (
    CANNOT_VERIFY,
    build_escalation_message,
    check_response,
    detect_high_risk,
    load_sources,
)
from core.llm import LLMError

GREETING = (
    "Hello, I'm Nyayam AI. Please tell me, in your own words, what happened with your "
    "rental security deposit. You don't need any legal words, and you can write casually."
)
DISCLAIMER = (
    "Nyayam AI is an AI tool that gives general information. It is not a lawyer and does "
    "not give legal advice. It can make mistakes."
)
UNVERIFIED_FOLLOWUP = (
    " For legal questions I cannot answer, please see the Guidance and Legal help tabs, "
    "ask your State Legal Services Authority, or call the 15100 helpline."
)
FIELD_KEYS = [
    "fld_sender_name", "fld_sender_address", "fld_sender_contact", "fld_landlord_name",
    "fld_landlord_address", "fld_property_address", "fld_letter_date", "fld_response_by",
]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

st.set_page_config(page_title="Nyayam AI", page_icon="⚖️", layout="centered")


def start_new_case():
    st.session_state.case = new_case()
    st.session_state.messages = [{"role": "assistant", "content": GREETING}]
    st.session_state.error = None
    st.session_state.blocked_log = []
    st.session_state.started = True
    for key in FIELD_KEYS + ["draft_text", "doc_risk_ack"]:
        st.session_state.pop(key, None)


def on_doc_change(doc_key, widget_key):
    set_document_status(
        st.session_state.case, doc_key, OPTION_TO_STATUS[st.session_state[widget_key]]
    )


def make_draft():
    details = {key[4:]: st.session_state.get(key, "") for key in FIELD_KEYS}
    st.session_state.draft_text = generate_draft(st.session_state.case, details)


if "started" not in st.session_state:
    st.session_state.started = False
    st.session_state.case = new_case()
    st.session_state.messages = []
    st.session_state.error = None
    st.session_state.blocked_log = []


def render_legal_aid_card():
    card = load_sources()["legal_aid_card"]
    st.markdown(f"**{card['title']}**")
    for line in card["lines"]:
        st.markdown(f"- {line}")
    st.markdown(f"Official website: {card['website']}")


st.title("Nyayam AI")
st.caption("Understand your rights. Know your next step.")

# ---------------- Welcome screen ----------------
if not st.session_state.started:
    st.write(
        "Nyayam AI helps you organise a **rental security deposit problem**: it asks a few "
        "questions, builds a clear summary of your case, and explains practical next steps "
        "in simple language."
    )
    st.info(
        "**Currently supports:** residential rental security deposit disputes in India only."
    )
    st.warning(
        "**Privacy:** what you type is sent to Google's Gemini AI service. Please do not share "
        "phone numbers, Aadhaar or PAN numbers, or bank account numbers. This is a prototype."
    )
    st.caption(DISCLAIMER)
    if st.button("Start a new case", type="primary"):
        start_new_case()
        st.rerun()
    st.stop()

case = st.session_state.case
messages = st.session_state.messages

# ---------------- Handle a new chat message (before drawing the page) ----------------
user_text = st.chat_input("Describe what happened, or answer the question above")
if user_text:
    # Safety rules run first, so they work even if the AI service fails.
    new_flags = detect_high_risk(user_text)
    known = {f["id"] for f in case["risk_flags"]}
    for flag in new_flags:
        if flag["id"] not in known:
            case["risk_flags"].append(flag)

    reply, error = None, None
    try:
        with st.spinner("Reading your message..."):
            result = process_user_message(case, messages, user_text)
        reply = result["reply"]
    except LLMError as e:
        if new_flags:
            error = (f"{e} Your case summary could not be updated from this message, "
                     "but the safety guidance below still applies.")
        else:
            error = f"{e} Your last message was not saved. Please send it again."

    if new_flags:
        reply = build_escalation_message(new_flags)  # fixed text replaces the AI's reply

    if reply is not None:
        safe_reply, blocked = check_response(reply)
        if blocked:
            st.session_state.blocked_log.append({"blocked": blocked, "replaced_with": safe_reply})
        if CANNOT_VERIFY in safe_reply and "15100" not in safe_reply:
            safe_reply += UNVERIFIED_FOLLOWUP
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": safe_reply})
    st.session_state.error = error

# ---------------- Persistent safety banner ----------------
if case["risk_flags"]:
    titles = "; ".join(f["title"] for f in case["risk_flags"])
    st.error(
        f"**Time-sensitive situation detected:** {titles}. "
        "Nyayam AI cannot give reliable procedural advice for this. Please speak to a "
        "qualified lawyer or your nearest legal services authority as soon as possible. "
        "See the **Legal help** tab for official contact information."
    )

# ---------------- Page ----------------
tab_chat, tab_summary, tab_timeline, tab_evidence, tab_guidance, tab_doc, tab_help = st.tabs(
    ["Chat", "Case summary", "Timeline", "Evidence checklist", "Guidance", "Document", "Legal help"]
)

with tab_chat:
    for m in messages:
        with st.chat_message(m["role"]):
            st.write(m["content"])
    if st.session_state.error:
        st.error(st.session_state.error)

with tab_summary:
    missing = missing_required(case)
    total = len(REQUIRED)
    done = total - len(missing)

    st.subheader(case["case_title"] or "Your case (still being built)")
    st.progress(done / total, text=f"Key details collected: {done} of {total}")
    st.caption(
        "Everything below comes from what you told me. It has not been checked or verified."
    )

    loc = case["location"]
    details = [
        ("Category", "Residential rental security deposit"),
        ("Location", ", ".join(x for x in (loc["city"], loc["state"]) if x) or None),
        ("Deposit amount", format_inr(case["deposit_amount_inr"]) if case["deposit_amount_inr"] else None),
        ("Monthly rent", format_inr(case["monthly_rent_inr"]) if case["monthly_rent_inr"] else None),
        ("Tenancy started", case["rental_start_date"]),
        ("Moved out", case["vacating_date"]),
        ("Tenant name", case["parties"]["tenant_name"]),
        ("Landlord name", case["parties"]["landlord_name"]),
        ("Property address", case["property_address"]),
    ]
    for label, value in details:
        st.markdown(f"**{label}:** {value if value else '_Not provided yet_'}")

    def bullet_section(title, items, empty):
        st.markdown(f"**{title}**")
        if items:
            for item in items:
                st.markdown(f"- {item}")
        else:
            st.caption(empty)

    st.divider()
    bullet_section("What you say happened", case["facts_established"], "Nothing recorded yet.")
    bullet_section("Your claims", case["user_claims"], "None recorded yet.")
    bullet_section("What the landlord has said or done (as you reported it)",
                   case["landlord_responses"], "None recorded yet.")
    bullet_section("The landlord's claims", case["landlord_claims"], "None recorded yet.")
    bullet_section("Still needed", missing, "Nothing is missing from the key details.")
    bullet_section("Things to verify", case["issues_to_verify"], "Nothing flagged.")

    with st.expander("Technical view: structured case (JSON)"):
        st.json(case)

with tab_timeline:
    items = get_timeline(case)
    if not items:
        st.info("No dates have been recorded yet. They will appear here as you answer questions.")
    for item in items:
        st.markdown(f"**{item['date'] or 'Date not given'}**: {item['event']}")
    if items:
        st.caption("Dates are shown in your own words. They have not been converted or checked.")

with tab_evidence:
    st.subheader("Evidence checklist")
    st.write(
        "Mark each item honestly. Only you know what you have. "
        "The groups below are our **practical suggestion**, not a legal rule."
    )
    st.info(
        "**Which documents are legally required?** We have not verified this from an official "
        "source, so Nyayam AI does not claim that any document is legally required. "
        "A lawyer or legal aid centre can tell you what applies to your situation."
    )

    r = readiness(case)
    st.progress(r["have"] / r["total"], text=f"Most useful documents you have: {r['have']} of {r['total']}")

    def render_group(title, priority):
        st.markdown(f"#### {title}")
        for item in EVIDENCE_ITEMS:
            if item["priority"] != priority:
                continue
            widget_key = f"doc_{item['key']}"
            st.session_state[widget_key] = STATUS_TO_OPTION[case["documents"][item["key"]]]
            st.markdown(f"**{item['label']}**")
            st.caption(f"{item['why']}  \nLegally required: {legal_status(item['key'])}")
            st.radio(
                item["label"],
                list(OPTION_TO_STATUS),
                key=widget_key,
                horizontal=True,
                label_visibility="collapsed",
                on_change=on_doc_change,
                args=(item["key"], widget_key),
            )
            if case["documents"][item["key"]] != "available":
                with st.expander("How could I get this?"):
                    st.write(item["how"])

    render_group("Most useful (our suggestion)", "most")
    render_group("Also useful", "also")

    if case["documents"]["rental_agreement"] == "unavailable":
        st.warning(
            "**No written agreement?** That does not mean you have nothing. Other records, such as "
            "payment proof, messages that mention the deposit, and rent receipts, become more "
            "important. Whether a particular record is accepted is a legal question, so please "
            "ask a lawyer or legal aid centre."
        )

with tab_guidance:
    g = build_guidance(case)
    st.subheader("Guidance")
    st.caption(
        "This page is built from what you told us and from sources we have checked. "
        "No AI writes it. Each part is labelled so you can see what kind of information it is. "
        "It is general information, not legal advice."
    )
    if case["risk_flags"]:
        st.error("A time-sensitive situation was noted. Please read the **Legal help** tab first.")

    st.markdown("#### Your situation")
    st.caption("Label: From you (not verified)")
    st.write(g["situation"])

    st.markdown("#### Facts that matter")
    st.caption("Label: From you, with our practical suggestion on why each matters")
    for f in g["facts"]:
        st.markdown(f"- **{f['fact']}:** {f['value']}  \n  _{f['why']}_")

    missing_now = missing_required(case)
    st.markdown("#### Information still missing")
    st.caption("Label: Based on our intake checklist")
    if missing_now:
        for m in missing_now:
            st.markdown(f"- {m}")
    else:
        st.write("Nothing is missing from the key details.")

    st.markdown("#### What the law says in your state")
    st.caption("Label: Verified source (official text), with limits")
    legal = g["legal"]
    if legal["status"] == "verified_state":
        entry = legal["entry"]
        st.markdown(f"**{entry['act_name']}**")
        for item in entry["what_it_says"]:
            st.markdown(f"- **{item['ref']}:** {item['text']}")
        st.warning("**Limits of this information**\n\n" + "\n".join(f"- {x}" for x in entry["limits"]))
        for x in entry["not_found"]:
            st.info(x)
        st.caption(f"Official source: {entry['official_url']} · Last checked: {entry['last_checked']}")
    else:
        st.info(legal["message"])

    st.markdown("#### What we could not verify")
    st.caption("Label: Not verified. Please ask a lawyer or legal aid centre.")
    for x in g["could_not_verify"]:
        st.markdown(f"- {x}")

    st.markdown("#### Practical next steps")
    st.caption("Label: Practical suggestion (not a legal rule)")
    for i, s in enumerate(g["next_steps"], 1):
        st.markdown(f"{i}. {s}")

    st.markdown("#### When to speak to a lawyer or legal aid centre")
    st.caption("Label: Practical suggestion")
    for line in g["when_to_get_help"]:
        st.markdown(f"- {line}")

    st.markdown("#### Sources")
    for link in g["links"]:
        st.markdown(f"- {link['name']}: {link['url']}")

with tab_doc:
    st.subheader("Refund request draft")
    st.warning(
        "This is a **draft communication**, not a lawyer-verified legal notice. Nyayam AI does not "
        "send anything for you. Read it carefully and edit it before you use it."
    )
    proceed = True
    if case["risk_flags"]:
        st.error(
            "A time-sensitive situation was noted in your chat (for example a court notice or an "
            "eviction threat). A refund request may not be the right first step. Please speak to a "
            "lawyer or legal aid centre before sending anything."
        )
        proceed = st.checkbox("I have read this and still want a draft", key="doc_risk_ack")

    if proceed:
        st.markdown("**Optional details.** Anything you leave blank stays as a [placeholder] in the draft.")
        st.caption("Please do not enter Aadhaar, PAN or bank account numbers. They are not needed.")
        st.text_input("Your name", key="fld_sender_name")
        st.text_input("Your address", key="fld_sender_address")
        st.text_input("Your phone or email", key="fld_sender_contact")
        st.text_input("Landlord's name", key="fld_landlord_name")
        st.text_input("Landlord's address", key="fld_landlord_address")
        st.text_input("Property address", key="fld_property_address")
        st.text_input("Date of the letter", key="fld_letter_date")
        st.text_input("Date you would like a reply by", key="fld_response_by",
                      help="You choose a reasonable date. Nyayam AI does not suggest a legal deadline.")

        has_draft = "draft_text" in st.session_state
        st.button("Regenerate draft (replaces your edits)" if has_draft else "Create draft",
                  on_click=make_draft, type="primary")

        if has_draft:
            st.markdown("**Your draft (you can edit it here):**")
            st.text_area("Draft text", key="draft_text", height=520, label_visibility="collapsed")
            left = count_placeholders(st.session_state.draft_text)
            if left:
                st.info(f"{left} placeholder(s) in [square brackets] still need your details.")
            else:
                st.info("No [placeholders] are left. Please still read the whole draft carefully.")

            st.download_button(
                "Download as TXT",
                data=st.session_state.draft_text.encode("utf-8-sig"),
                file_name="NyayamAI_refund_request_draft.txt",
                mime="text/plain",
            )
            try:
                st.download_button(
                    "Download as Word (DOCX)",
                    data=text_to_docx_bytes(st.session_state.draft_text),
                    file_name="NyayamAI_refund_request_draft.docx",
                    mime=DOCX_MIME,
                )
            except Exception as e:
                st.error(f"The Word file could not be created ({type(e).__name__}). The TXT download still works.")

with tab_help:
    st.subheader("Legal help")
    render_legal_aid_card()
    st.divider()
    st.markdown("**When to speak to a lawyer or legal aid centre (our general suggestion, not a legal rule)**")
    for line in WHEN_TO_GET_HELP:
        st.markdown(f"- {line}")

st.divider()
with st.expander("Safety checks log (for testing)"):
    st.write("Risk flags found in this case:", case["risk_flags"] or "none")
    st.write("Sentences the checker replaced with 'I cannot verify...':")
    st.json(st.session_state.blocked_log)

with st.expander("Start over"):
    st.write("This clears the current case, the conversation and any draft.")
    if st.button("Yes, clear everything and start a new case"):
        start_new_case()
        st.rerun()

st.caption(DISCLAIMER)