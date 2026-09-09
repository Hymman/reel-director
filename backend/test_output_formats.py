import io
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from app.models.campaign import Campaign, CampaignBrief, CreativeDirection, CreativeDirectionSet, ProductionSettings, Shot, ShotPlan
from app.models.job import Job
from app.models.library import AssetRecord, BrandKit
from app.services.state_store import JsonFileStore
import app.routers.campaigns as campaigns_router
import app.routers.jobs as jobs_router
import app.routers.media as media_router


client = TestClient(app)


class FakeBlob:
    size = 16

    def exists(self):
        return True

    def reload(self):
        return None

    def download_as_bytes(self, start=None, end=None):
        data = b"FAKE_PNG_CONTENT"
        if start is not None:
            return data[start:(end + 1 if end is not None else None)]
        return data


class FakeBucket:
    def blob(self, name):
        return FakeBlob()


@pytest.fixture(autouse=True)
def isolated_output_services(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        campaign_store = JsonFileStore(os.path.join(tmpdir, "campaigns.json"), Campaign)
        job_store = JsonFileStore(os.path.join(tmpdir, "jobs.json"), Job)
        asset_store = JsonFileStore(os.path.join(tmpdir, "assets.json"), AssetRecord)
        kit_store = JsonFileStore(os.path.join(tmpdir, "kits.json"), BrandKit)
        monkeypatch.setattr(campaigns_router, "campaign_store", campaign_store)
        monkeypatch.setattr(campaigns_router, "job_store", job_store)
        monkeypatch.setattr(campaigns_router, "asset_store", asset_store)
        monkeypatch.setattr(campaigns_router, "brand_kit_store", kit_store)
        monkeypatch.setattr(jobs_router, "job_store", job_store)
        monkeypatch.setattr(media_router, "campaign_store", campaign_store)
        monkeypatch.setattr(campaigns_router.settings, "demo_mode", False)

        class FakeVeo:
            def __init__(self):
                self.started = []

            def start_generation(self, shot, audio_mode="native_ambient"):
                self.started.append(shot.shot_id)
                return f"op_{shot.shot_id}"

            def check_operation(self, operation):
                return {"status": "completed", "gcs_uri": f"gs://fake/{operation}.mp4"}

        class FakeFFmpeg:
            def __init__(self):
                self.hybrid = MagicMock(side_effect=lambda selected, caption, cards, output, **kwargs: f"/api/media/reels/{output}")
                self.full = MagicMock(side_effect=lambda clips, texts, output, **kwargs: f"/api/media/reels/{output}")
                self.slideshow = MagicMock(side_effect=lambda cards, output, **kwargs: f"/api/media/reels/{output}")
                self.bucket = FakeBucket()

            def assemble_hybrid_reel(self, *args, **kwargs):
                return self.hybrid(*args, **kwargs)

            def assemble_reel(self, *args, **kwargs):
                return self.full(*args, **kwargs)

            def assemble_slideshow_reel(self, *args, **kwargs):
                return self.slideshow(*args, **kwargs)

        class FakeFinishing:
            def __init__(self):
                self.static = MagicMock(side_effect=lambda background, campaign, kit, logo, paths, output: f"/api/media/posts/{output}")
                self.cards = MagicMock(return_value=["opening.png", "product.png"])
                self.carousel = MagicMock(side_effect=lambda background, campaign, kit, logo, paths, prefix: [f"/api/media/posts/{prefix}_{index:02d}.png" for index in range(1, 6)])
                self.carousel_cards = MagicMock(return_value=[f"carousel_{index:02d}.png" for index in range(1, 6)])
                self.cover = MagicMock(side_effect=lambda campaign, kit, logo, paths, output: f"/api/media/covers/{output}")

            def compose_static_post(self, *args, **kwargs):
                return self.static(*args, **kwargs)

            def render_vertical_cards(self, *args, **kwargs):
                return self.cards(*args, **kwargs)

            def compose_carousel_post(self, *args, **kwargs):
                return self.carousel(*args, **kwargs)

            def render_carousel_cards(self, *args, **kwargs):
                return self.carousel_cards(*args, **kwargs)

            def render_reel_cover(self, *args, **kwargs):
                return self.cover(*args, **kwargs)

        fake_veo = FakeVeo()
        fake_ffmpeg = FakeFFmpeg()
        fake_finishing = FakeFinishing()
        fake_image = type("FakeImage", (), {"generate_background": AsyncMock(return_value=b"PNG")})()
        monkeypatch.setattr(campaigns_router, "veo_service", fake_veo)
        monkeypatch.setattr(campaigns_router, "ffmpeg_service", fake_ffmpeg)
        monkeypatch.setattr(campaigns_router, "branded_finishing_service", fake_finishing)
        monkeypatch.setattr(campaigns_router, "image_service", fake_image)
        monkeypatch.setattr(media_router, "ffmpeg_service", fake_ffmpeg)
        yield campaign_store, job_store, fake_veo, fake_ffmpeg, fake_finishing, fake_image, kit_store


def make_campaign(workspace="WS_OUTPUT"):
    directions = CreativeDirectionSet(
        directions=[CreativeDirection(direction_id="d1", name="Calm Shift", hook="Stop switching. Start finishing.", core_tension="Context switching", creative_hypothesis="Calm proof", visual_idea="Editorial focus ritual", cta_treatment="Try it", evidence_ids=["E1"], why_test="Evidence used: [E1]")],
        director_pick_direction_id="d1",
        director_pick_reason="Strong audience fit",
    )
    shots = [
        Shot(shot_id=f"h{index}", order=index, duration_seconds=6, purpose="hero", creative_mode=mode, visual=f"Hero visual {index}", action="Focused action", camera="Slow push", audio_direction="Yumuşak ofis ambiyansı", caption=f"Hero caption {index}", veo_prompt_intent=f"English hero production prompt {index}")
        for index, mode in [(1, "relatable_scenario"), (2, "creator_demo"), (3, "premium_metaphor")]
    ]
    full_reel_shots = [
        Shot(shot_id=f"f{index}", order=index, duration_seconds=6, purpose=purpose, creative_mode="sequential", visual=f"Full scene {index}", action="Focused action", camera="Slow push", audio_direction="Soft office ambience", caption=f"Full caption {index}", veo_prompt_intent=f"English sequential production prompt {index}")
        for index, purpose in [(1, "hook"), (2, "body"), (3, "payoff")]
    ]
    return Campaign(
        workspace_id=workspace,
        stage="studio",
        brief=CampaignBrief(subject_name="FocusFlow", subject_description="Deep work app", audience="Remote creators", cta="Start free"),
        direction_set=directions,
        selected_direction_id="d1",
        shot_plan=ShotPlan(direction_id="d1", shots=shots, full_reel_shots=full_reel_shots),
        selected_shot_id="h2",
    )


def test_hybrid_default_generates_exactly_one_veo_shot_and_branded_cards(isolated_output_services):
    campaign_store, job_store, veo, ffmpeg, finishing, _, _ = isolated_output_services
    campaign = make_campaign()
    campaign_store.save(campaign.id, campaign)
    response = client.post(f"/api/campaigns/{campaign.id}/produce", headers={"X-Workspace-ID": campaign.workspace_id})
    assert response.status_code == 200
    assert job_store.get(response.json()["job_id"]).stage == "complete"
    assert veo.started == ["h2"]
    ffmpeg.hybrid.assert_called_once()
    finishing.cards.assert_called_once()
    updated = campaign_store.get(campaign.id)
    assert updated.output_format == "hybrid_reel"
    assert [shot.status for shot in updated.shot_plan.shots] == ["planned", "ready", "planned"]
    assert updated.final_video_url.endswith(f"reel_{campaign.id}.mp4")


def test_full_video_reel_generates_three_shots_and_uses_full_assembler(isolated_output_services):
    campaign_store, _, veo, ffmpeg, _, _, _ = isolated_output_services
    campaign = make_campaign()
    campaign_store.save(campaign.id, campaign)
    select = client.post(f"/api/campaigns/{campaign.id}/output-format", headers={"X-Workspace-ID": campaign.workspace_id}, json={"output_format": "full_video_reel"})
    assert select.status_code == 200
    response = client.post(f"/api/campaigns/{campaign.id}/produce", headers={"X-Workspace-ID": campaign.workspace_id})
    assert response.status_code == 200
    assert veo.started == ["f1", "f2", "f3"]
    ffmpeg.full.assert_called_once()
    assert len(ffmpeg.full.call_args.args[0]) == 3
    ffmpeg.hybrid.assert_not_called()
    updated = campaign_store.get(campaign.id)
    assert all(shot.status == "planned" for shot in updated.shot_plan.shots)
    assert all(shot.status == "ready" for shot in updated.shot_plan.full_reel_shots)


def test_static_post_uses_imagen_and_deterministic_layout_without_veo(isolated_output_services):
    campaign_store, job_store, veo, ffmpeg, finishing, image, _ = isolated_output_services
    campaign = make_campaign()
    campaign_store.save(campaign.id, campaign)
    assert client.post(f"/api/campaigns/{campaign.id}/output-format", headers={"X-Workspace-ID": campaign.workspace_id}, json={"output_format": "static_post"}).status_code == 200
    response = client.post(f"/api/campaigns/{campaign.id}/produce", headers={"X-Workspace-ID": campaign.workspace_id})
    assert response.status_code == 200
    image.generate_background.assert_awaited_once()
    finishing.static.assert_called_once()
    assert veo.started == []
    ffmpeg.hybrid.assert_not_called()
    ffmpeg.full.assert_not_called()
    updated = campaign_store.get(campaign.id)
    assert updated.final_image_url.endswith(f"post_{campaign.id}.png")
    assert updated.final_video_url is None
    assert job_store.get(response.json()["job_id"]).stage == "complete"


def test_carousel_post_returns_five_ordered_cards_without_veo(isolated_output_services):
    campaign_store, job_store, veo, ffmpeg, finishing, image, _ = isolated_output_services
    campaign = make_campaign()
    campaign.shot_plan = None
    campaign_store.save(campaign.id, campaign)
    assert client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        headers={"X-Workspace-ID": campaign.workspace_id},
        json={"output_format": "carousel_post"},
    ).status_code == 200
    response = client.post(f"/api/campaigns/{campaign.id}/produce", headers={"X-Workspace-ID": campaign.workspace_id})
    assert response.status_code == 200
    assert job_store.get(response.json()["job_id"]).stage == "complete"
    image.generate_background.assert_awaited_once()
    finishing.carousel.assert_called_once()
    assert veo.started == []
    ffmpeg.hybrid.assert_not_called()
    ffmpeg.full.assert_not_called()
    ffmpeg.slideshow.assert_not_called()
    updated = campaign_store.get(campaign.id)
    assert updated.final_video_url is None
    assert len(updated.final_carousel_urls) == 5
    assert updated.final_carousel_urls[0].endswith(f"carousel_{campaign.id}_01.png")
    assert updated.final_carousel_urls[-1].endswith(f"carousel_{campaign.id}_05.png")


def test_slideshow_reel_animates_static_cards_without_veo(isolated_output_services):
    campaign_store, job_store, veo, ffmpeg, finishing, image, _ = isolated_output_services
    campaign = make_campaign()
    campaign.shot_plan = None
    campaign_store.save(campaign.id, campaign)
    assert client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        headers={"X-Workspace-ID": campaign.workspace_id},
        json={"output_format": "slideshow_reel"},
    ).status_code == 200
    response = client.post(f"/api/campaigns/{campaign.id}/produce", headers={"X-Workspace-ID": campaign.workspace_id})
    assert response.status_code == 200
    assert job_store.get(response.json()["job_id"]).stage == "complete"
    image.generate_background.assert_awaited_once()
    finishing.carousel_cards.assert_called_once()
    finishing.cover.assert_called_once()
    ffmpeg.slideshow.assert_called_once()
    assert veo.started == []
    updated = campaign_store.get(campaign.id)
    assert updated.final_video_url is None
    assert updated.final_slideshow_url.endswith(f"slideshow_{campaign.id}.mp4")
    assert updated.final_thumbnail_url.startswith("/api/media/covers/slideshow_cover_")
    assert updated.final_thumbnail_url.endswith(f"_{campaign.id}.png")
    assert updated.final_carousel_urls == []


def test_sequential_content_outputs_remain_in_one_campaign_record(isolated_output_services):
    campaign_store, job_store, veo, *_ = isolated_output_services
    campaign = make_campaign()
    campaign.shot_plan = None
    campaign_store.save(campaign.id, campaign)
    headers = {"X-Workspace-ID": campaign.workspace_id}

    for output_format in ("static_post", "carousel_post", "slideshow_reel"):
        selected = client.post(
            f"/api/campaigns/{campaign.id}/output-format",
            headers=headers,
            json={"output_format": output_format},
        )
        assert selected.status_code == 200
        produced = client.post(f"/api/campaigns/{campaign.id}/produce", headers=headers)
        assert produced.status_code == 200
        assert job_store.get(produced.json()["job_id"]).stage == "complete"

    updated = campaign_store.get(campaign.id)
    assert updated.final_image_url.endswith(f"post_{campaign.id}.png")
    assert len(updated.final_carousel_urls) == 5
    assert updated.final_slideshow_url.endswith(f"slideshow_{campaign.id}.mp4")
    assert updated.final_video_url is None
    assert veo.started == []


def test_campaign_pack_delivers_every_format_with_one_veo_call(isolated_output_services):
    campaign_store, job_store, veo, ffmpeg, finishing, image, _ = isolated_output_services
    campaign = make_campaign()
    campaign_store.save(campaign.id, campaign)
    assert client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        headers={"X-Workspace-ID": campaign.workspace_id},
        json={"output_format": "campaign_pack"},
    ).status_code == 200
    response = client.post(f"/api/campaigns/{campaign.id}/produce", headers={"X-Workspace-ID": campaign.workspace_id})
    assert response.status_code == 200
    assert job_store.get(response.json()["job_id"]).stage == "complete"
    assert veo.started == ["h2"]
    image.generate_background.assert_awaited_once()
    ffmpeg.hybrid.assert_called_once()
    ffmpeg.slideshow.assert_called_once()
    finishing.static.assert_called_once()
    finishing.carousel.assert_called_once()
    finishing.cover.assert_called_once()
    updated = campaign_store.get(campaign.id)
    assert updated.final_video_url.endswith(f"reel_{campaign.id}.mp4")
    assert updated.final_slideshow_url.endswith(f"slideshow_{campaign.id}.mp4")
    assert updated.final_image_url.endswith(f"post_{campaign.id}.png")
    assert len(updated.final_carousel_urls) == 5
    assert updated.final_thumbnail_url.startswith("/api/media/covers/cover_")
    assert updated.final_thumbnail_url.endswith(f"_{campaign.id}.png")


def test_output_format_is_workspace_scoped_and_locked_outside_studio(isolated_output_services):
    campaign_store, *_ = isolated_output_services
    campaign = make_campaign("WS_A")
    campaign_store.save(campaign.id, campaign)
    assert client.post(f"/api/campaigns/{campaign.id}/output-format", headers={"X-Workspace-ID": "WS_B"}, json={"output_format": "static_post"}).status_code == 404
    campaign_store.update(campaign.id, {"stage": "directions"})
    assert client.post(f"/api/campaigns/{campaign.id}/output-format", headers={"X-Workspace-ID": "WS_A"}, json={"output_format": "static_post"}).status_code == 400


def test_ready_shot_selection_survives_content_outputs_for_zero_cost_repackaging(isolated_output_services):
    campaign_store, *_ = isolated_output_services
    campaign = make_campaign("WS_READY_REPACK")
    selected = campaign.shot_plan.shots[0]
    selected.status = "ready"
    selected.video_url = "gs://private-bucket/approved.mp4"
    campaign.selected_shot_id = selected.shot_id
    campaign_store.save(campaign.id, campaign)
    headers = {"X-Workspace-ID": campaign.workspace_id}

    content = client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        headers=headers,
        json={"output_format": "static_post"},
    )
    assert content.status_code == 200
    assert content.json()["selected_shot_id"] == selected.shot_id

    pack = client.post(
        f"/api/campaigns/{campaign.id}/output-format",
        headers=headers,
        json={"output_format": "campaign_pack"},
    )
    assert pack.status_code == 200
    assert pack.json()["selected_shot_id"] == selected.shot_id


def test_static_post_media_proxy_requires_exact_owned_output(isolated_output_services):
    campaign_store, *_ = isolated_output_services
    campaign = make_campaign("WS_MEDIA")
    campaign.stage = "reel"
    filename = f"post_{campaign.id}.png"
    campaign.final_image_url = f"http://localhost:8000/api/media/posts/{filename}"
    campaign_store.save(campaign.id, campaign)
    assert client.get(f"/api/media/posts/{filename}", headers={"X-Workspace-ID": "WS_MEDIA"}).content == b"FAKE_PNG_CONTENT"
    assert client.get(f"/api/media/posts/{filename}", headers={"X-Workspace-ID": "WS_OTHER"}).status_code == 404
    assert client.get(f"/api/media/posts/post_{campaign.id}_wrong.png", headers={"X-Workspace-ID": "WS_MEDIA"}).status_code == 404


def test_carousel_media_proxy_accepts_only_ordered_owned_cards(isolated_output_services):
    campaign_store, *_ = isolated_output_services
    campaign = make_campaign("WS_CAROUSEL_MEDIA")
    campaign.stage = "reel"
    filenames = [f"carousel_{campaign.id}_{index:02d}.png" for index in range(1, 6)]
    campaign.final_carousel_urls = [f"/api/media/posts/{filename}" for filename in filenames]
    campaign_store.save(campaign.id, campaign)
    assert client.get(f"/api/media/posts/{filenames[2]}", headers={"X-Workspace-ID": "WS_CAROUSEL_MEDIA"}).content == b"FAKE_PNG_CONTENT"
    assert client.get(f"/api/media/posts/{filenames[2]}", headers={"X-Workspace-ID": "WS_OTHER"}).status_code == 404
    assert client.get(f"/api/media/posts/carousel_{campaign.id}_06.png", headers={"X-Workspace-ID": "WS_CAROUSEL_MEDIA"}).status_code == 404


def test_slideshow_media_proxy_accepts_secondary_pack_reel(isolated_output_services):
    campaign_store, *_ = isolated_output_services
    campaign = make_campaign("WS_SLIDESHOW_MEDIA")
    campaign.stage = "reel"
    main_filename = f"reel_{campaign.id}.mp4"
    slideshow_filename = f"slideshow_{campaign.id}.mp4"
    campaign.final_video_url = f"/api/media/reels/{main_filename}"
    campaign.final_slideshow_url = f"/api/media/reels/{slideshow_filename}"
    campaign_store.save(campaign.id, campaign)
    assert client.get(f"/api/media/reels/{slideshow_filename}", headers={"X-Workspace-ID": "WS_SLIDESHOW_MEDIA"}).status_code == 200
    assert client.get(f"/api/media/reels/notowned_{campaign.id}.mp4", headers={"X-Workspace-ID": "WS_SLIDESHOW_MEDIA"}).status_code == 404


def test_veo_request_enables_native_audio_and_includes_audio_direction(monkeypatch):
    from app.services.veo_service import VeoService

    captured = {}
    class Models:
        def generate_videos(self, **kwargs):
            captured.update(kwargs)
            return type("Operation", (), {"name": "op-audio"})()
    service = VeoService.__new__(VeoService)
    service.client = type("Client", (), {"models": Models()})()
    service.model_name = "veo-3.1-fast-generate-001"
    service.bucket = "test-bucket"
    shot = make_campaign().shot_plan.shots[0]
    assert service.start_generation(shot) == "op-audio"
    assert captured["config"].generate_audio is True
    assert "Audio:" in captured["source"].prompt
    assert shot.veo_audio_prompt.rstrip(".") in captured["source"].prompt
    assert shot.visual not in captured["source"].prompt


def test_veo_prompt_compiler_never_leaks_localized_storyboard_copy():
    from app.services.veo_service import VeoService

    shot = make_campaign().shot_plan.shots[0]
    compiled = VeoService.compile_prompt(shot)
    assert shot.veo_prompt_intent in compiled
    assert shot.visual not in compiled
    assert shot.action not in compiled
    assert shot.camera not in compiled
    assert shot.audio_direction not in compiled
    assert shot.caption not in compiled


def test_production_settings_are_workspace_scoped_and_validate_exact_assets(isolated_output_services):
    campaign_store, *_ = isolated_output_services
    campaign = make_campaign("WS_SETTINGS")
    campaign_store.save(campaign.id, campaign)
    own_image = AssetRecord(workspace_id="WS_SETTINGS", name="product.png", kind="image", mime_type="image/png", storage_key="product.png")
    foreign_image = AssetRecord(workspace_id="WS_OTHER", name="foreign.png", kind="image", mime_type="image/png", storage_key="foreign.png")
    campaigns_router.asset_store.save(own_image.asset_id, own_image)
    campaigns_router.asset_store.save(foreign_image.asset_id, foreign_image)
    payload = {"headline": "Protect one focused hour", "caption": "Finish what matters", "caption_start_seconds": 0.0, "cta": "Start free", "audio_mode": "silent", "product_asset_ids": [own_image.asset_id], "visual_treatment": "campaign_mood"}
    saved = client.put(f"/api/campaigns/{campaign.id}/production-settings", headers={"X-Workspace-ID": "WS_SETTINGS"}, json=payload)
    assert saved.status_code == 200
    assert saved.json()["production_settings"] == payload
    payload["product_asset_ids"] = [foreign_image.asset_id]
    assert client.put(f"/api/campaigns/{campaign.id}/production-settings", headers={"X-Workspace-ID": "WS_SETTINGS"}, json=payload).status_code == 404


def test_main_product_leads_default_campaign_proof(isolated_output_services):
    campaign_store, *_rest, kit_store = isolated_output_services
    campaign = make_campaign("WS_MAIN_PRODUCT")
    primary = AssetRecord(workspace_id=campaign.workspace_id, name="hero.png", kind="image", mime_type="image/png", storage_key="hero.png")
    supporting = AssetRecord(workspace_id=campaign.workspace_id, name="detail.png", kind="image", mime_type="image/png", storage_key="detail.png")
    campaigns_router.asset_store.save(primary.asset_id, primary)
    campaigns_router.asset_store.save(supporting.asset_id, supporting)
    kit_store.save(campaign.workspace_id, BrandKit(
        workspace_id=campaign.workspace_id,
        primary_product_asset_id=primary.asset_id,
        product_asset_ids=[supporting.asset_id],
    ))
    campaign_store.save(campaign.id, campaign)

    settings = campaigns_router._default_production_settings(campaign)
    assert settings.product_asset_ids == [primary.asset_id, supporting.asset_id]
    campaign.production_settings = settings
    _, _, product_paths = campaigns_router._brand_context(campaign)
    assert product_paths == ["hero.png", "detail.png"]


def test_corrected_brand_roles_replace_stale_logo_saved_as_campaign_product(isolated_output_services):
    campaign_store, *_rest, kit_store = isolated_output_services
    campaign = make_campaign("WS_STALE_ROLE")
    logo = AssetRecord(workspace_id=campaign.workspace_id, name="app-icon.png", kind="image", mime_type="image/png", storage_key="logo.png")
    product = AssetRecord(workspace_id=campaign.workspace_id, name="product-detail-screen.jpg", kind="image", mime_type="image/jpeg", storage_key="product.jpg")
    campaigns_router.asset_store.save(logo.asset_id, logo)
    campaigns_router.asset_store.save(product.asset_id, product)
    kit_store.save(campaign.workspace_id, BrandKit(
        workspace_id=campaign.workspace_id,
        logo_asset_id=logo.asset_id,
        primary_product_asset_id=product.asset_id,
    ))
    campaign.production_settings = ProductionSettings(
        headline="Keep the product visible",
        cta="Try it",
        product_asset_ids=[logo.asset_id],
    )
    campaign_store.save(campaign.id, campaign)

    _, logo_path, product_paths = campaigns_router._brand_context(campaign)

    assert logo_path == "logo.png"
    assert product_paths == ["product.jpg"]


def test_historical_campaign_records_still_deserialize_without_new_fields():
    historical = {
        "workspace_id": "WS_OLD",
        "stage": "studio",
        "brief": {"subject_name": "Old Product", "subject_description": "Legacy", "audience": "Creators"},
        "shot_plan": {
            "direction_id": "legacy",
            "shots": [{"shot_id": "s1", "order": 1, "duration_seconds": 6, "purpose": "hook", "visual": "v", "action": "a", "camera": "c", "audio_direction": "a", "caption": "c", "veo_prompt_intent": "English prompt"}],
        },
    }
    campaign = Campaign.model_validate(historical)
    assert campaign.production_settings is None
    assert campaign.shot_plan.full_reel_shots == []
    assert campaign.shot_plan.shots[0].creative_mode == "legacy"

    legacy_settings = ProductionSettings.model_validate({
        "headline": "Legacy",
        "caption": "Still readable",
        "cta": "Continue",
        "product_asset_ids": [],
    })
    assert legacy_settings.visual_treatment == "brand_safe"


def test_real_branded_finishing_renders_pixel_sized_assets(tmp_path, monkeypatch):
    from app.services.branded_finishing import branded_finishing_service, ffmpeg_service

    campaign = make_campaign()
    kit = BrandKit(workspace_id=campaign.workspace_id, brand_name="FocusFlow", brand_colors=["#F5F5F0", "#111111", "#7CFFB2"])
    product_path = tmp_path / "product.png"
    Image.new("RGB", (400, 700), "#336699").save(product_path)
    cards = branded_finishing_service.render_vertical_cards(campaign, kit, None, [str(product_path)], str(tmp_path))
    assert [Image.open(path).size for path in cards] == [(720, 1280), (720, 1280)]

    generated = io.BytesIO()
    Image.new("RGB", (768, 1024), "#884422").save(generated, "PNG")
    captured = {}
    def fake_upload(path, destination, content_type="video/mp4"):
        captured["size"] = Image.open(path).size
        captured["destination"] = destination
        captured["content_type"] = content_type
        return "http://localhost:8000/api/media/posts/static.png"
    monkeypatch.setattr(ffmpeg_service, "upload_to_gcs", fake_upload)
    url = branded_finishing_service.compose_static_post(generated.getvalue(), campaign, kit, None, [str(product_path)], "static.png")
    assert url.endswith("/static.png")
    assert captured == {"size": (1080, 1350), "destination": "final_posts/static.png", "content_type": "image/png"}


def test_visual_treatments_resolve_to_distinct_deterministic_palettes():
    from app.services.branded_finishing import _palette_for

    campaign = make_campaign()
    kit = BrandKit(workspace_id=campaign.workspace_id, brand_colors=["#F6F0E3", "#08172B", "#C8A358"])
    palettes = {}
    for treatment in ("brand_safe", "campaign_mood", "high_contrast"):
        campaign.production_settings = ProductionSettings(
            headline="A clear headline",
            cta="Try it",
            visual_treatment=treatment,
        )
        palettes[treatment] = _palette_for(campaign, kit)
    assert len(set(palettes.values())) == 3
    assert palettes["brand_safe"] == ("#F6F0E3", "#08172B", "#C8A358")
    assert palettes["high_contrast"][0] == "#FFFFFF"


def test_product_capture_white_canvas_is_trimmed_before_device_fit():
    from app.services.branded_finishing import branded_finishing_service

    screenshot = Image.new("RGB", (432, 768), "white")
    screenshot.paste(Image.new("RGB", (432, 636), "#0B1B35"), (0, 0))
    trimmed = branded_finishing_service._trim_outer_whitespace(screenshot)
    assert trimmed.size == (432, 636)
    assert trimmed.getpixel((200, 635))[:3] == (11, 27, 53)


def test_carousel_renderer_outputs_five_ordered_4x5_cards(tmp_path):
    from app.services.branded_finishing import branded_finishing_service

    campaign = make_campaign()
    campaign.brief.output_language = "tr"
    campaign.production_settings = ProductionSettings(
        headline="Odağını geri kazan.",
        caption="Planla. Başla. Bitir.",
        cta="Ücretsiz dene",
        audio_mode="silent",
        product_asset_ids=[],
    )
    kit = BrandKit(
        workspace_id=campaign.workspace_id,
        brand_name="FocusFlow",
        brand_colors=["#F5F5F0", "#0B1324", "#D4AA55"],
    )
    screenshot = Image.new("RGB", (432, 768), "white")
    screenshot.paste(Image.new("RGB", (432, 640), "#17345A"), (0, 0))
    product_path = tmp_path / "padded_product.png"
    screenshot.save(product_path)
    generated = io.BytesIO()
    Image.new("RGB", (768, 1024), "#6F5948").save(generated, "PNG")

    paths = branded_finishing_service.render_carousel_cards(
        generated.getvalue(), campaign, kit, None, [str(product_path)], str(tmp_path)
    )
    assert len(paths) == 5
    assert [os.path.basename(path) for path in paths] == [
        "carousel_01_hook.png",
        "carousel_02_tension.png",
        "carousel_03_product.png",
        "carousel_04_proof.png",
        "carousel_05_cta.png",
    ]
    assert all(Image.open(path).size == (1080, 1350) for path in paths)

    # Semi-transparent hex fills must not flatten to white during RGB export.
    proof_card = Image.open(paths[3]).convert("RGB")
    proof_panel_pixel = proof_card.getpixel((80, 520))
    assert max(proof_panel_pixel) < 245


def test_carousel_copy_prefers_customer_facing_language_and_caps_length():
    from app.services.branded_finishing import branded_finishing_service

    campaign = make_campaign()
    campaign.brief.output_language = "tr"
    campaign.brief.audience_problem = "Rüyaların sabah hızla unutulması ve kişisel örüntülerin fark edilememesi."
    campaign.brief.desired_feeling = "Sakin, mahrem ve düşünceli."
    campaign.brief.must_include = ["Rüyanı sabaha bırakma."]
    campaign.production_settings = ProductionSettings(
        headline="Rüyanı sabaha bırakma.",
        caption="Anlat. Mektubunu al. Örüntüleri gör.",
        cta="Google Play'den indir",
        audio_mode="silent",
        product_asset_ids=[],
    )
    campaign.direction_set.directions[0].core_tension = "Rüyaları hızla unutma ve bunun yarattığı hayal kırıklığı."
    campaign.direction_set.directions[0].creative_hypothesis = "Bu cümle, son kullanıcıya gösterilmemesi gereken çok uzun bir dahili yaratıcı hipotezdir. " * 3

    copy = branded_finishing_service._carousel_copy(campaign)

    assert copy["problem"] == "Rüyaların sabah hızla unutulması ve kişisel örüntülerin fark edilememesi."
    assert copy["solution"] == "Anlat. Mektubunu al. Örüntüleri gör."
    assert all(len(item) <= 97 for item in copy["proof_items"])
    assert all("dahili yaratıcı hipotez" not in item for item in copy["proof_items"])
    assert copy["proof_heading"] == "Neden önemli?"
    assert "kampanyanın anlatacağı" not in copy["proof_heading"].casefold()


def test_carousel_copy_rejects_internal_planning_language():
    from app.services.branded_finishing import branded_finishing_service

    campaign = make_campaign()
    campaign.brief.output_language = "tr"
    campaign.brief.subject_name = "DreamLetter"
    campaign.brief.audience_problem = "Kampanyanın anlatacağı üç şey"
    campaign.direction_set.directions[0].core_tension = "Kampanyanın anlatacağı üç şey"
    campaign.brief.must_include = [
        "Kampanya anlatısı için dahili planlama dili.",
        "Rüyanı anlat, kişisel mektubunu al.",
    ]
    campaign.production_settings = ProductionSettings(
        headline="Rüyanı sabaha bırakma.",
        caption="Anlat. Mektubunu al. Örüntüleri gör.",
        cta="Google Play'den indir",
        audio_mode="silent",
        product_asset_ids=[],
    )

    copy = branded_finishing_service._carousel_copy(campaign)
    visible_copy = " ".join([
        str(copy["problem"]),
        str(copy["solution"]),
        str(copy["proof_heading"]),
        *[str(item) for item in copy["proof_items"]],
    ]).casefold()

    assert copy["problem"] == "Anlat. Mektubunu al. Örüntüleri gör."
    assert copy["proof_heading"] == "Neden önemli?"
    assert "kampanyanın anlatacağı üç şey" not in visible_copy
    assert "kampanya anlatısı" not in visible_copy
    assert "dahili planlama" not in visible_copy


def test_carousel_copy_rejects_uploaded_asset_inventory_labels():
    from app.services.branded_finishing import branded_finishing_service

    campaign = make_campaign()
    campaign.brief.output_language = "tr"
    campaign.brief.subject_name = "DreamLetter"
    campaign.brief.subject_description = "Rüyaları kaydetmek ve kişisel örüntüleri keşfetmek için tasarlanmış bir mobil uygulama."
    campaign.brief.desired_feeling = "Sakin, mahrem ve düşünceli"
    campaign.brief.must_include = [
        "Rüyanı sabaha bırakma; anlat, kişisel mektubunu al, örüntüleri gör.",
        "mobil uygulama ekranı",
        "uygulama simgesi",
        "DL monogram logosu",
        "koyu mod kullanıcı arayüzü",
        "lacivert/indigo tonlarında arka planlar",
        "yuvarlak köşeli kartlar ve düğmeler",
    ]
    campaign.production_settings = ProductionSettings(
        headline="Sabah uyandığında rüyalarını unutmaktan sıkıldın mı?",
        caption="",
        cta="Google Play'den indir",
        audio_mode="native_ambient",
        product_asset_ids=[],
    )

    copy = branded_finishing_service._carousel_copy(campaign)
    visible_copy = " ".join(str(item) for item in copy["proof_items"]).casefold()

    assert "mobil uygulama ekranı" not in visible_copy
    assert "uygulama simgesi" not in visible_copy
    assert "monogram logosu" not in visible_copy
    assert "koyu mod kullanıcı arayüzü" not in visible_copy
    assert "arka planlar" not in visible_copy
    assert "kartlar ve düğmeler" not in visible_copy
    assert "sakin, mahrem ve düşünceli" in visible_copy


def test_carousel_copy_strips_production_requirements_but_keeps_customer_detail():
    from app.services.branded_finishing import branded_finishing_service

    campaign = make_campaign()
    campaign.brief.output_language = "en"
    campaign.brief.subject_name = "DreamLetter"
    campaign.brief.audience_problem = "Dream details disappear within minutes of waking."
    campaign.brief.must_include = [
        "Synchronized native ambience: breath, bedding and room tone.",
        "Use the exact supplied logo and real product screenshot during deterministic finishing.",
        "A concise three-part memory ritual: feeling, place and one strange detail.",
    ]
    campaign.production_settings = ProductionSettings(
        headline="What did you almost forget?",
        caption="Hold on to the feeling, the place, one strange detail.",
        cta="Keep the dream",
        audio_mode="native_ambient",
        product_asset_ids=[],
    )

    copy = branded_finishing_service._carousel_copy(campaign)
    visible_copy = " ".join(str(item) for item in copy["proof_items"]).casefold()

    assert "feeling, place and one strange detail" in visible_copy
    assert "synchronized" not in visible_copy
    assert "native ambience" not in visible_copy
    assert "supplied logo" not in visible_copy
    assert "deterministic" not in visible_copy


def test_provider_background_is_reduced_to_nonliteral_mood_layer():
    from app.services.branded_finishing import _safe_generated_background

    source = Image.new("RGB", (1080, 1350), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((80, 100, 1000, 500), fill="black")
    draw.text((120, 180), "100% PRIVATE & SECURE", fill="white")
    payload = io.BytesIO()
    source.save(payload, "PNG")

    safe = _safe_generated_background(payload.getvalue(), (1080, 1350)).convert("RGB")

    assert safe.size == (1080, 1350)
    # A hard black/white fake-ad edge must become a soft mood transition.
    assert safe.getpixel((80, 100)) != (0, 0, 0)
    assert safe.getpixel((79, 100)) != (255, 255, 255)


def test_turkish_shot_plan_prompt_contracts():
    from app.services.gemini_service import GeminiService

    tr_brief = CampaignBrief(
        subject_name="Masalcı",
        subject_description="Çocuklar için sesli masal uygulaması",
        audience="Ebeveynler",
        goal="app_install",
        output_language="tr",
    )
    direction = CreativeDirection(
        direction_id="d_tr",
        name="Sakin Uyku Ritüeli",
        hook="Her akşam masal arama derdine son.",
        core_tension="Yatma vakti karmaşası",
        creative_hypothesis="Sakinleştirici ses tasarımı dikkat çeker",
        visual_idea="Çocuğunu uyutan huzurlu anne",
        cta_treatment="Ücretsiz Dinle",
        evidence_ids=["E1"],
        why_test="Evidence used: [E1]",
    )
    prompt = GeminiService.build_shot_plan_prompt(tr_brief, direction)
    assert "Turkish (tr)" in prompt
    assert "visual`, `action`, `camera`, `audio_direction`, and `caption` MUST be in Turkish (tr)" in prompt
    assert "Internal fields `veo_prompt_intent`, `veo_audio_prompt`, and every `negative_constraints` item MUST be in English" in prompt
    assert "Do not ask Veo to render UI, screenshots, logos, captions, prices, claims, or readable text" in prompt
