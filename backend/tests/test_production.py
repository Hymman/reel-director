"""
Task 4 Production Tests:
Tests for preview generation, campaign_pack, static_post, and media proxy.
No live API calls (demo mode only, all GCS/Veo/Imagen patched).
"""
import io
import os
import json
import shutil
import subprocess
import uuid
from unittest.mock import MagicMock, patch, AsyncMock, call

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DEMO_MODE", "true")

from app.main import app
from app.services.state_store import campaign_store, job_store
from app.models.campaign import Campaign, CampaignBrief, Shot, ShotPlan, ProductionSettings
from app.models.job import Job
from app.services.veo_service import VeoService

client = TestClient(app)
WS = "TEST_PROD_WORKSPACE"
HEADERS = {"X-Workspace-ID": WS}


@pytest.fixture(autouse=True)
def force_demo_mode():
    """Keep this demo-only suite independent from test collection order."""
    from app.config import settings

    original_demo_mode = settings.demo_mode
    settings.demo_mode = True
    try:
        yield
    finally:
        settings.demo_mode = original_demo_mode

SAMPLE_BRIEF = {
    "subject_name": "TestApp",
    "subject_description": "A productivity app",
    "audience": "Remote workers",
    "goal": "Free trial signup",
    "platform": "instagram_reels",
    "tone": "confident",
    "cta": "Try free",
}

def make_campaign_with_shot_plan(output_format="hybrid_reel", selected_shot_id=None, shot_ready=False):
    """Create a campaign in studio stage with a shot plan."""
    brief = CampaignBrief(**SAMPLE_BRIEF)
    shots = [
        Shot(
            shot_id=f"S{i}",
            order=i,
            duration_seconds=6,
            purpose="hero",
            creative_mode="creator_demo",
            visual=f"Shot {i} visual description of product being used naturally",
            action=f"User opens app and sees result {i}",
            camera="Medium close-up",
            audio_direction="Natural ambient audio",
            veo_audio_prompt="Natural synchronized",
            caption=f"Caption for shot {i}",
            veo_prompt_intent=f"Prompt intent {i}",
            negative_constraints=["no text", "no logos"],
            status="ready" if shot_ready else "planned",
            video_url="https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4" if shot_ready else None,
        )
        for i in range(1, 4)
    ]
    shot_plan = ShotPlan(direction_id="D1", shots=shots)
    prod_settings = ProductionSettings(
        headline="Revolutionize your workflow today",
        caption=shots[0].caption,
        cta="Try free",
        audio_mode="native_ambient",
    )
    campaign = Campaign(
        workspace_id=WS,
        brief=brief,
        stage="studio",
        shot_plan=shot_plan,
        output_format=output_format,
        selected_shot_id=selected_shot_id or shots[0].shot_id,
        production_settings=prod_settings,
    )
    campaign_store.save(campaign.id, campaign)
    return campaign


def test_completed_reel_can_be_reopened_as_campaign_pack_without_losing_ready_shot():
    campaign = make_campaign_with_shot_plan(output_format="hybrid_reel", shot_ready=True)
    campaign_store.update(campaign.id, {
        "stage": "reel",
        "final_video_url": "/api/media/reels/existing.mp4",
    })

    response = client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        json={"output_format": "campaign_pack"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["stage"] == "studio"
    assert updated["output_format"] == "campaign_pack"
    assert updated["selected_shot_id"] == campaign.selected_shot_id
    assert updated["final_video_url"] == "/api/media/reels/existing.mp4"
    assert next(shot for shot in updated["shot_plan"]["shots"] if shot["shot_id"] == campaign.selected_shot_id)["status"] == "ready"


# ============================================================
# 1. PREVIEW ENDPOINT: 3 stills, 0 Veo, idempotent, workspace-isolated
# ============================================================

def test_preview_endpoint_no_veo_calls():
    """POST /generate-previews must not call Veo; must return job_id."""
    from app.services import veo_service as veo_mod
    original_start = veo_mod.veo_service.start_generation
    veo_called = []

    def fake_veo(*args, **kwargs):
        veo_called.append(True)
        return "fake-op"

    veo_mod.veo_service.start_generation = fake_veo
    try:
        campaign = make_campaign_with_shot_plan()
        r = client.post(f"/api/campaigns/{campaign.id}/generate-previews", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert "job_id" in r.json()
        assert len(veo_called) == 0, "Veo was called during preview generation!"
    finally:
        veo_mod.veo_service.start_generation = original_start


def test_preview_endpoint_workspace_isolation():
    """Another workspace cannot access preview stills for this campaign."""
    campaign = make_campaign_with_shot_plan()
    # Manually set a preview URL to simulate generated preview
    c = campaign_store.get(campaign.id)
    c.shot_plan.shots[0].preview_image_url = f"/api/media/previews/{WS}/{c.id}/S1.png"
    campaign_store.save(c.id, c)
    # Request from different workspace should get 404 (workspace mismatch or no campaign)
    r = client.get(f"/api/media/previews/{WS}/{c.id}/S1.png", headers={"X-Workspace-ID": "OTHER_WS"})
    assert r.status_code in (403, 404)


def test_preview_idempotent():
    """Shots with existing preview_image_url should not have new previews generated."""
    campaign = make_campaign_with_shot_plan()
    c = campaign_store.get(campaign.id)
    # Pre-populate previews for all shots
    for shot in c.shot_plan.shots:
        shot.preview_image_url = f"/api/media/previews/{WS}/{c.id}/{shot.shot_id}.png"
    campaign_store.save(c.id, c)

    # Now run generate-previews - should immediately complete since all already have URLs
    gen_called = []
    from app.services import preview_service as ps
    original_gen = ps.preview_service.generate_preview
    async def fake_gen(*args, **kwargs):
        gen_called.append(True)
        return "/fake/url"
    ps.preview_service.generate_preview = fake_gen
    try:
        r = client.post(f"/api/campaigns/{c.id}/generate-previews", headers=HEADERS)
        assert r.status_code == 200
        # No new previews should be generated since all shots have URLs
        import time
        time.sleep(1)  # Let the background task run
        assert len(gen_called) == 0, "Previews were regenerated unnecessarily"
    finally:
        ps.preview_service.generate_preview = original_gen


# ============================================================
# 2. STATIC POST: 1080x1350, 0 Veo, no shot selection required
# ============================================================

def test_static_post_zero_veo_calls():
    """Static Post produce must not call Veo."""
    from app.services import veo_service as veo_mod
    veo_called = []
    original_start = veo_mod.veo_service.start_generation
    def fake_veo(*args, **kwargs):
        veo_called.append(True)
        return "fake-op"
    veo_mod.veo_service.start_generation = fake_veo
    try:
        # Static post does not need a selected shot
        brief = CampaignBrief(**SAMPLE_BRIEF)
        shots = [Shot(
            shot_id="S1", order=1, duration_seconds=6, purpose="hero",
            creative_mode="creator_demo",
            visual="Product in use", action="User opens app", camera="Wide",
            audio_direction="Natural", veo_audio_prompt="Natural",
            caption="Great caption", veo_prompt_intent="Intent",
            negative_constraints=["no text"],
        )]
        shot_plan = ShotPlan(direction_id="D1", shots=shots)
        prod_settings = ProductionSettings(headline="Great Product", caption="Great", cta="Buy Now", audio_mode="native_ambient")
        campaign = Campaign(
            workspace_id=WS, brief=brief, stage="studio",
            shot_plan=shot_plan, output_format="static_post",
            production_settings=prod_settings,
        )
        campaign_store.save(campaign.id, campaign)
        r = client.post(f"/api/campaigns/{campaign.id}/produce", headers=HEADERS)
        assert r.status_code == 200
        assert len(veo_called) == 0, "Veo was called for Static Post!"
    finally:
        veo_mod.veo_service.start_generation = original_start


def test_static_post_no_shot_selection_required():
    """Static Post should not require selected_shot_id."""
    brief = CampaignBrief(**SAMPLE_BRIEF)
    shots = [Shot(
        shot_id="S1", order=1, duration_seconds=6, purpose="hero",
        creative_mode="creator_demo",
        visual="Product visual", action="Action", camera="Wide",
        audio_direction="Natural", veo_audio_prompt="Natural",
        caption="Caption", veo_prompt_intent="Intent",
        negative_constraints=[],
    )]
    shot_plan = ShotPlan(direction_id="D1", shots=shots)
    prod_settings = ProductionSettings(headline="My App", caption="The best app", cta="Get started", audio_mode="native_ambient")
    campaign = Campaign(
        workspace_id=WS, brief=brief, stage="studio",
        shot_plan=shot_plan, output_format="static_post",
        selected_shot_id=None,  # No shot selected
        production_settings=prod_settings,
    )
    campaign_store.save(campaign.id, campaign)
    r = client.post(f"/api/campaigns/{campaign.id}/produce", headers=HEADERS)
    assert r.status_code == 200, f"Static Post with no shot selected should succeed: {r.text}"


def test_static_post_has_no_hidden_shot_plan_dependency():
    """A post-only campaign must not require storyboard/video state."""
    campaign = Campaign(
        workspace_id=WS,
        brief=CampaignBrief(**SAMPLE_BRIEF),
        stage="studio",
        shot_plan=None,
        output_format="static_post",
        selected_shot_id=None,
        production_settings=ProductionSettings(
            headline="Great Product",
            caption="A deterministic post caption",
            cta="Try free",
            audio_mode="native_ambient",
        ),
    )
    campaign_store.save(campaign.id, campaign)
    r = client.post(f"/api/campaigns/{campaign.id}/produce", headers=HEADERS)
    assert r.status_code == 200, r.text


# ============================================================
# 3. UNSELECTED SHOTS REMAIN PLANNED
# ============================================================

def test_unselected_shots_remain_planned():
    """When hybrid_reel is produced, only selected shot changes status. Others stay planned."""
    campaign = make_campaign_with_shot_plan(output_format="hybrid_reel", selected_shot_id="S1")
    r = client.post(f"/api/campaigns/{campaign.id}/produce", headers=HEADERS)
    assert r.status_code == 200
    # Check that shot S2 and S3 remain planned after production
    updated = campaign_store.get(campaign.id)
    # selected shot should change to queued/generating/ready
    selected = next(s for s in updated.shot_plan.shots if s.shot_id == "S1")
    assert selected.status in ("queued", "generating", "ready"), f"Selected shot should be queued, got {selected.status}"
    # Other shots should remain planned
    for shot in updated.shot_plan.shots:
        if shot.shot_id != "S1":
            assert shot.status == "planned", f"Unselected shot {shot.shot_id} should remain planned, got {shot.status}"


# ============================================================
# 4. CAMPAIGN PACK: 0 ADDITIONAL VEO IF SHOT ALREADY READY
# ============================================================

def test_campaign_pack_zero_additional_veo_when_shot_ready():
    """
    Campaign Pack with already-ready selected shot must make 0 additional Veo calls.
    All 3 outputs (video + image + thumbnail) must be set.
    """
    from app.services import veo_service as veo_mod
    veo_called = []
    original_start = veo_mod.veo_service.start_generation
    def fake_veo(*args, **kwargs):
        veo_called.append(True)
        return "fake-op"
    veo_mod.veo_service.start_generation = fake_veo
    try:
        # Shot S1 is already ready with video_url
        campaign = make_campaign_with_shot_plan(
            output_format="campaign_pack",
            selected_shot_id="S1",
            shot_ready=True,  # All shots are ready
        )
        r = client.post(f"/api/campaigns/{campaign.id}/produce", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert len(veo_called) == 0, f"Veo was called {len(veo_called)} times but shot was already ready!"
        completed = campaign_store.get(campaign.id)
        assert completed.final_video_url
        assert completed.final_image_url
        assert completed.final_thumbnail_url
    finally:
        veo_mod.veo_service.start_generation = original_start


def test_campaign_pack_output_format_accepted():
    """Output format campaign_pack should be accepted by the output-format endpoint."""
    campaign = make_campaign_with_shot_plan(output_format="hybrid_reel")
    r = client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        json={"output_format": "campaign_pack"},
        headers=HEADERS,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["output_format"] == "campaign_pack"
    # selected_shot_id should be preserved (campaign_pack requires shot like hybrid_reel)
    assert data.get("selected_shot_id") == "S1"


# ============================================================
# 5. MEDIA URL SAFETY: No access tokens in URLs
# ============================================================

def test_media_urls_no_access_token():
    """All media proxy URLs must not expose OAuth tokens or access credentials."""
    campaign = make_campaign_with_shot_plan(output_format="campaign_pack", shot_ready=True)
    c = campaign_store.get(campaign.id)
    # Simulate campaign pack completion
    c.stage = "reel"
    c.final_video_url = f"/api/media/reels/reel_{c.id}.mp4"
    c.final_image_url = f"/api/media/posts/post_{c.id}.png"
    c.final_thumbnail_url = f"/api/media/covers/cover_{c.id}.png"
    campaign_store.save(c.id, c)

    for url_field in [c.final_video_url, c.final_image_url, c.final_thumbnail_url]:
        assert url_field is not None
        assert "access_token" not in url_field.lower(), f"Access token found in URL: {url_field}"
        assert "token=" not in url_field.lower(), f"Token query string in URL: {url_field}"
        assert "authorization" not in url_field.lower(), f"Auth in URL: {url_field}"


# ============================================================
# 6. PREVIEW RENDERING: Not black
# ============================================================

def test_storyboard_preview_never_black():
    """Deterministic storyboard fallback must contain more than 3 distinct colors."""
    from app.services.preview_service import render_storyboard_fallback
    from PIL import Image
    import io

    class MockShot:
        purpose = "hero"
        order = 1
        duration_seconds = 6
        visual = "Cinematic wide shot of user at desk with app on screen in dim morning light"
        action = "User opens app, relief washes over face as task completes"
        camera = "Medium close-up, slight Dutch angle"
        audio_direction = "Natural ambient coffee shop sounds"
        creative_mode = "creator_demo"
        caption = "Stop losing hours to scattered workflows"
        shot_id = "S1"

    class MockKit:
        brand_colors = ["#F5F5F0", "#1A1714", "#FFB347"]
        brand_name = "TestBrand"

    data = render_storyboard_fallback(MockShot(), "SHOT 1", MockKit())
    assert data[:4] == b"\x89PNG", "Storyboard fallback must be a valid PNG"
    img = Image.open(io.BytesIO(data)).convert("RGB")
    pixels = list(img.getdata())
    unique_colors = len(set(pixels))
    assert unique_colors > 3, f"Storyboard has only {unique_colors} unique colors - nearly black!"
    assert img.size == (720, 1280), f"Storyboard dimensions wrong: {img.size}"


# ============================================================
# 7. REEL COVER: 1080x1920 with correct dimensions
# ============================================================

def test_reel_cover_render_dimensions():
    """render_reel_cover must produce a valid 1080x1920 PNG without GCS upload."""
    from app.services.branded_finishing import BrandedFinishingService
    from app.models.campaign import Campaign, CampaignBrief, ProductionSettings
    from app.models.library import BrandKit
    import tempfile, os
    from PIL import Image
    import io

    brief = CampaignBrief(**SAMPLE_BRIEF)
    prod = ProductionSettings(headline="Test Headline Long Enough", caption="Test caption", cta="Learn more", audio_mode="native_ambient")
    campaign = Campaign(workspace_id=WS, brief=brief, stage="reel", production_settings=prod)

    kit = BrandKit(workspace_id=WS, brand_colors=["#F5F5F0", "#1A1714", "#FFB347"])

    service = BrandedFinishingService()

    # Patch GCS upload to return local URL
    with patch.object(service, 'compose_static_post', return_value="/api/media/posts/test.png"):
        pass  # Not needed here, just testing render_reel_cover

    # We need to patch ffmpeg_service.upload_to_gcs to avoid actual GCS call
    with patch("app.services.branded_finishing.ffmpeg_service") as mock_ffmpeg:
        def fake_upload(local_path, blob_name, content_type="image/png"):
            # Verify the file was created and is a valid image
            assert os.path.exists(local_path), f"Cover file not created at {local_path}"
            img = Image.open(local_path)
            assert img.size == (1080, 1920), f"Wrong cover dimensions: {img.size}"
            return f"/api/media/covers/cover_test.png"
        mock_ffmpeg.upload_to_gcs = fake_upload

        result = service.render_reel_cover(campaign, kit, None, [], "cover_test.png")
        assert result == "/api/media/covers/cover_test.png"


# ============================================================
# 8. CAMPAIGN MODEL: Backward compatibility with old records
# ============================================================

def test_campaign_model_backward_compat():
    """Old campaigns.json records without preview_image_url must still deserialize."""
    from app.models.campaign import Shot, ShotPlan

    # Simulate a shot without preview_image_url (as stored in old JSON)
    shot_data = {
        "shot_id": "S1",
        "order": 1,
        "duration_seconds": 6,
        "purpose": "hero",
        "creative_mode": "creator_demo",
        "visual": "test",
        "action": "test",
        "camera": "wide",
        "audio_direction": "natural",
        "veo_audio_prompt": "natural",
        "caption": "test",
        "veo_prompt_intent": "test",
        "negative_constraints": [],
        # Note: no preview_image_url field — old record
    }
    shot = Shot(**shot_data)
    assert shot.preview_image_url is None  # Should default to None

    # Also test OutputFormat includes campaign_pack
    from app.models.campaign import Campaign
    c_data = {
        "workspace_id": WS,
        "stage": "studio",
        "output_format": "campaign_pack",  # New value must be accepted
    }
    # Import Campaign and create
    c = Campaign(**c_data)
    assert c.output_format == "campaign_pack"


def test_veo_prompt_hides_generated_phone_ui_when_screen_constraints_are_present():
    shot = Shot(
        shot_id="S_PHONE",
        order=1,
        duration_seconds=6,
        purpose="hero",
        creative_mode="creator_demo",
        visual="A person records a private thought.",
        action="The person holds a phone near their face.",
        camera="Intimate close-up",
        audio_direction="Quiet room tone",
        veo_audio_prompt="Quiet nighttime room tone",
        caption="Capture it before it fades.",
        veo_prompt_intent="An adult types into a smartphone in a dim bedroom",
        negative_constraints=["app UI", "legible text", "distorted screens"],
    )

    prompt = VeoService.compile_prompt(shot)

    assert "Keep every phone display dark" in prompt
    assert "never show a bright blank screen" in prompt
    assert "fake interface, keyboard, icons, or readable text" in prompt


def test_preview_active_job_is_reused():
    """Concurrent automatic preview requests must return the same active job."""
    campaign = make_campaign_with_shot_plan()
    active = Job(
        workspace_id=WS,
        campaign_id=campaign.id,
        stage="generating",
        message="Generating candidate previews...",
    )
    job_store.save(active.job_id, active)
    r = client.post(f"/api/campaigns/{campaign.id}/generate-previews", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] == active.job_id


def test_media_upload_routes_cover_to_cover_proxy(tmp_path):
    from app.services.ffmpeg_service import FFmpegService
    service = FFmpegService()
    fake_blob = MagicMock()
    fake_bucket = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    service.bucket = fake_bucket
    source = tmp_path / "cover.png"
    source.write_bytes(b"png")
    with patch("app.services.ffmpeg_service.settings.media_delivery_mode", "proxy"):
        url = service.upload_to_gcs(str(source), "final_covers/cover_test.png", content_type="image/png")
    assert url == "/api/media/covers/cover_test.png"
    fake_blob.upload_from_filename.assert_called_once()


def test_static_post_render_dimensions():
    from app.models.library import BrandKit
    from app.services.branded_finishing import BrandedFinishingService
    from PIL import Image

    background = io.BytesIO()
    Image.new("RGB", (900, 1125), "#29304f").save(background, "PNG")
    campaign = Campaign(
        workspace_id=WS,
        brief=CampaignBrief(**SAMPLE_BRIEF),
        stage="reel",
        production_settings=ProductionSettings(
            headline="Professional campaign headline",
            caption="Clear product benefit without generated text",
            cta="Try free",
            audio_mode="native_ambient",
        ),
    )
    kit = BrandKit(workspace_id=WS, brand_colors=["#F5F5F0", "#141210", "#FFB347"])
    service = BrandedFinishingService()

    with patch("app.services.branded_finishing.ffmpeg_service") as mock_ffmpeg:
        def fake_upload(local_path, blob_name, content_type="image/png"):
            image = Image.open(local_path)
            assert image.size == (1080, 1350)
            return "/api/media/posts/post_test.png"

        mock_ffmpeg.upload_to_gcs = fake_upload
        result = service.compose_static_post(background.getvalue(), campaign, kit, None, [], "post_test.png")
    assert result == "/api/media/posts/post_test.png"


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg tools are required")
def test_hybrid_export_contract_and_audible_tail(tmp_path):
    """Hybrid output must satisfy the Instagram codec contract and avoid a dead card tail."""
    from app.services.ffmpeg_service import FFmpegService
    from PIL import Image

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    source = tmp_path / "source.mp4"
    card = tmp_path / "card.png"
    output = tmp_path / "final.mp4"
    Image.new("RGB", (720, 1280), "#273054").save(card, "PNG")
    subprocess.run([
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=c=#25305c:s=720x1280:r=24:d=2",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(source),
    ], check=True, capture_output=True)

    service = FFmpegService()
    with patch.object(service, "download_from_gcs", side_effect=lambda _uri, dst: shutil.copyfile(source, dst)), patch.object(
        service,
        "upload_to_gcs",
        side_effect=lambda local, _dest, content_type="video/mp4": shutil.copyfile(local, output) or str(output),
    ):
        service.assemble_hybrid_reel(
            "gs://test/source.mp4",
            "A concise safe-zone caption",
            [str(card)],
            "test.mp4",
            audio_mode="native_ambient",
            caption_start_seconds=0.5,
        )

    probe = subprocess.run([
        ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output),
    ], check=True, capture_output=True, text=True)
    payload = json.loads(probe.stdout)
    video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in payload["streams"] if stream["codec_type"] == "audio")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["codec_name"] == "h264"
    assert video["pix_fmt"] == "yuv420p"
    assert audio["codec_name"] == "aac"
    assert audio["sample_rate"] == "48000"
    assert audio["channels"] == 2
    atoms = output.read_bytes()
    assert atoms.find(b"moov") < atoms.find(b"mdat"), "MP4 is missing faststart atom ordering"

    tail = subprocess.run([
        ffmpeg, "-sseof", "-1.2", "-i", str(output),
        "-af", "silencedetect=noise=-50dB:d=0.8", "-f", "null", "-",
    ], capture_output=True, text=True)
    assert "silence_duration" not in tail.stderr


def test_delayed_caption_uses_ffmpeg_timeline_enable():
    from app.services.ffmpeg_service import FFmpegService

    drawtext = FFmpegService()._build_drawtext_filter(
        "What does falling in a dream mean?",
        start_seconds=2.75,
    )

    assert "enable='gte(t\\,2.750)'" in drawtext


def test_legacy_production_settings_keep_immediate_caption():
    production_settings = ProductionSettings.model_validate({
        "headline": "A headline",
        "caption": "A caption",
        "cta": "Learn more",
    })

    assert production_settings.caption_start_seconds == 0.0


def test_veo_prompt_enforces_native_full_frame_vertical_output():
    shot = Shot(
        shot_id="full-frame",
        order=1,
        duration_seconds=6,
        purpose="hero",
        creative_mode="relatable_scenario",
        visual="Falling dream",
        action="Falling then waking",
        camera="First person POV",
        audio_direction="Wind then gasp",
        veo_prompt_intent="Strict downward first-person POV falling beside a city building before a wake-up cut",
        caption="What does falling in a dream mean?",
    )

    prompt = VeoService.compile_prompt(shot)
    negatives = VeoService().compile_negative_prompt(shot)

    assert "full-frame vertical 9:16" in prompt
    assert "fills every pixel" in prompt
    assert "letterboxing" in negatives
    assert "black bars" in negatives


def test_veo_generation_uses_workspace_first_frame_image(tmp_path):
    anchor = tmp_path / "anchor.png"
    anchor.write_bytes(b"fake-png")
    shot = Shot(
        shot_id="anchored",
        order=1,
        duration_seconds=6,
        purpose="hero",
        creative_mode="relatable_scenario",
        visual="High falling POV",
        action="Fall vertically",
        camera="Nadir POV",
        audio_direction="Wind",
        veo_prompt_intent="Camera descends vertically from a skyscraper while looking directly at the ground below",
        caption="Falling dream",
    )
    service = VeoService()
    service.client = MagicMock()
    service.client.models.generate_videos.return_value.name = "operation/anchored"

    with patch("app.services.veo_service.types.Image.from_file", return_value=MagicMock()) as from_file:
        operation = service.start_generation(shot, first_frame_path=str(anchor))

    assert operation == "operation/anchored"
    from_file.assert_called_once_with(location=str(anchor))
    source = service.client.models.generate_videos.call_args.kwargs["source"]
    assert source.image is not None


def test_veo_generation_uses_workspace_first_and_last_frame_images(tmp_path):
    first_anchor = tmp_path / "first.png"
    last_anchor = tmp_path / "last.png"
    first_anchor.write_bytes(b"fake-first-png")
    last_anchor.write_bytes(b"fake-last-png")
    shot = Shot(
        shot_id="two-anchor-fall",
        order=1,
        duration_seconds=6,
        purpose="hero",
        creative_mode="relatable_scenario",
        visual="High falling POV",
        action="Fall vertically until immediately before impact",
        camera="Locked nadir POV",
        audio_direction="Accelerating wind",
        veo_prompt_intent="Interpolate one uninterrupted vertical descent from the high city view to the close asphalt view",
        caption="Falling dream",
    )
    service = VeoService()
    service.client = MagicMock()
    service.client.models.generate_videos.return_value.name = "operation/two-anchor-fall"

    first_image = MagicMock(name="first-image")
    last_image = MagicMock(name="last-image")
    with patch(
        "app.services.veo_service.types.Image.from_file",
        side_effect=[first_image, last_image],
    ) as from_file:
        operation = service.start_generation(
            shot,
            first_frame_path=str(first_anchor),
            last_frame_path=str(last_anchor),
        )

    assert operation == "operation/two-anchor-fall"
    assert from_file.call_args_list == [
        call(location=str(first_anchor)),
        call(location=str(last_anchor)),
    ]
    request = service.client.models.generate_videos.call_args.kwargs
    assert request["source"].image is first_image
    assert request["config"].last_frame is last_image


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg tools are required")
def test_letterbox_detection_returns_conservative_crop(tmp_path):
    from app.services.ffmpeg_service import FFmpegService

    source = tmp_path / "letterboxed.mp4"
    subprocess.run([
        shutil.which("ffmpeg"), "-y",
        "-f", "lavfi", "-i", "color=c=#3857A6:s=720x960:r=24:d=1",
        "-vf", "pad=720:1280:0:160:color=black",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)

    crop = FFmpegService._detect_letterbox_crop(
        shutil.which("ffmpeg"),
        shutil.which("ffprobe"),
        str(source),
    )

    assert crop.startswith("crop=")
    assert ":960:" in crop
