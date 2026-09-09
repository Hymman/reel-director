import time
import asyncio
from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from app.config import settings

class VeoService:
    BASE_NEGATIVE_CONSTRAINTS = (
        "legible text",
        "subtitles",
        "watermarks",
        "brand logos",
        "distorted screens",
        "malformed hands",
        "duplicate people",
        "flicker",
        "jitter",
        "warped objects",
        "letterboxing",
        "black bars",
        "cinematic matte",
        "uncanny facial expression",
        "unnatural eye proportions",
    )
    def __init__(self):
        self.model_name = settings.veo_model_name
        self.bucket = settings.gcs_bucket_name
        try:
            if settings.use_vertex_ai:
                self.client = genai.Client(
                    vertexai=True,
                    project=settings.google_cloud_project,
                    location=settings.google_cloud_location
                )
            else:
                self.client = genai.Client()
        except Exception as e:
            print(f"WARNING: Failed to initialize Google GenAI Client: {e}")
            self.client = None

    @staticmethod
    def _clean_negative_constraint(value: str) -> str:
        cleaned = (value or "").strip().strip(".,;:")
        lowered = cleaned.lower()
        for prefix in ("do not include ", "do not show ", "don't include ", "don't show ", "without ", "no "):
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        return cleaned

    def compile_negative_prompt(self, shot: Any) -> str:
        constraints = list(self.BASE_NEGATIVE_CONSTRAINTS)
        constraints.extend(getattr(shot, "negative_constraints", None) or [])
        unique = []
        seen = set()
        for value in constraints:
            cleaned = self._clean_negative_constraint(str(value))
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                unique.append(cleaned)
        return ", ".join(unique)

    @staticmethod
    def compile_prompt(shot: Any, audio_mode: str = "native_ambient") -> str:
        """Compile only internal English production fields for Veo.

        User-visible `visual`, `action`, `camera`, and `caption` fields can be
        localized and are intentionally never appended here.
        """
        visual_prompt = (getattr(shot, "veo_prompt_intent", "") or "").strip().rstrip(".")
        if not visual_prompt:
            raise ValueError("Shot is missing its internal Veo production prompt.")

        # Generated phone interfaces are not acceptable product proof. When a
        # shot already declares UI/text/screen constraints, keep the device
        # display out of view and communicate use through the person's action.
        # Exact product UI is added later by deterministic branded finishing.
        constraint_text = " ".join(
            str(value).casefold()
            for value in (getattr(shot, "negative_constraints", None) or [])
        )
        phone_scene = any(token in visual_prompt.casefold() for token in ("phone", "smartphone", "screen"))
        protected_ui = any(token in constraint_text for token in ("app ui", "legible text", "distorted screen"))
        if phone_scene and protected_ui:
            visual_prompt = (
                f"{visual_prompt}. Keep every phone display dark, oblique, out of focus, or facing away from "
                "the camera. Convey recording through natural human action only; never show a bright blank "
                "screen, fake interface, keyboard, icons, or readable text"
            )
        visual_prompt = (
            f"{visual_prompt}. Compose native full-frame vertical 9:16 imagery that fills every pixel from "
            "edge to edge; never add letterboxing, black bars, a cinematic matte, or an inset landscape frame"
        )
        if audio_mode == "silent":
            return f"{visual_prompt}. Audio: silent output; no dialogue, narration, or music lyrics."
        audio_prompt = (getattr(shot, "veo_audio_prompt", "") or "").strip().rstrip(".")
        if not audio_prompt:
            audio_prompt = "Natural synchronized environmental ambience and realistic action sound effects"
        return f"{visual_prompt}. Audio: {audio_prompt}."

    def start_generation(
        self,
        shot: Any,
        audio_mode: str = "native_ambient",
        first_frame_path: Optional[str] = None,
        last_frame_path: Optional[str] = None,
    ) -> str:
        """Starts a Veo generation job and returns the operation name."""
        if not self.client:
            raise ValueError("GenAI client not initialized.")
        
        combined_prompt = self.compile_prompt(shot, audio_mode=audio_mode)
        neg_prompt = self.compile_negative_prompt(shot)

        # Fix: Duration Contract - send correct duration_seconds to Veo (Fix 1)
        duration_sec = int(shot.duration_seconds) if hasattr(shot, 'duration_seconds') and shot.duration_seconds else 6

        source = types.GenerateVideosSource(prompt=combined_prompt)
        if first_frame_path:
            source.image = types.Image.from_file(location=first_frame_path)

        config = types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=duration_sec,
            negative_prompt=neg_prompt,
            person_generation="ALLOW_ADULT", # Typical policy requirement
            generate_audio=audio_mode != "silent",
            output_gcs_uri=f"gs://{self.bucket}/generated/{int(time.time())}/"
        )
        if last_frame_path:
            config.last_frame = types.Image.from_file(location=last_frame_path)

        operation = self.client.models.generate_videos(
            model=self.model_name,
            source=source,
            config=config,
        )
        return operation.name

    def check_operation(self, operation_name: str) -> Dict[str, Any]:
        """Checks the status of a long-running operation."""
        op = types.GenerateVideosOperation(name=operation_name)
        op = self.client.operations.get(op)
        
        status = "queued"
        gcs_uri = None
        error = None
        
        if op.done:
            if op.error:
                status = "failed"
                error = op.error.message if hasattr(op.error, 'message') else str(op.error)
            else:
                status = "completed"
                # Extract URI
                try:
                    # In google-genai, op.result might be a dict or a specific object depending on the endpoint.
                    # Based on help(client.models.generate_videos):
                    # operation.result.generated_videos[0].video.uri
                    gcs_uri = op.result.generated_videos[0].video.uri
                except Exception as e:
                    print(f"Error parsing Veo result: {e}")
                    status = "failed"
                    error = f"Failed to extract URI: {e}"
        else:
            status = "generating"
            
        return {
            "status": status,
            "gcs_uri": gcs_uri,
            "error": error
        }

veo_service = VeoService()
