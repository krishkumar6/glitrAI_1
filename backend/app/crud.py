from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Job, JobStatus


def create_job(
    db: Session,
    product_name: str,
    description: str,
    input_image: bytes | None,
    input_image_content_type: str | None,
) -> Job:
    job = Job(
        product_name=product_name,
        description=description,
        input_image=input_image,
        input_image_content_type=input_image_content_type,
        status=JobStatus.pending,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


def list_jobs(db: Session) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def set_status(db: Session, job: Job, status: JobStatus) -> None:
    job.status = status
    db.add(job)
    db.commit()


def complete_job(
    db: Session, job: Job, generated_prompt: str, result_image: bytes, result_content_type: str
) -> None:
    job.generated_prompt = generated_prompt
    job.result_image = result_image
    job.result_image_content_type = result_content_type
    job.status = JobStatus.completed
    db.add(job)
    db.commit()


def fail_job(db: Session, job: Job, error_message: str, generated_prompt: str | None = None) -> None:
    job.status = JobStatus.failed
    job.error_message = error_message
    if generated_prompt:
        job.generated_prompt = generated_prompt
    db.add(job)
    db.commit()
