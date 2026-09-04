import json
import time

import httpx

from backend.config import FEATHERLESS_API_KEY, FEATHERLESS_MODEL, FEATHERLESS_URL


def chat_completion(messages, max_tokens=1400, temperature=0.1):
    if not FEATHERLESS_API_KEY:
        raise RuntimeError("FEATHERLESS_API_KEY is not configured")

    payload = {
        "model": FEATHERLESS_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    last_error = None
    for attempt in range(3):
        try:
            response = httpx.post(
                FEATHERLESS_URL,
                headers={
                    "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=90,
            )
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Featherless request failed: {last_error}")


def parse_json_content(response: dict) -> dict:
    message = response.get("choices", [{}])[0].get("message", {})
    content = (message.get("content") or "").strip()
    if not content:
        raise ValueError("Featherless returned no final content")

    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(content[start : end + 1])
