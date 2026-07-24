import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.pending, nullable=False
    )
    generated_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    input_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    input_image_content_type: Mapped[str | None] = mapped_column(String, nullable=True)

    result_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    result_image_content_type: Mapped[str | None] = mapped_column(String, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
