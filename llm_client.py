"""
llm_client.py — Thin wrapper around the Gemini API (google-genai SDK).

All LLM calls go through here so we can easily swap models or add
retry/logging in one place.
"""

from __future__ import annotations
import json
import re
import time
from typing import Any

import google.generativeai as genai

from config import GEMINI_API_KEY

# Configure once at import time
genai.configure(api_key=GEMINI_API_KEY)

# ─── JSON extraction helper ───────────────────────────────────────────────────

def _extract_json(text: str) -> Any:
    """Pull JSON out of a Gemini response that may be wrapped in ```json fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences and try again
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: find the first { ... } or [ ... ] block
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
    max_output_tokens: int = 4096,
    retries: int = 3,
    retry_delay: float = 2.0,
) -> str | Any:
    """
    Call a Gemini model and return the text response.

    Parameters
    ----------
    prompt            : The user-turn prompt.
    model_name        : Which Gemini model to use (from config.py).
    system_instruction: Optional system/developer prompt.
    expect_json       : If True, parse and return the JSON object from the reply.
    temperature       : Sampling temperature (higher = more creative).
    max_output_tokens : Token budget for the response.
    retries           : How many times to retry on failure.
    retry_delay       : Seconds to wait between retries.

    Returns
    -------
    str   if expect_json is False
    dict/list if expect_json is True
    """
    generation_config = genai.types.GenerationConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    kwargs: dict[str, Any] = {"generation_config": generation_config}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction

    model = genai.GenerativeModel(model_name, **kwargs)

    for attempt in range(1, retries + 1):
        try:
            response = model.generate_content(prompt)
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
