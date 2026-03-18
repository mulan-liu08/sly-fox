from __future__ import annotations
import json
import re
import time
from typing import Any

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)

def _extract_json(text: str) -> Any:
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

def call_llm(
    prompt: str,
    model_name: str,
    system_instruction: str | None = None,
    expect_json: bool = False,
    temperature: float = 0.9,
    max_output_tokens: int = 8192,
    retries: int = 3,
    retry_delay: float = 2.0,
) -> str | Any:
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
        time.sleep(2)
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
