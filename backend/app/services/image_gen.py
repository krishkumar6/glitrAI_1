import logging
import random
import threading
import time
from urllib.parse import quote

import httpx

BASE_URL = "https://image.pollinations.ai/prompt/{prompt}"

# Pollinations is a free shared service with two failure modes worth handling:
#   - 5xx ("Queue full" upstream) and empty 200 bodies: transient, retry.
#   - 429: the keyless tier tolerates roughly one in-flight request, so
#     concurrent jobs rate-limit each other.
# Hence both a retry loop and a process-wide lock that serializes calls.
MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 20
REQUEST_TIMEOUT_SECONDS = 120

# Render's free tier runs a single instance and FastAPI BackgroundTasks run in
# its threadpool, so a process-level lock is enough to serialize generation.
_generation_lock = threading.Lock()

logger = logging.getLogger("glitrai")


class ImageGenError(Exception):
    pass


class _RetryableError(ImageGenError):
    """A failure that is worth retrying (rate limit, upstream 5xx, bad body)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def generate_image(prompt: str, reference_image_url: str | None = None) -> tuple[bytes, str]:
    """Generate an image via Pollinations.ai (free, keyless).

    If a publicly reachable reference_image_url is given, uses the
    image-to-image "kontext" model so the product photo informs the result.
    Falls back to plain text-to-image on any failure.
    """
    encoded_prompt = quote(prompt[:1000])
    url = BASE_URL.format(prompt=encoded_prompt)

    def base_params() -> dict:
        return {
            "width": 1024,
            "height": 1024,
            "seed": random.randint(0, 2_000_000_000),
            "nologo": "true",
        }

    if reference_image_url:
        params = base_params()
        params["model"] = "kontext"
        params["image"] = reference_image_url
        try:
            # Single attempt: when kontext is unavailable (it now requires a
            # Pollinations account) it fails fast and deterministically, so
            # retrying it would only delay the text-to-image fallback.
            return _locked_fetch(url, params)
        except ImageGenError as exc:
            logger.warning("Image-to-image failed, falling back to text-to-image: %s", exc)

    return _fetch_with_retries(url, base_params())


def _fetch_with_retries(url: str, params: dict) -> tuple[bytes, str]:
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # A fresh seed per attempt avoids re-serving a cached failure.
        params = {**params, "seed": random.randint(0, 2_000_000_000)}
        try:
            return _locked_fetch(url, params)
        except _RetryableError as exc:
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            delay = exc.retry_after if exc.retry_after is not None else RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "Image generation attempt %s/%s failed, retrying in %ss: %s",
                attempt,
                MAX_ATTEMPTS,
                round(delay),
                exc,
            )
            time.sleep(delay)
        except ImageGenError:
            # Not retryable (e.g. a 4xx that isn't a rate limit) - fail now.
            raise

    raise ImageGenError(f"Image generation failed after {MAX_ATTEMPTS} attempts: {last_error}")


def _locked_fetch(url: str, params: dict) -> tuple[bytes, str]:
    """Serialize outbound generation calls; the keyless tier rejects concurrency."""
    with _generation_lock:
        return _fetch(url, params)


def _fetch(url: str, params: dict) -> tuple[bytes, str]:
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = client.get(url, params=params)
    except Exception as exc:  # noqa: BLE001
        raise _RetryableError(f"Pollinations request failed: {exc}") from exc

    if resp.status_code == 429:
        raise _RetryableError(
            "Pollinations rate limit (429)", retry_after=_retry_after_seconds(resp)
        )
    if resp.status_code >= 500:
        raise _RetryableError(f"Pollinations server error ({resp.status_code})")
    if resp.status_code >= 400:
        raise ImageGenError(
            f"Pollinations rejected the request ({resp.status_code}): {resp.text[:200]}"
        )

    content_type = resp.headers.get("content-type", "image/jpeg")

    # Pollinations occasionally answers 200 with an empty or non-image body;
    # treat that as retryable rather than saving it as a result.
    if not content_type.startswith("image/"):
        raise _RetryableError(f"Pollinations returned non-image content-type: {content_type}")
    if len(resp.content) < 1024:
        raise _RetryableError(
            f"Pollinations returned an empty/truncated image ({len(resp.content)} bytes)"
        )

    return resp.content, content_type


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        # Cap it so a hostile/odd header can't stall a job indefinitely.
        return min(float(raw), 120.0)
    except ValueError:
        return None
