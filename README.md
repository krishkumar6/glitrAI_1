# GlitrAI Mini Content Engine

Takes a product name + description (+ optional product photo), turns it into an
image-generation prompt via an LLM, generates a product image, and lets you track
the job and view the result.

## Stack

- **Backend**: FastAPI (Python), SQLAlchemy, PostgreSQL
- **LLM (prompt generation)**: [Groq](https://console.groq.com) (free tier, OpenAI-compatible chat API). If no `GROQ_API_KEY` is set, falls back to a deterministic template so the pipeline still runs end to end.
- **Image generation**: [Pollinations.ai](https://pollinations.ai) (free, keyless). Uses the `kontext` image-to-image model with the uploaded product photo as a reference when the service is publicly reachable; otherwise falls back to text-to-image.
- **Frontend**: single static HTML page (vanilla JS + fetch), served by the backend
- **Jobs**: persisted in Postgres (`pending` → `processing` → `completed`/`failed`), processed via FastAPI `BackgroundTasks`. Uploaded and generated images are stored as bytes in Postgres (not local disk), so nothing is lost when a free-tier instance spins down.

## API

- `POST /generate` — multipart form: `product_name`, `description`, optional `image` file. Returns `{id, status}`.
- `GET /jobs` — list of jobs (id, product_name, status, created_at).
- `GET /jobs/{id}` — job detail: status, generated prompt, `input_image_url`, `result_image_url`, error (if failed).
- `GET /jobs/{id}/image/input` / `GET /jobs/{id}/image/result` — raw image bytes.
- `GET /health` — health check.

## Run locally (Docker, recommended)

Requires Docker + Docker Compose.

```bash
cp .env.example .env
# optionally set GROQ_API_KEY in .env (get a free key at https://console.groq.com/keys)
docker compose up --build
```

Open http://localhost:8000

Without a `GROQ_API_KEY`, prompt generation uses a template fallback — the rest of
the pipeline (job tracking, image generation, frontend) works unchanged.

Note: the Pollinations `kontext` (image-to-image) path needs a **publicly reachable**
URL to fetch your uploaded reference image from, so locally it's skipped and falls
back to plain text-to-image. It's used automatically once deployed (see below).

## Run locally (without Docker)

Requires Python 3.11+ and a local Postgres instance.

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/glitrai
export GROQ_API_KEY=...           # optional
uvicorn app.main:app --reload
```

## Deploy to Render (free tier)

This repo includes a `render.yaml` Blueprint that provisions a free web service
(built from `backend/Dockerfile`) and a free Postgres database.

1. Push this repo to GitHub.
2. In Render, choose **New > Blueprint** and point it at the repo — it reads `render.yaml` automatically.
3. After the first deploy, set `GROQ_API_KEY` in the web service's Environment tab (get a free key at https://console.groq.com/keys). It's marked `sync: false` in the blueprint so Render will prompt for it rather than committing it.
4. Render auto-injects `RENDER_EXTERNAL_URL`, which the app uses as its public base URL — no manual config needed for the image-to-image reference path.

`DATABASE_URL` is wired automatically from the linked Render Postgres instance.

## Optional: ComfyUI backend (open-source image gen via Colab)

As an alternative to Pollinations, the service can call a self-hosted [ComfyUI](https://github.com/comfyanonymous/ComfyUI) instance running a **img2img + upscaler** workflow (reference product photo + text prompt in, upscaled generated image out).

### 1. Stand up ComfyUI on a free Colab GPU

Open [`comfyui/colab_setup.ipynb`](comfyui/colab_setup.ipynb) in Google Colab (upload it, or File > Upload notebook), set the runtime to a T4 GPU, and run every cell in order. It will:

- Install ComfyUI
- Download a base SD1.5 checkpoint and a RealESRGAN 4x upscale model
- Launch the ComfyUI server
- Expose it publicly via a free Cloudflare Tunnel (no signup) and print the public URL

The printed `https://*.trycloudflare.com` URL is your `COMFYUI_BASE_URL`. **It's ephemeral** — every time the Colab runtime restarts or the tunnel cell reruns, you get a new URL and need to update the setting below.

### 2. Point the backend at it

The workflow itself lives at [`comfyui/workflow_api.json`](comfyui/workflow_api.json) (also bundled into the backend at `backend/app/data/comfyui_workflow.json`) — a ComfyUI API-format graph:

`LoadImage` (reference photo) → `VAEEncode` → `KSampler` (img2img, `denoise: 0.55`, conditioned on the LLM-generated prompt) → `VAEDecode` → `UpscaleModelLoader` + `ImageUpscaleWithModel` (RealESRGAN 4x) → `SaveImage`.

To use it, set on the backend (`.env` locally, or Render's Environment tab):

```
IMAGE_BACKEND=comfyui
COMFYUI_BASE_URL=https://your-tunnel-url.trycloudflare.com
```

`IMAGE_BACKEND=comfyui` only takes effect for jobs that include an uploaded reference image (the workflow requires one for img2img). It automatically falls back to Pollinations if `COMFYUI_BASE_URL` is unset, unreachable, or the ComfyUI job errors out — so a stale Colab tunnel degrades gracefully instead of failing jobs.

The integration code is in [`backend/app/services/comfyui_client.py`](backend/app/services/comfyui_client.py): it uploads the reference image via `/upload/image`, injects the prompt and reference filename into the workflow graph, queues it via `/prompt`, polls `/history/{id}`, and fetches the final upscaled image via `/view`.

## Design notes

- **Why store images in Postgres instead of disk**: Render's free web service tier has an ephemeral filesystem — it's wiped whenever the instance spins down after inactivity and back up. Storing generated/uploaded image bytes as `LargeBinary` columns means jobs stay retrievable regardless of instance restarts, without needing external object storage (S3, etc.) for an MVP.
- **Why BackgroundTasks over a task queue**: scope here is a single free-tier instance with no need for cross-process job distribution, so FastAPI's built-in `BackgroundTasks` (thread-pooled) is sufficient without adding Redis/Celery.
- **Failure handling**: if the LLM call fails, a template prompt is used instead of failing the job. If image-to-image (with reference photo) fails, it retries as plain text-to-image before giving up. Only a genuine image-generation failure marks the job `failed`, with `error_message` populated.
