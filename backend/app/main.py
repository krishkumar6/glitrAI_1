import logging
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from . import crud
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .models import JobStatus
from .schemas import JobCreateResponse, JobDetail, JobListItem
from .services.image_gen import ImageGenError, generate_image
from .services.llm import LLMError, generate_image_prompt

logger = logging.getLogger("glitrai")
logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="GlitrAI Mini Content Engine")

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def image_urls(job_id: str, has_input: bool, has_result: bool) -> tuple[str | None, str | None]:
    input_url = f"/jobs/{job_id}/image/input" if has_input else None
    result_url = f"/jobs/{job_id}/image/result" if has_result else None
    return input_url, result_url


def process_job(job_id: str) -> None:
    db: Session = SessionLocal()
    try:
        job = crud.get_job(db, job_id)
        if job is None:
            return

        crud.set_status(db, job, JobStatus.processing)

        try:
            prompt = generate_image_prompt(job.product_name, job.description)
        except LLMError as exc:
            logger.warning("LLM failed for job %s: %s", job_id, exc)
            prompt = (
                f"Professional product photograph of {job.product_name}. "
                f"{job.description} Soft natural lighting, clean background, high detail."
            )

        reference_url = None
        if job.input_image and not settings.public_base_url.startswith("http://localhost"):
            reference_url = f"{settings.public_base_url}/jobs/{job_id}/image/input"

        try:
            image_bytes, content_type = generate_image(prompt, reference_url)
        except ImageGenError as exc:
            crud.fail_job(db, job, str(exc), generated_prompt=prompt)
            return

        crud.complete_job(db, job, prompt, image_bytes, content_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error processing job %s", job_id)
        job = crud.get_job(db, job_id)
        if job is not None:
            crud.fail_job(db, job, f"Unexpected error: {exc}")
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=JobCreateResponse)
async def generate(
    background_tasks: BackgroundTasks,
    product_name: str = Form(...),
    description: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if not product_name.strip() or not description.strip():
        raise HTTPException(status_code=400, detail="product_name and description are required")

    input_image_bytes = None
    input_image_content_type = None
    if image is not None:
        input_image_bytes = await image.read()
        input_image_content_type = image.content_type or "application/octet-stream"

    job = crud.create_job(
        db, product_name.strip(), description.strip(), input_image_bytes, input_image_content_type
    )
    background_tasks.add_task(process_job, job.id)
    return JobCreateResponse(id=job.id, status=job.status)


@app.get("/jobs", response_model=list[JobListItem])
def get_jobs(db: Session = Depends(get_db)):
    jobs = crud.list_jobs(db)
    return [
        JobListItem(
            id=j.id, product_name=j.product_name, status=j.status, created_at=j.created_at
        )
        for j in jobs
    ]


@app.get("/jobs/{job_id}", response_model=JobDetail)
def get_job_detail(job_id: str, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    input_url, result_url = image_urls(
        job_id, job.input_image is not None, job.result_image is not None
    )
    return JobDetail(
        id=job.id,
        product_name=job.product_name,
        description=job.description,
        status=job.status,
        generated_prompt=job.generated_prompt,
        input_image_url=input_url,
        result_image_url=result_url,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@app.get("/jobs/{job_id}/image/input")
def get_job_input_image(job_id: str, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None or job.input_image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=job.input_image, media_type=job.input_image_content_type)


@app.get("/jobs/{job_id}/image/result")
def get_job_result_image(job_id: str, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None or job.result_image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=job.result_image, media_type=job.result_image_content_type)


@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")
