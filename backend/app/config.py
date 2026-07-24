import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/glitrai"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    app_base_url: str = ""

    class Config:
        env_file = ".env"

    @property
    def public_base_url(self) -> str:
        # Render injects RENDER_EXTERNAL_URL automatically for web services.
        return (
            self.app_base_url
            or os.environ.get("RENDER_EXTERNAL_URL", "")
            or "http://localhost:8000"
        )


settings = Settings()
