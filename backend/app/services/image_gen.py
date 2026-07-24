import random
from urllib.parse import quote

import httpx

BASE_URL = "https://image.pollinations.ai/prompt/{prompt}"


class ImageGenError(Exception):
    pass


def generate_image(prompt: str, reference_image_url: str | None = None) -> tuple[bytes, str]:
    """Generate an image via Pollinations.ai (free, keyless).

    If a publicly reachable reference_image_url is given, uses the
    image-to-image "kontext" model so the product photo informs the result.
    Falls back to plain text-to-image on any failure.
    """
    seed = random.randint(0, 2_000_000_000)
    encoded_prompt = quote(prompt[:1000])
    url = BASE_URL.format(prompt=encoded_prompt)
    params = {
        "width": 1024,
        "height": 1024,
        "seed": seed,
        "nologo": "true",
    }

    if reference_image_url:
        params["model"] = "kontext"
        params["image"] = reference_image_url
        try:
            return _fetch(url, params)
        except Exception:
            # Fall back to plain text-to-image if image-to-image fails
            params.pop("model", None)
            params.pop("image", None)

    return _fetch(url, params)


def _fetch(url: str, params: dict) -> tuple[bytes, str]:
    try:
        with httpx.Client(timeout=90, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            return resp.content, content_type
    except Exception as exc:  # noqa: BLE001
        raise ImageGenError(f"Pollinations image generation failed: {exc}") from exc
