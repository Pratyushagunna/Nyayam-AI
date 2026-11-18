# Nyayam AI

**Understand your rights. Know your next step.**

Nyayam AI is a prototype AI assistant that helps ordinary people in India organise a **residential rental security deposit dispute**. It turns an informal description into a structured case, an evidence checklist, plain-language guidance and an editable refund-request draft.

> Nyayam AI is **not a lawyer** and gives **general information only**, not legal advice. It can make mistakes. Built as a prototype for a Kuku Technologies assignment.

**Live app:** `PASTE-YOUR-STREAMLIT-URL-HERE` (it may take a moment to wake up if it has been idle)

## What it does
- **Conversational intake:** asks one or two follow-up questions at a time and builds a structured case. Python code, not the AI, decides what is still missing.
- **Case summary and timeline:** dates stay in the user's own words and nothing is invented.
- **Evidence checklist:** the user marks each document as available or not. The AI cannot tick documents.
- **Guidance page:** built by plain Python from the case and a verified-sources file. No AI writes it. Each part is labelled (from you, practical suggestion, verified source, not verified).
- **Refund-request draft:** built by plain Python, editable, downloadable as TXT or DOCX. Unknown details stay as `[placeholders]`. Nothing is sent anywhere.
- **Safety layer:** keyword rules detect court notices, eviction or lock-out threats, legal notices, police involvement and threats of violence, and replace the AI's reply with a fixed careful message. A checker also replaces sentences that look like unverified legal claims. Neither is perfect.

## Legal sources
Only information listed in `knowledge/legal_sources.json` is treated as verified: NALSA legal aid information, and the rent-control Acts of **Telangana** and **Maharashtra** (text copied by the developer from official copies). For any other state the app says the rules are not verified. See `could_not_verify_general` in that file for what we could not confirm.

## Run it locally (Windows)
Requires Python 3.12 and Git.
```
git clone https://github.com/YOUR-USERNAME/Nyayam-AI.git
cd Nyayam-AI
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Create a file named `.env` in the project folder (never upload it):
```
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3.5-flash-lite
```
Then run:
```
streamlit run app.py
```

## Offline self-tests (no AI key needed)
```
python -m core.legal_guardrails
python -m core.guidance
python -m core.document_generator
```

## Known limitations
- Only residential rental security deposit disputes; only Telangana and Maharashtra have verified legal text, and even there we found no official provision on refunding a deposit.
- The AI can still state something false in chat that matches none of our patterns.
- Free-tier model limits and the model name can change.
- Not tested with real users. Use fictional details when trying it.

## Privacy
Text typed in the chat is sent to Google's Gemini API. Do not enter phone numbers, Aadhaar or PAN, or bank account numbers.