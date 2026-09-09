import asyncio
import time

from google import genai
from google.genai import types

from app.config import settings


class ImageService:
    TRANSIENT_RETRY_DELAYS_SECONDS = (4, 12, 30)
    def __init__(self):
        try:
            if settings.use_vertex_ai:
                self.client = genai.Client(
                    vertexai=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location,
                )
            else:
                self.client = genai.Client()
        except Exception as exc:
            print(f"WARNING: Failed to initialize image client: {exc}")
            self.client = None
        self.model_name = settings.image_model_name

    def _generate_with_gemini_image(self, prompt: str) -> bytes:
        """Generate a native 4:5 background with the GA Gemini image endpoint."""
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.IMAGE],
                image_config=types.ImageConfig(aspect_ratio="4:5"),
            ),
        )
        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline_data = getattr(part, "inline_data", None)
                if inline_data and inline_data.data:
                    return bytes(inline_data.data)
        raise RuntimeError("Gemini image generation returned no image")

    def _generate_with_imagen(self, prompt: str) -> bytes:
        # Imagen supports 3:4 rather than 4:5. Deterministic finishing performs
        # the final center crop into the 1080x1350 feed contract.
        response = self.client.models.generate_images(
            model=self.model_name,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="3:4",
                output_mime_type="image/png",
                include_rai_reason=True,
            ),
        )
        if not response.generated_images:
            raise RuntimeError("Imagen generation returned no image")
        return response.generated_images[0].image.image_bytes

    async def generate_background(self, prompt: str) -> bytes:
        if not self.client:
            raise ValueError("Image generation client is not initialized")

        def generate_once():
            if self.model_name.startswith("gemini-"):
                return self._generate_with_gemini_image(prompt)
            try:
                return self._generate_with_imagen(prompt)
            except Exception as exc:
                # Project/region availability differs for Imagen publisher
                # endpoints. Fall back to the generally available Gemini image
                # endpoint, while preserving a real provider-backed result.
                print(f"WARNING: {self.model_name} unavailable; using gemini-2.5-flash-image: {exc}")
                return self._generate_with_gemini_image(prompt)

        def generate_with_retry():
            for attempt in range(len(self.TRANSIENT_RETRY_DELAYS_SECONDS) + 1):
                try:
                    return generate_once()
                except Exception as exc:
                    message = str(exc).casefold()
                    transient = any(token in message for token in (
                        "429",
                        "resource_exhausted",
                        "resource exhausted",
                        "503",
                        "service_unavailable",
                        "service unavailable",
                        "temporarily unavailable",
                    ))
                    if not transient or attempt >= len(self.TRANSIENT_RETRY_DELAYS_SECONDS):
                        raise
                    delay = self.TRANSIENT_RETRY_DELAYS_SECONDS[attempt]
                    print(f"WARNING: transient image provider failure; retrying in {delay}s: {exc}")
                    time.sleep(delay)

        return await asyncio.to_thread(generate_with_retry)


image_service = ImageService()
