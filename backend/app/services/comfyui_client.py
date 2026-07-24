import copy
import json
import mimetypes
import random
import time
import uuid
from pathlib import Path

import httpx

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / "data" / "comfyui_workflow.json"

POSITIVE_PROMPT_NODE = "2"
REFERENCE_IMAGE_NODE = "4"
SAMPLER_NODE = "6"
SAVE_IMAGE_NODE = "10"

POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 240


class ComfyUIError(Exception):
    pass


def _load_workflow_template() -> dict:
    with open(WORKFLOW_PATH) as f:
        return json.load(f)


def _upload_reference_image(base_url: str, image_bytes: bytes, content_type: str) -> str:
    ext = mimetypes.guess_extension(content_type) or ".png"
    filename = f"glitrai_ref_{uuid.uuid4().hex}{ext}"
    files = {"image": (filename, image_bytes, content_type)}
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{base_url}/upload/image", files=files)
        resp.raise_for_status()
        data = resp.json()
        return data["name"]


def _queue_prompt(base_url: str, graph: dict, client_id: str) -> str:
    payload = {"prompt": graph, "client_id": client_id}
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{base_url}/prompt", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ComfyUIError(f"ComfyUI rejected the workflow: {data['error']}")
        return data["prompt_id"]


def _wait_for_result(base_url: str, prompt_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    with httpx.Client(timeout=30) as client:
        while time.monotonic() < deadline:
            resp = client.get(f"{base_url}/history/{prompt_id}")
            resp.raise_for_status()
            history = resp.json()
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyUIError(f"ComfyUI job failed: {status}")
                outputs = entry.get("outputs", {})
                if SAVE_IMAGE_NODE in outputs:
                    return outputs[SAVE_IMAGE_NODE]
            time.sleep(POLL_INTERVAL_SECONDS)
    raise ComfyUIError(f"Timed out waiting for ComfyUI job {prompt_id} after {POLL_TIMEOUT_SECONDS}s")


def _fetch_image(base_url: str, filename: str, subfolder: str, image_type: str) -> tuple[bytes, str]:
    params = {"filename": filename, "subfolder": subfolder, "type": image_type}
    with httpx.Client(timeout=60) as client:
        resp = client.get(f"{base_url}/view", params=params)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/png")
        return resp.content, content_type


def generate_image(
    base_url: str,
    prompt_text: str,
    reference_image_bytes: bytes,
    reference_image_content_type: str,
) -> tuple[bytes, str]:
    """Run the bundled img2img + upscaler workflow against a ComfyUI instance.

    Uploads the product reference image, injects the LLM-generated prompt,
    queues the workflow, polls until done, and returns the upscaled result.
    """
    base_url = base_url.rstrip("/")

    try:
        uploaded_filename = _upload_reference_image(
            base_url, reference_image_bytes, reference_image_content_type
        )

        graph = copy.deepcopy(_load_workflow_template())
        graph[POSITIVE_PROMPT_NODE]["inputs"]["text"] = prompt_text
        graph[REFERENCE_IMAGE_NODE]["inputs"]["image"] = uploaded_filename
        graph[SAMPLER_NODE]["inputs"]["seed"] = random.randint(0, 2_000_000_000)

        client_id = str(uuid.uuid4())
        prompt_id = _queue_prompt(base_url, graph, client_id)
        output = _wait_for_result(base_url, prompt_id)

        images = output.get("images", [])
        if not images:
            raise ComfyUIError(f"ComfyUI job {prompt_id} completed with no output images")

        image_info = images[0]
        return _fetch_image(
            base_url,
            image_info["filename"],
            image_info.get("subfolder", ""),
            image_info.get("type", "output"),
        )
    except ComfyUIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ComfyUIError(f"ComfyUI request failed: {exc}") from exc
