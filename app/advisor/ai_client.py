
"""AI integration for Anthropic, OpenAI, and Google Gemini."""
import json
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
}


class AIError(Exception):
    """Raised when an external AI request fails."""


def generate_ai_reply(config, system_prompt, user_prompt, timeout=30):
    key = config.get("AI_API_KEY")
    if not key:
        raise AIError("AI_API_KEY is missing from the application configuration.")

    provider = (config.get("AI_PROVIDER") or "anthropic").strip().lower()
    model = config.get("AI_MODEL") or DEFAULT_MODELS.get(provider)

    if not model:
        raise AIError(f"Unsupported AI provider: {provider}")

    if provider == "gemini":
        base_url = (
            config.get("AI_BASE_URL")
            or "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")
        encoded_model = urllib.parse.quote(model, safe=".-_")
        url = f"{base_url}/models/{encoded_model}:generateContent"

        headers = {
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        }
        body = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 700,
                "temperature": 0.4,
            },
        }

    elif provider == "anthropic":
        url = config.get("AI_BASE_URL") or "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 700,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

    elif provider == "openai":
        url = config.get("AI_BASE_URL") or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

    else:
        raise AIError(f"Unsupported AI provider: {provider}")

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as exc:
        # Show the provider's error without ever printing the API key.
        try:
            detail = exc.read().decode("utf-8", errors="replace")
            detail_data = json.loads(detail)
            detail = (
                detail_data.get("error", {}).get("message")
                or detail_data.get("message")
                or f"HTTP {exc.code}"
            )
        except (ValueError, AttributeError):
            detail = f"HTTP {exc.code}"

        raise AIError(f"{provider} API returned HTTP {exc.code}: {detail}") from exc

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIError(f"Could not reach the {provider} API: {exc}") from exc

    try:
        if provider == "gemini":
            candidates = payload.get("candidates", [])
            if not candidates:
                feedback = payload.get("promptFeedback", {})
                reason = feedback.get("blockReason", "No response candidate returned")
                raise AIError(f"Gemini did not return a response: {reason}")

            parts = candidates[0].get("content", {}).get("parts", [])
            reply = "".join(part.get("text", "") for part in parts)

        elif provider == "anthropic":
            reply = "".join(
                item.get("text", "")
                for item in payload["content"]
                if item.get("type") == "text"
            )

        else:
            reply = payload["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError) as exc:
        raise AIError(f"Unexpected response from {provider}.") from exc

    reply = (reply or "").strip()
    if not reply:
        raise AIError(f"The {provider} API returned an empty response.")

    return reply
