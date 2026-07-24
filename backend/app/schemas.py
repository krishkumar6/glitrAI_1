from datetime import datetime

from pydantic import BaseModel

from .models import JobStatus


class JobCreateResponse(BaseModel):
    id: str
    status: JobStatus


class JobListItem(BaseModel):
    id: str
    product_name: str
    status: JobStatus
    created_at: datetime


class JobDetail(BaseModel):
    id: str
    product_name: str
    description: str
    status: JobStatus
    generated_prompt: str | None
    input_image_url: str | None
    result_image_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
