import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Reel Director API"
    app_version: str = "1.0.0"
    environment: str = os.getenv("ENVIRONMENT", "development")
    demo_mode: bool = False

    # Parallel Configuration
    parallel_api_key: str = os.getenv("PARALLEL_API_KEY", "")

    # Google Cloud Configuration
    google_cloud_project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    gcs_bucket_name: str = os.getenv("GCS_BUCKET_NAME", "")

    # Gemini Configuration
    gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    image_model_name: str = os.getenv("IMAGE_MODEL_NAME", "gemini-2.5-flash-image")
    use_vertex_ai: bool = os.getenv("USE_VERTEX_AI", "true").lower() in ("true", "1", "yes")

    # Veo Model Configuration
    veo_model_name: str = os.getenv("VEO_MODEL_NAME", "veo-3.1-fast-generate-001")

    # Server Configuration
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    media_delivery_mode: str = os.getenv(
        "MEDIA_DELIVERY_MODE",
        "signed" if os.getenv("ENVIRONMENT", "development").lower() == "production" else "proxy",
    )

    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        extra = "ignore"


settings = Settings()
