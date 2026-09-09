from types import SimpleNamespace

import pytest

from app.services.image_service import ImageService


def _gemini_response(data=b"gemini-image"):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data))
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


@pytest.mark.anyio
async def test_gemini_image_uses_native_four_by_five(monkeypatch):
    service = object.__new__(ImageService)
    calls = []
    service.model_name = "gemini-2.5-flash-image"
    service.client = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **kwargs: calls.append(kwargs) or _gemini_response(),
    ))

    result = await service.generate_background("premium background")

    assert result == b"gemini-image"
    assert calls[0]["model"] == "gemini-2.5-flash-image"
    assert calls[0]["config"].image_config.aspect_ratio == "4:5"


@pytest.mark.anyio
async def test_unavailable_imagen_falls_back_to_real_gemini_image(monkeypatch):
    service = object.__new__(ImageService)
    service.model_name = "imagen-4.0-generate-001"
    calls = []

    def unavailable_imagen(**kwargs):
        assert kwargs["config"].aspect_ratio == "3:4"
        raise RuntimeError("publisher model unavailable")

    service.client = SimpleNamespace(models=SimpleNamespace(
        generate_images=unavailable_imagen,
        generate_content=lambda **kwargs: calls.append(kwargs) or _gemini_response(b"fallback-image"),
    ))

    result = await service.generate_background("premium background")

    assert result == b"fallback-image"
    assert calls[0]["model"] == "gemini-2.5-flash-image"


@pytest.mark.anyio
async def test_transient_quota_failure_retries_then_succeeds(monkeypatch):
    service = object.__new__(ImageService)
    service.model_name = "gemini-2.5-flash-image"
    service.TRANSIENT_RETRY_DELAYS_SECONDS = (0, 0)
    attempts = []

    def flaky_generation(**kwargs):
        attempts.append(kwargs)
        if len(attempts) < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return _gemini_response(b"recovered-image")

    service.client = SimpleNamespace(models=SimpleNamespace(generate_content=flaky_generation))
    monkeypatch.setattr("app.services.image_service.time.sleep", lambda _: None)

    result = await service.generate_background("premium background")

    assert result == b"recovered-image"
    assert len(attempts) == 3
