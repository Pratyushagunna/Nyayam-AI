"""core/llm.py - the ONLY file that knows which AI provider we use.

Other files call:
    generate_response(messages, system_prompt)  -> text
    generate_json(messages, system_prompt, required_keys=[...]) -> dict

messages is a list like:
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
"""
import json
import re
import os
import time

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_ATTEMPTS = 3


class LLMError(Exception):
    """Raised with a user-friendly message when an AI call fails."""


def _get_setting(name, default=None):
    """Read a setting from environment variables (.env) or Streamlit secrets.
    Never prints or logs the value."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def _call_gemini(messages, system_prompt, json_mode, temperature, model):
    from google import genai
    from google.genai import errors, types

    api_key = _get_setting("GEMINI_API_KEY")
    if not api_key or "paste_your" in api_key:
        raise LLMError("The AI service is not configured: GEMINI_API_KEY is missing.")
    model = model or _get_setting("GEMINI_MODEL", DEFAULT_MODEL)

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in messages
    ]
    config_kwargs = {"system_instruction": system_prompt}
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    config = types.GenerateContentConfig(**config_kwargs)

    client = genai.Client(api_key=api_key)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=config
            )
            text = response.text
            if not text:
                raise LLMError(
                    "The AI returned an empty answer (it may have been blocked). "
                    "Please rephrase and try again."
                )
            return text
        except LLMError:
            raise
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code in (401, 403):
                raise LLMError(
                    "The AI service rejected the API key. Check GEMINI_API_KEY."
                )
            if code == 404:
                raise LLMError(
                    f"The model '{model}' was not found or is no longer available. "
                    "Check GEMINI_MODEL."
                )
            if code == 400:
                raise LLMError(f"The AI request was invalid: {str(e)[:300]}")
            if code not in (429, 500, 502, 503, 504):
                raise LLMError(f"AI service error ({code}): {str(e)[:300]}")
            # 429 / 5xx: temporary, fall through to retry
        except Exception:
            # network problems etc. are also worth a retry
            pass

        if attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)  # waits 2s, then 4s

    raise LLMError(
        "The AI service is busy or unreachable (rate limit or network). "
        "Please wait a minute and try again."
    )


# To support another provider later, write _call_xyz with the same arguments
# and add it here.
_PROVIDERS = {"gemini": _call_gemini}


def generate_response(messages, system_prompt, json_mode=False, temperature=None, model=None):
    """Send a conversation to the AI and return its text answer."""
    if not messages:
        raise LLMError("No messages were provided to the AI.")
    provider = _get_setting("LLM_PROVIDER", DEFAULT_PROVIDER).lower()
    caller = _PROVIDERS.get(provider)
    if caller is None:
        raise LLMError(f"Unknown LLM_PROVIDER '{provider}'.")
    return caller(messages, system_prompt, json_mode, temperature, model)


def _parse_json(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    return json.loads(cleaned)


def generate_json(messages, system_prompt, required_keys=None, **kwargs):
    """Like generate_response, but returns a validated dict.

    If the output is not valid JSON (or lacks required keys) we ask the model
    ONCE to fix the structure, explicitly forbidding new facts."""
    raw = generate_response(messages, system_prompt, json_mode=True, **kwargs)
    for attempt in range(2):
        try:
            data = _parse_json(raw)
            if not isinstance(data, dict):
                raise ValueError("The top-level JSON value must be an object.")
            missing = [k for k in (required_keys or []) if k not in data]
            if missing:
                raise ValueError(f"Missing required keys: {missing}")
            return data
        except ValueError as problem:
            if attempt == 1:
                raise LLMError(
                    "The AI did not return usable structured data. Please try again."
                )
            repair = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was not valid. Problem: {problem}. "
                        "Return the corrected JSON object only. Fix the structure "
                        "only; do not add, invent or change any facts."
                    ),
                },
            ]
            raw = generate_response(repair, system_prompt, json_mode=True, **kwargs)


if __name__ == "__main__":
    # Self-test: run with   python -m core.llm
    print("Test 1: plain text")
    print(" ", generate_response(
        [{"role": "user", "content": "Say hello in five words."}],
        "You are a concise assistant.",
    ))

    print("\nTest 2: structured JSON")
    print(" ", generate_json(
        [{"role": "user", "content": "My flat is in Pune and my deposit was 20000 rupees."}],
        'Extract facts. Return JSON with keys "city" and "amount". Use null if unknown.',
        required_keys=["city", "amount"],
    ))

    print("\nTest 3: a wrong model name should give a friendly error")
    try:
        generate_response(
            [{"role": "user", "content": "hi"}], "Be brief.", model="not-a-real-model"
        )
        print("  UNEXPECTED: no error was raised")
    except LLMError as e:
        print("  Got friendly error:", e)