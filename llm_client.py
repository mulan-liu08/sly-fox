"""
llm_client.py — Thin wrapper around the Gemini API (google-genai SDK).

Uses the NEW `google-genai` package (not the deprecated `google.generativeai`).
Install: pip install -q -U google-genai

For JSON calls we use response_mime_type="application/json" so the model is
constrained to emit valid, complete JSON — eliminates truncation/delimiter errors.
"""

from __future__ import annotations
import json
import re
import time
from typing import Any

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

# One client, reused for every call
_client = genai.Client(api_key=GEMINI_API_KEY)


# ─── JSON extraction helper (fallback for non-JSON-mode calls) ────────────────

def _extract_json(text: str) -> Any:
    """Pull JSON out of a response that may be wrapped in ```json fences."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if match:
            return json.loads(match.group(1))
    raise ValueError(f"Could not extract JSON from response:\n{text[:500]}")


# ─── Core call function ───────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    model_name: str,
    system_instruction: str | None = None,
    expect_json: bool = False,
    temperature: float = 0.9,
    max_output_tokens: int = 8192,   # raised — crime world state JSON needs room
    retries: int = 3,
    retry_delay: float = 10.0,
) -> str | Any:
    """
    Call a Gemini model and return the text (or parsed JSON) response.

    When expect_json=True we set response_mime_type="application/json", which
    forces the model to emit a complete, valid JSON object — no truncation.
    """
    config_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if expect_json:
        config_kwargs["response_mime_type"] = "application/json"

    generate_config = types.GenerateContentConfig(
        **config_kwargs,
        system_instruction=system_instruction or "",
    )

    for attempt in range(1, retries + 1):
        try:
            response = _client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=generate_config,
            )
            text = response.text.strip()
            if expect_json:
                return _extract_json(text)
            return text

        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Gemini call failed after {retries} attempts: {exc}"
                ) from exc
            print(f"  [LLM] attempt {attempt} failed ({exc}), retrying in {retry_delay}s…")
            time.sleep(retry_delay)
