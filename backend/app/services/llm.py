import httpx

from ..config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a prompt engineer for a product photography AI image generator. "
    "Given a product name and a short description, write a single vivid, concise "
    "image-generation prompt (max 60 words) that describes an appealing lifestyle "
    "or studio product shot. Focus on lighting, setting, composition, and materials. "
    "Reply with ONLY the prompt text, no preamble, no quotes."
)


class LLMError(Exception):
    pass


def generate_image_prompt(product_name: str, description: str) -> str:
    if not settings.groq_api_key:
        # No key configured: fall back to a deterministic template so the
        # pipeline still works end to end without an external dependency.
        return (
            f"Professional product photograph of {product_name}. {description} "
            "Soft natural lighting, clean minimal background, high detail, shallow depth of field."
        )

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Product name: {product_name}\nDescription: {description}",
            },
        ],
        "temperature": 0.7,
        # Reasoning models spend completion tokens on reasoning before emitting
        # any content, so a tight cap returns finish_reason="length" with an
        # empty message. The budget is generous; the prompt itself stays short.
        "max_tokens": 1024,
    }
    if _is_reasoning_model(settings.groq_model):
        payload["reasoning_effort"] = "low"

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(GROQ_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = (data["choices"][0]["message"].get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Groq prompt generation failed: {exc}") from exc

    if not content:
        # An empty completion is a failure, not a valid prompt - let the
        # caller fall back to its template instead of generating on "".
        raise LLMError("Groq returned an empty completion")

    return content


def _is_reasoning_model(model: str) -> bool:
    """Groq's reasoning families accept reasoning_effort; others reject it."""
    return model.startswith("openai/gpt-oss") or model.startswith("qwen/")
